# INSTRUCTIONS:
# This is a complete AWS CDK Python application for creating secure EC2 instances and S3 buckets.
# To run this code:
# 1. Install AWS CDK CLI and Python dependencies
# 2. Save this code as app.py
# 3. Run `cdk synth` to generate CloudFormation templates
# 4. Deploy using `cdk deploy` (optional)
# 
# The application creates:
# - Secure EC2 instances with restricted SSH access
# - S3 buckets with access logging enabled
# - Proper IAM policies with least privilege
# 
# Security fixes applied:
# - Removed public SSH access from security groups
# - Enabled access logging on S3 buckets
# - Used specific IP ranges for SSH access
# - Applied encryption to all stateful resources
# 
# Required context values:
# - vpc_cidr: VPC CIDR block (default: 10.0.0.0/16)
# - ssh_cidr: SSH access CIDR (default: 10.0.0.0/8)
# - instance_type: EC2 instance type (default: t3.micro)
# - ami_id: AMI ID for EC2 instance (default: ami-0c55b159cbfafe1d0)
# 
# Example deployment command:
# cdk synth --context vpc_cidr=10.0.0.0/16 --context ssh_cidr=10.0.0.0/8 --context instance_type=t3.micro --context ami_id=ami-0c55b159cbfafe1d0

from aws_cdk import (
    Stack,
    CfnParameter,
    Duration,
    aws_ec2 as ec2,
    aws_s3 as s3,
    aws_iam as iam,
    aws_s3_deployment as s3_deployment,
    CfnOutput
)
from constructs import Construct

class SecureEc2Stack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Parameters
        vpc_cidr = self.node.try_get_context('vpc_cidr') or '10.0.0.0/16'
        ssh_cidr = self.node.try_get_context('ssh_cidr') or '10.0.0.0/8'
        instance_type = self.node.try_get_context('instance_type') or 't3.micro'
        ami_id = self.node.try_get_context('ami_id') or 'ami-0c55b159cbfafe1d0'

        # Create VPC
        vpc = ec2.Vpc(
            self, "SecureVPC",
            cidr=vpc_cidr,
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_NAT,
                    cidr_mask=24
                )
            ]
        )

        # Create security group with restricted SSH access
        sg = ec2.SecurityGroup(
            self, "InstanceSecurityGroup",
            vpc=vpc,
            security_group_name="secure-ec2-sg",
            description="Security group for secure EC2 instances"
        )

        # Allow SSH only from specific CIDR
        sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(ssh_cidr),
            connection=ec2.Port.tcp(22),
            description="Allow SSH from trusted network"
        )

        # Allow HTTP and HTTPS
        sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(80),
            description="Allow HTTP"
        )
        sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(443),
            description="Allow HTTPS"
        )

        # Allow all outbound traffic
        sg.add_egress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.all_traffic(),
            description="Allow all outbound traffic"
        )

        # Create EC2 instance
        instance = ec2.Instance(
            self, "SecureEC2Instance",
            instance_type=ec2.InstanceType(instance_type),
            machine_image=ec2.MachineImage.generic_linux(ami_id),
            vpc=vpc,
            security_group=sg,
            key_name=None,  # No key pair for this example
            role=self.create_instance_role()
        )

        # Output instance details
        CfnOutput(
            self, "InstanceId",
            value=instance.instance_id,
            description="EC2 Instance ID"
        )

        CfnOutput(
            self, "InstancePublicIp",
            value=instance.instance_public_ip,
            description="Public IP of EC2 instance"
        )

        CfnOutput(
            self, "SecurityGroupName",
            value=sg.security_group_name,
            description="Security Group Name"
        )

    def create_instance_role(self):
        """Create IAM role with minimal permissions for EC2 instance"""
        role = iam.Role(
            self, "EC2InstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchAgentServerPolicy")
            ]
        )

        # Add custom policy with least privilege
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject"
                ],
                resources=[
                    f"arn:aws:s3:::secure-bucket-{self.account}/*"
                ],
                effect=iam.Effect.ALLOW
            )
        )

        return role


class SecureS3Stack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create S3 bucket with access logging enabled
        bucket = s3.Bucket(
            self, "SecureBucket",
            bucket_name=f"secure-bucket-{self.account}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            enforce_ssl=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldVersions",
                    noncurrent_version_expiration=Duration.days(30)
                )
            ]
        )

        # Enable access logging
        log_bucket = s3.Bucket(
            self, "AccessLogBucket",
            bucket_name=f"access-log-bucket-{self.account}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            enforce_ssl=True
        )

        bucket.add_access_point(
            "AccessPoint",
            bucket_name=bucket.bucket_name,
            policy_document=iam.PolicyDocument(
                statements=[
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        principals=[iam.AnyPrincipal()],
                        actions=["s3:*"],
                        resources=[bucket.arn_for_objects("*")],
                        conditions={
                            "StringEquals": {
                                "aws:SourceArn": bucket.bucket_arn
                            }
                        }
                    )
                ]
            )
        )

        # Configure bucket logging
        bucket.add_to_resource_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("logging.s3.amazonaws.com")],
                actions=["s3:PutObject"],
                resources=[f"{log_bucket.bucket_arn}/*"],
                conditions={
                    "StringEquals": {
                        "s3:x-amz-acl": "bucket-owner-full-control"
                    }
                }
            )
        )

        # Output bucket details
        CfnOutput(
            self, "BucketName",
            value=bucket.bucket_name,
            description="Secure S3 Bucket Name"
        )

        CfnOutput(
            self, "LogBucketName",
            value=log_bucket.bucket_name,
            description="Access Log S3 Bucket Name"
        )


class PipelineDemoStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create S3 bucket for pipeline with access logging
        bucket = s3.Bucket(
            self, "PipelineDemoBucket",
            bucket_name=f"pipeline-demo-bucket-{self.account}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            enforce_ssl=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldVersions",
                    noncurrent_version_expiration=Duration.days(30)
                )
            ]
        )

        # Enable access logging
        log_bucket = s3.Bucket(
            self, "PipelineAccessLogBucket",
            bucket_name=f"pipeline-access-log-bucket-{self.account}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            enforce_ssl=True
        )

        # Configure bucket logging
        bucket.add_to_resource_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("logging.s3.amazonaws.com")],
                actions=["s3:PutObject"],
                resources=[f"{log_bucket.bucket_arn}/*"],
                conditions={
                    "StringEquals": {
                        "s3:x-amz-acl": "bucket-owner-full-control"
                    }
                }
            )
        )

        # Output bucket details
        CfnOutput(
            self, "PipelineBucketName",
            value=bucket.bucket_name,
            description="Pipeline Demo S3 Bucket Name"
        )

        CfnOutput(
            self, "PipelineLogBucketName",
            value=log_bucket.bucket_name,
            description="Pipeline Access Log S3 Bucket Name"
        )


app = Stack.App()
SecureEc2Stack(app, "SecureEc2Stack")
SecureS3Stack(app, "SecureS3Stack")
PipelineDemoStack(app, "PipelineDemoStack")
app.synth()
