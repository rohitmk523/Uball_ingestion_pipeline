import subprocess
import json
import asyncio
from pathlib import Path
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

async def extract_segment(input_file: str, output_file: str, start: str, end: str):
    """Extract video segment using FFmpeg (fast, copy codec)"""
    cmd = [
        'ffmpeg',
        '-ss', start,  # Start time
        '-i', input_file,
        '-to', end,    # End time
        '-c', 'copy',  # Copy codec (no re-encoding)
        '-avoid_negative_ts', 'make_zero',
        output_file,
        '-y'  # Overwrite
    ]

    logger.info(f"Extracting segment from {start} to {end}")
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
        logger.error(f"Segment extraction failed: {error_msg}")
        raise RuntimeError(f"FFmpeg extraction failed: {error_msg}")

    logger.info(f"Successfully extracted segment to {output_file}")

def get_resolution(file_path: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Get video resolution

    Returns:
        (width, height) tuple
    """
    cmd = [
        'ffprobe', '-v', 'quiet',
        '-print_format', 'json',
        '-show_streams',
        file_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.error(f"ffprobe failed: {result.stderr}")
            return None, None

        data = json.loads(result.stdout)

        for stream in data['streams']:
            if stream['codec_type'] == 'video':
                return stream['width'], stream['height']

        return None, None

    except Exception as e:
        logger.error(f"Error getting resolution: {e}")
        return None, None

def is_4k_or_higher(width: int, height: int) -> bool:
    """
    Check if video is 4K or higher resolution

    Args:
        width: Video width in pixels
        height: Video height in pixels

    Returns:
        True if 4K (3840×2160) or higher, False otherwise
    """
    # Check if either dimension is 4K or higher
    return width >= 3840 or height >= 2160

def check_gpu_available() -> bool:
    """Check if NVIDIA GPU is available"""
    try:
        result = subprocess.run(
            ['nvidia-smi'],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

async def compress_video(input_file: str, output_file: str, use_gpu: bool = True):
    """
    Compress 4K to 1080p using GPU (if available) or CPU fallback

    Args:
        input_file: Input video path
        output_file: Output video path
        use_gpu: Whether to attempt GPU encoding
    """

    # Try GPU encoding first if available
    if use_gpu and check_gpu_available():
        logger.info("Using NVIDIA GPU hardware encoding")
        success = await _compress_with_gpu(input_file, output_file)
        if success:
            return
        else:
            logger.warning("GPU encoding failed, falling back to CPU")

    # Fallback to CPU encoding
    logger.info("Using CPU encoding (this will be slower)")
    await _compress_with_cpu(input_file, output_file)

async def _compress_with_gpu(input_file: str, output_file: str) -> bool:
    """Compress using NVIDIA nvenc hardware encoder"""
    try:
        cmd = [
            'ffmpeg',
            '-hwaccel', 'cuda',
            '-i', input_file,
            '-vf', 'scale_cuda=1920:1080',
            '-c:v', 'h264_nvenc',
            '-preset', 'p7',        # Highest quality preset
            '-tune', 'hq',          # High quality mode
            '-rc', 'vbr',           # Variable bitrate
            '-cq', '19',            # Quality (lower = better, 18-23 range)
            '-b:v', '8M',           # Target bitrate
            '-maxrate', '12M',      # Max bitrate for fast motion
            '-bufsize', '16M',      # Buffer size
            '-c:a', 'aac',
            '-b:a', '192k',
            '-movflags', '+faststart',
            output_file,
            '-y'
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            logger.info("GPU encoding completed successfully")
            return True
        else:
            logger.error(f"GPU encoding failed: {stderr.decode()}")
            return False

    except Exception as e:
        logger.error(f"GPU encoding exception: {e}")
        return False

async def _compress_with_cpu(input_file: str, output_file: str):
    """Compress using CPU (libx264) - slower but works everywhere"""
    cmd = [
        'ffmpeg',
        '-i', input_file,
        '-vf', 'scale=1920:1080',
        '-c:v', 'libx264',
        '-preset', 'slow',      # Better compression (slower)
        '-crf', '20',           # Quality (18-23 range, lower = better)
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac',
        '-b:a', '192k',
        '-movflags', '+faststart',
        output_file,
        '-y'
    ]

    logger.info("Starting CPU-based compression")
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
        logger.error(f"CPU compression failed: {error_msg}")
        raise RuntimeError(f"CPU compression failed: {error_msg}")

    logger.info("CPU compression completed successfully")