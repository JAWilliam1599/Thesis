# INSTRUCTIONS:
# This code creates an AWS CDK application that defines an EC2 instance
# To run this code:
# 1. Install AWS CDK CLI: npm install -g aws-cdk
# 2. Install Python dependencies: pip install aws-cdk-lib constructs
# 3. Save this code as app.py
# 4. Run: cdk synth
# 5. To deploy: cdk deploy
# 
# Required AWS credentials must be configured via AWS CLI or environment variables
# 
# The EC2 instance will be created with:
# - Default VPC
# - Default security group allowing SSH (port 22) and HTTP (port 80)
# - t3.micro instance type
# - Amazon Linux 2 AMI
# - Key pair name (must exist in AWS)
# 
# To customize:
# - Change instance type using instance_type parameter
# - Change AMI using machine_image parameter
# - Change key pair name using key_name parameter
# - Modify security group rules in security_group.add_ingress_rule()
# 
# The key pair name must exist in your AWS account before deployment
# You can create one in AWS Console under EC2 -> Key Pairs
# 
# To provide custom values, use CDK context or environment variables:
# cdk synth -c instance_type=t3.small -c key_name=my-key-pair
# END INSTRUCTIONS

from aws_cdk import (
    App,
    Stack,
    CfnParameter,
    aws_ec2 as ec2,
    aws_iam as iam
)
from constructs import Construct

class Ec2InstanceStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Parameters for customization
        instance_type = CfnParameter(
            self, "InstanceType",
            type="String",
            default="t3.micro",
            description="EC2 instance type"
        )

        key_name = CfnParameter(
            self, "KeyName",
            type="String",
            description="Name of existing EC2 key pair"
        )

        # Get the default VPC
        vpc = ec2.Vpc.from_lookup(self, "VPC", is_default=True)

        # Create security group
        security_group = ec2.SecurityGroup(
            self, "InstanceSecurityGroup",
            vpc=vpc,
            security_group_name="ec2-instance-sg",
            description="Security group for EC2 instance"
        )

        # Add ingress rules
        security_group.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(22),
            description="Allow SSH access"
        )
        security_group.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(80),
            description="Allow HTTP access"
        )

        # Create IAM role for EC2 instance
        instance_role = iam.Role(
            self, "InstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            role_name="ec2-instance-role"
        )

        # Attach basic EC2 instance profile policy
        instance_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ReadOnlyAccess")
        )

        # Create EC2 instance
        instance = ec2.Instance(
            self, "EC2Instance",
            instance_type=ec2.InstanceType(instance_type.value_as_string),
            machine_image=ec2.MachineImage.latest_amazon_linux(
                generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2
            ),
            key_name=key_name.value_as_string,
            security_group=security_group,
            vpc=vpc,
            role=instance_role,
            instance_name="MyEC2Instance"
        )

        # Output instance details
        self.instance_id = instance.instance_id
        self.instance_public_ip = instance.instance_public_ip

        # Add outputs
        from aws_cdk import CfnOutput
        CfnOutput(
            self, "InstanceId",
            value=instance.instance_id,
            description="EC2 Instance ID"
        )
        CfnOutput(
            self, "InstancePublicIP",
            value=instance.instance_public_ip,
            description="EC2 Instance Public IP"
        )
        CfnOutput(
            self, "InstancePrivateIP",
            value=instance.instance_private_ip,
            description="EC2 Instance Private IP"
        )

app = App()
Ec2InstanceStack(app, "Ec2InstanceStack")
app.synth()
