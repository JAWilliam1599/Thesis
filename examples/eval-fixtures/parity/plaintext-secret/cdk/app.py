"""Parity fixture: a credential written in clear text into the deployed artefact (cloud side).

Paired with ../ansible, which writes the same credential into a variable file.
The cloud gate has no secret scanner on its path, so this pair is expected to
expose an asymmetry rather than agreement — it is included precisely to measure
that gap rather than to hide it.

Weakness class: plaintext-secret
"""
import aws_cdk as cdk
from aws_cdk import Stack, aws_lambda as lambda_
from constructs import Construct

# Deliberately fake, non-functional placeholder. Never a real credential.
FIXTURE_DB_PASSWORD = "FIXTURE-not-a-real-password-p1"  # noqa: S105


class ParityPlaintextSecretStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        lambda_.Function(
            self,
            "AppFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_inline("def handler(event, context):\n    return {}\n"),
            # WEAKNESS (plaintext-secret): the credential is baked into the
            # template as an environment variable in clear text.
            environment={
                "DB_PASSWORD": FIXTURE_DB_PASSWORD,
                "API_KEY": "FIXTUREnotarealapikey0001",
            },
        )


app = cdk.App()
ParityPlaintextSecretStack(app, "ParityPlaintextSecretStack")
app.synth()
