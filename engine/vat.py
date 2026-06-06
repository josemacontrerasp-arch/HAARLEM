"""BTW (VAT) remittance — a real, periodic cash outflow the forecast must model.

Cash moves on gross (amount_incl_vat), but VAT is a pass-through: collected on
sales, reclaimed on purchases, and the NET is remitted to the Belastingdienst
quarterly. Stripping VAT to net would hide this outflow (Lane A schema is
explicit about keeping vat_amount separate so Lane B can model it).

If Lane A already emits explicit `vat_remittance` rows, the engine uses those.
Otherwise this computes them from the vat_amount column per calendar quarter.
"""
from __future__ import annotations

import calendar
from datetime import date
from typing import Dict, List, Tuple

from .schema import Transaction, TracedValue


def _quarter(d: date) -> Tuple[int, int]:
    return (d.year, (d.month - 1) // 3 + 1)


def _remittance_due_date(year: int, quarter: int) -> date:
    """Dutch rule (approx): BTW for a quarter is due by the last day of the month
    following the quarter end. Q1->Apr, Q2->Jul, Q3->Oct, Q4->Jan(next year)."""
    end_month = quarter * 3            # 3, 6, 9, 12
    due_month = end_month + 1
    due_year = year
    if due_month > 12:
        due_month -= 12
        due_year += 1
    last_day = calendar.monthrange(due_year, due_month)[1]
    return date(due_year, due_month, last_day)


def compute_vat_remittances(transactions: List[Transaction]) -> List[Transaction]:
    """Net VAT payable per quarter -> a synthetic vat_remittance outflow row.

    net payable = sum(vat_amount) over the quarter (sales VAT is +, purchase VAT
    is -). If positive the portfolio owes it -> outflow (negative cash).
    """
    by_q: Dict[Tuple[int, int], List[Transaction]] = {}
    for t in transactions:
        if t.driver_type == "vat_remittance":
            continue  # don't recompute an already-explicit remittance
        if abs(t.vat_amount) < 0.005:
            continue
        by_q.setdefault(_quarter(t.date), []).append(t)

    rows: List[Transaction] = []
    for (year, q), txns in sorted(by_q.items()):
        net_vat = sum(t.vat_amount for t in txns)   # +ve = owed to tax authority
        if abs(net_vat) < 0.005:
            continue
        due = _remittance_due_date(year, q)
        rows.append(Transaction(
            record_id=f"vat-{year}Q{q}",
            source_system="exact",   # computed; lineage points at contributing rows
            source_file="(computed by engine)",
            source_row=0,
            opco="PORTFOLIO",
            date=due,
            gl_account_native="1500",
            gl_account_unified="1500",
            driver_type="vat_remittance",
            amount_excl_vat=0.0,
            vat_amount=0.0,
            amount_incl_vat=-net_vat,        # owe -> cash out
            counterparty="Belastingdienst",
            project_id=None,
            status="open_ap",
            description=f"BTW aangifte {year} Q{q} (computed from {len(txns)} rows)",
        ))
    return rows
