"""Load Lane A's real reconciled table into engine objects.

Lane A ships "parquet and/or a duckdb/sqlite table" (Contract v1). This reader
is tolerant by design: unknown driver_types / statuses / UNMAPPED accounts are
kept, never dropped (matches Lane A's "flag, don't drop" rule). It also returns
a small reconciliation summary so we can prove rows-in == rows-out at the seam.

Supported inputs (auto-detected by extension):
  .parquet / .duckdb / .db / .sqlite   -> via duckdb (lazy import)
  .csv                                  -> stdlib only, zero deps

Projects: Lane A hasn't finalised the project/milestone table yet. `load_projects`
reads a JSON file in PRD section-5 shape when present; until then, pass the stub.
"""
from __future__ import annotations

import csv
import json
from dataclasses import fields
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from .schema import (
    Milestone,
    Project,
    Scheduled,
    Transaction,
    validate_transaction,
)

_TXN_FIELDS = {f.name for f in fields(Transaction)}


def _to_date(v) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def _to_float(v) -> float:
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    # defensive: Dutch decimals should already be normalised by Lane A's adapter,
    # but tolerate "1.234,56" just in case.
    s = str(v).strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s)


def _row_to_txn(d: Dict) -> Transaction:
    clean = {k: d[k] for k in d if k in _TXN_FIELDS}
    clean["date"] = _to_date(clean["date"])
    clean["source_row"] = int(clean.get("source_row") or 0)
    for money in ("amount_excl_vat", "vat_amount", "amount_incl_vat"):
        clean[money] = _to_float(clean.get(money))
    for opt in ("counterparty", "project_id", "description", "counterparty_segment"):
        if clean.get(opt) in ("", "None", None):
            clean[opt] = None
    return Transaction(**clean)


def load_transactions(path: str) -> Tuple[List[Transaction], Dict]:
    """Return (transactions, reconciliation_summary)."""
    p = path.lower()
    if p.endswith(".csv"):
        rows = _read_csv(path)
    else:
        rows = _read_duckdb(path)

    txns = [_row_to_txn(r) for r in rows]
    violations = [v for t in txns for v in validate_transaction(t)]
    summary = {
        "rows_in": len(rows),
        "rows_out": len(txns),
        "sum_amount_incl_vat": round(sum(t.amount_incl_vat for t in txns), 2),
        "unmapped_accounts": sum(1 for t in txns if t.gl_account_unified == "UNMAPPED"),
        "schema_violations": violations,
    }
    return txns, summary


def _read_csv(path: str) -> List[Dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def _read_duckdb(path: str) -> List[Dict]:
    try:
        import duckdb  # lazy: only needed for parquet/duckdb inputs
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "duckdb not installed. `pip install duckdb`, or export Lane A's table "
            "to CSV and load that."
        ) from e

    con = duckdb.connect()
    if path.lower().endswith(".parquet"):
        rel = con.sql(f"SELECT * FROM read_parquet('{path}')")
    else:
        con = duckdb.connect(path)
        # assume the unified table is named 'transactions'; adjust at integration
        rel = con.sql("SELECT * FROM transactions")
    cols = rel.columns
    return [dict(zip(cols, row)) for row in rel.fetchall()]


def load_projects(path: Optional[str]) -> List[Project]:
    """Read project/milestone records from JSON (PRD section 5 shape) if present."""
    if not path:
        return []
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    projects = []
    for d in raw:
        ms = [Milestone(
            milestone_id=m["milestone_id"], description=m.get("description", ""),
            planned_date=_to_date(m["planned_date"]), amount=_to_float(m["amount"]),
            completion_stage=m.get("completion_stage"),
            status=m.get("status", "pending"),
            weather_dependent=bool(m.get("weather_dependent", False)),
        ) for m in d.get("milestones", [])]
        mat = [Scheduled(_to_date(s["date"]), _to_float(s["amount"]),
                         s.get("milestone_id")) for s in d.get("materials_schedule", [])]
        sub = [Scheduled(_to_date(s["date"]), _to_float(s["amount"]),
                         s.get("milestone_id")) for s in d.get("subcontractor_schedule", [])]
        projects.append(Project(
            project_id=d["project_id"], opco=d["opco"], customer=d["customer"],
            customer_segment=d.get("customer_segment", "default"),
            contract_value=_to_float(d.get("contract_value", 0)),
            wip_to_date=_to_float(d.get("wip_to_date", 0)),
            percent_complete=_to_float(d.get("percent_complete", 0)),
            weather_exposure=_to_float(d.get("weather_exposure", 0)),
            milestones=ms, materials_schedule=mat, subcontractor_schedule=sub,
        ))
    return projects
