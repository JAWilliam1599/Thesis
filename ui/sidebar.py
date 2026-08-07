"""Sidebar: project selection, provider configuration and credential status badges."""
from __future__ import annotations

from typing import Any

import streamlit as st

from ui import config, credentials, projects


_PIPELINE_STATE_KEYS = (
    "pipeline_stage", "pipeline_prompt", "pipeline_run_id", "pipeline_gate_report",
    "pipeline_decision", "pipeline_approve_run_id", "pipeline_generated_code",
    "pipeline_logs_generate", "pipeline_logs_deploy", "pipeline_return_code",
    "pipeline_deploy_manual_approve", "pipeline_generate_running",
    "pipeline_regate_running", "pipeline_deploy_running", "pipeline_deploy_done",
    "pipeline_deploy_rc", "pipeline_code_editor",
    "hybrid_run_id", "hybrid_report", "hybrid_logs", "hybrid_running",
    "hybrid_deploying", "hybrid_deploy_done", "hybrid_return_code",
    "hybrid_manual_approve", "hybrid_manual_approve_confirm",
)


def _reset_run_state() -> None:
    """Clear all per-run session state when the active project changes."""
    for key in _PIPELINE_STATE_KEYS:
        st.session_state.pop(key, None)


def _render_project_section() -> dict[str, Any]:
    """Project selector + creation form. Returns the active project dict."""
    st.subheader("📁 Project")
    all_projects = projects.list_projects()
    ids = [p["id"] for p in all_projects]
    labels = {p["id"]: f"{p['name']}  ·  {p['workflow']}" for p in all_projects}

    active_id = st.session_state.get("active_project_id")
    if active_id not in ids:
        active_id = projects.get_active_project()["id"]
        st.session_state.active_project_id = active_id

    chosen = st.selectbox(
        "Active project", ids,
        index=ids.index(active_id),
        format_func=lambda pid: labels[pid],
        key="project_selector",
    )
    if chosen != active_id:
        st.session_state.active_project_id = chosen
        projects.set_active_project(chosen)
        _reset_run_state()
        st.rerun()

    project = projects.get_project(chosen) or projects.get_active_project()

    with st.expander("➕ New project", expanded=False):
        name = st.text_input("Name", key="new_project_name")
        workflow = st.radio(
            "Workflow", list(projects.WORKFLOWS),
            format_func=lambda w: (
                "CDK — generate + gate + deploy" if w == "cdk"
                else "Hybrid — your CDK + Ansible dirs (no codegen)"
            ),
            key="new_project_workflow",
        )
        if workflow == "cdk":
            cdk_path = st.text_input(
                "CDK project dir", value="generated_cdk", key="new_project_cdk_path"
            )
            ansible_path = playbook = inventory = target_host = ""
        else:
            cdk_path = st.text_input(
                "CDK app dir (blank to skip)", key="new_project_cdk_path_h"
            )
            ansible_path = st.text_input(
                "Ansible dir (blank to skip)", key="new_project_ansible_path"
            )
            playbook = st.text_input(
                "Playbook (blank = auto-detect site.yml…)", key="new_project_playbook"
            )
            inventory = st.text_input(
                "Inventory file (optional)", key="new_project_inventory"
            )
            target_host = st.text_input(
                "Target host / Tailscale IP (optional)", key="new_project_target_host"
            )
        if st.button("Create project", disabled=not name.strip()):
            created = projects.create_project(
                name, workflow,
                cdk_path=cdk_path, ansible_path=ansible_path,
                playbook=playbook, inventory=inventory, target_host=target_host,
            )
            st.session_state.active_project_id = created["id"]
            _reset_run_state()
            st.toast(f"Project '{created['name']}' created.", icon="📁")
            st.rerun()

    if project["id"] != projects.DEFAULT_PROJECT_ID:
        if st.button("🗑 Delete this project", key="delete_project"):
            projects.delete_project(project["id"])
            st.session_state.active_project_id = projects.DEFAULT_PROJECT_ID
            _reset_run_state()
            st.rerun()

    return project


def render_sidebar() -> dict[str, Any]:
    """Render the sidebar and return the effective pipeline settings."""
    creds = credentials.load_credentials()
    aws_ready = bool(creds.get("access_key") and creds.get("secret_key"))
    openrouter_ready = bool(creds.get("openrouter_key"))

    with st.sidebar:
        st.header("⚙️ Configuration")

        project = _render_project_section()
        is_hybrid = project.get("workflow") == "hybrid"

        st.divider()
        st.subheader("Credentials")
        st.markdown(
            ("✅ **AWS** ready" if aws_ready else "⚠️ **AWS** not configured")
            + "  \n"
            + ("✅ **OpenRouter** ready" if openrouter_ready else "⚠️ **OpenRouter** not set")
        )
        if not (aws_ready or openrouter_ready):
            st.info("Set credentials in the 🔑 Login tab.")

        st.divider()
        st.subheader("Generation")
        if is_hybrid:
            st.caption("Code generation is disabled for hybrid projects.")
        provider = st.selectbox(
            "Provider", config.PROVIDERS,
            index=0,
            help="Bedrock uses AWS; OpenRouter uses an API key.",
            disabled=is_hybrid,
        )
        default_model = (
            config.DEFAULT_BEDROCK_MODEL if provider == "bedrock"
            else config.DEFAULT_OPENROUTER_MODEL
        )
        model_id = st.text_input("Model ID", value=default_model, disabled=is_hybrid)
        region = st.text_input(
            "AWS region",
            value=creds.get("region") or config.DEFAULT_REGION,
            disabled=(provider != "bedrock" or is_hybrid),
        )
        max_regen_attempts = st.slider(
            "Max regen attempts", min_value=1, max_value=5, value=2,
            help="Auto-retries if the gate rejects the generated code.",
            disabled=is_hybrid,
        )

        st.divider()
        st.subheader("Security scanners")
        use_checkov = st.checkbox("Checkov", value=True)
        use_cfn_lint = st.checkbox("cfn-lint", value=True)
        use_infracost = st.checkbox("Infracost", value=True)
        use_aws_config = st.checkbox("AWS Config", value=True)
        use_ml_risk = st.checkbox(
            "ML risk model", value=True,
            help="Logistic-regression risk score (bandit + semgrep features) "
            "on the CDK Python source. Adds up to 85 points on a convex curve, "
            "so only a confident prediction weighs heavily.",
        )
        use_ansible_lint = True
        use_secret_scan = True
        if is_hybrid:
            use_ansible_lint = st.checkbox("ansible-lint (Ansible branch)", value=True)
            use_secret_scan = st.checkbox("Secret scan (Ansible branch)", value=True)

        st.divider()
        st.subheader("Gate thresholds")
        st.caption("Score bands that decide PASS / REVIEW / REJECT for each run.")
        pass_max = st.number_input(
            "Pass point (≤ = PASS)", min_value=0, max_value=1000,
            value=config.GATE_PASS_MAX, step=1,
            help="Scores at or below this value auto-pass.",
        )
        review_max = st.number_input(
            "Review point (≤ = REVIEW, above = REJECT)", min_value=0, max_value=1000,
            value=config.GATE_REVIEW_MAX, step=1,
            help="Scores above the pass point up to this value need manual review; "
            "anything higher is rejected.",
        )
        if review_max < pass_max:
            st.error("Review point must be ≥ pass point. Using defaults for this run.")
            pass_max = config.GATE_PASS_MAX
            review_max = config.GATE_REVIEW_MAX

        with st.expander("Cost & ML weights", expanded=False):
            cost_high_usd = st.number_input(
                "High cost band threshold (USD)", min_value=0.0, value=float(config.GATE_COST_HIGH_USD), step=1.0,
                help="Cost delta above this adds the high-band points.",
            )
            cost_high_points = st.number_input(
                "High cost band points", min_value=0, value=config.GATE_COST_HIGH_POINTS, step=1,
            )
            cost_med_usd = st.number_input(
                "Medium cost band threshold (USD)", min_value=0.0, value=float(config.GATE_COST_MED_USD), step=1.0,
                help="Cost delta above this (but below the high threshold) adds the medium-band points.",
            )
            cost_med_points = st.number_input(
                "Medium cost band points", min_value=0, value=config.GATE_COST_MED_POINTS, step=1,
            )
            ml_max_points = st.number_input(
                "ML risk max points", min_value=0, value=config.GATE_ML_MAX_POINTS, step=1,
                help="Points added at P(insecure)=1.0 from the logistic-regression model "
                "(CDK branch); lower probabilities scale in on a convex curve.",
            )

    return {
        "project": project,
        "provider": provider,
        "model_id": model_id,
        "region": region,
        "max_regen_attempts": max_regen_attempts,
        "use_checkov": use_checkov,
        "use_cfn_lint": use_cfn_lint,
        "use_infracost": use_infracost,
        "use_aws_config": use_aws_config,
        "use_ml_risk": use_ml_risk,
        "use_ansible_lint": use_ansible_lint,
        "use_secret_scan": use_secret_scan,
        "pass_max": int(pass_max),
        "review_max": int(review_max),
        "cost_high_usd": float(cost_high_usd),
        "cost_high_points": int(cost_high_points),
        "cost_med_usd": float(cost_med_usd),
        "cost_med_points": int(cost_med_points),
        "ml_max_points": int(ml_max_points),
        "aws_ready": aws_ready,
        "openrouter_ready": openrouter_ready,
    }
