"""Lane A — Gilde adapter.

Reads all GB XXXX *.xlsx files from `portfolio company data/` and produces
canonical Transaction rows (Contract v1 / engine/schema.py).

Source columns:
  Rekening   – GL account number (native)
  Periode    – accounting period (month start date)
  Datum      – transaction date
  Boeknummer – journal entry number
  Trek       – debtor/counterparty code (nullable)
  Debet      – debit amount (positive = outflow in Dutch GL convention)
  Credit     – credit amount (positive = inflow in Dutch GL convention)
  Boekingstekst – free-text description
  Dagboek    – journal book name
  BTW        – VAT amount (rarely populated; usually 0 or NaN)
  BTW-srt    – VAT type code (e.g. 'Bverlegd' = reverse charge)

Sign convention (Contract v1): cash in = positive, cash out = negative.
  Credit rows → positive (revenue inflow)
  Debit rows  → negative (correction / reversal)

VAT: these files cover revenue accounts only (8000/8001/8002).
  Account 8000 = 21% VAT (Omzet hoog). vat_amount = amount_excl / 1.21 * 0.21
  Account 8001 = reverse charge (BTW verlegd). vat_amount = 0 (no VAT on gross)
  Account 8002 = 9% VAT (Omzet laag). vat_amount = amount_excl / 1.09 * 0.09
  Memoriaalboek rows are correction entries; treated as 0% VAT.

Status: all rows from these files are historical GL lines → status = 'actual'.
  (Forward open_ar / wip rows are not in these exports.)
"""
from __future__ import annotations

import os
import re
from datetime import date
from typing import Dict, List, Tuple

import pandas as pd

from engine.schema import Transaction, validate_transaction

OPCO = "OpcoNoord"
SOURCE_SYSTEM = "gilde"
DATA_DIR = "data/portfolio company data"

# VAT rates by unified account
VAT_RATES: Dict[str, float] = {
    "8000": 0.21,
    "8001": 0.00,   # reverse charge — VAT not on gross
    "8002": 0.09,
    "8003": 0.00,
}

_MAPPING: Dict[str, Tuple[str, str]] = {}  # native -> (unified, driver_type)
_DEBTOR: Dict[int, Dict[str, str]] = {}   # trek_code -> {company_name, customer_segment}


def _load_mapping(mapping_path: str = "data/gl_mapping.csv") -> None:
    global _MAPPING
    df = pd.read_csv(mapping_path)
    gilde = df[df["source_system"] == "gilde"]
    for _, row in gilde.iterrows():
        _MAPPING[str(row["gl_account_native"]).strip()] = (
            str(row["gl_account_unified"]).strip(),
            str(row["driver_type"]).strip(),
        )


def _load_debtor_lookup(lookup_path: str = "data/debtor_lookup.csv") -> None:
    global _DEBTOR
    if not os.path.exists(lookup_path):
        return
    df = pd.read_csv(lookup_path, dtype={"trek_code": int})
    for _, row in df.iterrows():
        name = str(row["company_name"]).strip() if pd.notna(row["company_name"]) and str(row["company_name"]).strip() else None
        seg = str(row["customer_segment"]).strip() if pd.notna(row["customer_segment"]) and str(row["customer_segment"]).strip() else None
        _DEBTOR[int(row["trek_code"])] = {"company_name": name, "customer_segment": seg}


def _to_float(v) -> float:
    if pd.isna(v):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(".", "").replace(",", ".")
    return float(s) if s else 0.0


def _vat_split(gross: float, unified: str) -> Tuple[float, float]:
    """Return (amount_excl_vat, vat_amount) from a gross credit/debit amount."""
    rate = VAT_RATES.get(unified, 0.0)
    if rate == 0.0:
        return gross, 0.0
    excl = round(gross / (1 + rate), 2)
    vat = round(gross - excl, 2)
    return excl, vat


def _parse_file(path: str) -> Tuple[List[Transaction], Dict]:
    fname = os.path.basename(path)
    df = pd.read_excel(path)

    # Normalise Rekening to string (sometimes float e.g. 8000.0)
    df["Rekening"] = df["Rekening"].apply(
        lambda v: str(int(float(v))) if pd.notna(v) else "UNKNOWN"
    )

    rows_in = len(df)
    txns: List[Transaction] = []
    unmapped = 0

    # Drop rows with no date or no account (trailing junk / footer rows)
    df = df[df["Datum"].notna() & df["Rekening"].notna()]

    for source_row, row in enumerate(df.itertuples(index=False), start=2):
        native = str(row.Rekening).strip()
        unified, driver_type = _MAPPING.get(native, ("UNMAPPED", "other"))
        if unified == "UNMAPPED":
            unmapped += 1

        # Sign convention: Credit = inflow (+), Debit = outflow (-)
        debit = _to_float(row.Debet)
        credit = _to_float(row.Credit)
        gross = credit - debit          # signed: + = cash in

        excl, vat = _vat_split(abs(gross), unified)
        excl = excl if gross >= 0 else -excl
        vat = vat if gross >= 0 else -vat

        txn_date: date = pd.Timestamp(row.Datum).date()
        boeknummer = str(row.Boeknummer).strip()

        # Memoriaalboek = correction/reversal entry
        dagboek = str(row.Dagboek).strip() if pd.notna(row.Dagboek) else ""
        if dagboek == "Memoriaalboek":
            driver_type = "other"

        record_id = f"gilde-{re.sub(r'[^a-z0-9]', '', fname.lower())}-{source_row}"

        trek_code = int(float(row.Trek)) if pd.notna(row.Trek) else None
        debtor = _DEBTOR.get(trek_code, {}) if trek_code is not None else {}
        counterparty = debtor.get("company_name") or (str(trek_code) if trek_code else None)
        segment = debtor.get("customer_segment")

        t = Transaction(
            record_id=record_id,
            source_system=SOURCE_SYSTEM,
            source_file=fname,
            source_row=source_row,
            opco=OPCO,
            date=txn_date,
            gl_account_native=native,
            gl_account_unified=unified,
            driver_type=driver_type,
            amount_excl_vat=round(excl, 2),
            vat_amount=round(vat, 2),
            amount_incl_vat=round(gross, 2),
            currency="EUR",
            counterparty=counterparty,
            counterparty_segment=segment,
            project_id=None,
            status="actual",
            description=str(row.Boekingstekst) if pd.notna(row.Boekingstekst) else None,
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


def ingest_gilde(
    data_dir: str = DATA_DIR,
    mapping_path: str = "data/gl_mapping.csv",
    debtor_lookup_path: str = "data/debtor_lookup.csv",
) -> Tuple[List[Transaction], List[Dict]]:
    _load_mapping(mapping_path)
    _load_debtor_lookup(debtor_lookup_path)
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
    import json

    txns, summaries = ingest_gilde()

    print("=== Reconciliation report ===")
    total_rows_in = total_rows_out = total_unmapped = 0
    for s in summaries:
        print(f"  {s['file']}: {s['rows_in']} in / {s['rows_out']} out | "
              f"sum={s['sum_amount_incl_vat']:,.2f} | unmapped={s['unmapped_accounts']} | "
              f"violations={len(s['schema_violations'])}")
        total_rows_in += s["rows_in"]
        total_rows_out += s["rows_out"]
        total_unmapped += s["unmapped_accounts"]

    print(f"\n  TOTAL: {total_rows_in} in / {total_rows_out} out | "
          f"unmapped={total_unmapped}")
    print(f"  grand sum_amount_incl_vat: "
          f"{sum(t.amount_incl_vat for t in txns):,.2f}")

    violations = [v for s in summaries for v in s["schema_violations"]]
    if violations:
        print(f"\n  {len(violations)} schema violation(s):")
        for v in violations[:10]:
            print(f"    {v}")
    else:
        print("\n  0 schema violations")

    # Write to parquet
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq

        records = [
            {k: (v.isoformat() if isinstance(v, date) else v)
             for k, v in t.__dict__.items()}
            for t in txns
        ]
        table = pa.Table.from_pylist(records)
        pq.write_table(table, "data/gilde_transactions.parquet")
        print("\n  wrote data/gilde_transactions.parquet")
    except ImportError:
        print("\n  pyarrow not installed — skipping parquet output")
