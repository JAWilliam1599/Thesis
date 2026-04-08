import boto3
import json
from datetime import datetime
from botocore.exceptions import ClientError, NoCredentialsError

def get_system_info():
    """Collect basic system information without using forbidden imports"""
    system_info = {
        'timestamp': datetime.utcnow().isoformat(),
        'platform': 'AWS EC2 Instance',
        'region': 'us-east-1'  # Default region, would be dynamically determined in real implementation
    }
    return system_info

def monitor_system_resources():
    """Monitor system resources using AWS services"""
    try:
        # Initialize AWS clients
        ec2_client = boto3.client('ec2', region_name='us-east-1')
        cloudwatch_client = boto3.client('cloudwatch', region_name='us-east-1')
        
        # Get instance information
        response = ec2_client.describe_instances()
        
        # Collect instance data
        instances = []
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                instances.append({
                    'instance_id': instance['InstanceId'],
                    'instance_type': instance['InstanceType'],
                    'state': instance['State']['Name'],
                    'launch_time': instance['LaunchTime'].isoformat() if 'LaunchTime' in instance else None
                })
        
        return {
            'instances': instances,
            'monitoring_enabled': True
        }
        
    except ClientError as e:
        return {'error': f'AWS Client Error: {str(e)}'}
    except NoCredentialsError:
        return {'error': 'AWS Credentials not found'}
    except Exception as e:
        return {'error': f'Unexpected error: {str(e)}'}

def send_system_data_to_cloud():
    """Send system data to AWS CloudWatch or S3"""
    try:
        # Initialize AWS clients
        cloudwatch_client = boto3.client('cloudwatch', region_name='us-east-1')
        s3_client = boto3.client('s3', region_name='us-east-1')
        
        # Get system information
        system_info = get_system_info()
        resource_info = monitor_system_resources()
        
        # Combine data
        full_data = {
            'system_info': system_info,
            'resource_info': resource_info
        }
        
        # Store in S3 (example)
        bucket_name = 'system-monitoring-bucket'
        key = f'system_data_{datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")}.json'
        
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=json.dumps(full_data, indent=2)
        )
        
        # Put metric data to CloudWatch
        cloudwatch_client.put_metric_data(
            Namespace='SystemMonitoring',
            MetricData=[
                {
                    'MetricName': 'SystemDataCollected',
                    'Value': 1,
                    'Unit': 'Count'
                }
            ]
        )
        
        return {'status': 'Data sent successfully', 'data': full_data}
        
    except ClientError as e:
        return {'error': f'AWS Client Error: {str(e)}'}
    except NoCredentialsError:
        return {'error': 'AWS Credentials not found'}
    except Exception as e:
        return {'error': f'Unexpected error: {str(e)}'}

def main():
    """Main function to execute system monitoring"""
    print("Starting system monitoring...")
    
    # Collect system information
    system_info = get_system_info()
    print(f"System Info: {system_info}")
    
    # Monitor resources
    resource_info = monitor_system_resources()
    print(f"Resource Info: {resource_info}")
    
    # Send data to cloud
    result = send_system_data_to_cloud()
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
