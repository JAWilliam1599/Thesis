import boto3

# 1. Initialize connection
ec2 = boto3.resource('ec2', region_name='ap-southeast-2')

print("Starting EC2 instance provisioning...")

# 2. Create the instance
# Replace 'ami-0c55b159cbfafe1f0' with a valid AMI ID for your region!
instances = ec2.create_instances(
    ImageId='ami-098341ffb8b768450', 
    MinCount=1,
    MaxCount=1,
    InstanceType='t3.micro',
    TagSpecifications=[
        {
            'ResourceType': 'instance',
            'Tags': [
                {
                    'Key': 'Name',
                    'Value': 'Boto3-Test-Instance'
                },
            ]
        },
    ]
)

# 3. Get the instance object
instance = instances[0]

print(f"Instance created with ID: {instance.id}")
print("Waiting for the instance to reach the 'running' state...")

# 4. Wait until the instance is fully running
instance.wait_until_running()

# 5. Reload the instance attributes to get the assigned public IP
instance.reload()

print(f"Success! Instance is running.")
print(f"Public IP Address: {instance.public_ip_address}")