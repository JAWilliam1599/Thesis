"""Tab content layouts for the Streamlit UI."""
import json
import time
from pathlib import Path

import streamlit as st

from ui.config import GENERATED_CDK_DIR
from ui.cdk_control import (
    cdk_deploy_allowed,
    get_generated_cdk_source,
    prepare_generated_cdk_project,
    start_cdk_command_from_state,
    refresh_cdk_output_from_state,
    stop_cdk_command_from_state,
    sync_cdk_process_state,
    _on_review_approved_callback,
)
from ui.exec_control import (
    get_attempt_files,
    start_exec_from_state,
    stop_exec_from_state,
    refresh_exec_output_from_state,
    sync_exec_process_state,
    load_saved_prompt,
    build_exec_regen_prompt,
)
from ui.helpers import extract_instructions, format_run_label
from ui.pipeline_runner import run_pipeline_with_prompt
from ui.reports import render_evaluation_report


def render_tab1_pipeline(config):
    """Render Tab 1: Run Pipeline."""
    st.subheader("Generate and Evaluate Python Code")

    # Prompt input
    prompt = st.text_area(
        "Code Generation Prompt",
        placeholder="Describe the Python code you want to generate...",
        height=150,
        help="Provide detailed instructions for the code generation"
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        run_button = st.button(
            "▶️ Run Pipeline",
            use_container_width=True,
            type="primary",
            disabled=not prompt or st.session_state.is_running
        )

    with col2:
        clear_button = st.button(
            "🗑️ Clear Results",
            use_container_width=True,
            disabled=st.session_state.is_running
        )

    with col3:
        view_run_output = st.checkbox("Show Run Output", value=False)

    # Progress area
    if run_button:
        st.session_state.is_running = True
        st.session_state.run_results = None
        st.session_state.exec_results = None

        try:
            with st.spinner("🔄 Running pipeline..."):
                st.session_state.run_results = run_pipeline_with_prompt(
                    prompt_text=prompt,
                    provider=config["provider"],
                    model_id=config["model_id"],
                    region=config["region"],
                    api_key=config["api_key"],
                    fail_below=config["fail_below"],
                    max_regen=config["max_regen"],
                    verbose=config["verbose"],
                    show_run_output=view_run_output,
                )

        except Exception as e:
            st.error(f"❌ Error running pipeline: {str(e)}")

        finally:
            st.session_state.is_running = False

    if clear_button:
        st.session_state.run_results = None
        st.session_state.exec_results = None
        st.rerun()

    # Display results
    if st.session_state.run_results:
        results = st.session_state.run_results
        return_code = results.get("return_code", -1)

        # Status indicator
        if return_code == 0:
            st.success("✅ Pipeline completed successfully!")
        else:
            st.error(f"❌ Pipeline failed with exit code {return_code}")

        # Display generated code and report
        if return_code != 2 and (results.get("generated_code") or results.get("json_output")):
            tab_labels = ["💻 Generated Code", "📘 Instructions", "📋 Evaluation Report"]

            tabs = st.tabs(tab_labels)
            code_tab = tabs[0]
            instructions_tab = tabs[1]
            report_tab = tabs[2]

            with code_tab:
                if results.get("generated_code"):
                    st.code(results["generated_code"], language="python")
                    # Download button
                    st.download_button(
                        "📥 Download Code",
                        data=results["generated_code"],
                        file_name=f"generated_code_{results['timestamp'].replace(':', '')}.py",
                        mime="text/plain"
                    )
                else:
                    st.info("Generated code file not found")

            with instructions_tab:
                instructions_text = results.get("generated_instructions") or ""
                if instructions_text.strip():
                    st.code(instructions_text, language="text")
                else:
                    st.info("No instructions found for this run.")

            with report_tab:
                if results.get("json_output"):
                    render_evaluation_report(results["json_output"])
                else:
                    st.info("No evaluation report available")


def render_tab2_results():
    """Render Tab 2: View Results."""
    st.subheader("Recent Results")

    # List recent run directories
    exec_code_dir = Path(__file__).resolve().parents[1] / "ExecCode"
    run_dirs = sorted(
        [d for d in exec_code_dir.iterdir() if d.is_dir() and d.name.startswith("run_")],
        reverse=True
    )

    if not run_dirs:
        st.info("No runs found yet. Generate some code to see results here!")
    else:
        # Show recent runs
        selected_run = st.selectbox(
            "Select a run to view details",
            options=run_dirs,
            format_func=format_run_label,
        )

        if selected_run:
            st.caption(f"Selected run: {format_run_label(selected_run)}")
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("✅ Passed")
                passed_dir = selected_run / "passed"
                if passed_dir.exists():
                    passed_files = sorted(list(passed_dir.glob("*.json")), reverse=True)
                    if passed_files:
                        for json_file in passed_files:
                            py_file = json_file.with_suffix(".py")
                            report = json.loads(json_file.read_text())

                            with st.expander(f"📋 {json_file.stem}"):
                                code_tab, instructions_tab, report_tab = st.tabs(["💻 Code", "📘 Instructions", "📊 Report"])

                                with code_tab:
                                    if py_file.exists():
                                        code = py_file.read_text(encoding="utf-8")
                                        st.code(code, language="python")
                                        st.download_button(
                                            "📥 Download",
                                            data=code,
                                            file_name=py_file.name,
                                            mime="text/plain",
                                            key=f"download_passed_{py_file.name}"
                                        )
                                    else:
                                        st.warning("Code file not found")

                                with instructions_tab:
                                    instructions_path = py_file.with_suffix(".instructions.txt")
                                    if instructions_path.exists():
                                        st.code(instructions_path.read_text(encoding="utf-8"), language="text")
                                    elif py_file.exists():
                                        st.code(extract_instructions(code), language="text")
                                    else:
                                        st.info("No instructions found for this attempt.")

                                with report_tab:
                                    render_evaluation_report(report)
                    else:
                        st.info("No passed code")
                else:
                    st.info("Passed directory not found")

            with col2:
                st.subheader("❌ Failed")
                failed_dir = selected_run / "failed"
                if failed_dir.exists():
                    failed_files = sorted(list(failed_dir.glob("*.json")), reverse=True)
                    if failed_files:
                        for json_file in failed_files:
                            py_file = json_file.with_suffix(".py")
                            report = json.loads(json_file.read_text())

                            with st.expander(f"📋 {json_file.stem}"):
                                code_tab, instructions_tab, report_tab = st.tabs(["💻 Code", "📘 Instructions", "📊 Report"])

                                with code_tab:
                                    if py_file.exists():
                                        code = py_file.read_text(encoding="utf-8")
                                        st.code(code, language="python")
                                        st.download_button(
                                            "📥 Download",
                                            data=code,
                                            file_name=py_file.name,
                                            mime="text/plain",
                                            key=f"download_failed_{py_file.name}"
                                        )
                                    else:
                                        st.warning("Code file not found")

                                with instructions_tab:
                                    instructions_path = py_file.with_suffix(".instructions.txt")
                                    if instructions_path.exists():
                                        st.code(instructions_path.read_text(encoding="utf-8"), language="text")
                                    elif py_file.exists():
                                        st.code(extract_instructions(code), language="text")
                                    else:
                                        st.info("No instructions found for this attempt.")

                                with report_tab:
                                    render_evaluation_report(report)
                    else:
                        st.info("No failed code")
                else:
                    st.info("Failed directory not found")


def render_tab3_exec(config):
    """Render Tab 3: Execute Code."""
    st.subheader("Execute Generated Code")

    exec_code_dir = Path(__file__).resolve().parents[1] / "ExecCode"
    run_dirs = sorted(
        [d for d in exec_code_dir.iterdir() if d.is_dir() and d.name.startswith("run_")],
        reverse=True,
    )

    if not run_dirs:
        st.info("No runs found yet. Generate some code to see results here!")
    else:
        selected_run = st.selectbox(
            "Select a run",
            options=run_dirs,
            format_func=format_run_label,
            key="exec_run_select",
        )

        attempt_type = st.selectbox(
            "Attempt type",
            options=["passed", "failed"],
            key="exec_attempt_type",
        )

        attempt_map = get_attempt_files(selected_run, attempt_type) if selected_run else {}
        attempt_names = list(attempt_map.keys())

        if not attempt_names:
            st.info(f"No {attempt_type} attempts found for this run.")
        else:
            selected_attempt = st.selectbox(
                "Attempt",
                options=attempt_names,
                key="exec_attempt_select",
            )
            code_path = attempt_map.get(selected_attempt)

            if code_path is not None:
                code_path_str = str(code_path)
                if st.session_state.exec_code_path != code_path_str:
                    st.session_state.exec_code_path = code_path_str
                    st.session_state.exec_terminal_output = ""
                    st.session_state.exec_error = ""
                    st.session_state.exec_return_code = None
                    st.session_state.exec_logged = False

            sync_exec_process_state()

            st.session_state.exec_auto_follow = st.checkbox(
                "Auto-follow output (5s)",
                value=st.session_state.exec_auto_follow,
            )

            button_container = st.container()
            output_placeholder = st.empty()
            if st.session_state.exec_running and st.session_state.exec_auto_follow:
                for _ in range(10):
                    refresh_exec_output_from_state()
                    if st.session_state.exec_terminal_output:
                        output_placeholder.code(st.session_state.exec_terminal_output, language="text")
                    else:
                        output_placeholder.info("No output captured yet.")
                    time.sleep(0.5)

            exec_running = st.session_state.exec_running

            with button_container:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.button(
                        "▶️ Start Execution",
                        use_container_width=True,
                        disabled=exec_running,
                        on_click=start_exec_from_state,
                    )

                with col2:
                    st.button(
                        "🔄 Refresh Output",
                        use_container_width=True,
                        disabled=not exec_running,
                        on_click=refresh_exec_output_from_state,
                    )
                with col3:
                    st.button(
                        "⏹ Stop Execution",
                        use_container_width=True,
                        disabled=not exec_running,
                        on_click=stop_exec_from_state,
                    )

            if exec_running:
                st.success("Execution started.")

            if st.session_state.get("exec_error"):
                st.error(st.session_state.exec_error)

            st.subheader("Terminal Output")
            if st.session_state.exec_terminal_output:
                output_placeholder.code(st.session_state.exec_terminal_output, language="text")
            else:
                output_placeholder.info("No output captured yet.")

            if st.session_state.exec_return_code is not None:
                if st.session_state.exec_return_code == 0:
                    st.success("Execution completed successfully.")
                else:
                    st.error(f"Execution failed with exit code {st.session_state.exec_return_code}.")

                    regen_prompt = ""
                    if code_path is not None:
                        run_dir = code_path.parent.parent
                        saved_prompt = load_saved_prompt(run_dir)
                        if saved_prompt:
                            regen_prompt = build_exec_regen_prompt(
                                saved_prompt,
                                st.session_state.exec_terminal_output,
                            )
                        else:
                            st.warning("Saved prompt not found for this run.")

                    regen_clicked = st.button(
                        "🔁 Regenerate With Error Output",
                        use_container_width=True,
                        disabled=st.session_state.exec_regen_running or not regen_prompt,
                    )

                    if regen_clicked:
                        st.session_state.exec_regen_running = True
                        st.session_state.exec_regen_error = ""
                        try:
                            with st.spinner("Regenerating with error output..."):
                                st.session_state.run_results = run_pipeline_with_prompt(
                                    prompt_text=regen_prompt,
                                    provider=config["provider"],
                                    model_id=config["model_id"],
                                    region=config["region"],
                                    api_key=config["api_key"],
                                    fail_below=config["fail_below"],
                                    max_regen=config["max_regen"],
                                    verbose=config["verbose"],
                                )
                                st.success("Regeneration completed. Check the Run Pipeline tab for results.")
                        except Exception as exc:  # noqa: BLE001
                            st.session_state.exec_regen_error = str(exc)
                            st.error(f"Regeneration failed: {exc}")
                        finally:
                            st.session_state.exec_regen_running = False

            if st.session_state.exec_regen_error:
                st.error(st.session_state.exec_regen_error)

            input_text = st.text_input(
                "Send input to running process",
                key="exec_input_text",
                disabled=not st.session_state.exec_running,
            )
            send_input = st.button(
                "➡️ Send Input",
                use_container_width=True,
                disabled=not st.session_state.exec_running,
            )

            if send_input and st.session_state.exec_process and input_text:
                process = st.session_state.exec_process
                if process.stdin is not None:
                    process.stdin.write(input_text + "\n")
                    process.stdin.flush()
                st.session_state.exec_input_text = ""


def render_tab4_cdk():
    """Render Tab 4: CDK Deploy."""
    st.subheader("Deploy Generated CDK App")
    st.caption("This flow treats the latest generated code as `GeneratedCDK/app.py`. Use prompts that request a self-contained CDK Python app.")

    sync_cdk_process_state()
    has_generated_code = get_generated_cdk_source() is not None
    project_dir = Path(st.session_state.cdk_project_dir) if st.session_state.cdk_project_dir else GENERATED_CDK_DIR

    status_col1, status_col2, status_col3 = st.columns(3)
    with status_col1:
        st.metric("Project", "Ready" if st.session_state.cdk_prepared else "Not prepared")
    with status_col2:
        st.metric("cdk synth", "Passed" if st.session_state.cdk_synth_ok else "Pending")
    with status_col3:
        st.metric("cdk diff", "Passed" if st.session_state.cdk_diff_ok else "Pending")

    st.write(f"Project directory: {project_dir}")

    gate_report = st.session_state.get("cdk_gate_report")
    if gate_report:
        gate_cols = st.columns(3)
        with gate_cols[0]:
            st.metric("Gate Score", gate_report.get("score", 0))
        with gate_cols[1]:
            st.metric("Gate Decision", str(gate_report.get("decision", "unknown")).upper())
        with gate_cols[2]:
            st.metric("Findings", len(gate_report.get("findings", [])))

        st.info(str(gate_report.get("message", "")))

        if str(gate_report.get("decision", "")).lower() == "review":
            st.session_state.cdk_manual_review_approved = st.checkbox(
                "Manual review approved for this run",
                value=st.session_state.cdk_manual_review_approved,
                on_change=_on_review_approved_callback,
                key="_cdk_review_checkbox",
            )
            if st.session_state.get("cdk_approval_record_path"):
                st.caption(f"Approval record: `{st.session_state.cdk_approval_record_path}`")
        if st.session_state.get("cdk_rejection_record_path"):
            st.caption(f"Rejection record: `{st.session_state.cdk_rejection_record_path}`")

        with st.expander("IaC Gate Details"):
            st.json(gate_report)

    if not has_generated_code:
        st.info("Run the pipeline first to prepare a deployable CDK app.")

    st.session_state.cdk_auto_follow = st.checkbox(
        "Auto-follow CDK output (5s)",
        value=st.session_state.cdk_auto_follow,
    )

    action_row = st.container()
    output_placeholder = st.empty()

    if st.session_state.cdk_running and st.session_state.cdk_auto_follow:
        for _ in range(10):
            refresh_cdk_output_from_state()
            if st.session_state.cdk_terminal_output:
                output_placeholder.code(st.session_state.cdk_terminal_output, language="text")
            else:
                output_placeholder.info("No output captured yet.")
            time.sleep(0.5)

    with action_row:
        col1, col2, col3, col4 = st.columns(4)
        can_deploy_now, deploy_reason = cdk_deploy_allowed()
        prepare_clicked = col1.button(
            "📦 Prepare CDK Project",
            use_container_width=True,
            disabled=st.session_state.cdk_running or not has_generated_code,
        )
        synth_clicked = col2.button(
            "🧪 Run cdk synth",
            use_container_width=True,
            disabled=st.session_state.cdk_running or not st.session_state.cdk_prepared,
        )
        diff_clicked = col3.button(
            "📋 Run cdk diff",
            use_container_width=True,
            disabled=(
                st.session_state.cdk_running
                or not st.session_state.cdk_prepared
                or not st.session_state.cdk_synth_ok
            ),
        )
        deploy_clicked = col4.button(
            "☁️ Deploy",
            use_container_width=True,
            type="primary",
            disabled=(
                st.session_state.cdk_running
                or not st.session_state.cdk_prepared
                or not st.session_state.cdk_synth_ok
                or not st.session_state.cdk_diff_ok
                or not can_deploy_now
            ),
        )

    if not can_deploy_now and st.session_state.cdk_synth_ok and st.session_state.cdk_diff_ok:
        st.warning(f"Deploy blocked by risk gate: {deploy_reason}")

    refresh_col, stop_col = st.columns(2)
    refresh_clicked = refresh_col.button(
        "🔄 Refresh CDK Output",
        use_container_width=True,
        disabled=not st.session_state.cdk_running,
    )
    stop_clicked = stop_col.button(
        "⏹ Stop CDK Command",
        use_container_width=True,
        disabled=not st.session_state.cdk_running,
    )

    if prepare_clicked:
        prepared_dir = prepare_generated_cdk_project()
        if prepared_dir is not None:
            st.success(f"Prepared CDK project in {prepared_dir}")

    if synth_clicked:
        start_cdk_command_from_state("synth")

    if diff_clicked:
        start_cdk_command_from_state("diff")

    if deploy_clicked:
        start_cdk_command_from_state("deploy")

    if refresh_clicked:
        refresh_cdk_output_from_state()

    if stop_clicked:
        stop_cdk_command_from_state()

    if st.session_state.cdk_running:
        st.success(f"Running cdk {st.session_state.cdk_command_name}...")

    if st.session_state.cdk_error:
        st.error(st.session_state.cdk_error)

    st.subheader("CDK Command Output")
    if st.session_state.cdk_terminal_output:
        output_placeholder.code(st.session_state.cdk_terminal_output, language="text")
    else:
        output_placeholder.info("No output captured yet.")

    if st.session_state.cdk_return_code is not None:
        command_label = st.session_state.cdk_command_name or "command"
        if st.session_state.cdk_return_code == 0:
            st.success(f"cdk {command_label} completed successfully.")
        else:
            st.error(f"cdk {command_label} failed with exit code {st.session_state.cdk_return_code}.")

    with st.expander("GeneratedCDK Files"):
        if project_dir.exists():
            app_path = project_dir / "app.py"
            cdk_json_path = project_dir / "cdk.json"
            requirements_path = project_dir / "requirements.txt"
            if app_path.exists():
                st.code(app_path.read_text(encoding="utf-8"), language="python")
            if cdk_json_path.exists():
                st.code(cdk_json_path.read_text(encoding="utf-8"), language="json")
            if requirements_path.exists():
                st.code(requirements_path.read_text(encoding="utf-8"), language="text")
        else:
            st.info("GeneratedCDK project has not been prepared yet.")
