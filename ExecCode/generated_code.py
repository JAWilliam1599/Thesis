import boto3
import time
from botocore.exceptions import ClientError

def create_vpc_and_instance():
    """Create a VPC with an EC2 instance"""
    
    # Create EC2 and VPC clients
    ec2 = boto3.client('ec2')
    vpc = boto3.client('ec2')
    
    try:
        # Create VPC
        print("Creating VPC...")
        vpc_response = ec2.create_vpc(CidrBlock='10.0.0.0/16')
        vpc_id = vpc_response['Vpc']['VpcId']
        print(f"VPC created with ID: {vpc_id}")
        
        # Enable DNS hostnames and DNS resolution for the VPC
        ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames=True)
        ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport=True)
        
        # Create Internet Gateway
        print("Creating Internet Gateway...")
        igw_response = ec2.create_internet_gateway()
        igw_id = igw_response['InternetGateway']['InternetGatewayId']
        print(f"Internet Gateway created with ID: {igw_id}")
        
        # Attach Internet Gateway to VPC
        print("Attaching Internet Gateway to VPC...")
        ec2.attach_internet_gateway(
            InternetGatewayId=igw_id,
            VpcId=vpc_id
        )
        
        # Create subnet
        print("Creating subnet...")
        subnet_response = ec2.create_subnet(
            VpcId=vpc_id,
            CidrBlock='10.0.1.0/24'
        )
        subnet_id = subnet_response['Subnet']['SubnetId']
        print(f"Subnet created with ID: {subnet_id}")
        
        # Create route table
        print("Creating route table...")
        route_table_response = ec2.create_route_table(VpcId=vpc_id)
        route_table_id = route_table_response['RouteTable']['RouteTableId']
        print(f"Route table created with ID: {route_table_id}")
        
        # Add route to Internet Gateway
        print("Adding route to Internet Gateway...")
        ec2.create_route(
            RouteTableId=route_table_id,
            DestinationCidrBlock='0.0.0.0/0',
            GatewayId=igw_id
        )
        
        # Associate subnet with route table
        print("Associating subnet with route table...")
        ec2.associate_route_table(
            RouteTableId=route_table_id,
            SubnetId=subnet_id
        )
        
        # Create security group
        print("Creating security group...")
        sg_response = ec2.create_security_group(
            GroupName='web-sg',
            Description='Security group for web server',
            VpcId=vpc_id
        )
        sg_id = sg_response['GroupId']
        print(f"Security group created with ID: {sg_id}")
        
        # Add inbound rules to security group
        print("Adding inbound rules to security group...")
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
        
        # Create EC2 key pair (optional, for SSH access)
        print("Creating key pair...")
        try:
            key_pair = ec2.create_key_pair(KeyName='my-key-pair')
            print("Key pair created successfully")
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidKeyPair.Duplicate':
                print("Key pair already exists, using existing one")
            else:
                raise e
        
        # Launch EC2 instance
        print("Launching EC2 instance...")
        instance_response = ec2.run_instances(
            ImageId='ami-0c55b159cbfafe1d0',  # Amazon Linux 2
            MinCount=1,
            MaxCount=1,
            InstanceType='t2.micro',
            KeyName='my-key-pair',
            SecurityGroupIds=[sg_id],
            SubnetId=subnet_id,
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': 'MyVPC-Instance'
                        }
                    ]
                }
            ]
        )
        
        instance_id = instance_response['Instances'][0]['InstanceId']
        print(f"EC2 instance launched with ID: {instance_id}")
        
        # Wait for instance to be running
        print("Waiting for instance to be running...")
        waiter = ec2.get_waiter('instance_running')
        waiter.wait(InstanceIds=[instance_id])
        
        # Get instance public IP
        instance_details = ec2.describe_instances(InstanceIds=[instance_id])
        public_ip = instance_details['Reservations'][0]['Instances'][0].get('PublicIpAddress')
        print(f"Instance is running with public IP: {public_ip}")
        
        # Print summary
        print("\n=== VPC and EC2 Setup Complete ===")
        print(f"VPC ID: {vpc_id}")
        print(f"Subnet ID: {subnet_id}")
        print(f"Security Group ID: {sg_id}")
        print(f"Instance ID: {instance_id}")
        if public_ip:
            print(f"Public IP: {public_ip}")
        
        return {
            'vpc_id': vpc_id,
            'subnet_id': subnet_id,
            'sg_id': sg_id,
            'instance_id': instance_id,
            'public_ip': public_ip
        }
        
    except ClientError as e:
        print(f"Error creating VPC and instance: {e}")
        return None

def main():
    """Main function to execute the VPC and EC2 creation"""
    print("Starting VPC and EC2 creation...")
    result = create_vpc_and_instance()
    
    if result:
        print("\nSuccessfully created VPC and EC2 instance!")
    else:
        print("\nFailed to create VPC and EC2 instance.")

if __name__ == "__main__":
    main()
