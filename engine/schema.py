"""Lane B — the contract as code.

Mirrors Lane A's `schema` (Contract v1) for the transaction table, plus the
project/milestone record from PRD section 5, plus the TracedValue type that is
the heart of the traceability spine.

Rule: nothing downstream knows native formats. The engine only ever sees
`Transaction` (the unified table) and `Project` (the project/WIP data).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

# --- enums (kept as plain str sets so an UNMAPPED/new value never crashes us) ---

SOURCE_SYSTEMS = {"gilde", "yuki", "exact", "snelstart"}

# Lane A's driver_type enum has 7 values (two more than the PRD's "five drivers"):
# vat_remittance and other were added. Trace labels use these exact strings.
DRIVER_TYPES = {
    "materials",
    "subcontractor",
    "milestone_billing",
    "customer_payment",
    "weather",          # reserved: never a row, only shifts timing of others
    "vat_remittance",
    "other",
}

# The status lifecycle is the fuel of the forecast (Lane A schema).
STATUSES = {
    "actual",     # cash already moved (bank lines) -> historical anchor
    "open_ar",    # invoice issued, unpaid          -> future inflow at date + lag
    "open_ap",    # commitment, unpaid              -> future outflow at date
    "wip",        # work done, not yet invoiced     -> future inflow signal
}


@dataclass
class Transaction:
    """One financial event line, at transaction grain (Lane A Contract v1)."""

    record_id: str
    source_system: str
    source_file: str
    source_row: int
    opco: str
    date: date                       # cash events: when money moves; accruals: doc date
    gl_account_native: str
    gl_account_unified: str          # "UNMAPPED" if not in mapping file (kept, never dropped)
    driver_type: str
    amount_excl_vat: float           # signed: cash in = +, cash out = -
    vat_amount: float                # signed same direction; 0.0 if none
    amount_incl_vat: float           # gross = excl + vat; the amount that hits the bank
    currency: str = "EUR"
    counterparty: Optional[str] = None
    project_id: Optional[str] = None
    status: str = "actual"
    description: Optional[str] = None
    # GAP vs PRD: Lane A schema has no counterparty_segment yet. We resolve it via
    # a lookup (see config) so payment-lag works; this field caches the result.
    counterparty_segment: Optional[str] = None


@dataclass
class Milestone:
    milestone_id: str
    description: str
    planned_date: date
    amount: float
    completion_stage: Optional[str] = None
    status: str = "pending"          # pending | invoiced | paid
    weather_dependent: bool = False


@dataclass
class Scheduled:
    """A committed outflow on the project schedule (materials / subcontractor)."""

    date: date
    amount: float
    milestone_id: Optional[str] = None


@dataclass
class Project:
    """Project / milestone record (PRD section 5, second block)."""

    project_id: str
    opco: str
    customer: str
    customer_segment: str
    contract_value: float
    wip_to_date: float
    percent_complete: float
    weather_exposure: float = 0.0    # 0..1, how exposed the schedule is to weather
    milestones: List[Milestone] = field(default_factory=list)
    materials_schedule: List[Scheduled] = field(default_factory=list)
    subcontractor_schedule: List[Scheduled] = field(default_factory=list)


@dataclass
class TracedValue:
    """Trace metadata attached to EVERY computed cash contribution.

    Produced as a byproduct of computation, never bolted on after. A forecast
    cell is just a sum of TracedValues, so drill-down is free: click a cell,
    read its contributors.
    """

    value: float                     # signed EUR contribution to net cash
    week: int                        # 0..12 in the horizon
    driver: str
    contributing_records: List[str] = field(default_factory=list)   # source record_ids
    assumptions_applied: List[str] = field(default_factory=list)     # e.g. "payment_lag=30d(gov)"
    scenario: str = "base"
    toggle_values: Dict[str, object] = field(default_factory=dict)
    computation: str = ""            # short human-readable formula string


def validate_transaction(t: Transaction) -> List[str]:
    """Return a list of contract violations (empty == clean). Never raises."""
    problems: List[str] = []
    if t.source_system not in SOURCE_SYSTEMS:
        problems.append(f"{t.record_id}: bad source_system {t.source_system!r}")
    if t.driver_type not in DRIVER_TYPES:
        problems.append(f"{t.record_id}: bad driver_type {t.driver_type!r}")
    if t.status not in STATUSES:
        problems.append(f"{t.record_id}: bad status {t.status!r}")
    # sign integrity: gross should equal net + vat (within a cent)
    if abs(t.amount_incl_vat - (t.amount_excl_vat + t.vat_amount)) > 0.01:
        problems.append(f"{t.record_id}: amount_incl_vat != excl + vat")
    return problems
