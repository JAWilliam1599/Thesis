"""Real-time stack monitoring setup via CloudWatch Application Insights and alarms.

Called after a successful `cdk deploy` to attach observability to the deployed
AWS resources automatically.

Three-layer approach:
    Layer 1 — CloudWatch Application Insights (auto-discovery):
        Registers the CloudFormation stack as an Application Insights application
        so AWS auto-discovers EC2, Lambda, RDS, ECS resources and creates
        anomaly-detection dashboards.

    Layer 2 — Explicit CloudWatch alarms per resource type:
        Parses the synthesised CloudFormation template from cdk.out and creates
        targeted metric alarms — both operational and security-focused.

        Operational: EC2 CPU/status, Lambda errors/throttles, RDS storage/CPU,
                     ECS CPU/memory.
        Security:    EC2 network packet spike, Lambda duration/concurrency abuse,
                     RDS connection flood, S3 4xx/5xx request errors.

    Layer 3 — CloudTrail + VPC flow log metric filter alarms:
        3a CloudTrail: 7 CIS-aligned alarms (unauthorized calls, root usage,
                       IAM policy changes, SG changes, S3 policy changes,
                       CloudTrail tampering, console auth failures).
        3b VPC flow:   REJECT flood + SSH/RDP-from-internet alarms created on
                       flow log groups for any VPC in the CDK template.
                       Skips silently if no VPCs or no flow logs.

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
        # Operational
        ("CPUUtilization", "AWS/EC2", "Average", 80.0, "GreaterThanOrEqualToThreshold", "Percent"),
        ("StatusCheckFailed", "AWS/EC2", "Maximum", 1.0, "GreaterThanOrEqualToThreshold", "Count"),
        # Security: sudden network packet spike indicates port scan or DDoS
        ("NetworkPacketsIn", "AWS/EC2", "Sum", 1_000_000.0, "GreaterThanOrEqualToThreshold", "Count"),
    ],
    "AWS::Lambda::Function": [
        # Operational
        ("Errors", "AWS/Lambda", "Sum", 1.0, "GreaterThanOrEqualToThreshold", "Count"),
        ("Throttles", "AWS/Lambda", "Sum", 1.0, "GreaterThanOrEqualToThreshold", "Count"),
        # Security: near-timeout execution = DoS/timeout exhaustion; concurrency spike = resource abuse
        ("Duration", "AWS/Lambda", "Maximum", 720_000.0, "GreaterThanOrEqualToThreshold", "Milliseconds"),
        ("ConcurrentExecutions", "AWS/Lambda", "Maximum", 50.0, "GreaterThanOrEqualToThreshold", "Count"),
    ],
    "AWS::RDS::DBInstance": [
        # Operational
        ("FreeStorageSpace", "AWS/RDS", "Average", 10_737_418_240.0, "LessThanOrEqualToThreshold", "Bytes"),
        ("CPUUtilization", "AWS/RDS", "Average", 80.0, "GreaterThanOrEqualToThreshold", "Percent"),
        # Security: connection flood indicates brute-force or application-layer attack
        ("DatabaseConnections", "AWS/RDS", "Maximum", 100.0, "GreaterThanOrEqualToThreshold", "Count"),
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


def _create_s3_security_alarms(stack_name: str, template: dict[str, Any]) -> None:
    """Layer 2 (S3) — enable request metrics and create 4xx/5xx security alarms.

    Enables CloudWatch request metrics on each S3 bucket in the template, then
    creates alarms for access errors that indicate unauthorized access or injection
    attempts.  Resolves the physical bucket name via CloudFormation.
    Never raises.
    """
    resources = template.get("Resources", {})
    s3_logical_ids = [
        lid for lid, r in resources.items() if r.get("Type") == "AWS::S3::Bucket"
    ]
    if not s3_logical_ids:
        return

    _METRICS_FILTER_ID = "EntireBucket"
    _S3_ALARM_SPECS = [
        ("4xxErrors", 10.0, "GreaterThanOrEqualToThreshold", "Unauthorized or forbidden S3 access attempts"),
        ("5xxErrors", 5.0, "GreaterThanOrEqualToThreshold", "S3 server errors — possible injection or misconfiguration"),
    ]
    alarm_actions = [_SNS_TOPIC_ARN] if _SNS_TOPIC_ARN else []

    try:
        cfn_client = _get_client("cloudformation")
        s3_client = _get_client("s3")
        cw_client = _get_client("cloudwatch")

        for logical_id in s3_logical_ids:
            # Resolve physical bucket name from CloudFormation
            try:
                resp = cfn_client.describe_stack_resource(
                    StackName=stack_name, LogicalResourceId=logical_id
                )
                bucket_name = resp["StackResourceDetail"]["PhysicalResourceId"]
            except Exception as exc:
                logger.warning(
                    "S3 security alarms: could not resolve bucket %r in stack %r — %s",
                    logical_id, stack_name, exc,
                )
                continue

            # Enable request metrics so 4xx/5xx CloudWatch metrics are generated
            try:
                s3_client.put_bucket_metrics_configuration(
                    Bucket=bucket_name,
                    Id=_METRICS_FILTER_ID,
                    MetricsConfiguration={"Id": _METRICS_FILTER_ID},
                )
                logger.debug("S3: enabled request metrics on bucket %r", bucket_name)
            except Exception as exc:
                logger.warning(
                    "S3: could not enable request metrics on bucket %r — %s", bucket_name, exc
                )
                continue

            for metric_name, threshold, comparison_op, description in _S3_ALARM_SPECS:
                alarm_name = f"syssecops-{stack_name}-{logical_id}-{metric_name}"
                try:
                    cw_client.put_metric_alarm(
                        AlarmName=alarm_name,
                        AlarmDescription=(
                            f"SysSecOps S3 security: {description} "
                            f"— bucket={bucket_name} stack={stack_name}"
                        ),
                        Namespace="AWS/S3",
                        MetricName=metric_name,
                        Dimensions=[
                            {"Name": "BucketName", "Value": bucket_name},
                            {"Name": "FilterId", "Value": _METRICS_FILTER_ID},
                        ],
                        Statistic="Sum",
                        Period=300,
                        EvaluationPeriods=1,
                        Threshold=threshold,
                        ComparisonOperator=comparison_op,
                        TreatMissingData="notBreaching",
                        AlarmActions=alarm_actions,
                        OKActions=alarm_actions,
                    )
                    logger.info(
                        "S3 security alarm created: %r for bucket=%r",
                        alarm_name, bucket_name,
                    )
                except Exception as exc:
                    logger.warning("S3: failed to create alarm %r — %s", alarm_name, exc)

    except Exception as exc:
        logger.warning(
            "S3: _create_s3_security_alarms failed for stack=%r — %s", stack_name, exc
        )


def _setup_vpc_flow_log_alarms(stack_name: str, template: dict[str, Any]) -> None:
    """Layer 3b — VPC flow log metric filter alarms.

    Auto-detects VPC resources in the CDK template, looks up their CloudWatch
    flow log groups via EC2, then creates metric filters and alarms for:
        VPCFlowRejects     — REJECT action count >= 100/5min (port scan / mass connection)
        SSHRDPFromInternet — port 22 or 3389 traffic >= 1/5min

    Metric namespace: SysSecOps/VPCFlowLogs
    Silently skips if no VPCs are in the template or no CloudWatch flow logs exist.
    Never raises.
    """
    resources = template.get("Resources", {})
    vpc_logical_ids = [
        lid for lid, r in resources.items() if r.get("Type") == "AWS::EC2::VPC"
    ]
    if not vpc_logical_ids:
        logger.debug(
            "VPC flow alarms: no VPC resources in template for stack=%r — skipping", stack_name
        )
        return

    _METRIC_NAMESPACE = "SysSecOps/VPCFlowLogs"
    _VPC_FLOW_FILTERS = [
        (
            "VPCFlowRejects",
            "[version, account, eni, source, destination, srcport, destport, protocol, packets, bytes, windowstart, windowend, action=REJECT, flowlogstatus]",
            100.0,
            "GreaterThanOrEqualToThreshold",
            "High volume of rejected connections — possible port scan or DDoS",
        ),
        (
            "SSHRDPFromInternet",
            "[version, account, eni, source, destination, srcport, destport=22||destport=3389, protocol=6, packets, bytes, windowstart, windowend, action=ACCEPT, flowlogstatus]",
            1.0,
            "GreaterThanOrEqualToThreshold",
            "SSH or RDP access from the internet detected",
        ),
    ]
    alarm_actions = [_SNS_TOPIC_ARN] if _SNS_TOPIC_ARN else []

    try:
        cfn_client = _get_client("cloudformation")
        ec2_client = _get_client("ec2")
        logs_client = _get_client("logs")
        cw_client = _get_client("cloudwatch")

        for logical_id in vpc_logical_ids:
            # Resolve physical VPC ID
            try:
                resp = cfn_client.describe_stack_resource(
                    StackName=stack_name, LogicalResourceId=logical_id
                )
                vpc_id = resp["StackResourceDetail"]["PhysicalResourceId"]
            except Exception as exc:
                logger.warning(
                    "VPC flow alarms: could not resolve VPC %r in stack %r — %s",
                    logical_id, stack_name, exc,
                )
                continue

            # Find CloudWatch flow logs for this VPC
            try:
                fl_resp = ec2_client.describe_flow_logs(
                    Filters=[
                        {"Name": "resource-id", "Values": [vpc_id]},
                        {"Name": "log-destination-type", "Values": ["cloud-watch-logs"]},
                    ]
                )
                flow_logs = fl_resp.get("FlowLogs", [])
            except Exception as exc:
                logger.warning(
                    "VPC flow alarms: describe_flow_logs failed for VPC=%r — %s", vpc_id, exc
                )
                continue

            if not flow_logs:
                logger.info(
                    "VPC flow alarms: no CloudWatch flow logs configured for VPC=%r — skipping",
                    vpc_id,
                )
                continue

            log_group_name = flow_logs[0].get("LogGroupName", "")
            if not log_group_name:
                # Some flow logs store destination as an ARN; extract the group name
                dest = flow_logs[0].get("LogDestination", "")
                log_group_name = dest.split(":")[-1] if ":" in dest else dest
            if not log_group_name:
                logger.warning(
                    "VPC flow alarms: cannot determine log group for VPC=%r", vpc_id
                )
                continue

            logger.info(
                "VPC flow alarms: attaching alarms to log group %r for VPC=%r",
                log_group_name, vpc_id,
            )

            for metric_name, filter_pattern, threshold, comparison_op, description in _VPC_FLOW_FILTERS:
                filter_name = f"syssecops-{stack_name}-{logical_id}-{metric_name}"
                alarm_name = f"syssecops-{stack_name}-{logical_id}-{metric_name}"

                try:
                    logs_client.put_metric_filter(
                        logGroupName=log_group_name,
                        filterName=filter_name,
                        filterPattern=filter_pattern,
                        metricTransformations=[{
                            "metricName": metric_name,
                            "metricNamespace": _METRIC_NAMESPACE,
                            "metricValue": "1",
                            "defaultValue": 0,
                            "unit": "Count",
                        }],
                    )
                    logger.debug("VPC flow: upserted metric filter %r", filter_name)
                except Exception as exc:
                    logger.warning(
                        "VPC flow: failed to put metric filter %r — %s", filter_name, exc
                    )
                    continue

                try:
                    cw_client.put_metric_alarm(
                        AlarmName=alarm_name,
                        AlarmDescription=(
                            f"SysSecOps VPC flow: {description} — VPC={vpc_id} stack={stack_name}"
                        ),
                        Namespace=_METRIC_NAMESPACE,
                        MetricName=metric_name,
                        Statistic="Sum",
                        Period=300,
                        EvaluationPeriods=1,
                        Threshold=threshold,
                        ComparisonOperator=comparison_op,
                        TreatMissingData="notBreaching",
                        AlarmActions=alarm_actions,
                        OKActions=alarm_actions,
                    )
                    logger.info(
                        "VPC flow alarm created/updated: %r for VPC=%r",
                        alarm_name, vpc_id,
                    )
                except Exception as exc:
                    logger.warning("VPC flow: failed to put alarm %r — %s", alarm_name, exc)

    except Exception as exc:
        logger.warning(
            "VPC flow: _setup_vpc_flow_log_alarms failed for stack=%r — %s", stack_name, exc
        )


def _setup_cloudtrail_security_alarms(stack_name: str) -> None:
    """Layer 3 — Create CloudWatch metric filter alarms on the CloudTrail log group.

    Detects the log group by checking whether the SysSecOpsCloudTrailStack log
    group (/aws/cloudtrail/syssecops) exists.  Silently skips if the stack has
    not been deployed yet.

    Alarms created (CIS AWS Foundations Benchmark-aligned):
        UnauthorizedAPICalls    — AccessDenied / UnauthorizedAccess errors
        RootAccountUsage        — any activity from the root account
        IAMPolicyChanges        — CreatePolicy, AttachRolePolicy, DeletePolicy, etc.
        SecurityGroupChanges    — AuthorizeSecurityGroupIngress/Egress, Revoke*, etc.
        S3BucketPolicyChanges   — PutBucketPolicy, DeleteBucketPolicy
        CloudTrailChanges       — StopLogging, DeleteTrail, UpdateTrail
        ConsoleAuthFailures     — ConsoleLogin with Failed authentication result

    All alarms fire to SNS_TOPIC_ARN when triggered.  Alarm names are prefixed
    with syssecops-{stack_name}- for consistency with Layer 2 alarms.
    Never raises.
    """
    _LOG_GROUP = "/aws/cloudtrail/syssecops"
    _METRIC_NAMESPACE = "SysSecOps/CloudTrailSecurity"

    # Security metric filter definitions:
    # (metric_name, filter_pattern, threshold, comparison_operator, description)
    _SECURITY_FILTERS: list[tuple[str, str, float, str, str]] = [
        (
            "UnauthorizedAPICalls",
            '{ ($.errorCode = "AccessDenied") || ($.errorCode = "UnauthorizedAccess") }',
            5.0,
            "GreaterThanOrEqualToThreshold",
            "Unauthorized API calls — possible credential compromise or misconfiguration",
        ),
        (
            "RootAccountUsage",
            '{ $.userIdentity.type = "Root" && $.userIdentity.invokedBy NOT EXISTS && $.eventType != "AwsServiceEvent" }',
            1.0,
            "GreaterThanOrEqualToThreshold",
            "Root account activity — should never occur in normal operations",
        ),
        (
            "IAMPolicyChanges",
            '{ ($.eventName = CreatePolicy) || ($.eventName = DeletePolicy) || ($.eventName = AttachRolePolicy) || ($.eventName = DetachRolePolicy) || ($.eventName = PutRolePolicy) || ($.eventName = DeleteRolePolicy) || ($.eventName = AttachUserPolicy) || ($.eventName = DetachUserPolicy) || ($.eventName = AttachGroupPolicy) || ($.eventName = DetachGroupPolicy) }',
            1.0,
            "GreaterThanOrEqualToThreshold",
            "IAM policy change detected",
        ),
        (
            "SecurityGroupChanges",
            '{ ($.eventName = AuthorizeSecurityGroupIngress) || ($.eventName = AuthorizeSecurityGroupEgress) || ($.eventName = RevokeSecurityGroupIngress) || ($.eventName = RevokeSecurityGroupEgress) || ($.eventName = CreateSecurityGroup) || ($.eventName = DeleteSecurityGroup) }',
            1.0,
            "GreaterThanOrEqualToThreshold",
            "Security group rule change detected",
        ),
        (
            "S3BucketPolicyChanges",
            '{ ($.eventName = PutBucketAcl) || ($.eventName = PutBucketPolicy) || ($.eventName = DeleteBucketPolicy) || ($.eventName = PutBucketCors) || ($.eventName = PutBucketLifecycle) || ($.eventName = PutBucketReplication) || ($.eventName = DeleteBucketCors) }',
            1.0,
            "GreaterThanOrEqualToThreshold",
            "S3 bucket policy or ACL change detected",
        ),
        (
            "CloudTrailChanges",
            '{ ($.eventName = CreateTrail) || ($.eventName = UpdateTrail) || ($.eventName = DeleteTrail) || ($.eventName = StartLogging) || ($.eventName = StopLogging) }',
            1.0,
            "GreaterThanOrEqualToThreshold",
            "CloudTrail configuration change — audit logging may be at risk",
        ),
        (
            "ConsoleAuthFailures",
            '{ ($.eventName = ConsoleLogin) && ($.errorMessage = "Failed authentication") }',
            3.0,
            "GreaterThanOrEqualToThreshold",
            "Multiple console login failures — possible brute-force attempt",
        ),
    ]

    try:
        logs_client = _get_client("logs")
        cw_client = _get_client("cloudwatch")

        # Check if the CloudTrail log group exists
        try:
            resp = logs_client.describe_log_groups(logGroupNamePrefix=_LOG_GROUP)
            groups = [g for g in resp.get("logGroups", []) if g["logGroupName"] == _LOG_GROUP]
            if not groups:
                logger.info(
                    "CloudTrail security alarms: log group %r not found — "
                    "deploy SysSecOpsCloudTrailStack to activate Layer 3 alarms",
                    _LOG_GROUP,
                )
                return
        except Exception as exc:
            logger.warning("CloudTrail security alarms: could not check log group — %s", exc)
            return

        alarm_actions = [_SNS_TOPIC_ARN] if _SNS_TOPIC_ARN else []

        for metric_name, filter_pattern, threshold, comparison_op, description in _SECURITY_FILTERS:
            filter_name = f"syssecops-{stack_name}-{metric_name}"
            alarm_name = f"syssecops-{stack_name}-{metric_name}"

            # Create or update the metric filter
            try:
                logs_client.put_metric_filter(
                    logGroupName=_LOG_GROUP,
                    filterName=filter_name,
                    filterPattern=filter_pattern,
                    metricTransformations=[{
                        "metricName": metric_name,
                        "metricNamespace": _METRIC_NAMESPACE,
                        "metricValue": "1",
                        "defaultValue": 0,
                        "unit": "Count",
                    }],
                )
                logger.debug("CloudTrail: upserted metric filter %r", filter_name)
            except Exception as exc:
                logger.warning("CloudTrail: failed to put metric filter %r — %s", filter_name, exc)
                continue

            # Create or update the alarm on that metric
            try:
                cw_client.put_metric_alarm(
                    AlarmName=alarm_name,
                    AlarmDescription=f"SysSecOps CloudTrail security: {description}",
                    Namespace=_METRIC_NAMESPACE,
                    MetricName=metric_name,
                    Statistic="Sum",
                    Period=300,
                    EvaluationPeriods=1,
                    Threshold=threshold,
                    ComparisonOperator=comparison_op,
                    TreatMissingData="notBreaching",
                    AlarmActions=alarm_actions,
                    OKActions=alarm_actions,
                )
                logger.info("CloudTrail security alarm created/updated: %r", alarm_name)
            except Exception as exc:
                logger.warning("CloudTrail: failed to put alarm %r — %s", alarm_name, exc)

    except Exception as exc:
        logger.warning(
            "CloudTrail: _setup_cloudtrail_security_alarms failed for stack=%r — %s",
            stack_name, exc,
        )


def setup_stack_monitoring(stack_name: str, cdk_out_dir: Path) -> None:
    """Attach real-time CloudWatch monitoring to a deployed CDK stack.

    Runs three layers in sequence.  Never raises — all failures are logged as
    warnings so a monitoring setup issue never blocks the pipeline.

    Layer 1 — Application Insights auto-discovery
    Layer 2 — Explicit metric alarms per resource type from the CDK template
    Layer 3 — CloudTrail security metric filter alarms (auto-detected; skipped
               if the SysSecOpsCloudTrailStack has not been deployed yet)

    Args:
        stack_name:  Name of the CloudFormation stack (also used as resource group name).
        cdk_out_dir: Path to the CDK output directory (GeneratedCDK/cdk.out).
    """
    logger.info("stack_monitor: setting up monitoring for stack=%r", stack_name)

    # Layer 1 — Application Insights
    _register_application_insights(stack_name)

    # Layer 2 — Explicit alarms from template (operational + security per resource type)
    template = _find_template(stack_name, Path(cdk_out_dir))
    if template:
        _create_explicit_alarms(stack_name, template)      # EC2/Lambda/RDS/ECS metrics
        _create_s3_security_alarms(stack_name, template)   # S3 4xx/5xx + request metrics
    else:
        logger.warning(
            "stack_monitor: no template found for stack=%r in %s; skipping explicit alarms",
            stack_name,
            cdk_out_dir,
        )

    # Layer 3a — CloudTrail security alarms (account-wide CIS alarms; skips if trail not deployed)
    _setup_cloudtrail_security_alarms(stack_name)

    # Layer 3b — VPC flow log alarms (per-VPC; skips if no VPCs or no flow logs)
    if template:
        _setup_vpc_flow_log_alarms(stack_name, template)


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
