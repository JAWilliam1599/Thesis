"""Sidebar: provider configuration and credential status badges."""
from __future__ import annotations

from typing import Any

import streamlit as st

from ui import config, credentials


def render_sidebar() -> dict[str, Any]:
    """Render the sidebar and return the effective pipeline settings."""
    creds = credentials.load_credentials()
    aws_ready = bool(creds.get("access_key") and creds.get("secret_key"))
    openrouter_ready = bool(creds.get("openrouter_key"))

    with st.sidebar:
        st.header("⚙️ Configuration")

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
        provider = st.selectbox(
            "Provider", config.PROVIDERS,
            index=0,
            help="Bedrock uses AWS; OpenRouter uses an API key.",
        )
        default_model = (
            config.DEFAULT_BEDROCK_MODEL if provider == "bedrock"
            else config.DEFAULT_OPENROUTER_MODEL
        )
        model_id = st.text_input("Model ID", value=default_model)
        region = st.text_input(
            "AWS region",
            value=creds.get("region") or config.DEFAULT_REGION,
            disabled=(provider != "bedrock"),
        )
        max_regen_attempts = st.slider(
            "Max regen attempts", min_value=1, max_value=5, value=2,
            help="Auto-retries if the gate rejects the generated code.",
        )

        st.divider()
        st.subheader("Security scanners")
        use_checkov = st.checkbox("Checkov", value=True)
        use_cfn_lint = st.checkbox("cfn-lint", value=True)
        use_infracost = st.checkbox("Infracost", value=True)
        use_aws_config = st.checkbox("AWS Config", value=True)

    return {
        "provider": provider,
        "model_id": model_id,
        "region": region,
        "max_regen_attempts": max_regen_attempts,
        "use_checkov": use_checkov,
        "use_cfn_lint": use_cfn_lint,
        "use_infracost": use_infracost,
        "use_aws_config": use_aws_config,
        "aws_ready": aws_ready,
        "openrouter_ready": openrouter_ready,
    }
