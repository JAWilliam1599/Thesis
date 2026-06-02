# INSTRUCTIONS:
# This script creates an EC2 instance using AWS CDK
# To run this script, you need to have AWS CDK installed and configured
# Run with: python ec2_instance.py
# You will be prompted for:
# - AWS region (e.g., us-east-1)
# - Instance type (e.g., t3.micro)
# - AMI ID (e.g., ami-0c55b159cbfafe1d0)
# - Key pair name (existing key pair in your AWS account)
# - Instance name tag
# - VPC ID (existing VPC in your AWS account)
# - Subnet ID (existing subnet in your VPC)
# - Security group IDs (existing security groups)
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
        region = input("Enter AWS region (e.g., us-east-1): ")
        instance_type = input("Enter instance type (e.g., t3.micro): ")
        ami_id = input("Enter AMI ID (e.g., ami-0c55b159cbfafe1d0): ")
        key_name = input("Enter key pair name: ")
        instance_name = input("Enter instance name tag: ")
        vpc_id = input("Enter VPC ID: ")
        subnet_id = input("Enter subnet ID: ")
        security_groups = input("Enter security group IDs (comma-separated): ").split(',')

        # Lookup existing VPC
        vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=vpc_id)

        # Lookup existing subnet
        subnet = ec2.Subnet.from_subnet_attributes(
            self, "Subnet",
            subnet_id=subnet_id,
            availability_zone=region + "a"  # TODO: Make this dynamic if needed
        )

        # Create security group if needed (this is a simplified approach)
        # In a real scenario, you'd want to validate or create security groups properly
        sg_list = []
        for sg_id in security_groups:
            sg = ec2.SecurityGroup.from_security_group_id(self, f"SG-{sg_id}", sg_id.strip())
            sg_list.append(sg)

        # Create EC2 instance
        instance = ec2.Instance(
            self, "EC2Instance",
            instance_type=ec2.InstanceType(instance_type),
            machine_image=ec2.MachineImage.generic_linux({
                region: ami_id
            }),
            key_name=key_name,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=[subnet]),
            security_group=sg_list[0] if sg_list else None,
            instance_name=instance_name
        )

        # Output instance ID
        CfnOutput(self, "InstanceId", value=instance.instance_id)
        CfnOutput(self, "InstancePublicIp", value=instance.instance_public_ip or "No public IP")

def main():
    # TODO: Add CDK app setup if needed
    # This is a placeholder for the main entry point
    pass

if __name__ == "__main__":
    main()
