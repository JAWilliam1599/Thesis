"""Coverage fixture: application data readable by external parties (cloud side).

Paired with ../ansible, which shares the same data directory to every host on
the network.  Everything else in this stack is deliberately unremarkable so
that any difference in the gate's verdict is attributable to the one weakness.

Weakness class: externally-accessible-files (CWE-552)
"""
import aws_cdk as cdk
from aws_cdk import Stack, aws_s3 as s3
from constructs import Construct


class CoverageExternallyAccessibleStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # WEAKNESS (CWE-552): the document store is readable by anyone on the
        # internet. The public-access guards are switched off individually,
        # which is what makes the exposure reachable rather than merely
        # declared.
        s3.Bucket(
            self,
            "SharedDocuments",
            encryption=s3.BucketEncryption.S3_MANAGED,
            public_read_access=True,
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=False,
                block_public_policy=False,
                ignore_public_acls=False,
                restrict_public_buckets=False,
            ),
        )


app = cdk.App()
CoverageExternallyAccessibleStack(app, "CoverageExternallyAccessibleStack")
app.synth()
