"""Specificity control for the coverage measurement (cloud side).

This stack contains none of the weakness classes in
evaluation/coverage_catalogue.yaml.  Its purpose is negative: if a class matcher
fires here, that class cannot be credited on the cloud branch, because the
matcher is responding to something other than the weakness.

It deliberately avoids S3.  A bucket that receives access logs cannot log to
itself and carries a log-delivery ACL, so it provokes findings naming logging
and public ACLs no matter how the stack is written -- which would make the
control unable to discriminate for two of the eleven classes.

Weakness class: none (control)
"""
import aws_cdk as cdk
from aws_cdk import (
    Duration,
    Stack,
    aws_kms as kms,
    aws_logs as logs,
    aws_sqs as sqs,
)
from constructs import Construct


class CoverageControlStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        key = kms.Key(
            self,
            "ControlKey",
            description="Envelope key for the control workload",
            enable_key_rotation=True,
        )

        logs.LogGroup(
            self,
            "ControlLogGroup",
            retention=logs.RetentionDays.ONE_YEAR,
            encryption_key=key,
        )

        dead_letter = sqs.Queue(
            self,
            "ControlDlq",
            encryption=sqs.QueueEncryption.KMS,
            encryption_master_key=key,
            enforce_ssl=True,
        )

        sqs.Queue(
            self,
            "ControlQueue",
            encryption=sqs.QueueEncryption.KMS,
            encryption_master_key=key,
            enforce_ssl=True,
            visibility_timeout=Duration.seconds(60),
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=5, queue=dead_letter),
        )


app = cdk.App()
CoverageControlStack(app, "CoverageControlStack")
app.synth()
