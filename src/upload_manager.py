#!/usr/bin/env python3

import os
import boto3
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from botocore.exceptions import ClientError, NoCredentialsError
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/basketball_upload.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class BasketballUploader:
    """
    Basketball video uploader for GoPro footage from Jetson Orin to AWS S3
    Handles 2-5GB MP4/M4A files with proper error handling and cleanup
    """

    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.bucket_name = os.getenv('S3_BUCKET_NAME', 'basketball-recordings-prod')
        self.aws_region = os.getenv('AWS_REGION', 'us-east-1')

        # Initialize S3 client
        try:
            self.s3_client = boto3.client(
                's3',
                region_name=self.aws_region,
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
            )
            logger.info(f"✅ AWS S3 client initialized for region: {self.aws_region}")
        except NoCredentialsError:
            logger.error("❌ AWS credentials not found. Check your .env file.")
            raise

        # Video processing settings
        self.supported_formats = {'.mp4', '.m4a', '.mov'}
        self.max_file_size = 6 * 1024 * 1024 * 1024  # 6GB limit
        self.chunk_size = 50 * 1024 * 1024  # 50MB chunks for upload

    def create_s3_bucket_if_not_exists(self) -> bool:
        """Create S3 bucket if it doesn't exist"""
        try:
            # Check if bucket exists
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"✅ S3 bucket '{self.bucket_name}' already exists")
            return True
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                try:
                    # Create bucket
                    if self.aws_region != 'us-east-1':
                        self.s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': self.aws_region}
                        )
                    else:
                        self.s3_client.create_bucket(Bucket=self.bucket_name)

                    logger.info(f"✅ Created S3 bucket: {self.bucket_name}")
                    return True
                except ClientError as create_error:
                    logger.error(f"❌ Failed to create bucket: {create_error}")
                    return False
            else:
                logger.error(f"❌ Error checking bucket: {e}")
                return False

    def validate_video_file(self, video_path: Path) -> bool:
        """Validate video file before upload"""
        if not video_path.exists():
            logger.error(f"❌ File not found: {video_path}")
            return False

        # Check file extension
        if video_path.suffix.lower() not in self.supported_formats:
            logger.error(f"❌ Unsupported format: {video_path.suffix}. Supported: {self.supported_formats}")
            return False

        # Check file size
        file_size = video_path.stat().st_size
        if file_size > self.max_file_size:
            logger.error(f"❌ File too large: {file_size / (1024**3):.2f}GB. Max: {self.max_file_size / (1024**3):.2f}GB")
            return False

        logger.info(f"✅ File validation passed: {video_path.name} ({file_size / (1024**2):.1f}MB)")
        return True

    def generate_s3_key(self, video_path: Path) -> str:
        """Generate S3 key with timestamp and game identifier"""
        timestamp = datetime.now().strftime('%Y/%m/%d/%H%M%S')
        filename = video_path.name

        # Create a simple hash for uniqueness
        file_hash = hashlib.md5(f"{timestamp}_{filename}".encode()).hexdigest()[:8]

        return f"basketball_games/{timestamp}/{file_hash}_{filename}"

    def upload_with_progress(self, video_path: Path, s3_key: str) -> bool:
        """Upload video file with progress tracking"""
        try:
            file_size = video_path.stat().st_size
            uploaded_size = 0

            def progress_callback(bytes_transferred):
                nonlocal uploaded_size
                uploaded_size += bytes_transferred
                progress = (uploaded_size / file_size) * 100
                print(f"\r🏀 Uploading... {progress:.1f}% ({uploaded_size / (1024**2):.1f}/{file_size / (1024**2):.1f}MB)", end='', flush=True)

            # Upload file with progress callback
            logger.info(f"🏀 Starting upload: {video_path.name} -> s3://{self.bucket_name}/{s3_key}")
            start_time = time.time()

            self.s3_client.upload_file(
                str(video_path),
                self.bucket_name,
                s3_key,
                Callback=progress_callback
            )

            upload_time = time.time() - start_time
            speed = file_size / upload_time / (1024**2)  # MB/s

            print()  # New line after progress
            logger.info(f"✅ Upload completed in {upload_time:.1f}s ({speed:.1f}MB/s)")
            logger.info(f"📍 S3 Location: s3://{self.bucket_name}/{s3_key}")

            return True

        except Exception as e:
            print()  # New line after progress
            logger.error(f"❌ Upload failed: {str(e)}")
            return False

    def cleanup_local_file(self, video_path: Path) -> bool:
        """Remove local file after successful upload"""
        if self.test_mode:
            logger.info(f"🧪 Test mode: Would delete {video_path}")
            return True

        try:
            video_path.unlink()
            logger.info(f"🗑️  Local file deleted: {video_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to delete local file: {e}")
            return False

    def upload_video(self, video_path: str) -> bool:
        """Main method to upload a single video file"""
        video_path = Path(video_path)

        # Validation
        if not self.validate_video_file(video_path):
            return False

        # Ensure S3 bucket exists
        if not self.create_s3_bucket_if_not_exists():
            return False

        # Generate S3 key
        s3_key = self.generate_s3_key(video_path)

        # Upload file
        if not self.upload_with_progress(video_path, s3_key):
            return False

        # Cleanup local file
        if not self.cleanup_local_file(video_path):
            logger.warning("⚠️  Upload successful but failed to clean up local file")

        logger.info(f"🎉 Successfully processed: {video_path.name}")
        return True

    def scan_and_upload_directory(self, directory_path: str) -> List[str]:
        """Scan directory for video files and upload them"""
        directory = Path(directory_path)
        if not directory.exists():
            logger.error(f"❌ Directory not found: {directory_path}")
            return []

        # Find video files
        video_files = []
        for ext in self.supported_formats:
            video_files.extend(directory.glob(f"*{ext}"))
            video_files.extend(directory.glob(f"*{ext.upper()}"))

        if not video_files:
            logger.info(f"📁 No video files found in: {directory_path}")
            return []

        logger.info(f"📁 Found {len(video_files)} video files to upload")

        # Upload each file
        successful_uploads = []
        failed_uploads = []

        for video_file in video_files:
            if self.upload_video(str(video_file)):
                successful_uploads.append(str(video_file))
            else:
                failed_uploads.append(str(video_file))

        logger.info(f"📊 Upload Summary: {len(successful_uploads)} successful, {len(failed_uploads)} failed")

        if failed_uploads:
            logger.error(f"❌ Failed uploads: {failed_uploads}")

        return successful_uploads

def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Basketball Video Uploader for Jetson Orin')
    parser.add_argument('--file', help='Upload single video file')
    parser.add_argument('--directory', help='Upload all videos from directory')
    parser.add_argument('--test-mode', action='store_true', help='Run in test mode (no file deletion)')

    args = parser.parse_args()

    uploader = BasketballUploader(test_mode=args.test_mode)

    if args.file:
        uploader.upload_video(args.file)
    elif args.directory:
        uploader.scan_and_upload_directory(args.directory)
    else:
        # Default: scan common GoPro import locations
        common_paths = [
            '/media/usb/DCIM/100GOPRO',
            '/media/usb0/DCIM/100GOPRO',
            '/mnt/gopro/DCIM/100GOPRO',
            './sample_videos'  # For testing
        ]

        for path in common_paths:
            if Path(path).exists():
                logger.info(f"🔍 Scanning: {path}")
                uploader.scan_and_upload_directory(path)
                break
        else:
            logger.info("📋 Usage: python upload_manager.py --file video.mp4 or --directory /path/to/videos")

if __name__ == "__main__":
    main()