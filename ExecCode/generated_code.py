import boto3
from botocore.exceptions import ClientError

def create_ec2_instance(instance_type='t2.micro', image_id='ami-0c55b159cbfafe1d0', key_name=None, security_group='default'):
    """
    Create an EC2 instance
    
    Args:
        instance_type (str): Type of EC2 instance to create
        image_id (str): AMI ID to use for the instance
        key_name (str): Name of the key pair to use
        security_group (str): Name of the security group to use
    
    Returns:
        dict: Instance information or None if failed
    """
    try:
        # Create EC2 client
        ec2 = boto3.client('ec2')
        
        # Prepare instance launch parameters
        params = {
            'ImageId': image_id,
            'MinCount': 1,
            'MaxCount': 1,
            'InstanceType': instance_type,
            'SecurityGroups': [security_group]
        }
        
        # Add key pair if provided
        if key_name:
            params['KeyName'] = key_name
            
        # Launch instance
        response = ec2.run_instances(**params)
        
        instance = response['Instances'][0]
        print(f"Instance created successfully!")
        print(f"Instance ID: {instance['InstanceId']}")
        print(f"Instance Type: {instance['InstanceType']}")
        print(f"Public IP: {instance.get('PublicIpAddress', 'N/A')}")
        
        return {
            'instance_id': instance['InstanceId'],
            'instance_type': instance['InstanceType'],
            'public_ip': instance.get('PublicIpAddress', None)
        }
        
    except ClientError as e:
        print(f"Error creating EC2 instance: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None

def main():
    """Main function to demonstrate EC2 instance creation"""
    print("Creating EC2 instance...")
    
    # Create instance with default parameters
    instance_info = create_ec2_instance()
    
    if instance_info:
        print("\nInstance creation completed successfully!")
    else:
        print("\nFailed to create instance.")

if __name__ == "__main__":
    main()
