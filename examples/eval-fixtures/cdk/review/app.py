"""REVIEW-band CDK fixture — deliberately weakened.

Injected weaknesses (moderate, individually remediable):
  * object storage without access logging or versioning
  * a security group allowing HTTP from a wide internal range
  * a role granted read/write where read would suffice
  * an unencrypted queue carrying application data
  * a function with no dead-letter queue, no tracing and no concurrency cap
  * a log group with no retention policy

None of these expose the workload directly to the internet, so the expected
outcome is human adjudication rather than automatic rejection.

Expected gate decision: review.
"""
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_s3 as s3,
    aws_sqs as sqs,
)
from constructs import Construct


class FixtureReviewStack(Stack):
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

        # WEAKNESS: encrypted and private, but no access logging and no
        # versioning, so object tampering leaves no audit trail.
        data_bucket = s3.Bucket(
            self,
            "DataBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # WEAKNESS: plaintext HTTP accepted from the whole RFC1918 10/8 range.
        sg = ec2.SecurityGroup(
            self,
            "WorkloadSg",
            vpc=vpc,
            description="Workload security group",
            allow_all_outbound=True,
        )
        sg.add_ingress_rule(
            ec2.Peer.ipv4("10.0.0.0/8"),
            ec2.Port.tcp(80),
            "Plaintext HTTP from the entire internal range",
        )

        # WEAKNESS: write access granted to a read-only workload.
        role = iam.Role(
            self,
            "WorkloadRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
        )
        data_bucket.grant_read_write(role)

        # WEAKNESS: queue contents are not encrypted at rest.
        queue = sqs.Queue(
            self,
            "WorkQueue",
            encryption=sqs.QueueEncryption.UNENCRYPTED,
            visibility_timeout=Duration.seconds(60),
        )

        # WEAKNESS: no dead-letter queue, no tracing, no concurrency cap, and
        # not attached to the VPC, so failures are silent and unbounded.
        lambda_.Function(
            self,
            "WorkerFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_inline(
                "def handler(event, context):\n"
                "    return {'statusCode': 200}\n"
            ),
            timeout=Duration.seconds(30),
            environment={
                "QUEUE_URL": queue.queue_url,
                "BUCKET_NAME": data_bucket.bucket_name,
            },
        )

        # WEAKNESS: logs are retained forever and unencrypted, with no
        # retention policy to bound exposure.
        logs.LogGroup(
            self,
            "WorkerLogGroup",
            retention=logs.RetentionDays.INFINITE,
            removal_policy=RemovalPolicy.DESTROY,
        )


app = cdk.App()
FixtureReviewStack(app, "EvalFixtureReview")
app.synth()
