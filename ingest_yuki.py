"""Lane A — Yuki adapter (Dakdekkersbedrijf Peter Ummels).

Reads all 82604-*.xlsx files from `portfolio company 2 data/`. Each file is a
per-account GL export with a metadata header block followed by data rows.

Source columns (after skipping header):
  Nr.      – sequential row number within the file (also 'Totaal'/'Eindsaldo' footers)
  Per.     – accounting period number (1-12)
  Datum    – transaction date
  Bkst.nr. – journal entry number
  Dagboek  – journal book: '80 - Verkoop' | '90 - Memoriaal' | '95 - VJP'
  Debet    – debit amount (outflow / correction)
  Credit   – credit amount (inflow / revenue)

Account is extracted from the metadata block: 'Grootboekrekening' row, column 1.

Sign convention (Contract v1): cash in = positive, cash out = negative.
  Credit → positive, Debit → negative.

VAT: same rates as Gilde (reverse charge 8001/8005 = 0%, 8002 = 9%, 8004 = 0%).
  YUKI-8005 maps to unified 8001 (reverse charge) per gl_mapping.csv.

Dagboek routing:
  80 - Verkoop  → keep mapped driver_type (milestone_billing)
  90 - Memoriaal → driver_type = other  (period correction)
  95 - VJP       → driver_type = other  (year-end closing)

Status: all rows are historical → status = 'actual'.
"""
from __future__ import annotations

import os
import re
from datetime import date
from typing import Dict, List, Tuple

import pandas as pd

from engine.schema import Transaction, validate_transaction

# Dakdekkersbedrijf Peter Ummels IS the Brunssum operating company. Emit the
# canonical opco name directly so the historical Yuki actuals reconcile to the
# same opco as the P&L-calibrated pipeline (engine/pipeline.py: peter_ummels ->
# Brunssum). Previously emitted "PeterUmmels", which never matched and split the
# opco in two across the dashboard.
OPCO = "Brunssum"
SOURCE_SYSTEM = "yuki"
DATA_DIR = "data/portfolio company 2 data"

VAT_RATES: Dict[str, float] = {
    "8001": 0.00,
    "8002": 0.09,
    "8004": 0.00,
    "8005": 0.00,   # reverse charge; unified to 8001
}

_MAPPING: Dict[str, Tuple[str, str]] = {}


def _load_mapping(mapping_path: str = "data/gl_mapping.csv") -> None:
    global _MAPPING
    df = pd.read_csv(mapping_path)
    yuki = df[df["source_system"] == "yuki"]
    for _, row in yuki.iterrows():
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


def _vat_split(gross: float, unified: str) -> Tuple[float, float]:
    rate = VAT_RATES.get(unified, 0.0)
    if rate == 0.0:
        return gross, 0.0
    excl = round(gross / (1 + rate), 2)
    return excl, round(gross - excl, 2)


def _parse_file(path: str) -> Tuple[List[Transaction], Dict]:
    fname = os.path.basename(path)
    raw = pd.read_excel(path, header=None)

    # Extract account from metadata block
    native_account = "UNKNOWN"
    header_row = None
    for i, row in raw.iterrows():
        if str(row[0]).strip() == "Grootboekrekening" and pd.notna(row[1]):
            native_account = str(row[1]).split(" - ")[0].strip()
        if str(row[0]).strip() == "Nr.":
            header_row = i
            break

    if header_row is None:
        return [], {"file": fname, "rows_in": 0, "rows_out": 0,
                    "sum_amount_incl_vat": 0.0, "unmapped_accounts": 0,
                    "schema_violations": [], "error": "no header row found"}

    df = pd.read_excel(path, header=header_row)

    # Drop footer rows (Totaal / Eindsaldo) and rows with no date
    df = df[~df["Nr."].isin(["Totaal", "Eindsaldo"])]
    df = df[df["Datum"].notna()]

    rows_in = len(df)
    unified, driver_type = _MAPPING.get(native_account, ("UNMAPPED", "other"))
    unmapped = rows_in if unified == "UNMAPPED" else 0

    txns: List[Transaction] = []
    file_slug = re.sub(r"[^a-z0-9]", "", fname.lower())

    for source_row, row in enumerate(df.itertuples(index=False), start=2):
        dagboek = str(row.Dagboek).strip() if pd.notna(row.Dagboek) else ""
        effective_driver = driver_type
        if dagboek in ("90 - Memoriaal", "95 - VJP"):
            effective_driver = "other"

        debit = _to_float(row.Debet)
        credit = _to_float(row.Credit)
        gross = credit - debit

        excl, vat = _vat_split(abs(gross), unified)
        excl = excl if gross >= 0 else -excl
        vat = vat if gross >= 0 else -vat

        txn_date: date = pd.Timestamp(row.Datum).date()
        record_id = f"yuki-{file_slug}-{source_row}"

        t = Transaction(
            record_id=record_id,
            source_system=SOURCE_SYSTEM,
            source_file=fname,
            source_row=source_row,
            opco=OPCO,
            date=txn_date,
            gl_account_native=native_account,
            gl_account_unified=unified,
            driver_type=effective_driver,
            amount_excl_vat=round(excl, 2),
            vat_amount=round(vat, 2),
            amount_incl_vat=round(gross, 2),
            currency="EUR",
            counterparty=None,
            project_id=None,
            status="actual",
            description=dagboek or None,
        )
        txns.append(t)

    violations = [v for t in txns for v in validate_transaction(t)]
    summary = {
        "file": fname,
        "rows_in": rows_in,
        "rows_out": len(txns),
        "sum_amount_incl_vat": round(sum(t.amount_incl_vat for t in txns), 2),
        "unmapped_accounts": unmapped,
        "schema_violations": violations,
    }
    return txns, summary


def ingest_yuki(
    data_dir: str = DATA_DIR,
    mapping_path: str = "data/gl_mapping.csv",
) -> Tuple[List[Transaction], List[Dict]]:
    _load_mapping(mapping_path)
    all_txns: List[Transaction] = []
    summaries: List[Dict] = []

    for fname in sorted(os.listdir(data_dir)):
        if not fname.endswith(".xlsx"):
            continue
        path = os.path.join(data_dir, fname)
        txns, summary = _parse_file(path)
        all_txns.extend(txns)
        summaries.append(summary)

    return all_txns, summaries


if __name__ == "__main__":
    txns, summaries = ingest_yuki()

    print("=== Reconciliation report ===")
    total_in = total_out = total_unmapped = 0
    for s in summaries:
        print(f"  {s['file'][:55]}: {s['rows_in']} in / {s['rows_out']} out | "
              f"sum={s['sum_amount_incl_vat']:,.2f} | unmapped={s['unmapped_accounts']} | "
              f"violations={len(s['schema_violations'])}")
        total_in += s["rows_in"]
        total_out += s["rows_out"]
        total_unmapped += s["unmapped_accounts"]

    print(f"\n  TOTAL: {total_in} in / {total_out} out | unmapped={total_unmapped}")
    print(f"  grand sum_amount_incl_vat: {sum(t.amount_incl_vat for t in txns):,.2f}")

    violations = [v for s in summaries for v in s["schema_violations"]]
    if violations:
        print(f"\n  {len(violations)} schema violation(s):")
        for v in violations[:10]:
            print(f"    {v}")
    else:
        print("\n  0 schema violations")

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        records = [
            {k: (v.isoformat() if isinstance(v, date) else v)
             for k, v in t.__dict__.items()}
            for t in txns
        ]
        pq.write_table(pa.Table.from_pylist(records), "data/yuki_transactions.parquet")
        print("\n  wrote data/yuki_transactions.parquet")
    except ImportError:
        print("\n  pyarrow not installed — skipping parquet output")
