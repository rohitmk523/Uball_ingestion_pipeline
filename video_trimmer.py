#!/usr/bin/env python3
"""
Video Trimmer for Basketball Game Videos

This script trims the beginning of videos up to specified timestamps for each camera angle,
preserving original quality using stream copy. Creates corrected folder structure.

Usage:
    python video_trimmer.py --date "09-26-2025" --fl-timestamp "00:05:10" --fr-timestamp "00:05:15" --nl-timestamp "00:05:12" --nr-timestamp "00:05:08"
"""

import asyncio
import os
import sys
from pathlib import Path
import time
import logging

import click
import ffmpeg
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VideoTrimmer:
    def __init__(self):
        pass

    async def trim_video(self, input_path: str, output_path: str, start_timestamp: str) -> bool:
        """Trim video from start_timestamp to end, preserving original quality"""
        try:
            logger.info(f"🔪 Trimming {Path(input_path).name} from {start_timestamp}")
            
            # Use stream copy to preserve exact original quality, force MP4 container for HEVC compatibility
            input_stream = ffmpeg.input(input_path, ss=start_timestamp)
            output_stream = ffmpeg.output(
                input_stream,
                output_path,
                c='copy',  # Copy streams without re-encoding
                f='mp4',   # Force MP4 container format for HEVC compatibility
                **{'avoid_negative_ts': 'make_zero'}
            )

            # Run in thread pool
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                await loop.run_in_executor(
                    executor,
                    lambda: ffmpeg.run(output_stream, overwrite_output=True, quiet=True)
                )

            logger.info(f"✅ Trimmed {Path(output_path).name}")
            return True
            
        except ffmpeg.Error as e:
            logger.error(f"FFmpeg error during trimming: {e}")
            if hasattr(e, 'stderr') and e.stderr:
                logger.error(f"FFmpeg stderr: {e.stderr.decode()}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during trimming: {e}")
            return False

    async def process_angle(self, angle_name: str, source_folder: str, corrected_folder: str, timestamp: str) -> bool:
        """Process a single camera angle"""
        try:
            # Map angle names to expected file patterns
            angle_patterns = {
                'FL': ['*FL*', '*Far Left*', '*far*left*'],
                'FR': ['*FR*', '*Far Right*', '*far*right*'],
                'NL': ['*NL*', '*Near Left*', '*near*left*'],
                'NR': ['*NR*', '*Near Right*', '*near*right*']
            }
            
            source_folder_path = Path(source_folder)
            corrected_folder_path = Path(corrected_folder)
            
            # Find the source video file
            source_video_path = None
            for pattern in angle_patterns.get(angle_name, []):
                matches = list(source_folder_path.glob(pattern))
                if matches:
                    source_video_path = matches[0]
                    break
            
            if not source_video_path:
                logger.error(f"❌ No video file found for {angle_name} in {source_folder}")
                return False

            if not source_video_path.exists():
                logger.error(f"❌ Source video file not found: {source_video_path}")
                return False

            # Create corrected folder if it doesn't exist
            corrected_folder_path.mkdir(parents=True, exist_ok=True)
            
            # Output path with MP4 extension (convert M4V to MP4 for HEVC compatibility)
            output_filename = source_video_path.stem + '.mp4'
            output_path = corrected_folder_path / output_filename
            
            logger.info(f"🎬 Processing {angle_name}: {source_video_path.name}")
            
            # Check if already processed
            if output_path.exists():
                logger.info(f"⚠️ {output_path.name} already exists, skipping")
                return True
            
            # Trim the video
            success = await self.trim_video(str(source_video_path), str(output_path), timestamp)
            
            if success:
                logger.info(f"✅ {angle_name} trimmed successfully")
                return True
            else:
                # Cleanup on failure
                if output_path.exists():
                    output_path.unlink()
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to process {angle_name}: {e}")
            return False

    async def trim_all_angles(self, date: str, timestamps: dict) -> bool:
        """Trim all 4 camera angles"""
        source_folder = date
        corrected_folder = f"corrected/{date}"
        
        logger.info(f"📂 Source folder: {source_folder}")
        logger.info(f"📂 Corrected folder: {corrected_folder}")
        
        # Validate source folder exists
        if not Path(source_folder).exists():
            logger.error(f"❌ Source folder '{source_folder}' does not exist")
            return False
        
        # Process all angles concurrently
        tasks = []
        for angle_name, timestamp in timestamps.items():
            task = self.process_angle(angle_name, source_folder, corrected_folder, timestamp)
            tasks.append(task)

        # Run all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check results
        success_count = 0
        angle_names = list(timestamps.keys())
        for i, result in enumerate(results):
            angle_name = angle_names[i]
            if isinstance(result, Exception):
                logger.error(f"Failed to process {angle_name}: {result}")
            elif result:
                success_count += 1
            else:
                logger.error(f"Failed to process {angle_name}")

        logger.info(f"📊 Completed {success_count}/{len(timestamps)} angles")
        return success_count == len(timestamps)

@click.command()
@click.option('--date', required=True, help='Date folder name (e.g., 09-26-2025)')
@click.option('--fl-timestamp', required=True, help='FL (Far Left) trim timestamp in HH:MM:SS format')
@click.option('--fr-timestamp', required=True, help='FR (Far Right) trim timestamp in HH:MM:SS format')
@click.option('--nl-timestamp', required=True, help='NL (Near Left) trim timestamp in HH:MM:SS format')
@click.option('--nr-timestamp', required=True, help='NR (Near Right) trim timestamp in HH:MM:SS format')
def main(date: str, fl_timestamp: str, fr_timestamp: str, nl_timestamp: str, nr_timestamp: str):
    """Trim basketball game videos from beginning up to specified timestamps"""

    # Validate time format
    def validate_time_format(time_str: str) -> bool:
        try:
            time.strptime(time_str, '%H:%M:%S')
            return True
        except ValueError:
            return False

    timestamps = {
        'FL': fl_timestamp,
        'FR': fr_timestamp,
        'NL': nl_timestamp,
        'NR': nr_timestamp
    }

    # Validate all timestamps
    for angle, timestamp in timestamps.items():
        if not validate_time_format(timestamp):
            click.echo(f"Error: Invalid {angle} timestamp format '{timestamp}'. Use HH:MM:SS format.")
            sys.exit(1)

    # Create trimmer and run
    trimmer = VideoTrimmer()

    async def run_trimming():
        start_total = time.time()
        click.echo(f"Starting video trimming for date '{date}'")
        click.echo("Timestamps:")
        for angle, timestamp in timestamps.items():
            click.echo(f"  {angle}: {timestamp}")
        click.echo("=" * 60)

        success = await trimmer.trim_all_angles(date, timestamps)

        end_total = time.time()
        duration = end_total - start_total

        click.echo("=" * 60)
        if success:
            click.echo(f"✅ All angles trimmed successfully in {duration:.1f} seconds!")
            click.echo(f"Corrected videos saved to: corrected/{date}/")
        else:
            click.echo(f"❌ Some angles failed to process. Check logs for details.")
            sys.exit(1)

    # Run the async function
    try:
        asyncio.run(run_trimming())
    except KeyboardInterrupt:
        click.echo("\n❌ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()