# INSTRUCTIONS:
# This CDK app creates an EC2 instance with encrypted EBS, minimal IAM permissions, and restricted SSH access.
# It requires an AWS environment (account/region) to be specified either via environment variables or by hardcoding.
# To run:
# 1. Install AWS CDK: npm install -g aws-cdk
# 2. Set up Python virtual environment and install dependencies:
#    pip install aws-cdk-lib constructs
# 3. Provide AWS credentials (e.g., via AWS CLI or environment variables).
# 4. Optionally export CDK_DEFAULT_ACCOUNT and CDK_DEFAULT_REGION, or they will be read from the current AWS profile.
# 5. Provide additional inputs via CDK context (e.g., -c ami_id=ami-xxx, -c instance_type=t3.micro, -c key_name=mykey, -c vpc_id=vpc-xxx, -c subnet_id=subnet-xxx, -c ssh_cidr=1.2.3.4/32).
# 6. Synthesize: cdk synth
# 7. Deploy: cdk deploy
# Note: The app will not allow SSH from 0.0.0.0/0. Use a specific IP/CIDR via context (default: 10.0.0.0/8 — private range only).
# END INSTRUCTIONS

import os
import aws_cdk as cdk
from aws_cdk import (
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_ssm as ssm,
    Stack,
    App,
    CfnOutput,
)
from constructs import Construct

class Ec2InstanceStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- Context Parameters (with fallbacks) ---
        ami_id_param = self.node.try_get_context("ami_id") or ssm.StringParameter.value_for_string_parameter(
            self, "/aws/service/ami-amazon-linux-latest/amzn2-ami-hvm-x86_64-gp2"
        )
        instance_type_param = self.node.try_get_context("instance_type") or "t3.micro"
        key_name_param = self.node.try_get_context("key_name") or None
        vpc_id_param = self.node.try_get_context("vpc_id") or "default"
        subnet_id_param = self.node.try_get_context("subnet_id") or None
        ssh_cidr_param = self.node.try_get_context("ssh_cidr") or "10.0.0.0/8"  # Safe default (private range)

        # --- VPC ---
        if vpc_id_param == "default":
            vpc = ec2.Vpc.from_lookup(self, "Vpc", is_default=True)
        else:
            vpc = ec2.Vpc.from_lookup(self, "Vpc", vpc_id=vpc_id_param)

        # --- Subnet Selection ---
        if subnet_id_param:
            subnet = ec2.Subnet.from_subnet_id(self, "Subnet", subnet_id=subnet_id_param)
        else:
            # Pick the first public subnet
            subnet = vpc.public_subnets[0] if vpc.public_subnets else vpc.private_subnets[0]

        # --- Security Group (restrict SSH) ---
        sg = ec2.SecurityGroup(
            self, "InstanceSg",
            vpc=vpc,
            description="Security group with restricted SSH",
            allow_all_outbound=True,
        )
        # Add SSH only from allowed CIDR (never 0.0.0.0/0)
        if ssh_cidr_param != "0.0.0.0/0":
            sg.add_ingress_rule(
                peer=ec2.Peer.ipv4(ssh_cidr_param),
                connection=ec2.Port.tcp(22),
                description="Allow SSH from allowed CIDR",
            )
        else:
            # Fallback: do not add any SSH rule if 0.0.0.0/0 is given (least privilege)
            pass

        # --- IAM Role (minimal permissions) ---
        role = iam.Role(
            self, "InstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="Minimal IAM role for EC2 instance",
            # No managed policies by default – user can attach additional policies
        )

        # --- Instance Profile ---
        instance_profile = iam.CfnInstanceProfile(
            self, "InstanceProfile",
            roles=[role.role_name],
        )

        # --- Launch Template / Instance ---
        instance = ec2.CfnInstance(
            self, "Ec2Instance",
            image_id=ami_id_param,
            instance_type=instance_type_param,
            key_name=key_name_param,
            subnet_id=subnet.subnet_id,
            security_group_ids=[sg.security_group_id],
            iam_instance_profile=instance_profile.ref,
            block_device_mappings=[
                ec2.CfnInstance.BlockDeviceMappingProperty(
                    device_name="/dev/xvda",
                    ebs=ec2.CfnInstance.EbsProperty(
                        encrypted=True,
                        volume_size=8,
                        volume_type="gp3",
                    ),
                )
            ],
        )

        # --- Outputs ---
        CfnOutput(self, "InstanceId", value=instance.ref)
        CfnOutput(self, "InstancePublicIp", value=instance.attr_public_ip if subnet in vpc.public_subnets else "No public IP")
        CfnOutput(self, "SecurityGroupId", value=sg.security_group_id)


app = App()

# Use environment variables for account/region (set via AWS CLI or export CDK_DEFAULT_ACCOUNT, CDK_DEFAULT_REGION)
# If not available, the deployment will fail with a clear error; hardcode as fallback if needed.
env = cdk.Environment(
    account=os.environ.get('CDK_DEFAULT_ACCOUNT'),
    region=os.environ.get('CDK_DEFAULT_REGION')
)

Ec2InstanceStack(app, "Ec2InstanceStack", env=env)
app.synth()
