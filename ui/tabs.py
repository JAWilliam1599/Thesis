"""Tab renderers for the SysSecOps GUI."""
from __future__ import annotations

import shutil
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import streamlit as st

from ui import config, credentials, helpers, monitoring, pipeline_runner, projects, reports


def _logs_root(settings: dict[str, Any]) -> Path:
    """Artifact root of the active project (legacy logs/ for the default)."""
    return projects.logs_root(settings.get("project") or projects.get_active_project())


# ===========================================================================
# Tab 1 — Login
# ===========================================================================
def render_login_tab() -> None:
    st.header("🔑 Credentials")
    st.caption(
        "Enter credentials here instead of logging in via the terminal. "
        "AWS keys are saved to `~/.aws/credentials`; the OpenRouter, Infracost "
        "and Tailscale values to `.env`."
    )
    stored = credentials.load_credentials()

    with st.form("credentials_form"):
        st.subheader("AWS / Bedrock")
        access_key = st.text_input(
            "Access Key ID", value=stored.get("access_key", ""), type="password"
        )
        secret_key = st.text_input(
            "Secret Access Key", value=stored.get("secret_key", ""), type="password"
        )
        session_token = st.text_input(
            "Session Token (optional)",
            value=stored.get("session_token", ""),
            type="password",
            placeholder="Leave blank if not using MFA / temporary role",
        )
        region = st.text_input(
            "Region", value=stored.get("region", config.DEFAULT_REGION)
        )

        st.subheader("OpenRouter")
        openrouter_key = st.text_input(
            "API Key", value=stored.get("openrouter_key", ""), type="password"
        )

        st.subheader("Infracost")
        infracost_key = st.text_input(
            "Infracost API Key",
            value=stored.get("infracost_key", ""),
            type="password",
            help="Free key from https://dashboard.infracost.io — avoids running "
            "`infracost auth login` in a terminal. Saved to `.env` as INFRACOST_API_KEY.",
        )

        st.subheader("Tailscale (optional — on-prem monitoring)")
        tailscale_key = st.text_input(
            "Tailscale API Key",
            value=stored.get("tailscale_key", ""),
            type="password",
            help="Used to list tailnet devices for hybrid/on-prem status.",
        )
        tailscale_tailnet = st.text_input(
            "Tailnet name",
            value=stored.get("tailscale_tailnet", ""),
            placeholder="example.com or tailnet-xxxx.ts.net",
        )

        submitted = st.form_submit_button("Test & Save", type="primary")

    if not submitted:
        return

    any_ok = False

    # AWS
    if access_key or secret_key:
        ok, message = credentials.test_aws_credentials(
            access_key, secret_key, session_token, region
        )
        if ok:
            credentials.save_aws_credentials(access_key, secret_key, session_token, region)
            st.success(f"AWS: {message}")
            any_ok = True
        else:
            st.error(f"AWS: {message}")
    else:
        st.info("AWS: no keys entered — skipped.")

    # OpenRouter
    if openrouter_key:
        ok, message = credentials.test_openrouter_key(openrouter_key)
        if ok:
            credentials.save_openrouter_key(openrouter_key)
            st.success(f"OpenRouter: {message}")
            any_ok = True
        else:
            st.error(f"OpenRouter: {message}")
    else:
        st.info("OpenRouter: no key entered — skipped.")

    # Infracost (no validation endpoint worth blocking on — the CLI reports
    # auth failures at scan time; just persist the key).
    if infracost_key:
        credentials.save_infracost_key(infracost_key)
        st.success("Infracost: key saved to .env (INFRACOST_API_KEY).")
        any_ok = True
    else:
        st.info("Infracost: no key entered — skipped.")

    # Tailscale
    if tailscale_key or tailscale_tailnet:
        credentials.save_tailscale_settings(tailscale_key, tailscale_tailnet)
        st.success("Tailscale: settings saved to .env.")
        any_ok = True

    if any_ok:
        st.session_state.creds_loaded = True
        st.toast("Credentials saved.", icon="✅")


# ===========================================================================
# Tab 2 — Pipeline (workflow-dependent)
# ===========================================================================
def render_pipeline_tab(settings: dict[str, Any]) -> None:
    project = settings.get("project") or projects.get_active_project()
    if project.get("workflow") == "hybrid":
        _render_hybrid_pipeline(settings)
        return

    st.header("🚀 Pipeline")
    st.caption(
        "Each step is its own sub-tab — jump straight to **Review & Edit** if you "
        "already generated code, or to **Deploy** once a run is approved. Use "
        "**Load an existing run** to resume from a saved gate report."
    )

    _render_active_run_bar(settings)

    gen_tab, edit_tab, decision_tab, deploy_tab = st.tabs([
        "1 · Generate + Gate",
        "2 · Review & Edit",
        "3 · Decision",
        "4 · Deploy",
    ])
    with gen_tab:
        _render_generate_subtab(settings)
    with edit_tab:
        _render_edit_subtab(settings)
    with decision_tab:
        _render_decision_subtab()
    with deploy_tab:
        _render_deploy_subtab(settings)


def _render_active_run_bar(settings: dict[str, Any]) -> None:
    """Shared status line + 'load existing run' control above the sub-tabs."""
    logs_root = _logs_root(settings)
    gate = st.session_state.get("pipeline_gate_report")
    cols = st.columns([4, 1])
    with cols[0]:
        if gate:
            rid = (
                st.session_state.get("pipeline_approve_run_id")
                or st.session_state.get("pipeline_run_id")
                or "—"
            )
            dec = st.session_state.get("pipeline_decision") or helpers.decision_of(gate)
            score = gate.get("score", "—")
            st.markdown(
                f"**Active run:** `{rid}`　·　decision **{dec}**　·　score **{score}**"
            )
        else:
            st.markdown(
                "**Active run:** _none_ — generate a new one, or load an existing run ↓"
            )
    with cols[1]:
        if st.button("🔁 Reset", help="Clear the active run and logs"):
            _reset_pipeline()
            st.rerun()

    with st.expander("📂 Load an existing run", expanded=not gate):
        paths = helpers.list_gate_reports(logs_root)
        if not paths:
            st.caption("No gate reports found for this project.")
        else:
            options = {helpers.format_run_label(p): p for p in paths}
            choice = st.selectbox(
                "Gate report", list(options.keys()), key="pipeline_load_choice"
            )
            load_code = st.checkbox(
                "Also load current GeneratedCDK/app.py into the editor",
                value=True,
                key="pipeline_load_code",
            )
            if st.button("Load into pipeline"):
                report = helpers.load_gate_report(options[choice])
                _load_run_into_state(report, load_code)
                st.rerun()
    st.divider()


def _load_run_into_state(report: dict[str, Any] | None, load_code: bool) -> None:
    st.session_state.pipeline_gate_report = report
    st.session_state.pipeline_decision = helpers.decision_of(report)
    run_id = (report or {}).get("run_id")
    st.session_state.pipeline_run_id = run_id
    st.session_state.pipeline_approve_run_id = run_id
    st.session_state.pipeline_deploy_done = False
    st.session_state.pipeline_deploy_rc = None
    st.session_state.pipeline_logs_deploy = ""
    if load_code and config.GENERATED_CDK_APP.exists():
        try:
            st.session_state.pipeline_generated_code = (
                config.GENERATED_CDK_APP.read_text(encoding="utf-8")
            )
            st.session_state.pop("pipeline_code_editor", None)
        except OSError:
            pass
    st.toast("Run loaded.", icon="📂")


# --- Sub-tab 1: Generate + Gate ---------------------------------------------
def _render_generate_subtab(settings: dict[str, Any]) -> None:
    if st.session_state.get("pipeline_generate_running"):
        _run_generate(settings)
        return

    provider = settings["provider"]
    ready = settings["aws_ready"] if provider == "bedrock" else settings["openrouter_ready"]
    if not ready:
        st.warning(
            f"`{provider}` credentials are not configured. "
            "Set them in the 🔑 Login tab before running the pipeline."
        )

    st.text_area(
        "Describe the infrastructure to generate",
        key="pipeline_prompt_input",
        height=140,
        placeholder="e.g. Create an encrypted S3 bucket with versioning and access logging.",
    )
    prompt = st.session_state.get("pipeline_prompt_input", "").strip()

    if st.button("▶ Generate + Gate", type="primary", disabled=not (ready and prompt)):
        st.session_state.pipeline_prompt = prompt
        st.session_state.pipeline_logs_generate = ""
        st.session_state.pipeline_generate_running = True
        st.rerun()

    if st.session_state.get("pipeline_gate_report"):
        st.success(
            "A run is loaded. Open **2 · Review & Edit** to inspect the code and gate result."
        )
    if st.session_state.get("pipeline_logs_generate"):
        with st.expander("Last generation logs", expanded=False):
            st.code(st.session_state.pipeline_logs_generate)


def _run_generate(settings: dict[str, Any]) -> None:
    st.info(f"Generating for prompt: _{st.session_state.pipeline_prompt}_")
    with st.status("Stage 1 · Generate + Synth + Gate", expanded=True) as status:
        result = _run_with_live_logs(
            lambda on_line: pipeline_runner.run_generate_stage(
                settings, st.session_state.pipeline_prompt, on_line,
                logs_root=_logs_root(settings),
            )
        )
        st.session_state.pipeline_logs_generate = result["logs"]
        st.session_state.pipeline_run_id = result["run_id"]
        st.session_state.pipeline_gate_report = result["gate_report"]
        st.session_state.pipeline_decision = result["decision"]
        st.session_state.pipeline_approve_run_id = result["approve_run_id"]
        st.session_state.pipeline_generated_code = result["code"]
        st.session_state.pop("pipeline_code_editor", None)
        st.session_state.pipeline_deploy_done = False
        st.session_state.pipeline_deploy_rc = None

        if result["gate_report"]:
            status.update(label="Stage 1 · complete", state="complete")
        else:
            status.update(label="Stage 1 · failed", state="error")
            st.session_state.pipeline_return_code = result["return_code"]

    st.session_state.pipeline_generate_running = False
    st.rerun()


# --- Sub-tab 2: Review & Edit -----------------------------------------------
def _render_edit_subtab(settings: dict[str, Any]) -> None:
    if st.session_state.get("pipeline_regate_running"):
        _run_regate(settings)
        return

    if not st.session_state.get("pipeline_gate_report"):
        st.info(
            "No active run. Generate code in **1 · Generate + Gate**, or load an "
            "existing run from the bar above."
        )
        return

    st.subheader("✏️ Review & Edit Code")
    st.caption(
        "Edit the generated CDK app and re-run synth + gate as many times as you "
        "like, then open **3 · Decision** to review the deployment decision."
    )
    edited = st.text_area(
        "GeneratedCDK/app.py",
        value=st.session_state.pipeline_generated_code,
        height=360,
        key="pipeline_code_editor",
    )

    col1, col2 = st.columns(2)
    if col1.button("💾 Save & Re-run Synth+Gate", type="primary"):
        st.session_state.pipeline_generated_code = edited
        st.session_state.pipeline_regate_running = True
        st.rerun()
    if col2.button("💾 Save code only"):
        st.session_state.pipeline_generated_code = edited
        try:
            config.GENERATED_CDK_APP.write_text(edited, encoding="utf-8")
            st.toast("Saved GeneratedCDK/app.py.", icon="💾")
        except OSError as exc:
            st.error(f"Could not save: {exc}")

    if st.session_state.get("pipeline_logs_generate"):
        with st.expander("Generation logs", expanded=False):
            st.code(st.session_state.pipeline_logs_generate)

    st.divider()
    st.subheader("Current gate result")
    reports.render_gate_report(st.session_state.pipeline_gate_report)


def _run_regate(settings: dict[str, Any]) -> None:
    config.GENERATED_CDK_APP.write_text(
        st.session_state.pipeline_generated_code, encoding="utf-8"
    )
    with st.status("Re-running Synth + Gate", expanded=True) as status:
        result = _run_with_live_logs(
            lambda on_line: pipeline_runner.run_synth_gate_stage(
                settings, on_line, logs_root=_logs_root(settings)
            )
        )
        if result["gate_report"]:
            st.session_state.pipeline_gate_report = result["gate_report"]
            st.session_state.pipeline_decision = result["decision"]
            st.session_state.pipeline_approve_run_id = result["approve_run_id"]
            st.session_state.pipeline_run_id = result["run_id"]
            st.session_state.pipeline_deploy_done = False
            st.session_state.pipeline_deploy_rc = None
            status.update(label="Re-gate complete", state="complete")
        else:
            status.update(label="Re-gate failed (synth error?)", state="error")
    st.session_state.pipeline_regate_running = False
    st.rerun()


# --- Sub-tab 3: Decision ----------------------------------------------------
def _render_decision_subtab() -> None:
    gate = st.session_state.get("pipeline_gate_report")
    if not gate:
        st.info(
            "No active run. Generate or load a run first to see the deployment decision."
        )
        return

    st.subheader("🚦 Deployment Decision")
    decision = reports.render_decision_banner(gate)
    reports.render_gate_report(gate)
    st.divider()

    if decision == "pass":
        st.success("This run passed the gate. Open **4 · Deploy** to deploy it.")
    elif decision == "review":
        st.warning(
            "This run is in the review band — manual approval is required. "
            "Open **4 · Deploy** to approve and deploy."
        )
    else:
        st.error(
            "The gate rejected this run. Edit the code in **2 · Review & Edit** "
            "and re-run synth + gate, or generate a new run."
        )


# --- Sub-tab 4: Deploy ------------------------------------------------------
def _render_deploy_subtab(settings: dict[str, Any]) -> None:
    if st.session_state.get("pipeline_deploy_running"):
        _run_deploy(settings)
        return

    gate = st.session_state.get("pipeline_gate_report")
    if not gate:
        st.info("No active run. Generate or load an approved run first.")
        return

    if st.session_state.get("pipeline_deploy_done"):
        _render_deploy_result()
        return

    decision = st.session_state.get("pipeline_decision") or helpers.decision_of(gate)
    st.subheader("🚀 Deploy")
    rid = st.session_state.get("pipeline_approve_run_id") or st.session_state.get("pipeline_run_id")
    st.caption(f"Approve run `{rid}` and run `cdk deploy` — this may take several minutes.")

    if decision == "reject":
        st.error(
            "The gate rejected this run, so it cannot be deployed. Fix the code in "
            "**2 · Review & Edit** first."
        )
        return

    manual_approve = False
    if decision == "review":
        st.warning("Review-band result — confirm manual approval to deploy.")
        manual_approve = st.checkbox(
            "I approve this review-band deployment", key="pipeline_manual_approve_confirm"
        )

    deploy_disabled = decision == "review" and not manual_approve
    if st.button("🚀 Deploy Now", type="primary", disabled=deploy_disabled):
        st.session_state.pipeline_deploy_manual_approve = manual_approve
        st.session_state.pipeline_logs_deploy = ""
        st.session_state.pipeline_deploy_running = True
        st.rerun()


def _run_deploy(settings: dict[str, Any]) -> None:
    st.subheader("🚀 Deploy")
    st.caption("`cdk deploy` may take several minutes — keep this tab open.")
    with st.status("Deploying…", expanded=True) as status:
        result = _run_with_live_logs(
            lambda on_line: pipeline_runner.run_deploy_stage(
                st.session_state.pipeline_approve_run_id,
                st.session_state.pipeline_deploy_manual_approve,
                on_line,
                logs_root=_logs_root(settings),
            )
        )
        st.session_state.pipeline_logs_deploy = result["logs"]
        st.session_state.pipeline_return_code = result["return_code"]
        st.session_state.pipeline_deploy_rc = result["return_code"]
        if result["return_code"] == 0:
            status.update(label="Deploy complete", state="complete")
        else:
            status.update(label="Deploy failed", state="error")
    st.session_state.pipeline_deploy_done = True
    st.session_state.pipeline_deploy_running = False
    st.rerun()


def _render_deploy_result() -> None:
    rc = st.session_state.get("pipeline_deploy_rc")
    st.subheader("🚀 Deploy")
    if rc == 0:
        st.success("✅ Deployment complete.")
        st.markdown(
            "Post-deploy monitoring (CloudWatch alarms, CloudTrail, Application "
            "Insights) was provisioned for the stack. Open the **📡 Monitor** tab "
            "to track its live status."
        )
    else:
        meaning = config.RETURN_CODE_MEANING.get(rc, "Unknown error")
        st.error(f"Deploy failed: {meaning}" + (f" (exit {rc})" if rc is not None else ""))
        logs = st.session_state.get("pipeline_logs_deploy") or ""
        if any(
            marker in logs
            for marker in ("ROLLBACK", "CREATE_FAILED", "UPDATE_FAILED", "DELETE_FAILED")
        ):
            st.warning(
                "The stack appears to have **rolled back** in CloudFormation. "
                "Review the deploy logs below for the failing resource, fix the "
                "code in **2 · Review & Edit**, and re-run synth + gate before "
                "deploying again. If the stack is stuck in `ROLLBACK_COMPLETE`, "
                "delete it in the AWS console before redeploying."
            )

    with st.expander("Deploy logs", expanded=rc != 0):
        st.code(st.session_state.get("pipeline_logs_deploy") or "(no logs)")

    col1, col2 = st.columns(2)
    if col1.button("🔁 Deploy again"):
        st.session_state.pipeline_deploy_done = False
        st.session_state.pipeline_deploy_rc = None
        st.rerun()
    if col2.button("🆕 Start New Pipeline", type="primary"):
        _reset_pipeline()
        st.rerun()


# ===========================================================================
# Tab 2 (hybrid workflow) — Gate · Review · Deploy, no code generation
# ===========================================================================
def _render_hybrid_pipeline(settings: dict[str, Any]) -> None:
    project = settings.get("project") or projects.get_active_project()
    st.header("🚀 Hybrid Pipeline")
    st.caption(
        "Bring-your-own IaC: the gate scans your **CDK** and **Ansible** "
        "directories (no code generation). Each branch is scored independently "
        "with the same risk engine, then deployed when the gate allows."
    )

    if not (project.get("cdk_path") or project.get("ansible_path")):
        st.warning(
            "This project has no CDK or Ansible directory configured. "
            "Set at least one below."
        )

    with st.expander("📁 Project paths", expanded=not st.session_state.get("hybrid_report")):
        cdk_path = st.text_input(
            "CDK app dir (blank to skip)",
            value=project.get("cdk_path", ""), key="hybrid_cdk_path",
        )
        ansible_path = st.text_input(
            "Ansible dir (blank to skip)",
            value=project.get("ansible_path", ""), key="hybrid_ansible_path",
        )
        col1, col2, col3 = st.columns(3)
        playbook = col1.text_input(
            "Playbook (auto-detect if blank)",
            value=project.get("playbook", ""), key="hybrid_playbook",
        )
        inventory = col2.text_input(
            "Inventory (optional)",
            value=project.get("inventory", ""), key="hybrid_inventory",
        )
        target_host = col3.text_input(
            "Target host / Tailscale IP",
            value=project.get("target_host", ""), key="hybrid_target_host",
        )
        if st.button("💾 Save paths to project"):
            projects.update_project(
                project["id"],
                cdk_path=cdk_path, ansible_path=ansible_path,
                playbook=playbook, inventory=inventory, target_host=target_host,
            )
            st.toast("Project paths saved.", icon="💾")
            st.rerun()

    # Always run against the values currently in the inputs.
    effective_project = {
        **project,
        "cdk_path": st.session_state.get("hybrid_cdk_path", project.get("cdk_path", "")),
        "ansible_path": st.session_state.get("hybrid_ansible_path", project.get("ansible_path", "")),
        "playbook": st.session_state.get("hybrid_playbook", project.get("playbook", "")),
        "inventory": st.session_state.get("hybrid_inventory", project.get("inventory", "")),
        "target_host": st.session_state.get("hybrid_target_host", project.get("target_host", "")),
    }

    gate_tab, review_tab, deploy_tab = st.tabs([
        "1 · Gate", "2 · Review", "3 · Deploy",
    ])
    with gate_tab:
        _render_hybrid_gate_subtab(settings, effective_project)
    with review_tab:
        _render_hybrid_review_subtab(settings)
    with deploy_tab:
        _render_hybrid_deploy_subtab(settings, effective_project)


def _run_hybrid(
    settings: dict[str, Any],
    project: dict[str, Any],
    *,
    deploy: bool,
    manual_approve: bool = False,
) -> None:
    label = "Gate + Deploy" if deploy else "Gate"
    with st.status(f"Hybrid · {label} running…", expanded=True) as status:
        result = _run_with_live_logs(
            lambda on_line: pipeline_runner.run_hybrid_stage(
                settings, project, on_line,
                logs_root=_logs_root(settings),
                deploy=deploy, manual_approve=manual_approve,
            )
        )
        st.session_state.hybrid_logs = result["logs"]
        st.session_state.hybrid_run_id = result["run_id"]
        st.session_state.hybrid_return_code = result["return_code"]
        if result["hybrid_report"]:
            st.session_state.hybrid_report = result["hybrid_report"]
            status.update(label=f"Hybrid · {label} complete", state="complete")
        else:
            status.update(label=f"Hybrid · {label} failed (no report)", state="error")
    if deploy:
        st.session_state.hybrid_deploy_done = True
        st.session_state.hybrid_deploying = False
    else:
        st.session_state.hybrid_running = False
    st.rerun()


def _hybrid_branches() -> list[dict[str, Any]]:
    report = st.session_state.get("hybrid_report") or {}
    return report.get("branches") or []


def _render_hybrid_branch_summary() -> None:
    branches = _hybrid_branches()
    if not branches:
        return
    st.dataframe(
        [
            {
                "Branch": b.get("target", "—"),
                "Status": b.get("status", "—"),
                "Decision": b.get("decision") or "—",
                "Score": b.get("score", "—"),
            }
            for b in branches
        ],
        width="stretch",
        hide_index=True,
    )


def _render_hybrid_gate_subtab(settings: dict[str, Any], project: dict[str, Any]) -> None:
    if st.session_state.get("hybrid_running"):
        _run_hybrid(settings, project, deploy=False)
        return

    targets = [t for t, p in (("CDK", project.get("cdk_path")), ("Ansible", project.get("ansible_path"))) if p]
    if not targets:
        st.info("Configure a CDK and/or Ansible directory above, then run the gate.")
        return

    st.markdown(f"**Branches to gate:** {', '.join(targets)}")
    if st.button("▶ Run Gate", type="primary"):
        st.session_state.hybrid_logs = ""
        st.session_state.hybrid_report = None
        st.session_state.hybrid_deploy_done = False
        st.session_state.hybrid_running = True
        st.rerun()

    if st.session_state.get("hybrid_report"):
        st.success(
            f"Gate run `{st.session_state.get('hybrid_run_id')}` complete. "
            "Open **2 · Review** for per-branch findings."
        )
        _render_hybrid_branch_summary()
    if st.session_state.get("hybrid_logs"):
        with st.expander("Last run logs", expanded=False):
            st.code(st.session_state.hybrid_logs)


def _render_hybrid_review_subtab(settings: dict[str, Any]) -> None:
    branches = _hybrid_branches()
    if not branches:
        st.info("No hybrid run yet — run the gate in **1 · Gate** first.")
        return

    _render_hybrid_branch_summary()
    for branch in branches:
        target = branch.get("target", "branch")
        with st.expander(f"🔎 {target} — gate report", expanded=len(branches) == 1):
            report_path = branch.get("report_path")
            report = None
            if report_path:
                report = helpers.load_gate_report(Path(report_path))
            if report:
                reports.render_gate_report(report)
            elif branch.get("status") == "error":
                st.error(f"Branch failed before the gate: {branch.get('error', 'unknown error')}")
            else:
                st.info("No gate report recorded for this branch.")


def _render_hybrid_deploy_subtab(settings: dict[str, Any], project: dict[str, Any]) -> None:
    if st.session_state.get("hybrid_deploying"):
        _run_hybrid(
            settings, project, deploy=True,
            manual_approve=st.session_state.get("hybrid_manual_approve", False),
        )
        return

    branches = _hybrid_branches()
    if not branches:
        st.info("No hybrid run yet — run the gate in **1 · Gate** first.")
        return

    if st.session_state.get("hybrid_deploy_done"):
        rc = st.session_state.get("hybrid_return_code")
        if rc == 0:
            st.success("✅ Deploy run complete — all attempted branches succeeded.")
        else:
            st.error(
                f"Deploy run finished with exit code {rc} — a branch failed or was "
                "rejected. Check the logs and branch summary below."
            )
        _render_hybrid_branch_summary()
        with st.expander("Deploy logs", expanded=rc != 0):
            st.code(st.session_state.get("hybrid_logs") or "(no logs)")
        if st.button("🆕 New hybrid run", type="primary"):
            _reset_pipeline()
            st.rerun()
        return

    st.subheader("🚀 Deploy")
    _render_hybrid_branch_summary()
    decisions = {str(b.get("decision") or "").lower() for b in branches}

    if decisions <= {"reject", ""}:
        st.error("Every branch was rejected — remediate the findings and re-run the gate.")
        return

    st.caption(
        "Deploying re-runs the full hybrid pipeline with `--deploy`: each branch "
        "is re-gated and then deployed if its decision allows it."
    )
    manual_approve = False
    if "review" in decisions:
        st.warning("At least one branch is in the review band — manual approval is required for it.")
        manual_approve = st.checkbox(
            "I approve deploying review-band branches", key="hybrid_manual_approve_confirm"
        )
    if "reject" in decisions:
        st.error("Rejected branches will be skipped by the gate during deploy.")

    disabled = "review" in decisions and not manual_approve
    if st.button("🚀 Deploy allowed branches", type="primary", disabled=disabled):
        st.session_state.hybrid_manual_approve = manual_approve
        st.session_state.hybrid_logs = ""
        st.session_state.hybrid_deploying = True
        st.rerun()


# ===========================================================================
# Tab 3 — Results Browser
# ===========================================================================
def render_results_tab(settings: dict[str, Any]) -> None:
    st.header("📂 Results Browser")
    _render_gate_reports_browser(_logs_root(settings))


def _render_gate_reports_browser(logs_root: Path | None = None) -> None:
    paths = helpers.list_gate_reports(logs_root)
    if not paths:
        st.info("No gate reports found for this project.")
        return
    options = {helpers.format_run_label(p): p for p in paths}
    choice = st.selectbox("Gate report", list(options.keys()))
    report = helpers.load_gate_report(options[choice])
    reports.render_gate_report(report)


# ===========================================================================
# Tab 4 — Security Dashboard
# ===========================================================================
def render_security_tab(settings: dict[str, Any]) -> None:
    st.header("🛡️ Security Dashboard")
    all_reports = helpers.load_all_gate_reports(_logs_root(settings))
    if not all_reports:
        st.info("No gate reports yet. Run the pipeline to populate the dashboard.")
        return

    scores = [r.get("score", 0) for r in all_reports]
    decisions = Counter(str(r.get("decision", "")).lower() for r in all_reports)
    total = len(all_reports)
    passed = decisions.get("pass", 0)
    critical = sum(
        1
        for r in all_reports
        for f in (r.get("findings") or [])
        if str(f.get("severity", "")).lower() == "critical"
    )

    cols = st.columns(4)
    cols[0].metric("Total runs", total)
    cols[1].metric("Avg gate score", round(sum(scores) / total, 1))
    cols[2].metric("Pass rate", f"{round(100 * passed / total)}%")
    cols[3].metric("Critical findings", critical)

    st.subheader("Decision distribution")
    st.bar_chart(
        {
            "count": {
                "pass": decisions.get("pass", 0),
                "review": decisions.get("review", 0),
                "reject": decisions.get("reject", 0),
            }
        }
    )

    st.subheader("Top recurring findings")
    finding_counter: Counter = Counter()
    for r in all_reports:
        for f in (r.get("findings") or []):
            finding_counter[f.get("message", "unknown")] += 1
    if finding_counter:
        st.dataframe(
            [{"Finding": msg, "Count": n} for msg, n in finding_counter.most_common(10)],
            width="stretch",
            hide_index=True,
        )

    st.subheader("Latest gate report")
    reports.render_gate_report(all_reports[0])


# ===========================================================================
# Tab 5 — Monitor (sub-tabs: Resources · App Statistics)
# ===========================================================================
def render_monitor_tab(settings: dict[str, Any]) -> None:
    st.header("📡 Monitor")
    st.caption(
        "**Resources** — live AWS + on-prem resource health. "
        "**App Statistics** — pipeline history: gate scores, decisions, and user activity."
    )

    resources_tab, stats_tab = st.tabs(["📈 Resources", "🛡️ App Statistics"])
    with resources_tab:
        _render_monitor_resources()
    with stats_tab:
        _render_monitor_statistics(settings)


# --- Sub-tab: App Statistics -------------------------------------------------
def _render_monitor_statistics(settings: dict[str, Any]) -> None:
    _render_monitor_local(_logs_root(settings))
    st.divider()

    # Refresh controls for the live AWS-backed section.
    ctrl = st.columns([1, 2, 2])
    if ctrl[0].button("🔄 Refresh", help="Re-query SSM and CloudWatch now"):
        st.rerun()
    auto = ctrl[1].toggle(
        "Auto-refresh", key="monitor_auto_refresh",
        help="Periodically re-query the AWS-backed status below.",
    )
    interval = ctrl[2].selectbox(
        "Interval", [15, 30, 60, 120],
        index=1, format_func=lambda s: f"every {s}s",
        disabled=not auto, key="monitor_refresh_interval",
    )

    run_every = interval if auto else None
    fragment = st.fragment(run_every=run_every)(_render_monitor_aws)
    fragment()


def _render_monitor_local(logs_root: Path | None = None) -> None:
    st.subheader("Local activity")
    reports_list = helpers.load_all_gate_reports(logs_root)
    approvals = helpers.load_approvals(logs_root)
    rejections = helpers.load_rejections(logs_root)

    decisions = Counter(str(r.get("decision", "")).lower() for r in reports_list)
    cols = st.columns(5)
    cols[0].metric("Gate runs", len(reports_list))
    cols[1].metric("Pass / Review / Reject",
                   f"{decisions.get('pass', 0)} / {decisions.get('review', 0)} / {decisions.get('reject', 0)}")
    cols[2].metric("Approvals", len(approvals))
    cols[3].metric("Rejections", len(rejections))
    scores = [r.get("score", 0) for r in reports_list]
    cols[4].metric("Avg score", round(sum(scores) / len(scores), 1) if scores else "—")

    with st.expander("Gate score trend", expanded=bool(reports_list)):
        if reports_list:
            ordered = sorted(
                reports_list,
                key=lambda r: str(r.get("timestamp", r.get("run_id", ""))),
            )
            chart = {"gate score": [r.get("score", 0) for r in ordered]}
            ml_scores = [
                (r.get("components") or {}).get("ml_risk", 0) for r in ordered
            ]
            if any(ml_scores):
                chart["ml risk"] = ml_scores
            st.line_chart(chart)
        else:
            st.info("No gate reports yet.")

    with st.expander("User activity (approvals by approver)", expanded=False):
        if approvals:
            by_approver: Counter = Counter(
                a.get("approver_arn") or a.get("approver") or "unknown" for a in approvals
            )
            st.dataframe(
                [{"Approver": who, "Approvals": n} for who, n in by_approver.most_common()],
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("No approvals recorded.")

    with st.expander("Approval history", expanded=False):
        if approvals:
            st.dataframe(
                [
                    {
                        "Run": a.get("run_id", "—"),
                        "Decision": a.get("gate_decision", "—"),
                        "Score": a.get("gate_score", "—"),
                        "Approver": a.get("approver", "—"),
                        "When": a.get("approved_at", "—"),
                    }
                    for a in approvals
                ],
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("No approvals recorded.")

    with st.expander("Rejection log", expanded=False):
        if rejections:
            st.dataframe(
                [
                    {
                        "Run": r.get("run_id", "—"),
                        "Decision": r.get("gate_decision", "—"),
                        "Score": r.get("gate_score", "—"),
                        "When": r.get("rejected_at", r.get("timestamp", "—")),
                    }
                    for r in rejections
                ],
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("No rejections recorded.")


def _render_monitor_aws() -> None:
    st.subheader("AWS-backed status")
    creds = credentials.load_credentials()
    if not (creds.get("access_key") and creds.get("secret_key")):
        st.info(
            "AWS credentials not configured. Add them in the Login tab to see "
            "live SSM gate state and CloudWatch alarms."
        )
        return

    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    st.markdown("**Monitored stacks (SSM gate state)**")
    rows, error = monitoring.list_stack_statuses()
    if error:
        st.warning(f"SSM lookup failed: {error}")
    elif not rows:
        st.info("No monitored stacks found in SSM.")
    else:
        st.dataframe(
            [
                {
                    "Stack": r["stack"],
                    "Decision": r["decision"],
                    "Score": r["score"],
                    "Run": r["run_id"],
                }
                for r in rows
            ],
            width="stretch",
            hide_index=True,
        )

    st.markdown("**CloudWatch alarms**")
    alarms, alarm_error = monitoring.list_alarms()
    if alarm_error:
        st.warning(f"CloudWatch lookup failed: {alarm_error}")
    elif not alarms:
        st.info("No SysSecOps CloudWatch alarms found.")
    else:
        st.dataframe(
            [
                {
                    "State": _alarm_badge(a["state"]),
                    "Alarm": a["name"],
                    "Metric": a["metric"],
                    "Updated": a["updated"],
                }
                for a in alarms
            ],
            width="stretch",
            hide_index=True,
        )


def _alarm_badge(state: str) -> str:
    emoji, _ = config.ALARM_STATE_STYLE.get(state, ("❔", "#9a6700"))
    return f"{emoji} {state}"


# --- Sub-tab: Resources --------------------------------------------------------
def _render_monitor_resources() -> None:
    creds = credentials.load_credentials()
    aws_ready = bool(creds.get("access_key") and creds.get("secret_key"))

    st.subheader("AWS resources")
    if not aws_ready:
        st.info(
            "AWS credentials not configured. Add them in the Login tab to browse "
            "deployed stacks and resource metrics."
        )
    else:
        _render_stack_resources()

    st.divider()
    st.subheader("Dashboards")
    st.markdown(
        f"- [CloudWatch dashboards (incl. automatic per-service dashboards)]"
        f"({monitoring.cloudwatch_automatic_dashboards_url()})\n"
        f"- [SysSecOpsGate dashboard]({monitoring.cloudwatch_dashboard_url('SysSecOpsGate')})"
        " — gate score / decision / findings trends\n"
        f"- [SysSecOps-Hybrid dashboard]({monitoring.cloudwatch_dashboard_url('SysSecOps-Hybrid')})"
        " — per-target risk scores + hybrid network flow"
    )
    st.caption(
        "AWS automatic dashboards (EC2, Lambda, RDS…) are generated by CloudWatch "
        "for every service in use — open the first link and pick a service."
    )

    st.divider()
    st.subheader("On-premise / hybrid mesh")
    if not aws_ready:
        st.info("Requires AWS credentials (SSM) — Tailscale settings are optional.")
        return
    _render_onprem_status()


def _render_stack_resources() -> None:
    stacks, error = monitoring.list_cfn_stacks()
    if error:
        st.warning(f"CloudFormation lookup failed: {error}")
        return
    if not stacks:
        st.info("No active CloudFormation stacks found in this region.")
        return

    stack = st.selectbox("Stack", stacks, key="monitor_resource_stack")
    st.markdown(f"[Open in CloudFormation console]({monitoring.cloudformation_stack_url(stack)})")

    resources, res_error = monitoring.list_stack_resources(stack)
    if res_error:
        st.warning(f"Resource listing failed: {res_error}")
        return
    if not resources:
        st.info("Stack has no resources.")
        return

    st.dataframe(
        [
            {
                "Logical ID": r["logical_id"],
                "Type": r["type"],
                "Physical ID": r["physical_id"],
                "Status": r["status"],
            }
            for r in resources
        ],
        width="stretch",
        hide_index=True,
    )

    # Metric charts for supported resource types.
    chartable = [r for r in resources if r["type"] in monitoring.RESOURCE_METRICS and r["physical_id"]]
    if not chartable:
        st.caption("No chartable resources (EC2 / Lambda / RDS / ECS) in this stack.")
        return

    st.markdown("**Resource metrics (last 24 h)**")
    labels = {
        f"{r['logical_id']} ({r['type'].split('::')[-1]})": r for r in chartable
    }
    choice = st.selectbox("Resource", list(labels.keys()), key="monitor_resource_pick")
    resource = labels[choice]
    namespace, dim_name, metrics = monitoring.RESOURCE_METRICS[resource["type"]]

    cols = st.columns(len(metrics))
    for col, (metric, stat, unit) in zip(cols, metrics):
        with col:
            points, m_error = monitoring.get_metric_series(
                namespace, metric, dim_name, resource["physical_id"], stat=stat
            )
            st.caption(f"{metric} ({stat}, {unit})")
            if m_error:
                st.warning(m_error)
            elif not points:
                st.info("No datapoints.")
            else:
                st.line_chart({metric: [p["value"] for p in points]})


def _render_onprem_status() -> None:
    status, error = monitoring.get_hybrid_status()
    if error:
        st.warning(f"Hybrid status lookup failed: {error}")
        return

    nodes = status.get("ssm_nodes", {})
    compliance = status.get("ssm_compliance", {})
    devices = status.get("tailscale_devices", {})

    st.markdown("**SSM managed nodes (EC2 `i-*` + on-prem `mi-*`)**")
    if nodes.get("status") != "ok":
        st.info(f"SSM nodes unavailable: {nodes.get('status', 'unknown')}")
    elif not nodes.get("items"):
        st.info("No SSM-managed nodes registered.")
    else:
        st.dataframe(
            [
                {
                    "Node": n.get("name") or n.get("id", "—"),
                    "ID": n.get("id", "—"),
                    "On-prem": "🏠 yes" if n.get("is_hybrid") else "☁️ EC2",
                    "Ping": n.get("ping_status", "—"),
                    "Platform": n.get("platform", "—"),
                    "IP": n.get("ip", "—"),
                    "Last ping": n.get("last_ping", "—"),
                }
                for n in nodes["items"]
            ],
            width="stretch",
            hide_index=True,
        )

    st.markdown("**SSM compliance (State Manager / Patch)**")
    if compliance.get("status") != "ok":
        st.info(f"Compliance data unavailable: {compliance.get('status', 'unknown')}")
    elif not compliance.get("items"):
        st.info("No compliance summaries recorded.")
    else:
        st.dataframe(
            [
                {
                    "Resource": c.get("resource_id", "—"),
                    "Type": c.get("compliance_type", "—"),
                    "Status": c.get("status", "—"),
                    "Critical": c.get("critical_count", 0),
                    "High": c.get("high_count", 0),
                }
                for c in compliance["items"]
            ],
            width="stretch",
            hide_index=True,
        )

    st.markdown("**Tailscale mesh devices**")
    if devices.get("status") == "not_configured":
        st.info(
            "Tailscale not configured — set the API key and tailnet in the "
            "🔑 Login tab to see mesh device health."
        )
    elif devices.get("status") != "ok":
        st.info(f"Tailscale devices unavailable: {devices.get('status', 'unknown')}")
    elif not devices.get("items"):
        st.info("No devices in the tailnet.")
    else:
        st.dataframe(
            [
                {
                    "Device": d.get("hostname") or d.get("name", "—"),
                    "Online": "🟢 online" if d.get("online") else "🔴 offline",
                    "OS": d.get("os", "—"),
                    "Mesh IP": ", ".join(d.get("addresses", [])[:1]) or "—",
                    "Last seen": d.get("last_seen", "—"),
                }
                for d in devices["items"]
            ],
            width="stretch",
            hide_index=True,
        )


# ===========================================================================
# Tab 6 — Settings / About
# ===========================================================================
def render_settings_tab(settings: dict[str, Any]) -> None:
    st.header("⚙️ Settings & About")

    st.subheader("Effective settings")
    st.json({k: v for k, v in settings.items() if k not in ("aws_ready", "openrouter_ready")})

    st.subheader("Credential locations")
    st.markdown(
        f"- AWS credentials: `{config.AWS_CREDS_PATH}`\n"
        f"- AWS config: `{config.AWS_CONFIG_PATH}`\n"
        f"- OpenRouter key (.env): `{config.ENV_FILE}`"
    )

    st.subheader("Tool availability")
    rows = []
    for scanner in config.SCANNERS:
        path = shutil.which(scanner)
        rows.append({"Tool": scanner, "Status": "✅ " + path if path else "⚠️ not found"})
    rows.append({"Tool": "cdk", "Status": _cdk_version()})
    st.dataframe(rows, width="stretch", hide_index=True)

    if config.README_FILE.exists():
        with st.expander("Project README", expanded=False):
            st.markdown(config.README_FILE.read_text(encoding="utf-8"))


def _cdk_version() -> str:
    cdk = shutil.which("cdk")
    if not cdk:
        return "⚠️ not found"
    try:
        out = subprocess.run(
            [cdk, "--version"], capture_output=True, text=True, timeout=10
        )
        return "✅ " + out.stdout.strip()
    except Exception:  # noqa: BLE001
        return "✅ installed"


# ===========================================================================
# Shared helpers
# ===========================================================================
def _run_with_live_logs(runner: Callable[[Callable[[str], None]], dict]) -> dict:
    """Run a stage function, streaming its output into a live code box."""
    log_box = st.empty()
    buffer: list[str] = []

    def on_line(line: str) -> None:
        buffer.append(line)
        log_box.code("\n".join(buffer[-300:]))

    return runner(on_line)


def _reset_pipeline() -> None:
    st.session_state.pipeline_stage = "idle"
    st.session_state.pipeline_run_id = None
    st.session_state.pipeline_gate_report = None
    st.session_state.pipeline_decision = None
    st.session_state.pipeline_approve_run_id = None
    st.session_state.pipeline_generated_code = ""
    st.session_state.pipeline_logs_generate = ""
    st.session_state.pipeline_logs_deploy = ""
    st.session_state.pipeline_return_code = None
    st.session_state.pipeline_generate_running = False
    st.session_state.pipeline_regate_running = False
    st.session_state.pipeline_deploy_running = False
    st.session_state.pipeline_deploy_done = False
    st.session_state.pipeline_deploy_rc = None
    st.session_state.pop("pipeline_code_editor", None)
    # Hybrid workflow state
    st.session_state.hybrid_run_id = None
    st.session_state.hybrid_report = None
    st.session_state.hybrid_logs = ""
    st.session_state.hybrid_running = False
    st.session_state.hybrid_deploying = False
    st.session_state.hybrid_deploy_done = False
    st.session_state.hybrid_return_code = None
