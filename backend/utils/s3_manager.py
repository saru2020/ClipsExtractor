import os
import boto3
from botocore.exceptions import ClientError
import logging
import traceback
import shutil
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class S3Manager:
    def __init__(self):
        logger.info("Initializing S3Manager")
        
        # Check if AWS credentials are configured
        aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        aws_region = os.getenv('AWS_REGION')
        self.bucket_name = os.getenv('S3_BUCKET_NAME')
        
        if not all([aws_access_key, aws_secret_key, aws_region, self.bucket_name]):
            logger.warning("AWS credentials not fully configured in environment variables")
            logger.warning("Using mock S3 implementation for development")
            self.mock_mode = True
            self.mock_storage_dir = os.path.join(os.getcwd(), 'local_storage')
            os.makedirs(self.mock_storage_dir, exist_ok=True)
            logger.info(f"Using local storage directory: {self.mock_storage_dir}")
        else:
            logger.info(f"Connecting to AWS S3 in region {aws_region}")
            try:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=aws_access_key,
                    aws_secret_access_key=aws_secret_key,
                    region_name=aws_region
                )
                self.mock_mode = False
                logger.info(f"S3 client initialized, using bucket: {self.bucket_name}")
            except Exception as e:
                logger.error(f"Failed to initialize S3 client: {str(e)}")
                logger.error(traceback.format_exc())
                raise
        
    def upload_file(self, file_path, object_name=None):
        """Upload a file to S3 bucket and return the S3 URI."""
        logger.info(f"Uploading file {file_path} to S3")
        
        if not os.path.exists(file_path):
            error_msg = f"File does not exist: {file_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
            
        if object_name is None:
            object_name = os.path.basename(file_path)
            
        # Check file size for logging
        file_size = os.path.getsize(file_path)
        logger.info(f"File size: {file_size} bytes")
        
        # Handle mock mode for development without AWS
        if getattr(self, 'mock_mode', False):
            # Create directory structure if needed
            mock_object_path = os.path.join(self.mock_storage_dir, self.bucket_name, object_name)
            os.makedirs(os.path.dirname(mock_object_path), exist_ok=True)
            
            # Copy the file to the mock location
            logger.info(f"MOCK: Copying file to {mock_object_path}")
            shutil.copy2(file_path, mock_object_path)
            
            return f"s3://{self.bucket_name}/{object_name}"
        
        try:
            logger.info(f"Uploading to S3: {file_path} -> s3://{self.bucket_name}/{object_name}")
            self.s3_client.upload_file(file_path, self.bucket_name, object_name)
            logger.info(f"Upload successful: s3://{self.bucket_name}/{object_name}")
            return f"s3://{self.bucket_name}/{object_name}"
        except ClientError as e:
            logger.error(f"Error uploading file to S3: {str(e)}")
            logger.error(traceback.format_exc())
            raise
        except Exception as e:
            logger.error(f"Unexpected error uploading file to S3: {str(e)}")
            logger.error(traceback.format_exc())
            raise
            
    def generate_presigned_url(self, object_name, expiration=3600):
        """Generate a presigned URL for an S3 object."""
        logger.info(f"Generating presigned URL for {object_name}, expiration {expiration}s")
        
        # Handle mock mode for development without AWS
        if getattr(self, 'mock_mode', False):
            # In mock mode, generate a URL that points to our static file server
            mock_url = f"http://localhost:8000/mock-s3/{self.bucket_name}/{object_name}"
            logger.info(f"MOCK: Generated URL: {mock_url}")
            return mock_url
        
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': object_name},
                ExpiresIn=expiration
            )
            logger.info(f"Generated presigned URL: {url[:100]}...")
            return url
        except ClientError as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            logger.error(traceback.format_exc())
            raise
        except Exception as e:
            logger.error(f"Unexpected error generating presigned URL: {str(e)}")
            logger.error(traceback.format_exc())
            raise
            
    def download_file(self, object_name, file_path):
        """Download a file from S3 bucket."""
        logger.info(f"Downloading file from S3: {object_name} -> {file_path}")
        
        # Handle mock mode for development without AWS
        if getattr(self, 'mock_mode', False):
            mock_object_path = os.path.join(self.mock_storage_dir, self.bucket_name, object_name)
            
            if not os.path.exists(mock_object_path):
                error_msg = f"Mock file does not exist: {mock_object_path}"
                logger.error(error_msg)
                raise FileNotFoundError(error_msg)
                
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            logger.info(f"MOCK: Copying {mock_object_path} to {file_path}")
            shutil.copy2(mock_object_path, file_path)
            return file_path
        
        try:
            # Create the directory if it doesn't exist
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            self.s3_client.download_file(self.bucket_name, object_name, file_path)
            logger.info(f"Download successful: {file_path}")
            
            # Verify the download
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Downloaded file not found: {file_path}")
                
            file_size = os.path.getsize(file_path)
            logger.info(f"Downloaded file size: {file_size} bytes")
            
            if file_size == 0:
                logger.warning(f"Downloaded file is empty: {file_path}")
                
            return file_path
        except ClientError as e:
            logger.error(f"Error downloading file from S3: {str(e)}")
            logger.error(traceback.format_exc())
            raise
        except Exception as e:
            logger.error(f"Unexpected error downloading file from S3: {str(e)}")
            logger.error(traceback.format_exc())
            raise
