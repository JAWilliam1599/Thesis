"""Render helpers for evaluation reports and IaC gate reports."""
from __future__ import annotations

from typing import Any

import streamlit as st

from ui import config


# --- Gate report ------------------------------------------------------------
def render_gate_report(gate: dict[str, Any] | None) -> None:
    if not gate:
        st.info("No gate report available.")
        return

    decision = str(gate.get("decision", "reject")).lower()
    score = gate.get("score", 0)
    emoji, color, label = config.DECISION_STYLE.get(
        decision, ("❔", "#57606a", decision.upper())
    )

    st.markdown(
        f"<div style='padding:0.75rem 1rem;border-radius:0.5rem;"
        f"background:{color}1a;border-left:6px solid {color};'>"
        f"<span style='font-size:1.1rem;font-weight:600;color:{color};'>"
        f"{emoji} {label}</span>"
        f"<br><span style='color:#57606a;'>{gate.get('message', '')}</span></div>",
        unsafe_allow_html=True,
    )

    components = gate.get("components", {})
    cols = st.columns(5)
    cols[0].metric("Gate score", score)
    cols[1].metric("Severity", components.get("severity", 0))
    cols[2].metric("Cost", components.get("cost", 0))
    cols[3].metric("AWS Config", components.get("aws_config", 0))
    ml_analysis = gate.get("ml_analysis") or {}
    ml_help = None
    if ml_analysis.get("status") == "ok":
        ml_help = f"P(insecure) = {ml_analysis.get('probability', 0.0):.2f}"
    elif ml_analysis.get("status"):
        ml_help = f"status: {ml_analysis['status']}"
    cols[4].metric("ML risk", components.get("ml_risk", 0), help=ml_help)

    _render_scanner_status(gate.get("scanner_status", {}))

    warnings = gate.get("scanner_warnings") or []
    if warnings:
        with st.expander(f"Scanner warnings ({len(warnings)})"):
            for warning in warnings:
                st.warning(warning)

    findings = gate.get("findings") or []
    _render_findings(findings)


def _render_scanner_status(status: dict[str, str]) -> None:
    if not status:
        return
    chips = []
    for name, state in status.items():
        ok = state == "ok"
        icon = "✅" if ok else "⚠️"
        chips.append(f"{icon} {name}: {state}")
    st.caption("  ·  ".join(chips))


def _render_findings(findings: list[dict[str, Any]]) -> None:
    if not findings:
        st.success("No findings reported.")
        return

    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    findings_sorted = sorted(
        findings,
        key=lambda f: severity_rank.get(str(f.get("severity", "")).lower(), 5),
    )

    with st.expander(f"Findings ({len(findings_sorted)})", expanded=True):
        rows = []
        for f in findings_sorted:
            severity = str(f.get("severity", "unknown")).lower()
            color = config.SEVERITY_COLOR.get(severity, config.SEVERITY_COLOR["unknown"])
            rows.append({
                "Severity": severity.upper(),
                "Message": f.get("message", ""),
                "Resource": f.get("resource_id", ""),
                "Source": f.get("source", ""),
            })
        st.dataframe(rows, width="stretch", hide_index=True)


# --- Interactive decision banner --------------------------------------------
def render_decision_banner(gate: dict[str, Any] | None) -> str:
    """Render the colored PASS/REVIEW/REJECT banner; return the decision."""
    decision = str((gate or {}).get("decision", "reject")).lower()
    score = (gate or {}).get("score", 0)
    emoji, color, label = config.DECISION_STYLE.get(
        decision, ("❔", "#57606a", decision.upper())
    )
    st.markdown(
        f"<div style='padding:1rem;border-radius:0.5rem;"
        f"background:{color}1a;border-left:6px solid {color};'>"
        f"<span style='font-size:1.25rem;font-weight:700;color:{color};'>"
        f"{emoji} {label}</span>"
        f"<br><span style='color:#57606a;'>Gate score: {score} "
        f"(pass ≤ {config.GATE_PASS_MAX}, review ≤ {config.GATE_REVIEW_MAX})</span></div>",
        unsafe_allow_html=True,
    )
    return decision
