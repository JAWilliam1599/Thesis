"""CDK stack that provisions CloudTrail → CloudWatch Logs for security audit.

Provisions:
    - S3 bucket for CloudTrail log storage (versioned, encrypted, RETAIN policy)
    - CloudWatch Logs log group: /aws/cloudtrail/syssecops (90-day retention)
    - IAM role allowing CloudTrail to write to the log group
    - Multi-region CloudTrail trail with management events and log file validation

After this stack is deployed, setup_stack_monitoring() automatically creates
Layer 2 security metric filter alarms (unauthorized API calls, IAM changes,
security group changes, S3 bucket policy changes, root account usage, etc.)
on the /aws/cloudtrail/syssecops log group.

Deploy alongside SysSecOpsOpsLoopStack:

    cd monitoring
    cdk deploy SysSecOpsCloudTrailStack

Configuration via environment variables at synth time:
    AWS_DEFAULT_REGION — region (resolved by CDK automatically)
"""
from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_cloudtrail as cloudtrail,
    aws_iam as iam,
    aws_logs as logs,
    aws_s3 as s3,
)
from constructs import Construct

# Log group name consumed by stack_monitor._setup_cloudtrail_security_alarms()
CLOUDTRAIL_LOG_GROUP_NAME = "/aws/cloudtrail/syssecops"


class SysSecOpsCloudTrailStack(Stack):
    """Provisions CloudTrail with CloudWatch Logs delivery for security monitoring."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------ #
        # S3 bucket — trail storage (RETAIN: audit logs must survive destroy) #
        # ------------------------------------------------------------------ #
        trail_bucket = s3.Bucket(
            self,
            "TrailBucket",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
        )

        # ------------------------------------------------------------------ #
        # CloudWatch Logs log group (RETAIN: same reasoning as S3)            #
        # ------------------------------------------------------------------ #
        log_group = logs.LogGroup(
            self,
            "TrailLogGroup",
            log_group_name=CLOUDTRAIL_LOG_GROUP_NAME,
            retention=logs.RetentionDays.THREE_MONTHS,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ------------------------------------------------------------------ #
        # IAM role — allows CloudTrail to write to the log group              #
        # ------------------------------------------------------------------ #
        trail_role = iam.Role(
            self,
            "TrailCWLogsRole",
            role_name="SysSecOpsCloudTrailToCloudWatchLogs",
            assumed_by=iam.ServicePrincipal("cloudtrail.amazonaws.com"),
            description="Allows CloudTrail syssecops-trail to deliver events to CloudWatch Logs",
        )
        trail_role.add_to_policy(
            iam.PolicyStatement(
                actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                resources=[
                    log_group.log_group_arn,
                    f"{log_group.log_group_arn}:*",
                ],
            )
        )

        # ------------------------------------------------------------------ #
        # CloudTrail trail                                                     #
        # ------------------------------------------------------------------ #
        trail = cloudtrail.Trail(
            self,
            "Trail",
            trail_name="syssecops-trail",
            bucket=trail_bucket,
            cloud_watch_logs_retention=logs.RetentionDays.THREE_MONTHS,
            cloud_watch_log_group=log_group,
            send_to_cloud_watch_logs=True,
            # Capture management events (API calls that create/modify/delete resources)
            management_events=cloudtrail.ReadWriteType.ALL,
            # Enable log file validation so tampering can be detected
            enable_file_validation=True,
            # Multi-region: captures calls from all regions into this trail
            is_multi_region_trail=True,
            include_global_service_events=True,
        )

        # ------------------------------------------------------------------ #
        # Outputs                                                              #
        # ------------------------------------------------------------------ #
        cdk.CfnOutput(
            self,
            "TrailArn",
            value=trail.trail_arn,
            description="CloudTrail trail ARN",
            export_name="SysSecOpsTrailArn",
        )
        cdk.CfnOutput(
            self,
            "TrailLogGroupName",
            value=CLOUDTRAIL_LOG_GROUP_NAME,
            description="CloudWatch Logs log group receiving CloudTrail events",
            export_name="SysSecOpsTrailLogGroupName",
        )
        cdk.CfnOutput(
            self,
            "TrailBucketName",
            value=trail_bucket.bucket_name,
            description="S3 bucket storing CloudTrail log files",
        )
