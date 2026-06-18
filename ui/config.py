"""Paths, constants, and presentation maps for the SysSecOps GUI."""
from __future__ import annotations

from pathlib import Path

# --- Core paths -------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[1]

GENERATED_CDK_DIR = ROOT_DIR / "GeneratedCDK"
GENERATED_CDK_APP = GENERATED_CDK_DIR / "app.py"

LOGS_DIR = ROOT_DIR / "logs"
GATE_REPORTS_DIR = LOGS_DIR / "gate_reports"
CDK_REGEN_DIR = LOGS_DIR / "cdk_regen"
APPROVALS_DIR = LOGS_DIR / "approvals"
REJECTIONS_DIR = LOGS_DIR / "rejections"

README_FILE = ROOT_DIR / "README.md"

# --- Credential storage locations ------------------------------------------
AWS_DIR = Path.home() / ".aws"
AWS_CREDS_PATH = AWS_DIR / "credentials"
AWS_CONFIG_PATH = AWS_DIR / "config"
ENV_FILE = ROOT_DIR / ".env"

# --- Subprocess targets -----------------------------------------------------
REGEN_SCRIPT = ROOT_DIR / "AIgen" / "run_cdk_regen.py"
PIPELINE_SCRIPT = ROOT_DIR / "scripts" / "run_cdk_pipeline.py"

# --- Defaults ---------------------------------------------------------------
DEFAULT_REGION = "ap-southeast-2"
DEFAULT_BEDROCK_MODEL = "anthropic.claude-3-5-sonnet-20240620-v1:0"
DEFAULT_OPENROUTER_MODEL = "anthropic/claude-3.5-sonnet"
PROVIDERS = ["bedrock", "openrouter"]

# --- Gate thresholds (mirrors Eval/iac_security_gate.py) --------------------
GATE_PASS_MAX = 20
GATE_REVIEW_MAX = 80

# --- Presentation maps ------------------------------------------------------
# Gate decision -> (emoji, hex color, human label)
DECISION_STYLE = {
    "pass": ("✅", "#1a7f37", "PASS — safe to deploy"),
    "review": ("⚠️", "#9a6700", "REVIEW — manual approval required"),
    "reject": ("⛔", "#cf222e", "REJECT — remediation required"),
}

# Risk level -> hex color
RISK_COLOR = {
    "low": "#1a7f37",
    "medium": "#9a6700",
    "high": "#bc4c00",
    "critical": "#cf222e",
}

# Finding severity -> hex color
SEVERITY_COLOR = {
    "critical": "#cf222e",
    "high": "#bc4c00",
    "medium": "#9a6700",
    "low": "#1a7f37",
    "info": "#0969da",
    "unknown": "#57606a",
}

# Subprocess exit code -> human meaning
RETURN_CODE_MEANING = {
    0: "Success",
    2: "Project directory not found",
    3: "Gate report not found",
    9: "Bootstrap failed",
    10: "CDK synth failed",
    11: "CDK diff failed",
    12: "CDK deploy failed",
    21: "Gate requires manual review",
    22: "Gate rejected the deployment",
}

# Scanner CLI names for availability checks
SCANNERS = ["checkov", "cfn-lint", "infracost"]

# --- Monitoring (CloudWatch / SSM) ------------------------------------------
CLOUDWATCH_NAMESPACE = "SysSecOps/Gate"
SSM_GATE_PREFIX = "/syssecops/gate"
ALARM_NAME_PREFIX = "syssecops"

# CloudWatch alarm state -> (emoji, hex color)
ALARM_STATE_STYLE = {
    "OK": ("✅", "#1a7f37"),
    "ALARM": ("🚨", "#cf222e"),
    "INSUFFICIENT_DATA": ("❔", "#9a6700"),
}
