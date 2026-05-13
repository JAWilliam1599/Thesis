import boto3
import time
from botocore.exceptions import ClientError

def create_vpc_and_resources():
    """Create VPC with EC2 instance and RDS instance"""
    
    # Initialize clients
    ec2 = boto3.client('ec2', region_name='us-east-1')
    rds = boto3.client('rds', region_name='us-east-1')
    
    print("Creating VPC...")
    try:
        # Create VPC
        vpc_response = ec2.create_vpc(CidrBlock='10.0.0.0/16')
        vpc_id = vpc_response['Vpc']['VpcId']
        print(f"VPC created: {vpc_id}")
        
        # Enable DNS hostnames
        ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={'Value': True})
        
        # Enable DNS support
        ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={'Value': True})
        
        # Create Internet Gateway
        igw_response = ec2.create_internet_gateway()
        igw_id = igw_response['InternetGateway']['InternetGatewayId']
        print(f"Internet Gateway created: {igw_id}")
        
        # Attach Internet Gateway to VPC
        ec2.attach_internet_gateway(
            InternetGatewayId=igw_id,
            VpcId=vpc_id
        )
        
        # Create subnet
        subnet_response = ec2.create_subnet(
            VpcId=vpc_id,
            CidrBlock='10.0.1.0/24'
        )
        subnet_id = subnet_response['Subnet']['SubnetId']
        print(f"Subnet created: {subnet_id}")
        
        # Create route table
        route_table_response = ec2.create_route_table(VpcId=vpc_id)
        route_table_id = route_table_response['RouteTable']['RouteTableId']
        print(f"Route table created: {route_table_id}")
        
        # Add route to Internet Gateway
        ec2.create_route(
            RouteTableId=route_table_id,
            DestinationCidrBlock='0.0.0.0/0',
            GatewayId=igw_id
        )
        
        # Associate subnet with route table
        ec2.associate_route_table(
            RouteTableId=route_table_id,
            SubnetId=subnet_id
        )
        
        # Create security group for EC2
        sg_response = ec2.create_security_group(
            GroupName='ec2-sg',
            Description='Security group for EC2 instance',
            VpcId=vpc_id
        )
        sg_id = sg_response['GroupId']
        print(f"Security group created: {sg_id}")
        
        # Add inbound rules to security group
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
        
        # Create EC2 instance
        print("Creating EC2 instance...")
        ec2_response = ec2.run_instances(
            ImageId='ami-0c55b159cbfafe1d0',  # Amazon Linux 2
            MinCount=1,
            MaxCount=1,
            InstanceType='t2.micro',
            KeyName='my-key-pair',  # Make sure this key exists or create it
            SecurityGroupIds=[sg_id],
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
        waiter = ec2.get_waiter('instance_running')
        waiter.wait(InstanceIds=[ec2_instance_id])
        print("EC2 instance is running")
        
        # Create RDS instance
        print("Creating RDS instance...")
        rds_response = rds.create_db_instance(
            DBInstanceIdentifier='my-rds-instance',
            DBInstanceClass='db.t2.micro',
            Engine='mysql',
            MasterUsername='admin',
            MasterUserPassword='password123',
            AllocatedStorage=20,
            VpcSecurityGroupIds=[sg_id],
            DBSubnetGroupName='my-db-subnet-group',  # This needs to be created
            MultiAZ=False,
            PubliclyAccessible=True
        )
        print("RDS instance creation initiated")
        
        # Create DB subnet group
        try:
            db_subnet_group = rds.create_db_subnet_group(
                DBSubnetGroupName='my-db-subnet-group',
                DBSubnetGroupDescription='Subnet group for RDS',
                SubnetIds=[subnet_id]
            )
            print("DB subnet group created")
        except ClientError as e:
            if e.response['Error']['Code'] == 'DBSubnetGroupAlreadyExistsFault':
                print("DB subnet group already exists")
            else:
                raise e
        
        # Wait for RDS instance to be available
        rds_waiter = rds.get_waiter('db_instance_available')
        rds_waiter.wait(DBInstanceIdentifier='my-rds-instance')
        print("RDS instance is available")
        
        return {
            'vpc_id': vpc_id,
            'ec2_instance_id': ec2_instance_id,
            'rds_instance_identifier': 'my-rds-instance'
        }
        
    except ClientError as e:
        print(f"Error occurred: {e}")
        return None

def main():
    """Main function to execute the deployment"""
    print("Starting VPC, EC2, and RDS deployment...")
    result = create_vpc_and_resources()
    if result:
        print("Deployment completed successfully!")
        print(f"VPC ID: {result['vpc_id']}")
        print(f"EC2 Instance ID: {result['ec2_instance_id']}")
        print(f"RDS Instance Identifier: {result['rds_instance_identifier']}")
    else:
        print("Deployment failed!")

if __name__ == "__main__":
    main()
