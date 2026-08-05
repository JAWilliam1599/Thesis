"""Coverage fixture: sensitive traffic carried in the clear (cloud side).

Paired with ../ansible, which fetches an artifact over an unprotected channel.
Everything else in this stack is deliberately unremarkable so that any
difference in the gate's verdict is attributable to the one weakness.

Weakness class: cleartext-transmission (CWE-319)
"""
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
)
from constructs import Construct


class CoverageCleartextTransmissionStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc(self, "AppVpc", max_azs=2, nat_gateways=0)

        balancer = elbv2.ApplicationLoadBalancer(
            self, "AppLb", vpc=vpc, internet_facing=False
        )

        # WEAKNESS (CWE-319): the application is served over plaintext HTTP and
        # nothing redirects callers to a protected channel, so session material
        # crosses the network in the clear.
        listener = balancer.add_listener(
            "PlaintextListener",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            open=False,
        )
        listener.add_action(
            "Default",
            action=elbv2.ListenerAction.fixed_response(
                200, content_type="text/plain", message_body="ok"
            ),
        )


app = cdk.App()
CoverageCleartextTransmissionStack(app, "CoverageCleartextTransmissionStack")
app.synth()
