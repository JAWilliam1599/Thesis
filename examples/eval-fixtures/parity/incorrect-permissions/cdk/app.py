"""Coverage fixture: a critical resource anyone may use (cloud side).

Paired with ../ansible, which grants the same unrestricted access to a
credential file on a host.  Everything else in this stack is deliberately
unremarkable so that any difference in the gate's verdict is attributable to
the one weakness.

Weakness class: incorrect-permissions (CWE-732)
"""
import aws_cdk as cdk
from aws_cdk import Stack, aws_iam as iam, aws_kms as kms
from constructs import Construct


class CoverageIncorrectPermissionsStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        key = kms.Key(
            self,
            "RecordsKey",
            description="Envelope key for customer records",
            enable_key_rotation=True,
        )

        # WEAKNESS (CWE-732): the key policy names no principal and carries no
        # condition, so the control protecting the data is usable by anyone who
        # can reach the API.
        key.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"],
                resources=["*"],
                principals=[iam.AnyPrincipal()],
            )
        )


app = cdk.App()
CoverageIncorrectPermissionsStack(app, "CoverageIncorrectPermissionsStack")
app.synth()
