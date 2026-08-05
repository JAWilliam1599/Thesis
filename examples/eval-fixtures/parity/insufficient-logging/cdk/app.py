"""Coverage fixture: no record of access or control-plane activity (cloud side).

Paired with ../ansible, which suppresses the equivalent host audit trail.
Everything else in this stack is deliberately unremarkable so that any
difference in the gate's verdict is attributable to the one weakness.

Weakness class: insufficient-logging (CWE-778)
"""
import aws_cdk as cdk
from aws_cdk import Stack, aws_s3 as s3
from constructs import Construct


class CoverageInsufficientLoggingStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # WEAKNESS (CWE-778): the bucket records no server access logs and no
        # trail records control-plane activity, so reads of this data leave no
        # evidence anywhere. Encryption and public-access blocking are present
        # precisely so that logging is the only thing missing.
        s3.Bucket(
            self,
            "CustomerRecords",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=True,
        )


app = cdk.App()
CoverageInsufficientLoggingStack(app, "CoverageInsufficientLoggingStack")
app.synth()
