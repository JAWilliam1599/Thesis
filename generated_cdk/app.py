from aws_cdk import (
    App, Stack, CfnParameter,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_kms as kms,
    RemovalPolicy
)
from constructs import Construct

class SingleEC2InstanceStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc(self, "Vpc", max_azs=2)

        security_group = ec2.SecurityGroup(
            self, "InstanceSG",
            vpc=vpc,
            description="Security group for EC2 instance",
            allow_all_outbound=True
        )
        security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(22),
            description="Allow SSH from within VPC"
        )

        kms_key = kms.Key(
            self, "EBSKey",
            description="KMS key for EC2 EBS encryption",
            enable_key_rotation=True,
        )
        kms_key.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["kms:Decrypt", "kms:Encrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*"],
                resources=["*"],
                principals=[iam.AccountRootPrincipal()]
            )
        )

        role = iam.Role(
            self, "EC2Role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
            ]
        )

        instance = ec2.Instance(
            self, "EC2Instance",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3,
                ec2.InstanceSize.NANO
            ),
            machine_image=ec2.AmazonLinuxImage(
                generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2
            ),
            vpc=vpc,
            security_group=security_group,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            block_devices=[ec2.BlockDevice(
                device_name="/dev/xvda",
                volume=ec2.BlockDeviceVolume.ebs(
                    volume_size=20,
                    encrypted=True,
                    kms_key=kms_key
                )
            )],
            role=role,
        )

        instance.apply_removal_policy(RemovalPolicy.DESTROY)

app = App()
SingleEC2InstanceStack(app, "SingleEC2InstanceStack")
app.synth()
