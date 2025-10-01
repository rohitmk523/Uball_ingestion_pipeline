import os
import subprocess
import json
from datetime import datetime
from pathlib import Path
from typing import List
import logging

from .models import CameraFile

logger = logging.getLogger(__name__)

def detect_gopro_devices():
    """Detect GoPro cameras mounted as USB storage"""
    # Check both /media/ (typical Linux) and /tmp/ (for EC2 simulation)
    media_paths = [Path("/media"), Path("/tmp")]
    gopro_devices = []

    for media_path in media_paths:
        if not media_path.exists():
            continue

        for device in media_path.iterdir():
            if device.is_dir():
                # GoPros typically mount with DCIM folder structure
                dcim_path = device / "DCIM"
                if dcim_path.exists():
                    gopro_devices.append(str(device))
                    logger.info(f"Found GoPro device at {device}")

    return gopro_devices

def list_video_files(device_path: str) -> List[CameraFile]:
    """List all video files from GoPro storage"""
    videos = []
    dcim_path = Path(device_path) / "DCIM"

    if not dcim_path.exists():
        logger.warning(f"DCIM folder not found in {device_path}")
        return videos

    for video_file in dcim_path.rglob("*.MP4"):
        try:
            metadata = get_video_metadata(str(video_file))
            video_info = CameraFile(
                path=str(video_file),
                filename=video_file.name,
                size=video_file.stat().st_size,
                duration=metadata["duration"],
                resolution=metadata["resolution"],
                timestamp=metadata["timestamp"]
            )
            videos.append(video_info)
            logger.info(f"Found video: {video_file.name} ({metadata['resolution']})")
        except Exception as e:
            logger.error(f"Error processing video file {video_file}: {e}")
            continue

    return videos

def get_video_metadata(file_path: str):
    """Extract video metadata using ffprobe"""
    cmd = [
        'ffprobe', '-v', 'quiet',
        '-print_format', 'json',
        '-show_format', '-show_streams',
        file_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")

        data = json.loads(result.stdout)

        # Extract duration
        duration = float(data['format']['duration'])

        # Extract video stream info
        width, height = None, None
        for stream in data['streams']:
            if stream['codec_type'] == 'video':
                width = stream['width']
                height = stream['height']
                break

        if width is None or height is None:
            raise ValueError("No video stream found")

        resolution = f"{width}x{height}"

        # Get file creation timestamp
        timestamp = datetime.fromtimestamp(
            Path(file_path).stat().st_mtime
        )

        return {
            "duration": duration,
            "resolution": resolution,
            "timestamp": timestamp,
            "width": width,
            "height": height
        }

    except subprocess.TimeoutExpired:
        raise RuntimeError("ffprobe timeout")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse ffprobe output: {e}")
    except Exception as e:
        raise RuntimeError(f"Error getting video metadata: {e}")

def get_all_camera_files() -> List[CameraFile]:
    """Get all video files from all detected cameras"""
    all_files = []
    devices = detect_gopro_devices()

    for device in devices:
        files = list_video_files(device)
        all_files.extend(files)

    return sorted(all_files, key=lambda x: x.timestamp)