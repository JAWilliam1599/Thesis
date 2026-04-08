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

def upload_file_to_s3(file_path, bucket_name, object_name=None):
    """
    Upload a file to an S3 bucket
    
    :param file_path: Path to file to upload
    :param bucket_name: Bucket to upload to
    :param object_name: S3 object name. If not specified, file_path name is used
    :return: True if file was uploaded, else False
    """
    # If S3 object_name was not specified, use file_path name
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

def list_s3_buckets():
    """
    List all S3 buckets
    
    :return: List of bucket names or None if error
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

def main():
    """Main function to demonstrate S3 operations"""
    # Example usage
    bucket_name = 'my-test-bucket-12345'  # Change to your desired bucket name
    
    # List existing buckets
    list_s3_buckets()
    
    # Create a new bucket
    create_s3_bucket(bucket_name, 'us-west-2')
    
    # Note: For uploading files, you would need to have a local file
    # upload_file_to_s3('local_file.txt', bucket_name, 'remote_file.txt')

if __name__ == "__main__":
    main()
