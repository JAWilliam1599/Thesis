import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import json

def create_s3_bucket(bucket_name, region='us-east-1'):
    """
    Create an S3 bucket in a specified region
    
    :param bucket_name: Bucket to create
    :param region: Region to create bucket in
    :return: True if bucket created, else False
    """
    try:
        s3_client = boto3.client('s3', region_name=region)
        if region == 'us-east-1':
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={'LocationConstraint': region}
            )
        print(f"Bucket {bucket_name} created successfully")
        return True
    except ClientError as e:
        print(f"Error creating bucket: {e}")
        return False
    except NoCredentialsError:
        print("AWS credentials not found")
        return False

def list_s3_buckets():
    """
    List all S3 buckets
    
    :return: List of bucket names or None
    """
    try:
        s3_client = boto3.client('s3')
        response = s3_client.list_buckets()
        buckets = [bucket['Name'] for bucket in response['Buckets']]
        print("S3 Buckets:")
        for bucket in buckets:
            print(f"  {bucket}")
        return buckets
    except ClientError as e:
        print(f"Error listing buckets: {e}")
        return None
    except NoCredentialsError:
        print("AWS credentials not found")
        return None

def upload_file_to_s3(file_path, bucket_name, object_name=None):
    """
    Upload a file to an S3 bucket
    
    :param file_path: Path to file to upload
    :param bucket_name: Bucket to upload to
    :param object_name: S3 object name. If not specified, file_path name is used
    :return: True if file was uploaded, else False
    """
    if object_name is None:
        object_name = file_path.split('/')[-1]
    
    try:
        s3_client = boto3.client('s3')
        s3_client.upload_file(file_path, bucket_name, object_name)
        print(f"File {file_path} uploaded to {bucket_name}/{object_name}")
        return True
    except FileNotFoundError:
        print(f"The file {file_path} was not found")
        return False
    except ClientError as e:
        print(f"Error uploading file: {e}")
        return False
    except NoCredentialsError:
        print("AWS credentials not found")
        return False

def delete_s3_bucket(bucket_name):
    """
    Delete an S3 bucket
    
    :param bucket_name: Bucket to delete
    :return: True if bucket deleted, else False
    """
    try:
        s3_client = boto3.client('s3')
        # First delete all objects in the bucket
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name)
        
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    s3_client.delete_object(Bucket=bucket_name, Key=obj['Key'])
        
        # Then delete the bucket
        s3_client.delete_bucket(Bucket=bucket_name)
        print(f"Bucket {bucket_name} deleted successfully")
        return True
    except ClientError as e:
        print(f"Error deleting bucket: {e}")
        return False
    except NoCredentialsError:
        print("AWS credentials not found")
        return False

def main():
    """Main function to demonstrate AWS S3 operations"""
    print("Starting AWS S3 Operations Demo")
    
    # Example usage
    bucket_name = "my-test-bucket-12345"  # Use a unique name
    region = "us-west-2"
    
    # Create a bucket
    if create_s3_bucket(bucket_name, region):
        # List buckets
        list_s3_buckets()
        
        # Upload a test file (you'll need to create a test file first)
        # upload_file_to_s3("test.txt", bucket_name)
        
        # Delete the bucket
        # delete_s3_bucket(bucket_name)

if __name__ == "__main__":
    main()
