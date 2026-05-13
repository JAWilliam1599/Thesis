import boto3
import time
from botocore.exceptions import ClientError

def create_vpc_with_ec2_and_rds():
    """Create a VPC with EC2 instance and RDS database"""
    
    # Create clients
    ec2 = boto3.client('ec2', region_name='us-east-1')
    rds = boto3.client('rds', region_name='us-east-1')
    
    try:
        # Create VPC
        print("Creating VPC...")
        vpc_response = ec2.create_vpc(CidrBlock='10.0.0.0/16')
        vpc_id = vpc_response['Vpc']['VpcId']
        print(f"VPC created: {vpc_id}")
        
        # Enable DNS hostnames and DNS resolution
        ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames=True)
        ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport=True)
        
        # Create Internet Gateway
        print("Creating Internet Gateway...")
        igw_response = ec2.create_internet_gateway()
        igw_id = igw_response['InternetGateway']['InternetGatewayId']
        print(f"Internet Gateway created: {igw_id}")
        
        # Attach Internet Gateway to VPC
        ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
        print("Internet Gateway attached to VPC")
        
        # Create subnet
        print("Creating subnet...")
        subnet_response = ec2.create_subnet(VpcId=vpc_id, CidrBlock='10.0.1.0/24')
        subnet_id = subnet_response['Subnet']['SubnetId']
        print(f"Subnet created: {subnet_id}")
        
        # Create route table
        print("Creating route table...")
        route_table_response = ec2.create_route_table(VpcId=vpc_id)
        route_table_id = route_table_response['RouteTable']['RouteTableId']
        print(f"Route table created: {route_table_id}")
        
        # Add route to Internet Gateway
        ec2.create_route(RouteTableId=route_table_id, DestinationCidrBlock='0.0.0.0/0', GatewayId=igw_id)
        print("Route added to Internet Gateway")
        
        # Associate subnet with route table
        ec2.associate_route_table(RouteTableId=route_table_id, SubnetId=subnet_id)
        print("Subnet associated with route table")
        
        # Create security group for EC2
        print("Creating EC2 security group...")
        sg_response = ec2.create_security_group(
            GroupName='ec2-sg',
            Description='Security group for EC2 instance',
            VpcId=vpc_id
        )
        ec2_sg_id = sg_response['GroupId']
        print(f"EC2 Security group created: {ec2_sg_id}")
        
        # Add rules to security group
        ec2.authorize_security_group_ingress(
            GroupId=ec2_sg_id,
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
        print("Security group rules added")
        
        # Create security group for RDS
        print("Creating RDS security group...")
        rds_sg_response = ec2.create_security_group(
            GroupName='rds-sg',
            Description='Security group for RDS database',
            VpcId=vpc_id
        )
        rds_sg_id = rds_sg_response['GroupId']
        print(f"RDS Security group created: {rds_sg_id}")
        
        # Add rules to RDS security group
        ec2.authorize_security_group_ingress(
            GroupId=rds_sg_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 3306,
                    'ToPort': 3306,
                    'UserIdGroupPairs': [{'GroupId': ec2_sg_id}]
                }
            ]
        )
        print("RDS security group rules added")
        
        # Create EC2 instance
        print("Creating EC2 instance...")
        ec2_response = ec2.run_instances(
            ImageId='ami-0c55b159cbfafe1d0',  # Amazon Linux 2
            MinCount=1,
            MaxCount=1,
            InstanceType='t2.micro',
            KeyName='my-key-pair',  # Make sure this key exists or create it first
            SecurityGroupIds=[ec2_sg_id],
            SubnetId=subnet_id,
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': 'my-ec2-instance'
                        }
                    ]
                }
            ]
        )
        ec2_instance_id = ec2_response['Instances'][0]['InstanceId']
        print(f"EC2 instance created: {ec2_instance_id}")
        
        # Wait for instance to be running
        print("Waiting for EC2 instance to be running...")
        waiter = ec2.get_waiter('instance_running')
        waiter.wait(InstanceIds=[ec2_instance_id])
        print("EC2 instance is running")
        
        # Get public IP of EC2 instance
        instance_response = ec2.describe_instances(InstanceIds=[ec2_instance_id])
        public_ip = instance_response['Reservations'][0]['Instances'][0]['PublicIpAddress']
        print(f"EC2 instance public IP: {public_ip}")
        
        # Create RDS instance
        print("Creating RDS instance...")
        rds_response = rds.create_db_instance(
            DBInstanceIdentifier='my-rds-instance',
            DBInstanceClass='db.t2.micro',
            Engine='mysql',
            MasterUsername='admin',
            MasterUserPassword='password123',
            AllocatedStorage=20,
            VpcSecurityGroupIds=[rds_sg_id],
            DBSubnetGroupName='my-db-subnet-group',
            MultiAZ=False,
            PubliclyAccessible=True
        )
        print("RDS instance creation initiated")
        
        # Wait for RDS instance to be available
        print("Waiting for RDS instance to be available...")
        rds_waiter = rds.get_waiter('db_instance_available')
        rds_waiter.wait(DBInstanceIdentifier='my-rds-instance')
        print("RDS instance is available")
        
        # Get RDS endpoint
        rds_instance = rds.describe_db_instances(DBInstanceIdentifier='my-rds-instance')
        rds_endpoint = rds_instance['DBInstances'][0]['Endpoint']['Address']
        print(f"RDS endpoint: {rds_endpoint}")
        
        print("\n=== Summary ===")
        print(f"VPC ID: {vpc_id}")
        print(f"EC2 Instance ID: {ec2_instance_id}")
        print(f"EC2 Public IP: {public_ip}")
        print(f"RDS Endpoint: {rds_endpoint}")
        
        return {
            'vpc_id': vpc_id,
            'ec2_instance_id': ec2_instance_id,
            'rds_endpoint': rds_endpoint
        }
        
    except ClientError as e:
        print(f"Error: {e}")
        return None

def main():
    """Main function to execute the VPC, EC2, and RDS creation"""
    print("Starting VPC, EC2, and RDS creation...")
    result = create_vpc_with_ec2_and_rds()
    
    if result:
        print("\nSuccessfully created VPC with EC2 and RDS!")
    else:
        print("\nFailed to create VPC with EC2 and RDS.")

if __name__ == "__main__":
    main()
