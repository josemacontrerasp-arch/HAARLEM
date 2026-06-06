"""Lane A — Exact adapter (Altis dataset 1, opco Andijk).

The 4th accounting system. Unlike the other three exports (transaction-grain GL
lines), Exact arrives here as an already-AGGREGATED monthly revenue matrix:

  data/datasets/Altis dataset 1.xlsx
    sheets '2023' | '2024' | '2025' | '2026YTD'
    layout (per sheet):
       row 0     : month headers     [nan, Jan, Feb, Mrt, ... Dec, Totaal]
       'Netto-omzet'                 -> subtotal row (== sum of the account rows); SKIPPED
       '80000 Omzet hoog'            -> 21% VAT revenue
       '80020 Omzet verlegd 21%'     -> reverse-charge revenue (BTW verlegd)

Reconciliation into the canonical schema (engine/schema.py):
  Each (account, month) cell becomes ONE canonical Transaction:
    - opco            = Andijk
    - date            = month-end of that calendar month
    - status          = 'actual'  (historical recognised revenue)
    - driver_type     = from gl_mapping.csv (milestone_billing)
    - sign            = revenue is an inflow -> positive

VAT note (the one place this differs from the Gilde/Yuki adapters): the cells are
labelled 'Netto-omzet' = turnover NET of VAT, so we gross UP to the cash amount,
rather than splitting VAT out of a gross figure:
    80000 (unified 8000)  -> incl = net * 1.21
    80020 (unified 8001)  -> reverse charge, no VAT on gross -> incl = net
amount_incl_vat == amount_excl_vat + vat_amount always holds (schema invariant).

Account is read from the row label ('80000 Omzet hoog' -> native '80000').
Only columns whose header is a known Dutch month are read (Totaal / blank /
the 'Andijk' label column are ignored).
"""
from __future__ import annotations

import calendar
import os
from datetime import date
from typing import Dict, List, Tuple

import pandas as pd

from engine.schema import Transaction, validate_transaction

OPCO = "Andijk"
SOURCE_SYSTEM = "exact"
SOURCE_FILE = "Altis dataset 1.xlsx"
DATA_PATH = "data/datasets/Altis dataset 1.xlsx"
SHEETS = ["2023", "2024", "2025", "2026YTD"]

# Dutch month abbreviation -> month number. Only these column headers are read.
DUTCH_MONTHS: Dict[str, int] = {
    "jan": 1, "feb": 2, "mrt": 3, "apr": 4, "mei": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12,
}

# net -> gross VAT rate by unified account (cells are NET of VAT).
VAT_RATES: Dict[str, float] = {
    "8000": 0.21,   # Omzet hoog
    "8001": 0.00,   # reverse charge — no VAT on gross
}

_MAPPING: Dict[str, Tuple[str, str]] = {}  # native -> (unified, driver_type)


def _load_mapping(mapping_path: str = "data/gl_mapping.csv") -> None:
    global _MAPPING
    df = pd.read_csv(mapping_path)
    ex = df[df["source_system"] == "exact"]
    for _, row in ex.iterrows():
        _MAPPING[str(row["gl_account_native"]).strip()] = (
            str(row["gl_account_unified"]).strip(),
            str(row["driver_type"]).strip(),
        )


def _to_float(v) -> float:
    if pd.isna(v):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(".", "").replace(",", ".")
    return float(s) if s else 0.0


def _gross_up(net: float, unified: str) -> Tuple[float, float, float]:
    """(amount_excl_vat, vat_amount, amount_incl_vat) from a NET revenue figure."""
    rate = VAT_RATES.get(unified, 0.0)
    excl = round(net, 2)
    vat = round(net * rate, 2)
    return excl, vat, round(excl + vat, 2)


def _year_for_sheet(sheet: str) -> int:
    return int(sheet[:4])   # '2026YTD' -> 2026


def _parse_sheet(sheet: str) -> Tuple[List[Transaction], Dict]:
    raw = pd.read_excel(DATA_PATH, sheet_name=sheet, header=None)
    year = _year_for_sheet(sheet)

    # Map each column index -> month number, from the header row (row 0).
    header = list(raw.iloc[0].values)
    month_cols: Dict[int, int] = {}
    for col, label in enumerate(header):
        key = str(label).strip().lower()[:3]
        if key in DUTCH_MONTHS:
            month_cols[col] = DUTCH_MONTHS[key]

    txns: List[Transaction] = []
    unmapped = 0
    rows_in = 0

    for r in range(1, len(raw)):
        label = raw.iloc[r, 0]
        if pd.isna(label):
            continue
        label = str(label).strip()
        head = label.split(" ", 1)
        native = head[0]
        if not native.isdigit():
            continue   # 'Netto-omzet' subtotal and any non-account row
        native_desc = head[1] if len(head) > 1 else ""
        unified, driver_type = _MAPPING.get(native, ("UNMAPPED", "other"))

        for col, month in month_cols.items():
            net = _to_float(raw.iloc[r, col])
            if net == 0.0:
                continue
            rows_in += 1
            if unified == "UNMAPPED":
                unmapped += 1
            excl, vat, incl = _gross_up(net, unified)
            txn_date = date(year, month, calendar.monthrange(year, month)[1])
            record_id = f"exact-{year}-{native}-{month:02d}"

            t = Transaction(
                record_id=record_id,
                source_system=SOURCE_SYSTEM,
                source_file=f"{SOURCE_FILE}#{sheet}",
                source_row=r + 1,
                opco=OPCO,
                date=txn_date,
                gl_account_native=native,
                gl_account_unified=unified,
                driver_type=driver_type,
                amount_excl_vat=excl,
                vat_amount=vat,
                amount_incl_vat=incl,
                currency="EUR",
                counterparty=None,
                project_id=None,
                status="actual",
                description=f"{native_desc} ({sheet} {month:02d})".strip(),
            )
            txns.append(t)

    violations = [v for t in txns for v in validate_transaction(t)]
    summary = {
        "file": f"{SOURCE_FILE}#{sheet}",
        "rows_in": rows_in,
        "rows_out": len(txns),
        "sum_amount_incl_vat": round(sum(t.amount_incl_vat for t in txns), 2),
        "unmapped_accounts": unmapped,
        "schema_violations": violations,
    }
    return txns, summary


def ingest_exact(
    mapping_path: str = "data/gl_mapping.csv",
) -> Tuple[List[Transaction], List[Dict]]:
    _load_mapping(mapping_path)
    all_txns: List[Transaction] = []
    summaries: List[Dict] = []
    for sheet in SHEETS:
        txns, summary = _parse_sheet(sheet)
        all_txns.extend(txns)
        summaries.append(summary)
    return all_txns, summaries


if __name__ == "__main__":
    txns, summaries = ingest_exact()

    print("=== Reconciliation report (Exact / Andijk) ===")
    total_in = total_out = total_unmapped = 0
    for s in summaries:
        print(f"  {s['file']}: {s['rows_in']} in / {s['rows_out']} out | "
              f"sum={s['sum_amount_incl_vat']:,.2f} | unmapped={s['unmapped_accounts']} | "
              f"violations={len(s['schema_violations'])}")
        total_in += s["rows_in"]
        total_out += s["rows_out"]
        total_unmapped += s["unmapped_accounts"]

    print(f"\n  TOTAL: {total_in} in / {total_out} out | unmapped={total_unmapped}")
    print(f"  grand sum_amount_incl_vat: {sum(t.amount_incl_vat for t in txns):,.2f}")

    violations = [v for s in summaries for v in s["schema_violations"]]
    print(f"\n  {len(violations)} schema violation(s)" if violations
          else "\n  0 schema violations")
    for v in violations[:10]:
        print(f"    {v}")

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        records = [
            {k: (v.isoformat() if isinstance(v, date) else v)
             for k, v in t.__dict__.items()}
            for t in txns
        ]
        pq.write_table(pa.Table.from_pylist(records), "data/exact_transactions.parquet")
        print("\n  wrote data/exact_transactions.parquet")
    except ImportError:
        print("\n  pyarrow not installed — skipping parquet output")
