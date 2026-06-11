"""Configuration constants and Streamlit page setup."""
import json
from pathlib import Path

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[1]
GENERATED_CDK_DIR = ROOT_DIR / "GeneratedCDK"

CDK_JSON_CONTENT = json.dumps({"app": "../.venv/bin/python app.py"}, indent=2) + "\n"
CDK_REQUIREMENTS_CONTENT = "aws-cdk-lib>=2.0.0\nconstructs>=10.0.0\n"


def configure_page():
    """Configure Streamlit page settings."""
    st.set_page_config(
        page_title="Code Generation & Eval Pipeline",
        page_icon="🔧",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.title("🔧 Code Generation & Evaluation Pipeline")
