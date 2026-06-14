"""Main entry point for the Streamlit UI."""
import streamlit as st

from ui.config import configure_page
from ui.sidebar import render_sidebar
from ui.tabs import render_tab1_pipeline, render_tab2_results, render_tab3_exec, render_tab4_cdk


def initialize_session_state():
    """Initialize all session state variables."""
    # Pipeline state
    if "run_results" not in st.session_state:
        st.session_state.run_results = None
    if "is_running" not in st.session_state:
        st.session_state.is_running = False

    # Execution state
    if "exec_results" not in st.session_state:
        st.session_state.exec_results = None
    if "is_executing" not in st.session_state:
        st.session_state.is_executing = False
    if "exec_process" not in st.session_state:
        st.session_state.exec_process = None
    if "exec_terminal_output" not in st.session_state:
        st.session_state.exec_terminal_output = ""
    if "exec_running" not in st.session_state:
        st.session_state.exec_running = False
    if "exec_code_path" not in st.session_state:
        st.session_state.exec_code_path = ""
    if "exec_auto_follow" not in st.session_state:
        st.session_state.exec_auto_follow = True
    if "exec_return_code" not in st.session_state:
        st.session_state.exec_return_code = None
    if "exec_regen_running" not in st.session_state:
        st.session_state.exec_regen_running = False
    if "exec_regen_error" not in st.session_state:
        st.session_state.exec_regen_error = ""
    if "exec_logged" not in st.session_state:
        st.session_state.exec_logged = False
    if "exec_error" not in st.session_state:
        st.session_state.exec_error = ""

    # CDK state
    if "cdk_project_dir" not in st.session_state:
        st.session_state.cdk_project_dir = ""
    if "cdk_process" not in st.session_state:
        st.session_state.cdk_process = None
    if "cdk_terminal_output" not in st.session_state:
        st.session_state.cdk_terminal_output = ""
    if "cdk_running" not in st.session_state:
        st.session_state.cdk_running = False
    if "cdk_auto_follow" not in st.session_state:
        st.session_state.cdk_auto_follow = True
    if "cdk_return_code" not in st.session_state:
        st.session_state.cdk_return_code = None
    if "cdk_command_name" not in st.session_state:
        st.session_state.cdk_command_name = ""
    if "cdk_error" not in st.session_state:
        st.session_state.cdk_error = ""
    if "cdk_prepared" not in st.session_state:
        st.session_state.cdk_prepared = False
    if "cdk_synth_ok" not in st.session_state:
        st.session_state.cdk_synth_ok = False
    if "cdk_diff_ok" not in st.session_state:
        st.session_state.cdk_diff_ok = False
    if "cdk_gate_report" not in st.session_state:
        st.session_state.cdk_gate_report = None
    if "cdk_manual_review_approved" not in st.session_state:
        st.session_state.cdk_manual_review_approved = False
    if "cdk_approval_record_path" not in st.session_state:
        st.session_state.cdk_approval_record_path = None
    if "cdk_rejection_record_path" not in st.session_state:
        st.session_state.cdk_rejection_record_path = None


def main():
    """Main entry point."""
    # Configure page
    configure_page()

    # Initialize session state
    initialize_session_state()

    # Render sidebar and get config
    config = render_sidebar()

    # Main content area
    tab1, tab2, tab3, tab4 = st.tabs(["🚀 Run Pipeline", "📊 View Results", "🖥️ Exec Code", "☁️ CDK Deploy"])

    with tab1:
        render_tab1_pipeline(config)

    with tab2:
        render_tab2_results()

    with tab3:
        render_tab3_exec(config)

    with tab4:
        render_tab4_cdk()

    # Footer
    st.divider()
    st.caption("🧪 Code Generation & Evaluation Pipeline UI | Thesis Research")


if __name__ == "__main__":
    main()
