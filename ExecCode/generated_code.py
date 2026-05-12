import boto3
import time
from botocore.exceptions import ClientError

def create_vpc():
    """Create a VPC with public and private subnets"""
    ec2 = boto3.client('ec2')
    
    # Create VPC
    vpc_response = ec2.create_vpc(CidrBlock='10.0.0.0/16')
    vpc_id = vpc_response['Vpc']['VpcId']
    
    # Enable DNS hostnames
    ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={'Value': True})
    
    # Create Internet Gateway
    igw_response = ec2.create_internet_gateway()
    igw_id = igw_response['InternetGateway']['InternetGatewayId']
    
    # Attach Internet Gateway to VPC
    ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
    
    # Create public subnet
    public_subnet = ec2.create_subnet(VpcId=vpc_id, CidrBlock='10.0.1.0/24', AvailabilityZone='us-east-1a')
    public_subnet_id = public_subnet['Subnet']['SubnetId']
    
    # Create private subnet
    private_subnet = ec2.create_subnet(VpcId=vpc_id, CidrBlock='10.0.2.0/24', AvailabilityZone='us-east-1a')
    private_subnet_id = private_subnet['Subnet']['SubnetId']
    
    # Create route table for public subnet
    route_table = ec2.create_route_table(VpcId=vpc_id)
    route_table_id = route_table['RouteTable']['RouteTableId']
    
    # Add route to Internet Gateway
    ec2.create_route(RouteTableId=route_table_id, DestinationCidrBlock='0.0.0.0/0', GatewayId=igw_id)
    
    # Associate public subnet with route table
    ec2.associate_route_table(RouteTableId=route_table_id, SubnetId=public_subnet_id)
    
    return vpc_id, public_subnet_id, private_subnet_id, igw_id

def create_ec2_instance(vpc_id, subnet_id):
    """Create EC2 instance in the VPC"""
    ec2 = boto3.client('ec2')
    
    # Create security group
    sg_response = ec2.create_security_group(
        GroupName='web-sg',
        Description='Security group for web server',
        VpcId=vpc_id
    )
    sg_id = sg_response['GroupId']
    
    # Add inbound rules
    ec2.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[
            {
                'IpProtocol': 'tcp',
                'FromPort': 22,
                'ToPort': 22,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
            },
            {
                'IpProtocol': 'tcp',
                'FromPort': 80,
                'ToPort': 80,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
            }
        ]
    )
    
    # Launch EC2 instance
    instance_response = ec2.run_instances(
        ImageId='ami-0c55b159cbfafe1d0',  # Amazon Linux 2
        MinCount=1,
        MaxCount=1,
        InstanceType='t2.micro',
        KeyName='my-key-pair',  # Make sure this key exists
        SecurityGroupIds=[sg_id],
        SubnetId=subnet_id,
        TagSpecifications=[
            {
                'ResourceType': 'instance',
                'Tags': [
                    {
                        'Key': 'Name',
                        'Value': 'web-server'
                    }
                ]
            }
        ]
    )
    
    instance_id = instance_response['Instances'][0]['InstanceId']
    return instance_id, sg_id

def create_rds_instance(vpc_id, subnet_id):
    """Create RDS instance in the VPC"""
    rds = boto3.client('rds')
    
    # Create DB subnet group
    db_subnet_group = rds.create_db_subnet_group(
        DBSubnetGroupName='my-db-subnet-group',
        DBSubnetGroupDescription='Subnet group for RDS instance',
        SubnetIds=[subnet_id]
    )
    
    # Create DB instance
    db_response = rds.create_db_instance(
        DBInstanceIdentifier='my-db-instance',
        DBInstanceClass='db.t2.micro',
        Engine='mysql',
        MasterUsername='admin',
        MasterUserPassword='password123',
        AllocatedStorage=20,
        VpcSecurityGroupIds=['sg-12345678'],  # Replace with actual security group ID
        DBSubnetGroupName='my-db-subnet-group',
        MultiAZ=False,
        PubliclyAccessible=False,
        Tags=[
            {
                'Key': 'Name',
                'Value': 'my-db-instance'
            }
        ]
    )
    
    return db_response['DBInstance']['DBInstanceIdentifier']

def main():
    """Main function to create VPC, EC2, and RDS instances"""
    try:
        print("Creating VPC...")
        vpc_id, public_subnet_id, private_subnet_id, igw_id = create_vpc()
        print(f"VPC created: {vpc_id}")
        
        print("Creating EC2 instance...")
        instance_id, sg_id = create_ec2_instance(vpc_id, public_subnet_id)
        print(f"EC2 instance created: {instance_id}")
        
        print("Creating RDS instance...")
        db_instance_id = create_rds_instance(vpc_id, private_subnet_id)
        print(f"RDS instance created: {db_instance_id}")
        
        print("All resources created successfully!")
        
    except ClientError as e:
        print(f"Error creating resources: {e}")

if __name__ == "__main__":
    main()
