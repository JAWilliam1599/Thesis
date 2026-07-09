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

    _render_scanner_status(gate)

    warnings = gate.get("scanner_warnings") or []
    if warnings:
        with st.expander(f"Scanner warnings ({len(warnings)})"):
            for warning in warnings:
                st.warning(warning)

    findings = gate.get("findings") or []
    _render_findings(findings)


# Scanner-status key -> the "source" label its findings carry.
_SCANNER_SOURCE = {
    "checkov": "checkov",
    "cfn_lint": "cfn-lint",
    "ansible_lint": "ansible-lint",
    "secret_scan": "secret-scan",
}


def _render_scanner_status(gate: dict[str, Any]) -> None:
    """Explicit per-scanner outcome so 'ran but found nothing' is visible."""
    status: dict[str, str] = gate.get("scanner_status") or {}
    if not status:
        return

    # Findings per source (dedup merges sources as "a+b" — count each part).
    counts: dict[str, int] = {}
    for finding in gate.get("findings") or []:
        for src in str(finding.get("source", "")).split("+"):
            src = src.strip()
            if src:
                counts[src] = counts.get(src, 0) + 1

    lines: list[str] = []
    for name, state in status.items():
        if state != "ok":
            lines.append(f"⚠️ **{name}** — {state}")
            continue
        source = _SCANNER_SOURCE.get(name)
        if source is not None:
            n = counts.get(source, 0)
            lines.append(
                f"✅ **{name}** — ran, {n} finding(s)" if n
                else f"✅ **{name}** — ran, no findings"
            )
        elif name == "infracost":
            cost = (gate.get("cost_analysis") or {}).get("total_monthly_usd", 0.0)
            cost_pts = (gate.get("components") or {}).get("cost", 0)
            note = f"+{cost_pts} pts" if cost_pts else "below the $10 → +5 band, +0 pts"
            lines.append(f"✅ **infracost** — ran, ${cost:,.2f}/month ({note})")
        elif name == "aws_config":
            violations = (gate.get("inputs") or {}).get("aws_config_violations", 0)
            lines.append(f"✅ **aws_config** — ran, {violations} violation(s)")
        elif name == "ml_risk":
            ml = gate.get("ml_analysis") or {}
            lines.append(
                f"✅ **ml_risk** — P(insecure) {ml.get('probability', 0.0):.2f} "
                f"→ +{ml.get('ml_score', 0)} pts"
            )
        else:
            lines.append(f"✅ **{name}** — ok")
    st.markdown("  \n".join(lines))


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
    thresholds = (gate or {}).get("thresholds", {})
    pass_max = thresholds.get("pass_max", config.GATE_PASS_MAX)
    review_max = thresholds.get("review_max", config.GATE_REVIEW_MAX)
    emoji, color, label = config.DECISION_STYLE.get(
        decision, ("❔", "#57606a", decision.upper())
    )
    st.markdown(
        f"<div style='padding:1rem;border-radius:0.5rem;"
        f"background:{color}1a;border-left:6px solid {color};'>"
        f"<span style='font-size:1.25rem;font-weight:700;color:{color};'>"
        f"{emoji} {label}</span>"
        f"<br><span style='color:#57606a;'>Gate score: {score} "
        f"(pass ≤ {pass_max}, review ≤ {review_max})</span></div>",
        unsafe_allow_html=True,
    )
    return decision
