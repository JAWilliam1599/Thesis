import boto3

def create_ec2_instance():
    ec2 = boto3.resource('ec2')
    
    instance = ec2.create_instances(
        ImageId='ami-0c55b159cbfafe1f0',  # Amazon Linux 2 AMI (us-east-1)
        InstanceType='t2.micro',
        MinCount=1,
        MaxCount=1,
        KeyName='your-key-pair-name',  # Replace with your key pair name
        SecurityGroupIds=['sg-xxxxxxxx'],  # Replace with your security group ID
        SubnetId='subnet-xxxxxxxx'  # Replace with your subnet ID
    )
    
    instance_id = instance[0].id
    print(f"EC2 instance created with ID: {instance_id}")
    return instance_id

def main():
    try:
        create_ec2_instance()
    except Exception as e:
        print(f"Error creating EC2 instance: {e}")

if __name__ == "__main__":
    main()
