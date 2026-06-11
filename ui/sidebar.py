"""Sidebar configuration and provider selection."""
import streamlit as st


def render_sidebar():
    """Render sidebar configuration."""
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
            api_key = None
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

    return {
        "provider": provider,
        "model_id": model_id,
        "region": region,
        "api_key": api_key,
        "fail_below": fail_below,
        "max_regen": max_regen,
        "verbose": verbose,
    }
