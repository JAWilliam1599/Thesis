"""CDK stack defining all Phase 4 ops-loop AWS infrastructure.

Provisions:
    - Lambda function (pipeline/lambda_handler.py) for EventBridge re-trigger and SNS notification
    - EventBridge rule: AWS Config compliance change → Lambda
    - EventBridge rule: CloudFormation stack status change (rollback) → Lambda
    - Lambda IAM execution role with least-privilege permissions
    - CloudWatch alarms: GateRejectAlarm and HighCriticalFindingsAlarm
    - CloudWatch dashboard: SysSecOpsGate (score trend + findings counts)

Deploy this stack separately from user-generated CDK stacks:

    cd generated_cdk
    cdk deploy SysSecOpsOpsLoopStack

Configuration via environment variables at synth time:
    SNS_TOPIC_ARN      — SNS topic ARN for alarm actions and Lambda notifications
    AWS_DEFAULT_REGION — region (resolved by CDK automatically)
"""
from __future__ import annotations

import os

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    Stack,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_sns as sns,
)
from constructs import Construct

_SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
_RETRIGGER_MODE = os.environ.get("RETRIGGER_MODE", "notify_only")


class SysSecOpsOpsLoopStack(Stack):
    """Phase 4 ops-loop infrastructure stack."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------ #
        # SNS topic reference (external — must already exist)                  #
        # ------------------------------------------------------------------ #
        alarm_actions: list[cloudwatch.IAlarmAction] = []
        if _SNS_TOPIC_ARN:
            sns_topic = sns.Topic.from_topic_arn(self, "GateTopic", _SNS_TOPIC_ARN)
            alarm_actions = [cw_actions.SnsAction(sns_topic)]

        # ------------------------------------------------------------------ #
        # IAM execution role for the Lambda function                           #
        # ------------------------------------------------------------------ #
        lambda_role = iam.Role(
            self,
            "OpsLoopLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        # SSM read/write for gate results
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParametersByPath", "ssm:PutParameter"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/syssecops/*"
                ],
            )
        )

        # SNS publish for notifications
        if _SNS_TOPIC_ARN:
            lambda_role.add_to_policy(
                iam.PolicyStatement(
                    actions=["sns:Publish"],
                    resources=[_SNS_TOPIC_ARN],
                )
            )

        # AWS Config read
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["config:DescribeComplianceByResource"],
                resources=["*"],
            )
        )

        # CloudWatch metrics and alarms
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:PutMetricData", "cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms"],
                resources=["*"],
            )
        )

        # CloudWatch Logs
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=[f"arn:aws:logs:{self.region}:{self.account}:log-group:/syssecops/*"],
            )
        )

        # Application Insights
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "applicationinsights:CreateApplication",
                    "applicationinsights:DeleteApplication",
                    "applicationinsights:DescribeApplication",
                ],
                resources=["*"],
            )
        )

        # Resource Groups (required by Application Insights)
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "resource-groups:CreateGroup",
                    "resource-groups:DeleteGroup",
                    "resource-groups:GetGroup",
                ],
                resources=["*"],
            )
        )

        # Lambda self-invoke for auto_retrigger mode
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[f"arn:aws:lambda:{self.region}:{self.account}:function:*"],
            )
        )

        # ------------------------------------------------------------------ #
        # Lambda function                                                       #
        # ------------------------------------------------------------------ #
        # Resolve path relative to this file: monitoring/ → project root → pipeline/
        import pathlib
        project_root = pathlib.Path(__file__).resolve().parents[1]
        handler_asset_path = str(project_root / "pipeline")

        ops_loop_fn = lambda_.Function(
            self,
            "OpsLoopFunction",
            function_name="syssecops-ops-loop",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="lambda_handler.handler",
            code=lambda_.Code.from_asset(handler_asset_path),
            role=lambda_role,
            timeout=Duration.seconds(60),
            memory_size=256,
            environment={
                "SNS_TOPIC_ARN": _SNS_TOPIC_ARN,
                "RETRIGGER_MODE": _RETRIGGER_MODE,
                "SSM_ENABLED": "true",
            },
            description="SysSecOps Phase 4 ops-loop: drift detection and rollback notifications",
        )

        # ------------------------------------------------------------------ #
        # EventBridge rule 1 — AWS Config compliance changes                   #
        # ------------------------------------------------------------------ #
        events.Rule(
            self,
            "ConfigComplianceRule",
            rule_name="syssecops-config-compliance-change",
            description="Trigger SysSecOps ops-loop Lambda on AWS Config NON_COMPLIANT events",
            event_pattern=events.EventPattern(
                source=["aws.config"],
                detail_type=["Config Rules Compliance Change"],
            ),
            targets=[targets.LambdaFunction(ops_loop_fn)],
        )

        # ------------------------------------------------------------------ #
        # EventBridge rule 2 — CloudFormation stack rollback events            #
        # ------------------------------------------------------------------ #
        events.Rule(
            self,
            "CfnRollbackRule",
            rule_name="syssecops-cfn-rollback",
            description="Trigger SysSecOps ops-loop Lambda on CloudFormation stack rollback events",
            event_pattern=events.EventPattern(
                source=["aws.cloudformation"],
                detail_type=["CloudFormation Stack Status Change"],
                detail={
                    "status-details": {
                        "stack-status": [
                            "ROLLBACK_COMPLETE",
                            "UPDATE_ROLLBACK_COMPLETE",
                            "DELETE_FAILED",
                            "CREATE_FAILED",
                            "UPDATE_FAILED",
                        ]
                    }
                },
            ),
            targets=[targets.LambdaFunction(ops_loop_fn)],
        )

        # ------------------------------------------------------------------ #
        # CloudWatch alarms on gate evaluation metrics                         #
        # ------------------------------------------------------------------ #
        gate_decision_metric = cloudwatch.Metric(
            namespace="SysSecOps/Gate",
            metric_name="GateDecision",
            statistic="Maximum",
            period=Duration.minutes(5),
        )

        critical_findings_metric = cloudwatch.Metric(
            namespace="SysSecOps/Gate",
            metric_name="CriticalFindings",
            statistic="Sum",
            period=Duration.minutes(5),
        )

        reject_alarm = cloudwatch.Alarm(
            self,
            "GateRejectAlarm",
            alarm_name="syssecops-gate-reject",
            alarm_description="SysSecOps gate produced a REJECT decision (GateDecision >= 2)",
            metric=gate_decision_metric,
            threshold=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        critical_alarm = cloudwatch.Alarm(
            self,
            "HighCriticalFindingsAlarm",
            alarm_name="syssecops-critical-findings",
            alarm_description="SysSecOps gate detected one or more CRITICAL severity findings",
            metric=critical_findings_metric,
            threshold=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        if alarm_actions:
            reject_alarm.add_alarm_action(*alarm_actions)
            critical_alarm.add_alarm_action(*alarm_actions)

        # ------------------------------------------------------------------ #
        # CloudWatch dashboard                                                  #
        # ------------------------------------------------------------------ #
        cloudwatch.Dashboard(
            self,
            "SysSecOpsDashboard",
            dashboard_name="SysSecOpsGate",
            widgets=[
                [
                    cloudwatch.GraphWidget(
                        title="Gate Score (last 7 days)",
                        left=[
                            cloudwatch.Metric(
                                namespace="SysSecOps/Gate",
                                metric_name="GateScore",
                                statistic="Maximum",
                                period=Duration.minutes(5),
                                label="GateScore",
                            )
                        ],
                        width=12,
                        height=6,
                    ),
                    cloudwatch.GraphWidget(
                        title="Findings Count (last 7 days)",
                        left=[
                            cloudwatch.Metric(
                                namespace="SysSecOps/Gate",
                                metric_name="CriticalFindings",
                                statistic="Sum",
                                period=Duration.minutes(5),
                                label="Critical",
                                color=cloudwatch.Color.RED,
                            ),
                            cloudwatch.Metric(
                                namespace="SysSecOps/Gate",
                                metric_name="HighFindings",
                                statistic="Sum",
                                period=Duration.minutes(5),
                                label="High",
                                color=cloudwatch.Color.ORANGE,
                            ),
                        ],
                        width=12,
                        height=6,
                    ),
                ],
                [
                    cloudwatch.AlarmWidget(
                        title="Gate Reject Alarm",
                        alarm=reject_alarm,
                        width=12,
                        height=3,
                    ),
                    cloudwatch.AlarmWidget(
                        title="Critical Findings Alarm",
                        alarm=critical_alarm,
                        width=12,
                        height=3,
                    ),
                ],
            ],
        )

        # ------------------------------------------------------------------ #
        # Stack outputs                                                         #
        # ------------------------------------------------------------------ #
        cdk.CfnOutput(
            self,
            "OpsLoopFunctionArn",
            value=ops_loop_fn.function_arn,
            description="ARN of the SysSecOps ops-loop Lambda function (set as PIPELINE_LAMBDA_ARN for auto_retrigger mode)",
            export_name="SysSecOpsOpsLoopFunctionArn",
        )
