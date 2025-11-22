"""
Parallel Video Processor with Concurrency Control
Handles resource-aware parallel processing of games with semaphore-based queuing
"""
import asyncio
import os
import psutil
from pathlib import Path
from typing import List, Dict, Optional
import logging
from datetime import datetime

from .video_processor import extract_segment, is_4k_or_higher, compress_video, get_resolution
from .s3_uploader import upload_to_s3
from .models import Config

logger = logging.getLogger(__name__)

class ResourceManager:
    """Detects and manages system resources for optimal concurrency"""

    @staticmethod
    def get_cpu_count() -> int:
        """Get number of CPU cores"""
        return os.cpu_count() or 2

    @staticmethod
    def get_available_memory_gb() -> float:
        """Get available RAM in GB"""
        try:
            mem = psutil.virtual_memory()
            return mem.available / (1024 ** 3)
        except:
            return 4.0  # Default assumption

    @staticmethod
    def check_gpu_available() -> bool:
        """Check if NVIDIA GPU is available"""
        try:
            import subprocess
            result = subprocess.run(
                ['nvidia-smi'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False

    @staticmethod
    def get_max_concurrent_ffmpeg() -> int:
        """
        Calculate optimal max concurrent FFmpeg processes based on resources

        Returns:
            Recommended max concurrent processes
        """
        cpu_count = ResourceManager.get_cpu_count()
        available_mem_gb = ResourceManager.get_available_memory_gb()
        has_gpu = ResourceManager.check_gpu_available()

        logger.info(f"System resources: {cpu_count} CPUs, {available_mem_gb:.1f}GB RAM, GPU: {has_gpu}")

        # Conservative calculation
        # Each FFmpeg process needs ~2GB RAM for 4K compression
        mem_based_limit = int(available_mem_gb / 2)

        # CPU-based limit (use 50% of cores for encoding)
        cpu_based_limit = max(1, cpu_count // 2)

        # GPU can handle more concurrent sessions (3-5 typically)
        if has_gpu:
            # Jetson Nano shares RAM with GPU, so we must be conservative
            # 4 concurrent 4K streams might OOM a 8GB Nano
            gpu_limit = 2 
            recommended = min(mem_based_limit, gpu_limit)
        else:
            # CPU encoding is much heavier
            recommended = min(mem_based_limit, cpu_based_limit)

        # Ensure at least 1, at most 4 for stability on edge devices
        recommended = max(1, min(recommended, 4))

        logger.info(f"Recommended max concurrent FFmpeg processes: {recommended}")
        return recommended


class GameJob:
    """Represents a single game processing job (4 angles)"""

    def __init__(self, date: str, game_number: int, time_start: str, time_end: str, video_files: Dict[str, str]):
        """
        Args:
            date: Date string (MM-DD)
            game_number: Game number (1, 2, 3, ...)
            time_start: Start time HH:MM:SS
            time_end: End time HH:MM:SS
            video_files: Dict mapping angle_full -> file_path
                        e.g. {'farright': '/path/to/10-2 FR.m4v', ...}
        """
        self.date = date
        self.game_number = game_number
        self.time_start = time_start
        self.time_end = time_end
        self.video_files = video_files

        # Generate identifiers
        self.game_id = f"{date}_game{game_number}"  # "10-02_game1"
        self.s3_prefix = f"{date}/Game-{game_number}"  # "10-02/Game-1"

        # Status tracking
        self.status = "pending"  # pending, processing, completed, error
        self.angle_status = {}  # angle -> status
        self.error_message = None

        # Initialize angle statuses
        for angle in video_files.keys():
            self.angle_status[angle] = "pending"

    def to_dict(self):
        return {
            'game_id': self.game_id,
            'date': self.date,
            'game_number': self.game_number,
            'time_start': self.time_start,
            'time_end': self.time_end,
            'status': self.status,
            'angle_status': self.angle_status,
            'error_message': self.error_message
        }


class ParallelProcessor:
    """Processes multiple games in parallel with concurrency control"""

    def __init__(self, config: Config, max_concurrent: Optional[int] = None, progress_callback=None):
        """
        Args:
            config: Application config (AWS credentials, GPU settings)
            max_concurrent: Max concurrent FFmpeg processes (auto-detect if None)
            progress_callback: Async callback for progress updates
        """
        self.config = config

        # Auto-detect or use provided
        if max_concurrent is None:
            self.max_concurrent = ResourceManager.get_max_concurrent_ffmpeg()
        else:
            self.max_concurrent = max_concurrent

        # Semaphore to control concurrency
        self.semaphore = asyncio.Semaphore(self.max_concurrent)

        # Progress callback
        self.progress_callback = progress_callback

        # Statistics
        self.total_jobs = 0
        self.completed_jobs = 0
        self.failed_jobs = 0

        logger.info(f"ParallelProcessor initialized with max_concurrent={self.max_concurrent}")

    async def process_games(self, jobs: List[GameJob]):
        """
        Process multiple games in parallel with concurrency control

        Args:
            jobs: List of GameJob objects to process
        """
        self.total_jobs = len(jobs)
        self.completed_jobs = 0
        self.failed_jobs = 0

        logger.info(f"Starting parallel processing of {self.total_jobs} games")

        # Create tasks for all games
        tasks = [self._process_game(job) for job in jobs]

        # Wait for all to complete
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(f"Parallel processing complete: {self.completed_jobs} succeeded, {self.failed_jobs} failed")

    async def _process_game(self, job: GameJob):
        """Process a single game (all 4 angles in parallel with semaphore control)"""
        try:
            job.status = "processing"
            await self._broadcast_progress(job, "started")

            # Create tasks for all 4 angles
            angle_tasks = []
            for angle_full, video_path in job.video_files.items():
                task = self._process_angle(job, angle_full, video_path)
                angle_tasks.append(task)

            # Process all angles (semaphore controls actual concurrency)
            results = await asyncio.gather(*angle_tasks, return_exceptions=True)

            # Check if any failed
            failures = [r for r in results if isinstance(r, Exception)]
            if failures:
                job.status = "error"
                job.error_message = f"{len(failures)} angles failed"
                self.failed_jobs += 1
                logger.error(f"Game {job.game_id} failed: {job.error_message}")
            else:
                job.status = "completed"
                self.completed_jobs += 1
                logger.info(f"Game {job.game_id} completed successfully")

            await self._broadcast_progress(job, "completed")

        except Exception as e:
            job.status = "error"
            job.error_message = str(e)
            self.failed_jobs += 1
            logger.error(f"Game {job.game_id} error: {e}")
            await self._broadcast_progress(job, "error", str(e))

    async def _process_angle(self, job: GameJob, angle_full: str, video_path: str):
        """
        Process a single angle with semaphore control

        Args:
            job: GameJob object
            angle_full: Angle name (farright, farleft, nearleft, nearright)
            video_path: Path to source video file
        """
        # Acquire semaphore (blocks if max concurrent reached)
        async with self.semaphore:
            try:
                job.angle_status[angle_full] = "processing"
                await self._broadcast_progress(job, "angle_started", angle=angle_full)

                # Create temp directories
                temp_dir = Path("temp")
                segments_dir = temp_dir / "segments"
                compressed_dir = temp_dir / "compressed"
                segments_dir.mkdir(parents=True, exist_ok=True)
                compressed_dir.mkdir(parents=True, exist_ok=True)

                # Step 1: Extract segment (fast, copy codec)
                segment_filename = f"{job.game_id}_{angle_full}_segment.mp4"
                segment_path = segments_dir / segment_filename

                logger.info(f"[{job.game_id}][{angle_full}] Extracting segment...")
                await self._broadcast_progress(job, "extracting", angle=angle_full)

                await extract_segment(
                    video_path,
                    str(segment_path),
                    job.time_start,
                    job.time_end
                )

                # Step 2: Check resolution
                logger.info(f"[{job.game_id}][{angle_full}] Checking resolution...")
                width, height = get_resolution(str(segment_path))

                if width is None or height is None:
                    raise ValueError(f"Could not determine resolution for {segment_path}")

                logger.info(f"[{job.game_id}][{angle_full}] Resolution: {width}x{height}")

                # Step 3: Compress if 4K
                if is_4k_or_higher(width, height):
                    logger.info(f"[{job.game_id}][{angle_full}] Video is 4K - compressing to 1080p...")
                    await self._broadcast_progress(job, "compressing", angle=angle_full)

                    compressed_filename = f"{job.game_id}_{angle_full}.mp4"
                    compressed_path = compressed_dir / compressed_filename

                    await compress_video(
                        str(segment_path),
                        str(compressed_path),
                        use_gpu=self.config.gpu_available
                    )

                    # Use compressed file
                    final_path = compressed_path

                    # Delete segment to save space
                    segment_path.unlink()

                else:
                    logger.info(f"[{job.game_id}][{angle_full}] Video is {width}x{height} - no compression needed")
                    await self._broadcast_progress(job, "skipping_compression", angle=angle_full)

                    # Use original segment
                    final_path = segment_path

                # Step 4: Upload to S3
                logger.info(f"[{job.game_id}][{angle_full}] Uploading to S3...")
                await self._broadcast_progress(job, "uploading", angle=angle_full)

                # S3 key: 10-02/Game-1/10-02_game1_farright.mp4
                s3_key = f"{job.s3_prefix}/{job.game_id}_{angle_full}.mp4"

                # Use configured bucket
                await upload_to_s3(str(final_path), f"Games/{s3_key}", self.config)

                # Step 5: Cleanup
                final_path.unlink()

                job.angle_status[angle_full] = "completed"
                logger.info(f"[{job.game_id}][{angle_full}] Completed successfully")
                await self._broadcast_progress(job, "angle_completed", angle=angle_full)

            except Exception as e:
                job.angle_status[angle_full] = "error"
                logger.error(f"[{job.game_id}][{angle_full}] Error: {e}")
                await self._broadcast_progress(job, "angle_error", angle=angle_full, error=str(e))
                raise

    async def _broadcast_progress(self, job: GameJob, stage: str, angle: Optional[str] = None, error: Optional[str] = None):
        """Broadcast progress update via callback"""
        if self.progress_callback:
            try:
                message = {
                    'game_id': job.game_id,
                    'stage': stage,
                    'status': job.status,
                    'angle': angle,
                    'angle_status': job.angle_status,
                    'error': error,
                    'progress': {
                        'total': self.total_jobs,
                        'completed': self.completed_jobs,
                        'failed': self.failed_jobs
                    }
                }
                await self.progress_callback(message)
            except Exception as e:
                logger.error(f"Error broadcasting progress: {e}")
