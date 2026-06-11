"""Report rendering and extraction functions."""
import json
from typing import Optional

import streamlit as st

from ui.helpers import format_report_value


def extract_json_report(output_text: str) -> Optional[dict]:
    """Extract the final JSON evaluation report from mixed log output."""
    if not output_text:
        return None

    for line in reversed(output_text.splitlines()):
        if "Evaluation report:" in line:
            _, _, payload = line.partition("Evaluation report:")
            payload = payload.strip()
            if payload:
                try:
                    return json.loads(payload)
                except json.JSONDecodeError:
                    pass

    first_brace = output_text.find("{")
    if first_brace == -1:
        return None

    decoder = json.JSONDecoder()
    try:
        report, _ = decoder.raw_decode(output_text[first_brace:])
        if isinstance(report, dict):
            return report
    except json.JSONDecodeError:
        return None

    return None


def render_report_field(label, value, description, source):
    """Render a single report field with optional expansion."""
    st.metric(label, format_report_value(value), help=f"Source: {source}. {description}")
    if isinstance(value, list) and value:
        with st.expander(f"View {label.lower()}"):
            for item in value:
                if isinstance(item, dict):
                    st.json(item)
                else:
                    st.write(f"• {item}")
    elif isinstance(value, dict) and value:
        with st.expander(f"View {label.lower()}"):
            st.json(value)


def render_evaluation_report(report: dict) -> None:
    """Render a full evaluation report with sections and details."""
    security_report = report.get("security_analysis", {}) if isinstance(report.get("security_analysis"), dict) else {}

    st.subheader("Overview")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        score = report.get("score", 0)
        st.metric("Score", f"{score}/100", delta=f"{score - 50}", help="Source: QuickVal + Security analysis. Overall quality score from the evaluator.")
    with col2:
        st.metric("Syntax OK", "✅" if report.get("syntax_ok") else "❌", help="Source: QuickVal. Whether the generated code parsed successfully.")
    with col3:
        st.metric("Risk Score", f"{report.get('risk_score', 0):.2f}", help="Source: Risk Scoring. Estimated security risk from the risk scorer.")
    with col4:
        st.metric("Approval", "✅" if report.get("approval") else "❌", help="Source: QuickVal + Risk Scoring + Security analysis. Whether the run passed the approval checks.")

    st.divider()
    st.subheader("Assessment Details")
    detail_cols = st.columns(2)
    with detail_cols[0]:
        render_report_field(
            "Risk Level",
            report.get("risk_level"),
            "Human-readable classification of the current risk.",
            "Risk Scoring",
        )
        render_report_field(
            "Risk Action",
            report.get("risk_action"),
            "Recommended next step based on the calculated risk.",
            "Risk Scoring",
        )
        render_report_field(
            "Quality Score",
            report.get("quality_score", report.get("score")),
            "Mirror of the final score used by downstream checks.",
            "QuickVal + Security analysis",
        )
        render_report_field(
            "Lines of Code",
            report.get("line_count"),
            "Number of lines in the generated file.",
            "Evaluator",
        )
    with detail_cols[1]:
        render_report_field(
            "Function Count",
            report.get("function_count"),
            "How many Python function definitions were detected.",
            "Evaluator",
        )
        render_report_field(
            "Main Guard Present",
            report.get("has_main_guard"),
            "Whether the file includes an if __name__ == '__main__' guard.",
            "Evaluator",
        )
        render_report_field(
            "Try/Except Present",
            report.get("has_try_except"),
            "Whether the code includes exception handling.",
            "Evaluator",
        )
    st.divider()
    st.subheader("Security Analysis")
    security_cols = st.columns(3)
    with security_cols[0]:
        render_report_field(
            "Issues",
            security_report.get("issues", []),
            "Blocking security findings reported by the scanners.",
            "Security analysis",
        )
    with security_cols[1]:
        render_report_field(
            "Warnings",
            security_report.get("warnings", []),
            "Non-blocking security warnings reported by the scanners.",
            "Security analysis",
        )
    with security_cols[2]:
        render_report_field(
            "Findings",
            security_report.get("findings", []),
            "Structured security findings used for risk scoring.",
            "Security analysis",
        )

    tool_status = security_report.get("tool_status", {})
    if isinstance(tool_status, dict) and tool_status:
        status_cols = st.columns(max(1, len(tool_status)))
        for idx, (tool_name, tool_value) in enumerate(tool_status.items()):
            with status_cols[idx % len(status_cols)]:
                st.metric(tool_name.title(), format_report_value(tool_value), help="Source: Security analysis. Scanner execution state for this tool.")

    st.info(
        f"Risk Level: {report.get('risk_level', 'N/A')} | "
        f"Recommended Action: {report.get('risk_action', 'N/A')}"
    )

    if report.get("issues"):
        st.subheader("📝 Issues/Notes")
        for issue in report.get("issues", []):
            st.warning(f"• {issue}")

    with st.expander("📄 Full Report"):
        st.json(report)
