"""Parity fixture: unrestricted administrative privilege (cloud side).

Paired with ../ansible, which grants the same unrestricted privilege to a local
account via passwordless sudo.  Weakness class: overprivileged-access
"""
import aws_cdk as cdk
from aws_cdk import Stack, aws_iam as iam
from constructs import Construct


class ParityOverprivilegedStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        role = iam.Role(
            self,
            "AppRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
        )
        # WEAKNESS (overprivileged-access): every action on every resource.
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["*"],
                resources=["*"],
            )
        )


app = cdk.App()
ParityOverprivilegedStack(app, "ParityOverprivilegedStack")
app.synth()
