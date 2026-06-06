"""Lane A — Snelstart adapter (Altis dataset 2).

Reads 'Altis dataset 2.xlsx'. Contains two data sources in one file:

1. Sheets '2023', '2024', '2025', '2026' — transaction-level GL export.
   Columns: Datum, Bkst.nr., Dagboek, Debet, Credit, Btw-bedrag
   Dagboek values: '006 - Verkoop', '60 - Verkoopboek Gilde',
                   '008 - MMEM', '001 - Kas'

2. Sheet 'Company E 2026' — invoice list (Jan-May 2026).
   Columns: Factuurdatum, Factuurnummer, Factuurbedrag (gross incl. VAT)
   These are open invoices → status = 'open_ar' (future inflow).

VAT: Btw-bedrag is already the VAT portion (signed, same direction as the
     transaction). Use it directly. Where null, derive from Dagboek:
     - 006 - Verkoop: 21% on the gross amount
     - 60 - Verkoopboek Gilde: 21% (reverse charge — but Btw-bedrag present
       when applicable; null rows are already net amounts, treat vat=0)
     - 008 - MMEM: 0% (no VAT on memorial/adjustment entries)
     - 001 - Kas: 0% (cash movements, VAT already settled)

MMEM routing (per gl_mapping.csv):
   Debit  → driver=milestone_billing, status=wip    (WIP accrual: revenue recognised, not yet invoiced)
   Credit → driver=other,             status=actual  (accrual reversal: real invoice has been posted)

Company E invoices: no VAT breakdown available → treat as 21% gross.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Dict, List, Tuple

import pandas as pd

from engine.schema import Transaction, validate_transaction

SOURCE_SYSTEM = "snelstart"
SOURCE_FILE_GL = "Altis dataset 2.xlsx"
SOURCE_FILE_CE = "Altis dataset 2.xlsx"
DATA_PATH = "data/datasets/Altis dataset 2.xlsx"
OPCO_GL = "Winschoten"
OPCO_CE = "Winschoten"

_MAPPING: Dict[str, Tuple[str, str]] = {}


def _load_mapping(mapping_path: str = "data/gl_mapping.csv") -> None:
    global _MAPPING
    df = pd.read_csv(mapping_path)
    sn = df[df["source_system"] == "snelstart"]
    for _, row in sn.iterrows():
        _MAPPING[str(row["gl_account_native"]).strip()] = (
            str(row["gl_account_unified"]).strip(),
            str(row["driver_type"]).strip(),
            str(row["mapping_rule_id"]).strip(),
        )


def _to_float(v) -> float:
    if pd.isna(v):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(".", "").replace(",", ".")
    return float(s) if s else 0.0


def _mmem_route(row) -> Tuple[str, str]:
    """Return (driver_type, status) for a MMEM row per gl_mapping split rule."""
    credit = _to_float(row.Credit)
    is_credit = credit > 0
    is_yearend = (pd.Timestamp(row.Datum).month == 12
                  and pd.Timestamp(row.Datum).day == 31)
    if is_credit and not is_yearend:
        return "milestone_billing", "actual"   # WIP recognition (DS2-MMEM-WIP)
    return "other", "actual"                   # accrual reversal (DS2-MMEM-ACCRUAL)


def _ingest_gl_sheets() -> Tuple[List[Transaction], List[Dict]]:
    all_txns: List[Transaction] = []
    summaries: List[Dict] = []

    for sheet in ["2023", "2024", "2025", "2026"]:
        df = pd.read_excel(DATA_PATH, sheet_name=sheet)
        df = df[df["Datum"].notna()]
        rows_in = len(df)
        unmapped = 0
        txns: List[Transaction] = []

        # itertuples renames cols with special chars; use iloc-based iteration
        cols = list(df.columns)
        idx = {c: i for i, c in enumerate(cols)}

        for source_row, row in enumerate(df.itertuples(index=False), start=2):
            vals = list(row)
            dagboek = str(vals[idx["Dagboek"]]).strip() if pd.notna(vals[idx["Dagboek"]]) else ""
            mapped = _MAPPING.get(dagboek)
            if mapped is None:
                unified, driver_type = "UNMAPPED", "other"
                unmapped += 1
            else:
                unified, driver_type, _ = mapped

            debit = _to_float(vals[idx["Debet"]])
            credit = _to_float(vals[idx["Credit"]])
            gross = credit - debit

            # MMEM: debit = WIP accrual (revenue recognised, not yet invoiced)
            #        credit = accrual reversal when real invoice is posted
            datum_val = vals[idx["Datum"]]
            if dagboek == "008 - MMEM":
                if debit > 0:
                    driver_type = "milestone_billing"
                    status = "wip"       # forward-looking: will become an invoice
                else:
                    driver_type = "other"
                    status = "actual"    # reversal of prior accrual, already settled
            else:
                status = "actual"

            btw_raw = vals[idx["Btw-bedrag"]]
            btw = _to_float(btw_raw) if pd.notna(btw_raw) else None
            if btw is not None:
                vat = btw if gross >= 0 else -abs(btw)
            else:
                vat = 0.0   # Gilde reverse-charge rows and Kas have no VAT here
            excl = round(gross - vat, 2)

            txn_date: date = pd.Timestamp(datum_val).date()
            record_id = f"snelstart-{sheet}-{source_row}"

            t = Transaction(
                record_id=record_id,
                source_system=SOURCE_SYSTEM,
                source_file=f"{SOURCE_FILE_GL}#{sheet}",
                source_row=source_row,
                opco=OPCO_GL,
                date=txn_date,
                gl_account_native=dagboek,
                gl_account_unified=unified,
                driver_type=driver_type,
                amount_excl_vat=excl,
                vat_amount=round(vat, 2),
                amount_incl_vat=round(gross, 2),
                currency="EUR",
                counterparty=None,
                project_id=None,
                status=status,
                description=dagboek or None,
            )
            txns.append(t)

        violations = [v for t in txns for v in validate_transaction(t)]
        summary = {
            "file": f"{SOURCE_FILE_GL}#{sheet}",
            "rows_in": rows_in,
            "rows_out": len(txns),
            "sum_amount_incl_vat": round(sum(t.amount_incl_vat for t in txns), 2),
            "unmapped_accounts": unmapped,
            "schema_violations": violations,
        }
        all_txns.extend(txns)
        summaries.append(summary)

    return all_txns, summaries


def _ingest_company_e() -> Tuple[List[Transaction], Dict]:
    raw = pd.read_excel(DATA_PATH, sheet_name="Company E 2026", header=None)
    raw.columns = ["Factuurdatum", "_1", "Factuurnummer", "_3", "_4", "Factuurbedrag"]

    # Keep only rows with a parseable date
    raw["_date"] = pd.to_datetime(raw["Factuurdatum"], errors="coerce")
    df = raw[raw["_date"].notna()].copy()
    df["Factuurbedrag"] = pd.to_numeric(df["Factuurbedrag"], errors="coerce")
    df = df[df["Factuurbedrag"].notna()]

    rows_in = len(df)
    txns: List[Transaction] = []

    unified, driver_type, _ = _MAPPING.get("006 - Verkoop",
                                           ("8000", "milestone_billing", "DS2-VERKOOP"))

    for source_row, (_, row) in enumerate(df.iterrows(), start=2):
        gross = float(row["Factuurbedrag"])
        excl = round(gross / 1.21, 2)
        vat = round(gross - excl, 2)
        txn_date: date = row["_date"].date()
        invoice_nr = str(row["Factuurnummer"]).strip()

        t = Transaction(
            record_id=f"snelstart-companyE-{invoice_nr}",
            source_system=SOURCE_SYSTEM,
            source_file=f"{SOURCE_FILE_CE}#Company E 2026",
            source_row=source_row,
            opco=OPCO_CE,
            date=txn_date,
            gl_account_native="006 - Verkoop",
            gl_account_unified=unified,
            driver_type=driver_type,
            amount_excl_vat=excl,
            vat_amount=vat,
            amount_incl_vat=round(gross, 2),
            currency="EUR",
            counterparty=None,
            project_id=None,
            status="open_ar",   # invoice list = unpaid receivables
            description=f"Factuur {invoice_nr}",
        )
        txns.append(t)

    violations = [v for t in txns for v in validate_transaction(t)]
    summary = {
        "file": f"{SOURCE_FILE_CE}#Company E 2026",
        "rows_in": rows_in,
        "rows_out": len(txns),
        "sum_amount_incl_vat": round(sum(t.amount_incl_vat for t in txns), 2),
        "unmapped_accounts": 0,
        "schema_violations": violations,
    }
    return txns, summary


def ingest_snelstart(
    mapping_path: str = "data/gl_mapping.csv",
) -> Tuple[List[Transaction], List[Dict]]:
    _load_mapping(mapping_path)
    txns_gl, summaries = _ingest_gl_sheets()
    txns_ce, summary_ce = _ingest_company_e()
    return txns_gl + txns_ce, summaries + [summary_ce]


if __name__ == "__main__":
    txns, summaries = ingest_snelstart()

    print("=== Reconciliation report ===")
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
        pq.write_table(pa.Table.from_pylist(records), "data/snelstart_transactions.parquet")
        print("\n  wrote data/snelstart_transactions.parquet")
    except ImportError:
        print("\n  pyarrow not installed — skipping parquet output")
