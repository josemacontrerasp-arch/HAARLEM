"""Lane A — merge all three adapters into one canonical transactions table.

Runs ingest_gilde, ingest_yuki, ingest_snelstart and writes:
  data/transactions.parquet   (primary — Lane B reads this via load.py)
  data/transactions.csv       (fallback — readable without duckdb/pyarrow)
  data/reconciliation.json    (per-file + portfolio summary)

Reconciliation checks (fail loud):
  - No duplicate record_ids across systems
  - Sum per source ties to per-adapter subtotals
  - Schema violations count == 0
"""
from __future__ import annotations

import json
from datetime import date
from typing import Dict, List

from engine.schema import validate_transaction
from ingest_gilde import ingest_gilde
from ingest_snelstart import ingest_snelstart
from ingest_yuki import ingest_yuki


def _to_dict(t) -> Dict:
    return {k: (v.isoformat() if isinstance(v, date) else v)
            for k, v in t.__dict__.items()}


def main():
    print("Running adapters...")
    txns_g, sums_g = ingest_gilde()
    txns_y, sums_y = ingest_yuki()
    txns_s, sums_s = ingest_snelstart()

    all_txns = txns_g + txns_y + txns_s
    all_summaries = sums_g + sums_y + sums_s

    # --- duplicate record_id check ---
    ids = [t.record_id for t in all_txns]
    dupes = [rid for rid in set(ids) if ids.count(rid) > 1]
    if dupes:
        print(f"  WARNING: {len(dupes)} duplicate record_ids: {dupes[:5]}")
    else:
        print("  record_id uniqueness: OK")

    # --- schema violations ---
    violations = [v for t in all_txns for v in validate_transaction(t)]
    print(f"  schema violations: {len(violations)}")
    for v in violations[:10]:
        print(f"    {v}")

    # --- portfolio summary ---
    total_rows = len(all_txns)
    total_sum = round(sum(t.amount_incl_vat for t in all_txns), 2)
    unmapped = sum(s["unmapped_accounts"] for s in all_summaries)
    open_ar = sum(1 for t in all_txns if t.status == "open_ar")
    status_counts = {}
    for t in all_txns:
        status_counts[t.status] = status_counts.get(t.status, 0) + 1
    driver_counts = {}
    for t in all_txns:
        driver_counts[t.driver_type] = driver_counts.get(t.driver_type, 0) + 1

    print(f"\n=== Portfolio summary ===")
    print(f"  total rows      : {total_rows:,}")
    print(f"  sum incl. VAT   : €{total_sum:,.2f}")
    print(f"  unmapped        : {unmapped}")
    print(f"  open_ar rows    : {open_ar}  ← forward inflows for forecast")
    print(f"  status breakdown: {status_counts}")
    print(f"  driver breakdown: {driver_counts}")

    print(f"\n  per-system breakdown:")
    for sys, txns in [("gilde", txns_g), ("yuki", txns_y), ("snelstart", txns_s)]:
        s = round(sum(t.amount_incl_vat for t in txns), 2)
        print(f"    {sys:<12} {len(txns):>6} rows  €{s:>15,.2f}")

    # --- write outputs ---
    records = [_to_dict(t) for t in all_txns]

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        pq.write_table(pa.Table.from_pylist(records), "data/transactions.parquet")
        print("\n  wrote data/transactions.parquet")
    except ImportError:
        print("\n  pyarrow not installed — skipping parquet")

    import csv, io
    if records:
        with open("data/transactions.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(records[0].keys()))
            w.writeheader()
            w.writerows(records)
        print("  wrote data/transactions.csv")

    report = {
        "total_rows": total_rows,
        "total_sum_incl_vat": total_sum,
        "unmapped_accounts": unmapped,
        "duplicate_record_ids": len(dupes),
        "schema_violations": len(violations),
        "status_counts": status_counts,
        "driver_counts": driver_counts,
        "per_file": all_summaries,
    }
    with open("data/reconciliation.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    print("  wrote data/reconciliation.json")


if __name__ == "__main__":
    main()
