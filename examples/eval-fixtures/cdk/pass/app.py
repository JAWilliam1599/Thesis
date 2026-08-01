"""PASS-band CDK fixture.

A minimal, hardened stack: encrypted and fully private object storage with
access logging and versioning, a security group with no ingress, and a scoped
IAM policy.  Establishes that the gate does not block compliant cloud change.

Expected gate decision: pass.
"""
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_s3 as s3,
)
from constructs import Construct


class FixturePassStack(Stack):
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

        # No ingress at all: the workload is reached through VPC endpoints.
        ec2.SecurityGroup(
            self,
            "WorkloadSg",
            vpc=vpc,
            description="Workload security group with no inbound access",
            allow_all_outbound=False,
        )

        role = iam.Role(
            self,
            "WorkloadRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="Least-privilege read access to the data bucket",
        )
        data_bucket.grant_read(role)


app = cdk.App()
FixturePassStack(app, "EvalFixturePass")
app.synth()
