"""REJECT-band CDK fixture — severely and deliberately insecure.

Do not copy any part of this file into a real project.

Injected weaknesses (severe, compounding):
  * SSH and RDP open to 0.0.0.0/0
  * unencrypted, public-readable object storage with no public-access block
  * a wildcard IAM policy (Action "*" on Resource "*")
  * an unencrypted EBS volume on a publicly reachable instance

Expected gate decision: reject.
"""
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_s3 as s3,
)
from constructs import Construct


class FixtureRejectStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc(self, "FixtureVpc", max_azs=2, nat_gateways=1)

        # WEAKNESS: administrative ports exposed to the entire internet.
        sg = ec2.SecurityGroup(
            self,
            "AdminSg",
            vpc=vpc,
            description="Administrative access",
            allow_all_outbound=True,
        )
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(22), "SSH from anywhere")
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(3389), "RDP from anywhere")
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(5432), "PostgreSQL from anywhere")

        # WEAKNESS: unencrypted, publicly readable bucket with no public-access
        # block and no logging or versioning.
        s3.Bucket(
            self,
            "PublicBucket",
            encryption=s3.BucketEncryption.UNENCRYPTED,
            public_read_access=True,
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=False,
                block_public_policy=False,
                ignore_public_acls=False,
                restrict_public_buckets=False,
            ),
            object_ownership=s3.ObjectOwnership.OBJECT_WRITER,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # WEAKNESS: unrestricted administrative permissions.
        role = iam.Role(
            self,
            "AdminRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["*"],
                resources=["*"],
            )
        )

        # WEAKNESS: unencrypted root volume on a publicly reachable instance.
        ec2.Instance(
            self,
            "AdminInstance",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            instance_type=ec2.InstanceType("t3.micro"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            security_group=sg,
            role=role,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(20, encrypted=False),
                )
            ],
        )


app = cdk.App()
FixtureRejectStack(app, "EvalFixtureReject")
app.synth()
