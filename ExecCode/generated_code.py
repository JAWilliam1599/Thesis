import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        logger.info(f"Bucket {bucket_name} created successfully")
        return True
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'BucketAlreadyExists':
            logger.error(f"Bucket {bucket_name} already exists")
        elif error_code == 'BucketAlreadyOwnedByYou':
            logger.info(f"Bucket {bucket_name} already exists and is owned by you")
            return True
        else:
            logger.error(f"Error creating bucket {bucket_name}: {e}")
        return False
    except NoCredentialsError:
        logger.error("AWS credentials not found")
        return False

def main():
    """Main function to demonstrate S3 bucket creation"""
    bucket_name = "my-test-bucket-12345"  # Use a unique name
    region = "us-west-2"
    
    success = create_s3_bucket(bucket_name, region)
    if success:
        logger.info("S3 bucket creation completed successfully")
    else:
        logger.error("Failed to create S3 bucket")

if __name__ == "__main__":
    main()
