"""Hand-made synthetic data in the exact Contract v1 shape, so Lane B and Lane C
develop in parallel before Lane A's real reconciliation lands. Swap for the real
duckdb/parquet table at integration time (see load.py)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import List, Tuple

from .config import ForecastConfig
from .schema import Milestone, Project, Scheduled, Transaction


def _d(week_offset: int, cfg: ForecastConfig) -> date:
    return cfg.anchor_monday + timedelta(weeks=week_offset)


def make_stub(cfg: ForecastConfig | None = None) -> Tuple[List[Transaction], List[Project]]:
    cfg = cfg or ForecastConfig()

    # Committed outflows live on the project schedules (PRD section 6, drivers 1-2),
    # NOT in GL — the real GL mapping is revenue-only. Amounts are gross (cash).
    projects = [
        Project("PRJ-118", "OpcoNoord", "Gemeente Haarlem", "government",
                contract_value=480_000, wip_to_date=120_000, percent_complete=0.25,
                weather_exposure=0.8,
                milestones=[Milestone("M1", "Termijn 2 dak", _d(3, cfg), 60_000,
                                      weather_dependent=True)],
                materials_schedule=[Scheduled(_d(1, cfg), 60_500)],
                subcontractor_schedule=[Scheduled(_d(2, cfg), 26_620, "M1")]),
        Project("PRJ-204", "OpcoZuid", "Bouwbedrijf Y", "enterprise",
                contract_value=300_000, wip_to_date=90_000, percent_complete=0.40,
                weather_exposure=0.2,
                subcontractor_schedule=[Scheduled(_d(3, cfg), 18_150)]),
        Project("PRJ-091", "OpcoNoord", "Gemeente X", "government",
                contract_value=210_000, wip_to_date=40_000, percent_complete=0.15,
                weather_exposure=0.9,
                materials_schedule=[Scheduled(_d(4, cfg), 21_780)]),
    ]

    def txn(rid, sys, file, row, opco, wk, native, unified, drv, excl, vat, cp, proj, status, desc):
        return Transaction(
            record_id=rid, source_system=sys, source_file=file, source_row=row,
            opco=opco, date=_d(wk, cfg), gl_account_native=native,
            gl_account_unified=unified, driver_type=drv,
            amount_excl_vat=excl, vat_amount=vat, amount_incl_vat=excl + vat,
            counterparty=cp, project_id=proj, status=status, description=desc,
        )

    transactions = [
        # --- invoices issued, unpaid (open_ar, inflows after payment lag) -------
        txn("yuki-88", "yuki", "yuki_export.csv", 88, "OpcoZuid", 1,
            "8000", "1300", "milestone_billing", 12_000, 2_520, "Bouwbedrijf Y", "PRJ-204",
            "open_ar", "Termijn 2 - dakrenovatie"),
        txn("yuki-89", "yuki", "yuki_export.csv", 89, "OpcoNoord", 2,
            "8000", "1300", "milestone_billing", 60_000, 12_600, "Gemeente Haarlem", "PRJ-118",
            "open_ar", "Termijn 2 - dak Haarlem"),

        # --- work done, not yet invoiced (wip -> future milestone billing) ------
        txn("gilde-w1", "gilde", "gilde_wip.csv", 7, "OpcoNoord", 1,
            "9000", "1310", "milestone_billing", 40_000, 8_400, "Gemeente X", "PRJ-091",
            "wip", "WIP dak gemeente X termijn 3"),
        txn("gilde-w2", "gilde", "gilde_wip.csv", 8, "OpcoZuid", 5,
            "9000", "1310", "milestone_billing", 25_000, 5_250, "Bouwbedrijf Y", "PRJ-204",
            "wip", "WIP afbouw"),

        # --- quarterly VAT remittance to Belastingdienst (outflow) --------------
        txn("vat-q2", "exact", "btw_q2.csv", 1, "OpcoNoord", 6,
            "1500", "1500", "vat_remittance", -28_000, 0, "Belastingdienst", None,
            "open_ap", "BTW aangifte Q2"),

        # --- an UNMAPPED row: engine must not crash, bucket as 'other' ----------
        txn("snel-x", "snelstart", "snel_export.csv", 99, "OpcoZuid", 2,
            "7999", "UNMAPPED", "other", -3_000, -630, "Onbekend", "PRJ-204",
            "open_ap", "Onbekende kostenpost"),

        # --- a historical actual (anchors balance, excluded from forward cash) --
        txn("gilde-15", "gilde", "gilde_bank.csv", 15, "OpcoNoord", -2,
            "1100", "1100", "customer_payment", 8_000, 1_680, "Bouwbedrijf Y", "PRJ-091",
            "actual", "Ontvangst factuur 2025-0042"),
    ]
    return transactions, projects
