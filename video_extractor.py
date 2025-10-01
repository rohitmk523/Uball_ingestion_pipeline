#!/usr/bin/env python3
"""
Basketball Game Video Extractor

This script extracts specific time segments from basketball videos stored in S3
for all 4 camera angles (far left, far right, near left, near right) and saves
them back to S3 in organized directories.

Usage:
    python video_extractor.py --game-name game1 --start-time 00:15:30 --end-time 00:45:20 \
        --far-left-key "source-videos/court1-farleft.mp4" \
        --far-right-key "source-videos/court1-farright.mp4" \
        --near-left-key "source-videos/court1-nearleft.mp4" \
        --near-right-key "source-videos/court1-nearright.mp4"
"""

import asyncio
import tempfile
import os
import sys
from pathlib import Path
from typing import List, Tuple
import time
import logging

import click
import boto3
import ffmpeg
from botocore.exceptions import ClientError
from tqdm.asyncio import tqdm
from concurrent.futures import ThreadPoolExecutor

from app.config import load_config
from app.models import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VideoExtractor:
    def __init__(self, config: Config):
        self.config = config
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=config.aws_access_key,
            aws_secret_access_key=config.aws_secret_key,
            region_name=config.s3_region
        )
        self.bucket = config.s3_bucket

    async def download_with_progress(self, s3_key: str, local_path: str) -> bool:
        """Download file from S3 with progress bar"""
        try:
            # Get file size first
            response = self.s3_client.head_object(Bucket=self.bucket, Key=s3_key)
            file_size = response['ContentLength']

            with open(local_path, 'wb') as f:
                with tqdm(total=file_size, unit='B', unit_scale=True, desc=f"Downloading {Path(s3_key).name}") as pbar:
                    def callback(chunk):
                        f.write(chunk)
                        pbar.update(len(chunk))

                    # Download in chunks
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: self.s3_client.download_fileobj(
                            self.bucket, s3_key, f
                        )
                    )
            return True
        except ClientError as e:
            logger.error(f"Failed to download {s3_key}: {e}")
            return False

    async def upload_with_progress(self, local_path: str, s3_key: str) -> bool:
        """Upload file to S3 with progress bar"""
        try:
            file_size = os.path.getsize(local_path)

            with tqdm(total=file_size, unit='B', unit_scale=True, desc=f"Uploading {Path(s3_key).name}") as pbar:
                def callback(bytes_transferred):
                    pbar.update(bytes_transferred)

                # Use multipart upload for better progress tracking
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: self.s3_client.upload_file(
                        local_path, self.bucket, s3_key,
                        Callback=callback
                    )
                )
            return True
        except ClientError as e:
            logger.error(f"Failed to upload {s3_key}: {e}")
            return False

    async def extract_video_segment(self, input_path: str, output_path: str, start_time: str, end_time: str) -> bool:
        """Extract video segment using ffmpeg"""
        try:
            logger.info(f"Extracting segment {start_time} to {end_time} from {Path(input_path).name}")

            # Use ffmpeg-python with stream copy for lossless extraction
            input_stream = ffmpeg.input(input_path, ss=start_time, to=end_time)
            output_stream = ffmpeg.output(
                input_stream,
                output_path,
                c='copy',  # Copy streams without re-encoding
                **{'avoid_negative_ts': 'make_zero'}
            )

            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                await loop.run_in_executor(
                    executor,
                    lambda: ffmpeg.run(output_stream, overwrite_output=True, quiet=True)
                )

            return True
        except ffmpeg.Error as e:
            logger.error(f"FFmpeg error: {e}")
            if hasattr(e, 'stderr') and e.stderr:
                logger.error(f"FFmpeg stderr: {e.stderr.decode()}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during video extraction: {e}")
            return False

    def generate_presigned_url(self, s3_key: str, expiration: int = 3600) -> str:
        """Generate a pre-signed URL for S3 object"""
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': s3_key},
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            logger.error(f"Failed to generate pre-signed URL for {s3_key}: {e}")
            raise

    async def extract_from_s3_direct(self, s3_key: str, output_path: str, start_time: str, end_time: str) -> bool:
        """Extract video segment directly from S3 using pre-signed URL"""
        try:
            # Processing video segment

            # Generate pre-signed URL for direct access
            presigned_url = self.generate_presigned_url(s3_key)

            # Use ffmpeg with the pre-signed URL as input and stream copy for lossless extraction
            input_stream = ffmpeg.input(presigned_url, ss=start_time, to=end_time)
            output_stream = ffmpeg.output(
                input_stream,
                output_path,
                c='copy',  # Copy streams without re-encoding
                **{'avoid_negative_ts': 'make_zero'}
            )

            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                await loop.run_in_executor(
                    executor,
                    lambda: ffmpeg.run(output_stream, overwrite_output=True, quiet=True)
                )

            return True
        except ffmpeg.Error as e:
            logger.error(f"FFmpeg error during direct extraction: {e}")
            if hasattr(e, 'stderr') and e.stderr:
                logger.error(f"FFmpeg stderr: {e.stderr.decode()}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during direct extraction: {e}")
            return False

    async def process_angle(self, angle_name: str, s3_source_key: str, game_name: str,
                          start_time: str, end_time: str) -> bool:
        """Process a single camera angle using direct S3 streaming"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)

            # Local output file (use MP4 container for HEVC compatibility)
            output_file = temp_dir_path / f"{game_name}_{angle_name}.mp4"

            # S3 output path (use MP4 container for HEVC compatibility)
            s3_output_key = f"{game_name}/{game_name}_{angle_name}.mp4"

            try:
                # Processing angle

                # Step 1: Extract video segment directly from S3
                if not await self.extract_from_s3_direct(s3_source_key, str(output_file), start_time, end_time):
                    return False

                # Step 2: Upload extracted segment
                if not await self.upload_with_progress(str(output_file), s3_output_key):
                    return False

                logger.info(f"✓ {angle_name} completed")
                return True

            except Exception as e:
                logger.error(f"Failed to process {angle_name}: {e}")
                return False

    async def extract_all_angles(self, game_name: str, start_time: str, end_time: str,
                               angle_keys: dict) -> bool:
        """Process all 4 camera angles concurrently"""
        tasks = []

        for angle_name, s3_key in angle_keys.items():
            task = self.process_angle(angle_name, s3_key, game_name, start_time, end_time)
            tasks.append(task)

        # Run all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check results
        success_count = 0
        for i, result in enumerate(results):
            angle_name = list(angle_keys.keys())[i]
            if isinstance(result, Exception):
                logger.error(f"Failed to process {angle_name}: {result}")
            elif result:
                success_count += 1
            else:
                logger.error(f"Failed to process {angle_name}")

        logger.info(f"Completed {success_count}/4 angles")
        return success_count == 4

@click.command()
@click.option('--game-name', required=True, help='Name of the game (e.g., game1)')
@click.option('--start-time', required=True, help='Start time in HH:MM:SS format')
@click.option('--end-time', required=True, help='End time in HH:MM:SS format')
@click.option('--far-left-key', required=True, help='S3 key for far left camera video')
@click.option('--far-right-key', required=True, help='S3 key for far right camera video')
@click.option('--near-left-key', required=True, help='S3 key for near left camera video')
@click.option('--near-right-key', required=True, help='S3 key for near right camera video')
def main(game_name: str, start_time: str, end_time: str, far_left_key: str,
         far_right_key: str, near_left_key: str, near_right_key: str):
    """Extract basketball game segments from all 4 camera angles"""

    # Validate time format
    def validate_time_format(time_str: str) -> bool:
        try:
            time.strptime(time_str, '%H:%M:%S')
            return True
        except ValueError:
            return False

    if not validate_time_format(start_time):
        click.echo(f"Error: Invalid start time format '{start_time}'. Use HH:MM:SS format.")
        sys.exit(1)

    if not validate_time_format(end_time):
        click.echo(f"Error: Invalid end time format '{end_time}'. Use HH:MM:SS format.")
        sys.exit(1)

    # Load configuration
    try:
        config = load_config()

        # Validate AWS credentials
        if not config.aws_access_key or not config.aws_secret_key:
            click.echo("Error: AWS credentials not found. Please set them in .env file.")
            sys.exit(1)

        if not config.s3_bucket:
            click.echo("Error: S3 bucket not configured. Please set AWS_S3_BUCKET in .env file.")
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error loading configuration: {e}")
        sys.exit(1)

    # Prepare angle keys
    angle_keys = {
        'farleft': far_left_key,
        'farright': far_right_key,
        'nearleft': near_left_key,
        'nearright': near_right_key
    }

    # Create extractor and run
    extractor = VideoExtractor(config)

    async def run_extraction():
        start_total = time.time()
        click.echo(f"Starting extraction for game '{game_name}' from {start_time} to {end_time}")
        click.echo(f"Target bucket: s3://{config.s3_bucket}")
        click.echo("=" * 60)

        success = await extractor.extract_all_angles(game_name, start_time, end_time, angle_keys)

        end_total = time.time()
        duration = end_total - start_total

        click.echo("=" * 60)
        if success:
            click.echo(f"✅ All angles processed successfully in {duration:.1f} seconds!")
            click.echo(f"Videos saved to: s3://{config.s3_bucket}/{game_name}/")
        else:
            click.echo(f"❌ Some angles failed to process. Check logs for details.")
            sys.exit(1)

    # Run the async function
    try:
        asyncio.run(run_extraction())
    except KeyboardInterrupt:
        click.echo("\n❌ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()