import boto3
from botocore.exceptions import ClientError
import asyncio
from pathlib import Path
import logging
from typing import Optional
from .models import Config

logger = logging.getLogger(__name__)

class S3Uploader:
    _client = None
    _client_config_hash = None

    def __init__(self, config: Config):
        self.config = config
        self.bucket = config.s3_bucket
        
        # Reuse client if config hasn't changed
        current_hash = hash((config.aws_access_key, config.aws_secret_key, config.s3_region))
        
        if S3Uploader._client is None or S3Uploader._client_config_hash != current_hash:
            logger.info("Initializing new S3 client")
            S3Uploader._client = boto3.client(
                's3',
                aws_access_key_id=config.aws_access_key,
                aws_secret_access_key=config.aws_secret_key,
                region_name=config.s3_region
            )
            S3Uploader._client_config_hash = current_hash
            
        self.s3_client = S3Uploader._client

    async def upload_file(self, file_path: str, s3_key: str, max_retries: int = 3) -> bool:
        """Upload file to S3 with retry logic"""
        file_size = Path(file_path).stat().st_size
        logger.info(f"Uploading {file_path} ({file_size / (1024*1024):.1f} MB) to s3://{self.bucket}/{s3_key}")

        # Use multipart upload for files > 100MB
        if file_size > 100 * 1024 * 1024:
            return await self._multipart_upload(file_path, s3_key, max_retries)
        else:
            return await self._simple_upload(file_path, s3_key, max_retries)

    async def _simple_upload(self, file_path: str, s3_key: str, max_retries: int) -> bool:
        """Simple upload for smaller files"""
        for attempt in range(max_retries):
            try:
                # Run in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    self.s3_client.upload_file,
                    file_path,
                    self.bucket,
                    s3_key
                )
                logger.info(f"Successfully uploaded {s3_key}")
                return True
            except ClientError as e:
                logger.error(f"Upload attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

        return False

    async def _multipart_upload(self, file_path: str, s3_key: str, max_retries: int) -> bool:
        """Multipart upload for large files"""
        from boto3.s3.transfer import TransferConfig

        config = TransferConfig(
            multipart_threshold=100 * 1024 * 1024,
            max_concurrency=4,
            multipart_chunksize=25 * 1024 * 1024
        )

        for attempt in range(max_retries):
            try:
                # Run in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: self.s3_client.upload_file(
                        file_path,
                        self.bucket,
                        s3_key,
                        Config=config
                    )
                )
                logger.info(f"Successfully uploaded {s3_key} (multipart)")
                return True
            except ClientError as e:
                logger.error(f"Multipart upload attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)

        return False

    async def test_connection(self) -> bool:
        """Test AWS credentials and bucket access"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self.s3_client.head_bucket,
                Bucket=self.bucket
            )
            return True
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '403':
                raise ValueError("AWS credentials are invalid or lack permissions")
            elif error_code == '404':
                raise ValueError(f"S3 bucket '{self.bucket}' does not exist")
            else:
                raise ValueError(f"AWS connection failed: {str(e)}")

async def upload_to_s3(file_path: str, s3_key: str, config: Config) -> bool:
    """Convenience function to upload file to S3"""
    uploader = S3Uploader(config)
    return await uploader.upload_file(file_path, s3_key)

async def validate_aws_credentials(config: Config) -> bool:
    """Test AWS credentials before processing"""
    try:
        uploader = S3Uploader(config)
        await uploader.test_connection()
        return True
    except Exception as e:
        logger.error(f"AWS validation failed: {e}")
        raise