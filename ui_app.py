"""
Simple Streamlit UI for Code Generation and Evaluation Pipeline
"""
import importlib.util
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

# Configure Streamlit page
st.set_page_config(
    page_title="Code Generation & Eval Pipeline",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🔧 Code Generation & Evaluation Pipeline")


def load_run_generation_module():
    """Dynamically load the run_generation_and_eval module"""
    run_gen_file = Path(__file__).resolve().parent / "AIgen" / "run_generation_and_eval.py"
    spec = importlib.util.spec_from_file_location("run_generation_and_eval", run_gen_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load run_generation_and_eval module from {run_gen_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract_json_report(output_text: str) -> dict | None:
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


def format_report_value(value):
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, (list, tuple, set)):
        return str(len(value))
    if isinstance(value, dict):
        return f"{len(value)} items"
    return str(value)


def render_report_field(label, value, description, source):
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


def format_run_label(run_dir: Path) -> str:
    run_name = run_dir.name
    if not run_name.startswith("run_"):
        return run_name

    timestamp_text = run_name[len("run_"):]
    try:
        parsed = datetime.strptime(timestamp_text, "%Y%m%dT%H%M%S%fZ")
        return f"{run_name} | {parsed.strftime('%Y-%m-%d %H:%M:%S UTC')}"
    except ValueError:
        return run_name


def render_evaluation_report(report: dict) -> None:
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
        render_report_field(
            "Boto3 Import Detected",
            report.get("imports_boto3"),
            "Whether the code imports boto3 or from boto3.",
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


# Initialize session state
if "run_results" not in st.session_state:
    st.session_state.run_results = None
if "is_running" not in st.session_state:
    st.session_state.is_running = False


# Sidebar configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    provider = st.selectbox(
        "Model Provider",
        options=["bedrock", "openrouter"],
        help="Choose between AWS Bedrock or OpenRouter for code generation"
    )
    
    if provider == "bedrock":
        model_id = st.text_input(
            "Model ID",
            value="anthropic.claude-3-5-sonnet-20241022-v2:0",
            help="Default Claude 3.5 Sonnet model ID"
        )
        region = st.text_input(
            "AWS Region",
            value="us-east-1",
            help="AWS region for Bedrock runtime"
        )
    else:
        model_id = st.text_input(
            "Model ID",
            value="qwen/qwen3-coder-30b-a3b-instruct",
            help="Qwen3 Coder model ID for OpenRouter"
        )
        api_key = st.text_input(
            "API Key",
            type="password",
            help="OpenRouter API key (or set OPENROUTER_API_KEY env var)"
        )
        region = None
    
    st.divider()
    
    fail_below = st.slider(
        "Fail Below Score",
        min_value=0,
        max_value=100,
        value=60,
        help="Pipeline fails if eval score is below this value"
    )
    
    max_regen = st.slider(
        "Max Regeneration Attempts",
        min_value=0,
        max_value=5,
        value=2,
        help="Number of auto-regeneration retries after failed evaluation"
    )
    
    verbose = st.checkbox("Verbose Logging", value=False, help="Show detailed runtime logs")


# Main content area
tab1, tab2 = st.tabs(["🚀 Run Pipeline", "📊 View Results"])

with tab1:
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
        view_logs = st.checkbox("Show Logs", value=False)
    
    # Progress area
    if run_button:
        st.session_state.is_running = True
        st.session_state.run_results = None
        
        try:
            with st.spinner("🔄 Running pipeline..."):
                # Build command
                root_dir = Path(__file__).resolve().parent
                cmd = [
                    sys.executable,
                    "-u",
                    str(root_dir / "AIgen" / "run_generation_and_eval.py"),
                    "--provider", provider,
                    "--prompt", prompt,
                    "--fail-below", str(fail_below),
                    "--max-regen", str(max_regen),
                ]
                env = os.environ.copy()
                
                if provider == "bedrock":
                    if region:
                        cmd.extend(["--region", region])
                    if model_id:
                        cmd.extend(["--model-id", model_id])
                else:
                    if model_id:
                        cmd.extend(["--model-id", model_id])
                    api_key_input = (api_key or "").strip()
                    env_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
                    if api_key_input:
                        env["OPENROUTER_API_KEY"] = api_key_input
                    elif not env_api_key:
                        st.warning("API Key field is empty and OPENROUTER_API_KEY is not set.")
                
                if verbose:
                    cmd.append("--verbose")

                env["PYTHONUNBUFFERED"] = "1"

                live_status = st.empty()
                live_log = st.empty()
                live_status.info("Streaming pipeline output in real time...")

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(root_dir / "AIgen"),
                    env=env,
                    bufsize=1,
                )

                stdout_lines = []
                if process.stdout is not None:
                    for line in iter(process.stdout.readline, ""):
                        stdout_lines.append(line)
                        live_log.code("".join(stdout_lines[-400:]), language="text")
                    process.stdout.close()

                return_code = process.wait()
                combined_output = "".join(stdout_lines)
                
                # Parse results
                json_output = extract_json_report(combined_output)
                
                # Try to find the generated code file
                generated_code = None
                generated_code_path = root_dir / "ExecCode" / "generated_code.py"
                if generated_code_path.exists():
                    generated_code = generated_code_path.read_text(encoding="utf-8")
                
                st.session_state.run_results = {
                    "return_code": return_code,
                    "stdout": combined_output,
                    "stderr": "",
                    "json_output": json_output,
                    "generated_code": generated_code,
                    "timestamp": datetime.now().isoformat(),
                }
        
        except Exception as e:
            st.error(f"❌ Error running pipeline: {str(e)}")
        
        finally:
            st.session_state.is_running = False
    
    if clear_button:
        st.session_state.run_results = None
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
        if results.get("generated_code") or results.get("json_output"):
            # Create tabs for code and report
            code_tab, report_tab = st.tabs(["💻 Generated Code", "📋 Evaluation Report"])
            
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
            
            with report_tab:
                if results.get("json_output"):
                    render_evaluation_report(results["json_output"])
                else:
                    st.info("No evaluation report available")
        
        # Display logs if requested
        if view_logs:
            st.subheader("📋 Output Logs")
            
            if results.get("stdout"):
                st.write("**STDOUT:**")
                st.code(results["stdout"], language="text")
            
            if results.get("stderr"):
                st.write("**STDERR:**")
                st.code(results["stderr"], language="text")


with tab2:
    st.subheader("Recent Results")
    
    # List recent run directories
    exec_code_dir = Path(__file__).resolve().parent / "ExecCode"
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
                                # Tabs for code and report
                                code_tab, report_tab = st.tabs(["💻 Code", "📊 Report"])
                                
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
                                # Tabs for code and report
                                code_tab, report_tab = st.tabs(["💻 Code", "📊 Report"])
                                
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
                                
                                with report_tab:
                                    render_evaluation_report(report)
                    else:
                        st.info("No failed code")
                else:
                    st.info("Failed directory not found")


# Footer
st.divider()
st.caption("🧪 Code Generation & Evaluation Pipeline UI | Thesis Research")
