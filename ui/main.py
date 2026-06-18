"""Streamlit entry point for the SysSecOps pipeline GUI.

Run with:
    streamlit run ui/main.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the repo root is importable when launched via `streamlit run ui/main.py`.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from ui import credentials, sidebar, tabs


def initialize_session_state() -> None:
    creds = credentials.load_credentials()
    defaults = {
        "creds_loaded": bool(creds.get("access_key") or creds.get("openrouter_key")),
        "pipeline_stage": "idle",
        "pipeline_prompt": "",
        "pipeline_run_id": None,
        "pipeline_gate_report": None,
        "pipeline_decision": None,
        "pipeline_approve_run_id": None,
        "pipeline_generated_code": "",
        "pipeline_logs_generate": "",
        "pipeline_logs_deploy": "",
        "pipeline_return_code": None,
        "pipeline_deploy_manual_approve": False,
        "pipeline_generate_running": False,
        "pipeline_regate_running": False,
        "pipeline_deploy_running": False,
        "pipeline_deploy_done": False,
        "pipeline_deploy_rc": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def main() -> None:
    st.set_page_config(
        page_title="SysSecOps Pipeline",
        page_icon="🛡️",
        layout="wide",
    )
    initialize_session_state()

    st.title("🛡️ SysSecOps IaC Pipeline")
    settings = sidebar.render_sidebar()

    login_tab, pipeline_tab, results_tab, monitor_tab, security_tab, settings_tab = st.tabs(
        ["🔑 Login", "🚀 Pipeline", "📂 Results", "📡 Monitor", "🛡️ Security", "⚙️ Settings"]
    )

    with login_tab:
        tabs.render_login_tab()
    with pipeline_tab:
        tabs.render_pipeline_tab(settings)
    with results_tab:
        tabs.render_results_tab()
    with monitor_tab:
        tabs.render_monitor_tab()
    with security_tab:
        tabs.render_security_tab()
    with settings_tab:
        tabs.render_settings_tab(settings)


if __name__ == "__main__":
    main()
