"""Coverage fixture: a workload running with more privilege than it needs
(cloud side).

Paired with ../ansible, which runs the equivalent service as the host's
administrative account.  Everything else in this stack is deliberately
unremarkable so that any difference in the gate's verdict is attributable to
the one weakness.

Weakness class: unnecessary-privileges (CWE-250)
"""
import aws_cdk as cdk
from aws_cdk import Stack, aws_ec2 as ec2, aws_ecs as ecs
from constructs import Construct


class CoverageUnnecessaryPrivilegesStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc(self, "AppVpc", max_azs=2, nat_gateways=0)
        ecs.Cluster(self, "AppCluster", vpc=vpc)

        task = ecs.Ec2TaskDefinition(self, "IngestTask")

        # WEAKNESS (CWE-250): the container runs as the administrative account
        # and with the host's full device and capability set, although the
        # workload only reads and writes application data.
        task.add_container(
            "Ingest",
            image=ecs.ContainerImage.from_registry("public.ecr.aws/docker/library/python:3.12-slim"),
            memory_limit_mib=512,
            privileged=True,
            user="root",
        )


app = cdk.App()
CoverageUnnecessaryPrivilegesStack(app, "CoverageUnnecessaryPrivilegesStack")
app.synth()
