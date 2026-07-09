from aws_cdk import (
    App, Stack, CfnParameter, CfnOutput,
    aws_ec2 as ec2,
    aws_iam as iam,
)
from constructs import Construct

class Ec2InstanceStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Parameters
        instance_type_param = CfnParameter(
            self, "InstanceType",
            type="String",
            default="t3.micro",
            description="EC2 instance type"
        )
        ssh_cidr_param = CfnParameter(
            self, "SshCidr",
            type="String",
            default="10.0.0.0/8",
            description="CIDR block allowed for SSH access (do not use 0.0.0.0/0)"
        )

        # VPC with public subnets
        vpc = ec2.Vpc(
            self, "Vpc",
            max_azs=2,
            nat_gateways=0,  # no NAT to keep costs low; instance gets public IP
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                )
            ]
        )

        # Security group: allow SSH only from specified CIDR
        sg = ec2.SecurityGroup(
            self, "InstanceSecurityGroup",
            vpc=vpc,
            description="Security group for EC2 instance",
            allow_all_outbound=True
        )
        sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(ssh_cidr_param.value_as_string),
            connection=ec2.Port.tcp(22),
            description="Allow SSH from specified CIDR"
        )

        # IAM role with least privilege for Session Manager
        role = iam.Role(
            self, "InstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
            ]
        )

        # AMI: latest Amazon Linux 2
        ami = ec2.MachineImage.latest_amazon_linux2()

        # EC2 instance with encrypted root volume
        instance = ec2.Instance(
            self, "Instance",
            instance_type=ec2.InstanceType(instance_type_param.value_as_string),
            machine_image=ami,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=sg,
            role=role,
            associate_public_ip_address=True,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=20,
                        encrypted=True
                    )
                )
            ]
        )

        # Output
        CfnOutput(self, "InstanceId", value=instance.instance_id)

app = App()
Ec2InstanceStack(app, "Ec2InstanceStack")
app.synth()
