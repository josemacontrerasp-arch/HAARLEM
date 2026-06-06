"""Lane A — LLM-assisted GL-account mapping (reviewable & auditable).

Tier-3 requirement: a model proposes how each native GL account maps into the
unified chart (which unified account + which cash-flow driver), with a CONFIDENCE
and a RATIONALE; a controller approves or rejects each suggestion; every decision
is logged. We then validate the suggestions against the controller-approved
`data/gl_mapping.csv` and report an agreement rate.

Design choices that matter for judging:

  * Three backends, same interface:
      - "openai"    : OpenAI API (used automatically if OPENAI_API_KEY is set and
                      the `openai` SDK is importable). JSON-mode, temperature 0.
      - "anthropic" : Anthropic API (used if ANTHROPIC_API_KEY is set and the
                      `anthropic` SDK is importable). Prompt-cached.
      - "heuristic" : a deterministic, keyless rule set over the Dutch account
                      descriptions. The fallback so the demo, the tests and a
                      fresh clone all run with no key and no network.
    "auto" (the default) prefers OpenAI, then Anthropic, then the heuristic. The
    controller review loop, the audit log and the agreement-rate report are
    identical regardless of backend — the LLM is an assist, never the authority.

  * Keys are read ONLY from the environment (OPENAI_API_KEY / ANTHROPIC_API_KEY).
    Never hard-code a key here or commit one.

  * The unified chart the model must choose from is loaded FROM the approved
    mapping file (its `gl_account_unified` column), so suggestions are always
    constrained to the real canonical chart — no invented accounts.

  * `gl_mapping.csv` is treated as the controller's ground truth. "Approve" =
    the suggestion matches it; "reject" = it doesn't, and we log the correction.
    That is exactly the approve/reject trail a controller would produce live.

Run it:
    py llm_gl_mapping.py                     # auto (OpenAI -> Anthropic -> heuristic)
    py llm_gl_mapping.py --backend openai    # force OpenAI
    py llm_gl_mapping.py --backend heuristic # force the keyless heuristic
    py llm_gl_mapping.py --demo-new          # also map a NEW, unseen account
Writes data/mapping_suggestions.json (the audit log) and prints the agreement rate.

Provide a key via the environment first, e.g. (PowerShell):
    $env:OPENAI_API_KEY = "sk-..."
"""
from __future__ import annotations

import csv
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

def _load_dotenv(path: Optional[str] = None) -> None:
    """Load KEY=VALUE pairs from a local .env into os.environ (stdlib-only, no
    dependency). A real environment variable always wins, so .env is just a
    convenient default. The .env file is gitignored — never committed."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8-sig") as fh:   # utf-8-sig: tolerate a Windows BOM
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


_load_dotenv()   # so OPENAI_API_KEY / ANTHROPIC_API_KEY from .env are always present

MAPPING_CSV = "data/gl_mapping.csv"
AUDIT_LOG = "data/mapping_suggestions.json"
OPENAI_MODEL = os.environ.get("ALTIS_OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_MODEL = os.environ.get("ALTIS_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

# Drivers the unified chart routes into (mirror of engine/schema.DRIVER_TYPES).
KNOWN_DRIVERS = {
    "materials", "subcontractor", "milestone_billing",
    "customer_payment", "vat_remittance", "other",
}


# --------------------------------------------------------------------------- #
# Data types
# --------------------------------------------------------------------------- #
@dataclass
class CanonicalAccount:
    """One target in the unified chart the model may choose from."""
    unified: str
    description: str
    driver_type: str


@dataclass
class NativeAccount:
    """A source account to be mapped (what a controller would see arrive)."""
    source_system: str
    native: str
    description: str
    # The approved answer, when this account is already in the mapping file.
    expected_unified: Optional[str] = None
    expected_driver: Optional[str] = None
    rule_id: Optional[str] = None


@dataclass
class MappingSuggestion:
    source_system: str
    native: str
    native_description: str
    suggested_unified: str
    suggested_unified_description: str
    suggested_driver: str
    confidence: float
    rationale: str
    backend: str


@dataclass
class ReviewDecision:
    suggestion: MappingSuggestion
    decision: str                       # "approve" | "reject"
    expected_unified: Optional[str]
    expected_driver: Optional[str]
    agreed_unified: bool
    agreed_driver: bool
    controller_note: str = ""


@dataclass
class MappingReport:
    backend: str
    n_accounts: int
    agreement_rate: float               # unified-account agreement (the headline)
    driver_agreement_rate: float
    n_flagged_for_review: int           # suggestions a controller had to reject
    decisions: List[ReviewDecision] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Load the approved chart + the universe of native accounts
# --------------------------------------------------------------------------- #
def load_catalog(mapping_csv: str = MAPPING_CSV) -> List[CanonicalAccount]:
    """The unified chart (deduped) the model is allowed to choose from."""
    seen: Dict[str, CanonicalAccount] = {}
    with open(mapping_csv, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            u = row["gl_account_unified"].strip()
            if u and u not in seen:
                seen[u] = CanonicalAccount(
                    unified=u,
                    description=row["gl_account_unified_description"].strip(),
                    driver_type=row["driver_type"].strip(),
                )
    return list(seen.values())


def load_native_accounts(mapping_csv: str = MAPPING_CSV) -> List[NativeAccount]:
    """Distinct (system, native) accounts seen in the data, with their approved
    answer attached. Where one native maps two ways (e.g. Snelstart MMEM debit vs
    credit), we keep the first rule as the 'headline' expectation and note it."""
    out: List[NativeAccount] = []
    seen: set = set()
    with open(mapping_csv, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            key = (row["source_system"].strip(), row["gl_account_native"].strip())
            if key in seen:
                continue
            seen.add(key)
            out.append(NativeAccount(
                source_system=key[0],
                native=key[1],
                description=row["gl_account_native_description"].strip(),
                expected_unified=row["gl_account_unified"].strip(),
                expected_driver=row["driver_type"].strip(),
                rule_id=row["mapping_rule_id"].strip(),
            ))
    return out


# --------------------------------------------------------------------------- #
# Backend 1 — deterministic, keyless heuristic
# --------------------------------------------------------------------------- #
def _catalog_lookup(catalog: List[CanonicalAccount], unified: str) -> CanonicalAccount:
    for c in catalog:
        if c.unified == unified:
            return c
    return CanonicalAccount(unified="UNMAPPED", description="Unrecognised account", driver_type="other")


def heuristic_suggest(acc: NativeAccount, catalog: List[CanonicalAccount]) -> MappingSuggestion:
    """Rule set over the Dutch descriptions. Order = most specific first."""
    text = f"{acc.native} {acc.description}".lower()

    def has(*words: str) -> bool:
        return any(w in text for w in words)

    # (predicate, unified, driver, confidence, rationale)
    rules: List[Tuple[bool, str, str, float, str]] = [
        (has("kas", "kasboek", "bank", "cash"),
         "1100", "customer_payment", 0.9,
         "Cash/bank journal -> liquidity account; cash receipts drive customer_payment."),
        (has("memoriaal", "mmem", "accrual", "memorial"),
         "9000", "other", 0.5,
         "Memorial/adjustment journal: ambiguous. Debit side opens a WIP accrual, "
         "credit side reverses it once invoiced -> a controller must split debit vs credit."),
        (has("verlegd", "reverse", "heffing naar u"),
         "8001", "milestone_billing", 0.85,
         "'BTW verlegd' / reverse-charge construction revenue -> unified 8001 (no VAT on gross)."),
        (has("9%", "belast 9", "laag", "reduced"),
         "8002", "milestone_billing", 0.8,
         "Reduced 9% VAT revenue line -> unified 8002."),
        (has("0%", "nul", "niet bij u belast", "exempt", "vrijgesteld", "zero"),
         "8004", "milestone_billing", 0.8,
         "Zero-rated / exempt revenue -> unified 8004."),
        (has("overig", "other"),
         "8002", "milestone_billing", 0.6,
         "Low-volume 'other' revenue line -> unified 8002."),
        (has("omzet", "verkoop", "sales", "revenue", "hoog", "factuur"),
         "8000", "milestone_billing", 0.75,
         "Standard-rate sales/revenue line -> unified 8000 (21% VAT), milestone_billing."),
    ]
    for ok, unified, driver, conf, why in rules:
        if ok:
            cat = _catalog_lookup(catalog, unified)
            desc = cat.description if cat.unified == unified else unified
            return MappingSuggestion(
                source_system=acc.source_system, native=acc.native,
                native_description=acc.description,
                suggested_unified=unified, suggested_unified_description=desc,
                suggested_driver=driver, confidence=conf, rationale=why,
                backend="heuristic")

    return MappingSuggestion(
        source_system=acc.source_system, native=acc.native,
        native_description=acc.description,
        suggested_unified="UNMAPPED", suggested_unified_description="Unrecognised account",
        suggested_driver="other", confidence=0.2,
        rationale="No rule matched the description -> flag UNMAPPED for the controller (kept, never dropped).",
        backend="heuristic")


# --------------------------------------------------------------------------- #
# Backend 2 — LLM (OpenAI or Anthropic; optional, used only if a key is present)
# --------------------------------------------------------------------------- #
def _openai_available() -> bool:
    if not os.environ.get("OPENAI_API_KEY"):
        return False
    try:
        import openai  # noqa: F401
        return True
    except ImportError:
        return False


def _anthropic_available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def _resolve_backend(backend: str) -> str:
    """Map 'auto'/'llm' to a concrete backend given what keys/SDKs are present."""
    if backend in ("auto", "llm"):
        if _openai_available():
            return "openai"
        if _anthropic_available():
            return "anthropic"
        return "heuristic"
    return backend


def _catalog_block(catalog: List[CanonicalAccount]) -> str:
    return "\n".join(
        f"  {c.unified} | {c.description} | driver={c.driver_type}" for c in catalog)


def _system_prompt(catalog: List[CanonicalAccount]) -> str:
    return (
        "You are a Dutch financial controller's assistant reconciling roofing-"
        "company GL accounts into one unified chart. Choose EXACTLY ONE unified "
        "account from this catalog (never invent one):\n"
        f"{_catalog_block(catalog)}\n\n"
        "Valid drivers: " + ", ".join(sorted(KNOWN_DRIVERS)) + ".\n"
        "Reply with ONLY a JSON object: "
        '{"unified": "<code>", "driver": "<driver>", "confidence": <0..1>, '
        '"rationale": "<one sentence>"}. If nothing fits, use "UNMAPPED".'
    )


def _user_prompt(acc: NativeAccount) -> str:
    return (f"Source system: {acc.source_system}\n"
            f"Native account: {acc.native}\n"
            f"Description (Dutch): {acc.description}")


def _suggestion_from_json(acc: NativeAccount, catalog: List[CanonicalAccount],
                          data: dict, backend: str) -> MappingSuggestion:
    unified = str(data.get("unified", "UNMAPPED")).strip()
    driver = str(data.get("driver", "other")).strip()
    if driver not in KNOWN_DRIVERS:
        driver = "other"
    cat = _catalog_lookup(catalog, unified)
    return MappingSuggestion(
        source_system=acc.source_system, native=acc.native,
        native_description=acc.description,
        suggested_unified=unified,
        suggested_unified_description=cat.description if cat.unified == unified else unified,
        suggested_driver=driver,
        confidence=float(data.get("confidence", 0.5)),
        rationale=str(data.get("rationale", "")).strip(),
        backend=backend)


def openai_suggest(acc: NativeAccount, catalog: List[CanonicalAccount],
                   model: str = OPENAI_MODEL) -> MappingSuggestion:
    """Ask an OpenAI model to map ONE native account into the unified chart,
    constrained to the catalog, returned as a JSON object (json_object mode)."""
    import openai

    client = openai.OpenAI()
    resp = client.chat.completions.create(
        model=model, temperature=0, max_tokens=300,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _system_prompt(catalog)},
            {"role": "user", "content": _user_prompt(acc)},
        ],
    )
    data = _extract_json(resp.choices[0].message.content or "")
    return _suggestion_from_json(acc, catalog, data, "openai")


def anthropic_suggest(acc: NativeAccount, catalog: List[CanonicalAccount],
                      model: str = ANTHROPIC_MODEL) -> MappingSuggestion:
    """Ask Claude to map ONE native account. The chart + instructions live in a
    cache-controlled system block (constant across calls), so only the per-account
    user turn is uncached."""
    import anthropic

    client = anthropic.Anthropic()
    system = [{"type": "text", "text": _system_prompt(catalog),
               "cache_control": {"type": "ephemeral"}}]
    msg = client.messages.create(
        model=model, max_tokens=300, system=system,
        messages=[{"role": "user", "content": _user_prompt(acc)}],
    )
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    return _suggestion_from_json(acc, catalog, _extract_json(raw), "anthropic")


def _extract_json(raw: str) -> dict:
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            pass
    return {}


# --------------------------------------------------------------------------- #
# Suggest -> review -> report
# --------------------------------------------------------------------------- #
def suggest(acc: NativeAccount, catalog: List[CanonicalAccount],
            backend: str = "auto") -> MappingSuggestion:
    resolved = _resolve_backend(backend)
    if resolved in ("openai", "anthropic"):
        fn = openai_suggest if resolved == "openai" else anthropic_suggest
        try:
            return fn(acc, catalog)
        except Exception as exc:   # network/key/parse failure -> degrade gracefully
            s = heuristic_suggest(acc, catalog)
            s.rationale = f"[{resolved} fell back to heuristic: {exc}] " + s.rationale
            return s
    return heuristic_suggest(acc, catalog)


def review(suggestion: MappingSuggestion, acc: NativeAccount) -> ReviewDecision:
    """The controller's decision, using the approved mapping as ground truth.
    Approve when the unified account matches; otherwise reject and log the
    correction. (For a brand-new account with no expected answer, approve only
    if the model was confident, else flag for review.)"""
    exp_u, exp_d = acc.expected_unified, acc.expected_driver
    if exp_u is None:
        decided = "approve" if suggestion.confidence >= 0.7 and suggestion.suggested_unified != "UNMAPPED" else "reject"
        note = ("New account, no prior rule. "
                + ("Accepted on high confidence." if decided == "approve"
                   else "Held for a controller - low confidence or UNMAPPED."))
        return ReviewDecision(suggestion, decided, None, None,
                              agreed_unified=False, agreed_driver=False, controller_note=note)

    agreed_u = suggestion.suggested_unified == exp_u
    agreed_d = suggestion.suggested_driver == exp_d
    if agreed_u:
        note = "Matches the approved chart."
        return ReviewDecision(suggestion, "approve", exp_u, exp_d, agreed_u, agreed_d, note)
    note = (f"Rejected: controller maps this to {exp_u} (driver {exp_d}). "
            "Logged as a correction.")
    return ReviewDecision(suggestion, "reject", exp_u, exp_d, agreed_u, agreed_d, note)


def build_report(backend: str = "auto", mapping_csv: str = MAPPING_CSV) -> MappingReport:
    catalog = load_catalog(mapping_csv)
    accounts = load_native_accounts(mapping_csv)
    decisions = [review(suggest(a, catalog, backend), a) for a in accounts]

    scored = [d for d in decisions if d.expected_unified is not None]
    n = len(scored) or 1
    agree_u = sum(1 for d in scored if d.agreed_unified) / n
    agree_d = sum(1 for d in scored if d.agreed_driver) / n
    flagged = sum(1 for d in decisions if d.decision == "reject")
    used = decisions[0].suggestion.backend if decisions else _resolve_backend(backend)
    return MappingReport(
        backend=used, n_accounts=len(decisions),
        agreement_rate=round(agree_u, 4), driver_agreement_rate=round(agree_d, 4),
        n_flagged_for_review=flagged, decisions=decisions)


def write_audit_log(report: MappingReport, path: str = AUDIT_LOG) -> None:
    payload = {
        "backend": report.backend,
        "n_accounts": report.n_accounts,
        "agreement_rate": report.agreement_rate,
        "driver_agreement_rate": report.driver_agreement_rate,
        "n_flagged_for_review": report.n_flagged_for_review,
        "decisions": [
            {
                "source_system": d.suggestion.source_system,
                "native": d.suggestion.native,
                "native_description": d.suggestion.native_description,
                "suggested_unified": d.suggestion.suggested_unified,
                "suggested_driver": d.suggestion.suggested_driver,
                "confidence": d.suggestion.confidence,
                "rationale": d.suggestion.rationale,
                "decision": d.decision,
                "expected_unified": d.expected_unified,
                "expected_driver": d.expected_driver,
                "agreed_unified": d.agreed_unified,
                "agreed_driver": d.agreed_driver,
                "controller_note": d.controller_note,
            }
            for d in report.decisions
        ],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    backend = "auto"
    demo_new = "--demo-new" in sys.argv
    if "--backend" in sys.argv:
        backend = sys.argv[sys.argv.index("--backend") + 1]

    report = build_report(backend=backend)

    print("=== LLM-assisted GL mapping - controller review ===")
    print(f"  backend                : {report.backend}"
          + ("" if report.backend in ("openai", "anthropic")
             else "  (keyless; set OPENAI_API_KEY for the LLM backend)"))
    print(f"  accounts reviewed      : {report.n_accounts}")
    print(f"  unified agreement rate : {report.agreement_rate:.0%}")
    print(f"  driver  agreement rate : {report.driver_agreement_rate:.0%}")
    print(f"  flagged for controller : {report.n_flagged_for_review}")
    print()
    for d in report.decisions:
        mark = "OK  " if d.decision == "approve" else "FLAG"
        exp = "" if d.agreed_unified or d.expected_unified is None else f"  (controller: {d.expected_unified}/{d.expected_driver})"
        s = d.suggestion
        print(f"  [{mark}] {s.source_system:<9} {s.native:<22} -> "
              f"{s.suggested_unified}/{s.suggested_driver} "
              f"@{s.confidence:.0%}{exp}")

    if demo_new:
        print("\n  --- edge case: a NEW, never-seen account arrives ---")
        catalog = load_catalog()
        new = NativeAccount(
            source_system="exact", native="80030",
            description="Omzet laag 9% (new reduced-rate revenue line)")
        d = review(suggest(new, catalog, backend), new)
        s = d.suggestion
        print(f"  [{'OK  ' if d.decision == 'approve' else 'FLAG'}] {s.native} "
              f"-> {s.suggested_unified}/{s.suggested_driver} @{s.confidence:.0%}")
        print(f"        rationale: {s.rationale}")
        print(f"        decision : {d.decision} - {d.controller_note}")

    write_audit_log(report)
    print(f"\n  wrote {AUDIT_LOG}  (full audit trail: suggestion + confidence + "
          f"rationale + approve/reject per account)")


if __name__ == "__main__":
    main()
