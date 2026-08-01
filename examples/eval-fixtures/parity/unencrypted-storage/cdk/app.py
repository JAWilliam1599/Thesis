"""Parity fixture: data stored without encryption at rest (cloud side).

Paired with ../ansible, which mounts an unencrypted data volume on an
on-premises host.  Weakness class: unencrypted-storage
"""
import aws_cdk as cdk
from aws_cdk import Stack, RemovalPolicy, aws_ec2 as ec2, aws_s3 as s3
from constructs import Construct


class ParityUnencryptedStorageStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # WEAKNESS (unencrypted-storage): object storage without encryption.
        s3.Bucket(
            self,
            "DataBucket",
            encryption=s3.BucketEncryption.UNENCRYPTED,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # WEAKNESS (unencrypted-storage): block storage without encryption.
        ec2.CfnVolume(
            self,
            "DataVolume",
            availability_zone="us-east-1a",
            size=20,
            encrypted=False,
        )


app = cdk.App()
ParityUnencryptedStorageStack(app, "ParityUnencryptedStorageStack")
app.synth()
