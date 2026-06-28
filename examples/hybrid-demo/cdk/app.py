"""Hybrid demo CDK app — the AWS side of the hybrid system.

A minimal, single-stack app that provisions a hardened S3 bucket so the security
gate has a real CloudFormation template to score.  Bring-your-own-code: there is
no generation step in the hybrid pipeline.
"""
import aws_cdk as cdk
from aws_cdk import Stack, aws_s3 as s3
from constructs import Construct


class HybridDemoStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        s3.Bucket(
            self,
            "DemoBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )


app = cdk.App()
HybridDemoStack(app, "HybridDemoStack")
app.synth()
