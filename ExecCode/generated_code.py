# INSTRUCTIONS:
# This code uses AWS CDK to create an EC2 instance
# To run this code, you need to have AWS CDK installed and configured
# Run 'cdk bootstrap' in your terminal to bootstrap your AWS account
# Run 'cdk deploy' to deploy the stack
# You will be prompted for:
# - Instance type (e.g., t3.micro)
# - AMI ID (e.g., ami-0c55b159cbfafe1d0)
# - Key pair name (must exist in your AWS account)
# - VPC ID (must exist in your AWS account)
# - Region (e.g., us-east-1)
# - Instance name tag
# Make sure you have AWS credentials configured (via AWS CLI, environment variables, or IAM roles)
# END INSTRUCTIONS

from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    CfnOutput
)
from constructs import Construct

class Ec2InstanceStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get user inputs
        instance_type = input("Enter instance type (e.g., t3.micro): ") or "t3.micro"
        ami_id = input("Enter AMI ID (e.g., ami-0c55b159cbfafe1d0): ") or "ami-0c55b159cbfafe1d0"
        key_name = input("Enter key pair name: ")
        vpc_id = input("Enter VPC ID: ")
        instance_name = input("Enter instance name tag: ") or "MyEC2Instance"
        region = input("Enter region (e.g., us-east-1): ") or "us-east-1"

        # Retrieve existing VPC
        vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=vpc_id)

        # Create security group
        security_group = ec2.SecurityGroup(
            self,
            "EC2SecurityGroup",
            vpc=vpc,
            security_group_name="ec2-security-group",
            description="Security group for EC2 instance"
        )

        # Add inbound rules (adjust as needed)
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

        # Create EC2 instance
        instance = ec2.Instance(
            self,
            "EC2Instance",
            instance_type=ec2.InstanceType(instance_type),
            machine_image=ec2.MachineImage.generic_linux(ami_id),
            key_name=key_name,
            security_group=security_group,
            vpc=vpc,
            instance_name=instance_name
        )

        # Output instance details
        CfnOutput(
            self,
            "InstanceId",
            value=instance.instance_id,
            description="The instance ID of the EC2 instance"
        )

        CfnOutput(
            self,
            "InstancePublicIp",
            value=instance.instance_public_ip,
            description="Public IP address of the EC2 instance"
        )

        CfnOutput(
            self,
            "InstancePrivateIp",
            value=instance.instance_private_ip,
            description="Private IP address of the EC2 instance"
        )

def main():
    # This function is for demonstration purposes
    # In practice, you would run 'cdk deploy' from the command line
    print("To deploy this stack, run 'cdk deploy' in your terminal")

if __name__ == "__main__":
    main()
