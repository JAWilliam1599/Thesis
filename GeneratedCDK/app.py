# INSTRUCTIONS:
# This is a Python AWS CDK application that creates an S3 bucket with specific security configurations.
# To run this code:
# 1. Install AWS CDK CLI and Python CDK library (cdk version 2.x recommended)
# 2. Save this code as app.py
# 3. Run 'cdk synth' in the terminal to generate CloudFormation template
# 4. The bucket will have:
#    - All PublicAccessBlockConfiguration settings set to True
#    - Versioning enabled
#    - Server-side encryption with AES256
# No interactive inputs are required - all settings are hardcoded for non-interactive execution

from aws_cdk import (
    App,
    Stack,
    aws_s3 as s3,
    CfnOutput
)
from constructs import Construct

class S3BucketStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create S3 bucket with specified configurations
        bucket = s3.Bucket(
            self, "SecureBucket",
            bucket_name="qwuagspivhvajwegf",  # TODO: Replace with unique bucket name
            public_read_access=False,
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=True,
                ignore_public_acls=True,
                block_public_policy=True,
                restrict_public_buckets=True
            ),
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            encryption_key=None,
            enforce_ssl=True
        )

        # Output the bucket name
        CfnOutput(
            self, "BucketName",
            value=bucket.bucket_name,
            description="Name of the created S3 bucket"
        )

app = App()
S3BucketStack(app, "S3BucketStack")
app.synth()
