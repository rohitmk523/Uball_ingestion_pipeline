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

    def generate_presigned_url(self, s3_key: str, expiration: int = 86400) -> str:
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

    async def download_segment_with_better_progress(self, s3_key: str, local_path: str, start_time: str, end_time: str) -> bool:
        """Download only the segment using FFmpeg with better progress estimation"""
        try:
            logger.info(f"Downloading segment {start_time} to {end_time} from {Path(s3_key).name}")

            # Generate pre-signed URL for direct access
            presigned_url = self.generate_presigned_url(s3_key, expiration=7200)  # 2 hours

            # Calculate segment duration for better progress estimation
            start_seconds = self._time_to_seconds(start_time)
            end_seconds = self._time_to_seconds(end_time)
            segment_duration = end_seconds - start_seconds

            # Use ffmpeg to download and extract the segment
            input_stream = ffmpeg.input(presigned_url, ss=start_time, to=end_time)
            output_stream = ffmpeg.output(
                input_stream,
                local_path,
                c='copy',  # Copy streams without re-encoding
                **{'avoid_negative_ts': 'make_zero'}
            )

            # Better progress tracking with time-based estimation
            with tqdm(total=100, unit='%', desc=f"📥 Downloading {Path(s3_key).name} segment") as pbar:
                loop = asyncio.get_event_loop()

                def run_with_better_progress():
                    start_time_process = time.time()
                    process = ffmpeg.run_async(output_stream, overwrite_output=True, quiet=True)

                    while process.poll() is None:
                        elapsed = time.time() - start_time_process

                        # More realistic progress estimation
                        # For stream copy, expect roughly 1-2x real-time for network streaming
                        estimated_total_time = segment_duration * 1.5  # 1.5x segment duration

                        if estimated_total_time > 0:
                            progress = min(98, (elapsed / estimated_total_time) * 100)
                        else:
                            progress = min(98, elapsed * 2)  # Fallback

                        pbar.n = int(progress)
                        pbar.refresh()
                        time.sleep(1)  # Update every second

                    # Wait for completion
                    process.wait()
                    pbar.n = 100
                    pbar.refresh()

                    if process.returncode != 0:
                        raise ffmpeg.Error('ffmpeg', '', '')

                await loop.run_in_executor(None, run_with_better_progress)

            return True
        except ffmpeg.Error as e:
            logger.error(f"FFmpeg error during segment download: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during segment download: {e}")
            return False

    async def extract_segment_offline(self, input_path: str, output_path: str, start_time: str, end_time: str) -> bool:
        """Extract video segment from local file - fast offline processing"""
        try:
            logger.info(f"⚡ Processing segment {start_time} to {end_time} offline")

            # Local FFmpeg processing - much faster
            input_stream = ffmpeg.input(input_path, ss=start_time, to=end_time)
            output_stream = ffmpeg.output(
                input_stream,
                output_path,
                c='copy',  # Copy streams without re-encoding
                **{'avoid_negative_ts': 'make_zero'}
            )

            # Run in thread pool
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                await loop.run_in_executor(
                    executor,
                    lambda: ffmpeg.run(output_stream, overwrite_output=True, quiet=True)
                )

            return True
        except ffmpeg.Error as e:
            logger.error(f"FFmpeg error during offline extraction: {e}")
            if hasattr(e, 'stderr') and e.stderr:
                logger.error(f"FFmpeg stderr: {e.stderr.decode()}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during offline extraction: {e}")
            return False

    def _time_to_seconds(self, time_str: str) -> float:
        """Convert HH:MM:SS to seconds"""
        h, m, s = map(float, time_str.split(':'))
        return h * 3600 + m * 60 + s

    async def process_angle(self, angle_name: str, local_folder: str, game_name: str,
                          start_time: str, end_time: str) -> bool:
        """Process a single camera angle from local video file in specified folder"""

        # Use the provided local folder
        local_folder_path = Path(local_folder)
        
        # Create temp directory in the repo for output segments
        repo_temp_dir = Path("temp_videos")
        repo_temp_dir.mkdir(exist_ok=True)

        try:
            # Map angle names to expected file patterns in the folder
            angle_patterns = {
                'farleft': ['*FL*', '*Far Left*', '*far*left*'],
                'farright': ['*FR*', '*Far Right*', '*far*right*'],
                'nearleft': ['*NL*', '*Near Left*', '*near*left*'],
                'nearright': ['*NR*', '*Near Right*', '*near*right*']
            }
            
            # Find the video file for this angle
            local_video_path = None
            for pattern in angle_patterns.get(angle_name, []):
                matches = list(local_folder_path.glob(pattern))
                if matches:
                    local_video_path = matches[0]
                    break
            
            if not local_video_path:
                logger.error(f"❌ No video file found for {angle_name} in {local_folder}")
                return False

            # Output segment file path
            segment_file = repo_temp_dir / f"{game_name}_{angle_name}.mp4"
            
            # Always upload to main path (remove 'corrected/' from S3 key if present)
            clean_folder = local_folder.replace('corrected/', '') if local_folder.startswith('corrected/') else local_folder
            s3_output_key = f"Games/{clean_folder}/{game_name}/{game_name}_{angle_name}.mp4"

            logger.info(f"🎬 Processing {angle_name}")

            # Step 1: Confirm the video file was found and exists
            if not local_video_path.exists():
                logger.error(f"❌ Local video file not found: {local_video_path}")
                logger.error(f"Please ensure video files are in the {local_folder}/ folder")
                return False

            # Step 2: Check if output already exists in S3
            try:
                self.s3_client.head_object(Bucket=self.bucket, Key=s3_output_key)
                logger.info(f"✓ {angle_name} already exists in S3 - skipped")
                return True
            except ClientError as e:
                if e.response['Error']['Code'] != '404':
                    logger.error(f"Error checking if {s3_output_key} exists: {e}")
                    return False
                # File doesn't exist, continue with processing

            # Step 3: Extract segment from local video file
            logger.info(f"⚡ Extracting segment from local file: {local_video_path.name}")
            if not await self.extract_segment_offline(str(local_video_path), str(segment_file), start_time, end_time):
                return False

            # Step 4: Upload processed segment
            logger.info(f"📤 Uploading {angle_name} segment...")
            if not await self.upload_with_progress(str(segment_file), s3_output_key):
                # Cleanup segment file on error
                if segment_file.exists():
                    segment_file.unlink()
                return False

            # Step 5: Cleanup generated segment file (keep original local videos)
            logger.info(f"🧹 Cleaning up segment file...")
            if segment_file.exists():
                segment_file.unlink()
                logger.info(f"   Removed segment: {segment_file.name}")

            logger.info(f"✅ {angle_name} completed successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to process {angle_name}: {e}")
            # Cleanup on any error
            try:
                segment_file = repo_temp_dir / f"{game_name}_{angle_name}.mp4"
                if segment_file.exists():
                    segment_file.unlink()
            except:
                pass
            return False

    async def extract_all_angles(self, game_name: str, start_time: str, end_time: str,
                               local_folder: str) -> bool:
        """Process all 4 camera angles concurrently"""
        tasks = []
        angle_names = ['farleft', 'farright', 'nearleft', 'nearright']

        for angle_name in angle_names:
            task = self.process_angle(angle_name, local_folder, game_name, start_time, end_time)
            tasks.append(task)

        # Run all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check results
        success_count = 0
        for i, result in enumerate(results):
            angle_name = angle_names[i]
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
@click.option('--local-folder', required=True, help='Local folder containing video files (e.g., 09-26-2025)')
def main(game_name: str, start_time: str, end_time: str, local_folder: str):
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

    # Check for corrected folder first, then fall back to original
    corrected_folder = f"corrected/{local_folder}"
    corrected_folder_path = Path(corrected_folder)
    original_folder_path = Path(local_folder)
    
    if corrected_folder_path.exists():
        actual_folder = corrected_folder
        click.echo(f"📁 Using corrected folder: {corrected_folder}")
    elif original_folder_path.exists():
        actual_folder = local_folder
        click.echo(f"📁 Using original folder: {local_folder}")
    else:
        click.echo(f"Error: Neither corrected folder '{corrected_folder}' nor original folder '{local_folder}' exists.")
        sys.exit(1)

    # Create extractor and run
    extractor = VideoExtractor(config)

    async def run_extraction():
        start_total = time.time()
        click.echo(f"Starting extraction for game '{game_name}' from {start_time} to {end_time}")
        click.echo(f"Target bucket: s3://{config.s3_bucket}")
        click.echo("=" * 60)

        success = await extractor.extract_all_angles(game_name, start_time, end_time, actual_folder)

        end_total = time.time()
        duration = end_total - start_total

        click.echo("=" * 60)
        if success:
            click.echo(f"✅ All angles processed successfully in {duration:.1f} seconds!")
            clean_folder = local_folder.replace('corrected/', '') if local_folder.startswith('corrected/') else local_folder
            click.echo(f"Videos saved to: s3://{config.s3_bucket}/Games/{clean_folder}/{game_name}/")
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