"""Real-time stack monitoring setup via CloudWatch Application Insights and alarms.

Called after a successful `cdk deploy` to attach observability to the deployed
AWS resources automatically.

Two-layer approach:
    Layer 1 — CloudWatch Application Insights (auto-discovery):
        Registers the CloudFormation stack as an Application Insights application
        so AWS auto-discovers EC2, Lambda, RDS, ECS resources and creates
        anomaly-detection dashboards.

    Layer 2 — Explicit CloudWatch alarms per resource type:
        Parses the synthesised CloudFormation template from cdk.out and creates
        targeted metric alarms for known resource types.

Supported resource types for explicit alarms:
    AWS::EC2::Instance   → CPUUtilization > 80%, StatusCheckFailed > 0
    AWS::Lambda::Function → Errors > 0, Throttles > 0
    AWS::RDS::DBInstance → FreeStorageSpace < 10 GB, CPUUtilization > 80%
    AWS::ECS::Service    → CPUUtilization > 80%, MemoryUtilization > 80%

All alarm actions fire to SNS_TOPIC_ARN (same topic as gate notifications).

Configuration via environment variables:
    SNS_TOPIC_ARN      — alarm action target (alarms created without action if unset)
    AWS_DEFAULT_REGION — region for all boto3 clients (falls back to us-east-1)
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")

# Explicit alarm definitions per resource type
# Format: (MetricName, Namespace, Statistic, Threshold, ComparisonOperator, Unit)
_ALARM_SPECS: dict[str, list[tuple[str, str, str, float, str, str]]] = {
    "AWS::EC2::Instance": [
        ("CPUUtilization", "AWS/EC2", "Average", 80.0, "GreaterThanOrEqualToThreshold", "Percent"),
        ("StatusCheckFailed", "AWS/EC2", "Maximum", 1.0, "GreaterThanOrEqualToThreshold", "Count"),
    ],
    "AWS::Lambda::Function": [
        ("Errors", "AWS/Lambda", "Sum", 1.0, "GreaterThanOrEqualToThreshold", "Count"),
        ("Throttles", "AWS/Lambda", "Sum", 1.0, "GreaterThanOrEqualToThreshold", "Count"),
    ],
    "AWS::RDS::DBInstance": [
        ("FreeStorageSpace", "AWS/RDS", "Average", 10_737_418_240.0, "LessThanOrEqualToThreshold", "Bytes"),
        ("CPUUtilization", "AWS/RDS", "Average", 80.0, "GreaterThanOrEqualToThreshold", "Percent"),
    ],
    "AWS::ECS::Service": [
        ("CPUUtilization", "AWS/ECS", "Average", 80.0, "GreaterThanOrEqualToThreshold", "Percent"),
        ("MemoryUtilization", "AWS/ECS", "Average", 80.0, "GreaterThanOrEqualToThreshold", "Percent"),
    ],
}

# Dimension key per resource type used in metric alarms
_DIMENSION_KEY: dict[str, str] = {
    "AWS::EC2::Instance": "InstanceId",
    "AWS::Lambda::Function": "FunctionName",
    "AWS::RDS::DBInstance": "DBInstanceIdentifier",
    "AWS::ECS::Service": "ServiceName",
}


def _get_region() -> str:
    return (
        os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("CDK_DEFAULT_REGION")
        or "us-east-1"
    )


def _get_client(service: str):
    """Return a boto3 service client using the shared aws_credentials session."""
    from pipeline.aws_credentials import get_session

    session = get_session()
    if session is not None:
        return session.client(service)
    import boto3
    return boto3.client(service, region_name=_get_region())


def _find_template(stack_name: str, cdk_out_dir: Path) -> dict[str, Any] | None:
    """Locate and parse the CloudFormation template for the stack."""
    candidate = cdk_out_dir / f"{stack_name}.template.json"
    if candidate.exists():
        try:
            return json.loads(candidate.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("stack_monitor: failed to parse template %s — %s", candidate, exc)
            return None

    # Fall back: search for any template containing the stack name
    for path in cdk_out_dir.glob("*.template.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data
        except Exception:
            continue
    return None


def _register_application_insights(stack_name: str) -> None:
    """Register the stack with CloudWatch Application Insights (Layer 1).

    Creates a tag-based resource group for all resources tagged with the CDK
    stack name, then registers it as an Application Insights application.
    Never raises.
    """
    try:
        rg_client = _get_client("resource-groups")
        ai_client = _get_client("application-insights")

        resource_group_name = f"syssecops-{stack_name}"

        # Use TAG_FILTERS_1_0 — matches all resources CDK tagged with the stack name.
        # CLOUDFORMATION_STACK_1_0 is rejected by the API for IAM users.
        tag_query = json.dumps({
            "ResourceTypeFilters": ["AWS::AllSupported"],
            "TagFilters": [{"Key": "aws:cloudformation:stack-name", "Values": [stack_name]}],
        })
        group_created = False
        try:
            rg_client.create_group(
                Name=resource_group_name,
                ResourceQuery={"Type": "TAG_FILTERS_1_0", "Query": tag_query},
            )
            logger.info("Application Insights: created resource group %r", resource_group_name)
            group_created = True
        except Exception as exc:
            err_code = ""
            if hasattr(exc, "response"):
                err_code = exc.response.get("Error", {}).get("Code", "")  # type: ignore[union-attr]
            if err_code in ("BadRequestException", "ConflictException"):
                logger.debug("Application Insights: resource group %r already exists", resource_group_name)
                group_created = True
            else:
                logger.warning(
                    "Application Insights: resource group creation failed for %r — %s",
                    resource_group_name, exc,
                )

        if not group_created:
            return  # don't call create_application on a non-existent group

        # Register Application Insights application
        try:
            ai_client.create_application(
                ResourceGroupName=resource_group_name,
                AutoConfigEnabled=True,
                OpsCenterEnabled=False,
            )
            logger.info(
                "Application Insights: registered application for stack=%r group=%r",
                stack_name,
                resource_group_name,
            )
        except ai_client.exceptions.ResourceInUseException:
            logger.info(
                "Application Insights: application already exists for group=%r", resource_group_name
            )
        except Exception as exc:
            logger.warning(
                "Application Insights: create_application failed for %r — %s",
                resource_group_name,
                exc,
            )
    except Exception as exc:
        logger.warning("Application Insights: setup failed for stack=%r — %s", stack_name, exc)


def _create_explicit_alarms(stack_name: str, template: dict[str, Any]) -> None:
    """Create targeted CloudWatch alarms per resource type found in the template (Layer 2).

    Never raises.
    """
    resources: dict[str, dict[str, Any]] = template.get("Resources", {})
    if not resources:
        return

    alarm_actions = [_SNS_TOPIC_ARN] if _SNS_TOPIC_ARN else []

    try:
        cw_client = _get_client("cloudwatch")

        for logical_id, resource in resources.items():
            resource_type = resource.get("Type", "")
            specs = _ALARM_SPECS.get(resource_type)
            if not specs:
                continue

            dimension_key = _DIMENSION_KEY.get(resource_type, "ResourceId")

            for metric_name, namespace, statistic, threshold, comparison_op, unit in specs:
                alarm_name = f"syssecops-{stack_name}-{logical_id}-{metric_name}"
                try:
                    cw_client.put_metric_alarm(
                        AlarmName=alarm_name,
                        AlarmDescription=(
                            f"SysSecOps auto-alarm: {metric_name} on {resource_type} "
                            f"{logical_id} in stack {stack_name}"
                        ),
                        Namespace=namespace,
                        MetricName=metric_name,
                        Dimensions=[{"Name": dimension_key, "Value": logical_id}],
                        Statistic=statistic,
                        Period=300,  # 5-minute evaluation window
                        EvaluationPeriods=1,
                        Threshold=threshold,
                        ComparisonOperator=comparison_op,
                        Unit=unit,
                        TreatMissingData="notBreaching",
                        AlarmActions=alarm_actions,
                        OKActions=alarm_actions,
                    )
                    logger.info(
                        "CloudWatch alarm created: %r for %s.%s",
                        alarm_name,
                        resource_type,
                        logical_id,
                    )
                except Exception as exc:
                    logger.warning(
                        "CloudWatch: failed to create alarm %r — %s", alarm_name, exc
                    )
    except Exception as exc:
        logger.warning(
            "CloudWatch: _create_explicit_alarms failed for stack=%r — %s", stack_name, exc
        )


def setup_stack_monitoring(stack_name: str, cdk_out_dir: Path) -> None:
    """Attach real-time CloudWatch monitoring to a deployed CDK stack.

    Runs Layer 1 (Application Insights auto-discovery) and Layer 2 (explicit
    alarms from parsed template) in sequence.  Never raises — all failures are
    logged as warnings so a monitoring setup issue never blocks the pipeline.

    Args:
        stack_name:  Name of the CloudFormation stack (also used as resource group name).
        cdk_out_dir: Path to the CDK output directory (GeneratedCDK/cdk.out).
    """
    logger.info("stack_monitor: setting up monitoring for stack=%r", stack_name)

    # Layer 1 — Application Insights
    _register_application_insights(stack_name)

    # Layer 2 — Explicit alarms from template
    template = _find_template(stack_name, Path(cdk_out_dir))
    if template:
        _create_explicit_alarms(stack_name, template)
    else:
        logger.warning(
            "stack_monitor: no template found for stack=%r in %s; skipping explicit alarms",
            stack_name,
            cdk_out_dir,
        )


def teardown_stack_monitoring(stack_name: str) -> None:
    """Remove CloudWatch Application Insights registration for a destroyed stack.

    Optional cleanup — never raises.
    """
    resource_group_name = f"syssecops-{stack_name}"
    try:
        client = _get_client("application-insights")
        client.delete_application(ResourceGroupName=resource_group_name)
        logger.info(
            "Application Insights: deleted application for group=%r", resource_group_name
        )
    except Exception as exc:
        logger.warning(
            "Application Insights: teardown failed for stack=%r — %s", stack_name, exc
        )
