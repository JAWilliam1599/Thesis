"""REJECT-band CDK fixture that reaches reject only with the learned component.

The storage, logging, network and function configuration are hardened to the
same standard as the pass fixture.  One template-level weakness is injected — a
wildcard IAM policy — and it is calibrated to leave the stack inside the review
band on its own.  A second weakness lives where no template scanner can reach
it: certificate validation is disabled on an outbound call in the Lambda
handler bundled from ``handler/``.  The learned code-risk component is what
carries the stack across the reject threshold, so removing it returns the
decision to review.

This fixture exists because every other CDK fixture in the set contains only
resource declarations, while real CDK applications routinely bundle handler
source.  The learned code-risk component can act only on Python, so without an
artifact of this class the component is never exercised.

Expected gate decision: reject; review with ``--no-ml-risk``.
"""
import os

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_kms as kms,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_s3 as s3,
    aws_sqs as sqs,
)
from constructs import Construct

HANDLER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "handler")


class FixtureMlRiskStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc(
            self,
            "FixtureVpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                )
            ],
        )

        # Log-delivery target: CDK applies the LogDeliveryWrite ACL to this
        # bucket, which requires object-writer ownership.
        access_logs = s3.Bucket(
            self,
            "AccessLogsBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
        )

        data_bucket = s3.Bucket(
            self,
            "DataBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            server_access_logs_bucket=access_logs,
            server_access_logs_prefix="data-bucket/",
            removal_policy=RemovalPolicy.RETAIN,
        )

        ec2.SecurityGroup(
            self,
            "WorkloadSg",
            vpc=vpc,
            description="Workload security group with no inbound access",
            allow_all_outbound=False,
        )

        # WEAKNESS: unrestricted administrative permissions.
        maintenance_role = iam.Role(
            self,
            "MaintenanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
        )
        maintenance_role.add_to_policy(
            iam.PolicyStatement(actions=["*"], resources=["*"])
        )

        key = kms.Key(self, "WorkloadKey", enable_key_rotation=True)

        dead_letter_queue = sqs.Queue(
            self,
            "InventoryDlq",
            encryption=sqs.QueueEncryption.KMS,
            encryption_master_key=key,
            enforce_ssl=True,
        )

        log_group = logs.LogGroup(
            self,
            "InventoryFunctionLogGroup",
            retention=logs.RetentionDays.ONE_MONTH,
            encryption_key=key,
            removal_policy=RemovalPolicy.DESTROY,
        )

        function = lambda_.Function(
            self,
            "InventoryFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_asset(HANDLER_DIR),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            timeout=Duration.seconds(30),
            reserved_concurrent_executions=5,
            tracing=lambda_.Tracing.ACTIVE,
            dead_letter_queue=dead_letter_queue,
            environment_encryption=key,
            environment={"BUCKET_NAME": data_bucket.bucket_name},
            log_group=log_group,
        )
        data_bucket.grant_read(function)


app = cdk.App()
FixtureMlRiskStack(app, "EvalFixtureMlRisk")
app.synth()
