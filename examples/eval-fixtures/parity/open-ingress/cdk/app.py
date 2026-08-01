"""Parity fixture: administrative ingress open to the whole internet (cloud side).

Paired with ../ansible, which opens the same port to the same source range on an
on-premises host.  Everything else in this stack is deliberately unremarkable so
that any difference in the gate's verdict is attributable to the one weakness.

Weakness class: open-ingress
"""
import aws_cdk as cdk
from aws_cdk import Stack, aws_ec2 as ec2
from constructs import Construct


class ParityOpenIngressStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc(self, "ParityVpc", max_azs=2, nat_gateways=1)

        sg = ec2.SecurityGroup(
            self,
            "AppSg",
            vpc=vpc,
            description="Application host access",
            allow_all_outbound=True,
        )
        # WEAKNESS (open-ingress): SSH reachable from any address on the internet.
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(22), "SSH from anywhere")


app = cdk.App()
ParityOpenIngressStack(app, "ParityOpenIngressStack")
app.synth()
