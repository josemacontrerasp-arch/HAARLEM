"""Drop-in Streamlit panel for the LLM-assisted GL mapping (controller review).

Frontend-agnostic on purpose: the whole panel is ONE function. Wherever the new
frontend wants it, call:

    from mapping_panel import render_mapping_review
    render_mapping_review()                 # full panel (backend picker + table)

or just the headline numbers as a small card:

    from mapping_panel import mapping_summary
    s = mapping_summary()                   # {"backend","agreement_rate",...}

Nothing else in the app needs to change. Importing this module also loads the
local .env (via llm_gl_mapping), so OPENAI_API_KEY is picked up automatically.
"""
from __future__ import annotations

import json
from typing import Dict, List

import streamlit as st

from llm_gl_mapping import (
    AUDIT_LOG,
    NativeAccount,
    _anthropic_available,
    _openai_available,
    build_report,
    load_catalog,
    review,
    suggest,
)


def _available_backends() -> List[str]:
    backends = ["auto"]
    if _openai_available():
        backends.append("openai")
    if _anthropic_available():
        backends.append("anthropic")
    backends.append("heuristic")
    return backends


@st.cache_data(show_spinner="Mapping GL accounts…")
def _report(backend: str) -> Dict:
    """Cached so we don't re-call the LLM on every Streamlit rerun. Returns plain
    dicts (not dataclasses) so caching is trivial."""
    r = build_report(backend=backend)
    rows = []
    for d in r.decisions:
        s = d.suggestion
        rows.append({
            "status": "OK" if d.decision == "approve" else "FLAG",
            "system": s.source_system,
            "native": s.native,
            "description": s.native_description,
            "suggested": f"{s.suggested_unified} / {s.suggested_driver}",
            "confidence": round(s.confidence, 2),
            "controller_says": (
                "matches" if d.agreed_unified
                else (f"{d.expected_unified} / {d.expected_driver}"
                      if d.expected_unified else "new account")
            ),
            "rationale": s.rationale,
        })
    return {
        "backend": r.backend,
        "n_accounts": r.n_accounts,
        "agreement_rate": r.agreement_rate,
        "driver_agreement_rate": r.driver_agreement_rate,
        "n_flagged": r.n_flagged_for_review,
        "rows": rows,
    }


def mapping_summary(backend: str = "auto") -> Dict:
    """Headline numbers only — for a compact card in any role view."""
    return _report(backend)


def render_mapping_review(default_backend: str = "auto", key: str = "gl_map") -> None:
    """The full controller-review panel. Self-contained; safe to call anywhere."""
    st.subheader("GL mapping — controller review")
    st.caption(
        "An LLM proposes how each source GL account maps into the unified chart "
        "(account + cash-flow driver) with a confidence and a rationale. The "
        "controller approves or rejects each one; every decision is logged. "
        "Suggestions are scored against the approved chart."
    )

    backends = _available_backends()
    backend = st.selectbox(
        "Suggestion engine", backends, index=backends.index(default_backend) if default_backend in backends else 0,
        key=f"{key}_backend",
        help="auto = OpenAI if a key is set, else the keyless heuristic. "
             "Set OPENAI_API_KEY (in .env) to enable the LLM backend.",
    )
    if backend == "auto" and "openai" not in backends and "anthropic" not in backends:
        st.info("No LLM key detected — running the keyless heuristic. "
                "Add OPENAI_API_KEY to .env for the LLM backend.")

    data = _report(backend)

    cols = st.columns(5)
    cols[0].metric("Engine", data["backend"])
    cols[1].metric("Accounts", data["n_accounts"])
    cols[2].metric("Unified agreement", f"{data['agreement_rate']:.0%}")
    cols[3].metric("Driver agreement", f"{data['driver_agreement_rate']:.0%}")
    cols[4].metric("Flagged for review", data["n_flagged"])

    flagged = [r for r in data["rows"] if r["status"] == "FLAG"]
    if flagged:
        st.warning(
            f"{len(flagged)} account(s) need a controller decision — the engine "
            "either disagreed with the approved chart or wasn't confident:"
        )
        for r in flagged:
            st.markdown(
                f"- **{r['system']} {r['native']}** ({r['description']}) → "
                f"suggested `{r['suggested']}` @{r['confidence']:.0%}; "
                f"controller maps to **{r['controller_says']}**"
            )

    st.markdown("**All suggestions (click a column to sort)**")
    st.dataframe(data["rows"], use_container_width=True, hide_index=True)

    with st.expander("Try a new / unseen account (live suggestion)"):
        c = st.columns([1, 1, 2])
        sys_in = c[0].text_input("Source system", "exact", key=f"{key}_sys")
        nat_in = c[1].text_input("Native account", "80030", key=f"{key}_nat")
        desc_in = c[2].text_input("Description (Dutch)", "Omzet laag 9%", key=f"{key}_desc")
        if st.button("Suggest mapping", key=f"{key}_btn"):
            catalog = load_catalog()
            acc = NativeAccount(sys_in.strip(), nat_in.strip(), desc_in.strip())
            d = review(suggest(acc, catalog, backend), acc)
            s = d.suggestion
            verdict = "approve" if d.decision == "approve" else "hold for controller"
            st.write(
                f"**{s.suggested_unified} / {s.suggested_driver}** "
                f"@{s.confidence:.0%} — _{verdict}_"
            )
            st.caption(s.rationale or "(no rationale returned)")

    st.download_button(
        "Download audit log (JSON)",
        data=json.dumps(data, indent=2, ensure_ascii=False),
        file_name="mapping_suggestions.json",
        mime="application/json",
        key=f"{key}_dl",
    )
    st.caption(f"Same audit trail is written to `{AUDIT_LOG}` by "
               "`py llm_gl_mapping.py`.")
