"""
Input Video Scanner for /input directory
Scans for angle videos: FR (Far Right), FL (Far Left), NL (Near Left), NR (Near Right)
"""
import re
from pathlib import Path
from typing import List, Dict, Optional
import logging
from datetime import datetime

from .video_processor import get_resolution, get_video_metadata_extended

logger = logging.getLogger(__name__)

# Angle mapping
ANGLE_PATTERNS = {
    'FR': 'farright',
    'FL': 'farleft',
    'NL': 'nearleft',
    'NR': 'nearright'
}

class InputVideo:
    """Represents a video file from /input directory"""
    def __init__(self, path: str, date: str, angle_short: str, angle_full: str):
        self.path = path
        self.date = date  # Format: "10-02"
        self.angle_short = angle_short  # "FR", "FL", "NL", "NR"
        self.angle_full = angle_full  # "farright", "farleft", etc.
        self.filename = Path(path).name
        self.size = 0
        self.duration = 0.0
        self.width = 0
        self.height = 0
        self.resolution = ""
        self.is_4k = False

    def to_dict(self):
        return {
            'path': self.path,
            'filename': self.filename,
            'date': self.date,
            'angle_short': self.angle_short,
            'angle_full': self.angle_full,
            'size': self.size,
            'duration': self.duration,
            'resolution': self.resolution,
            'is_4k': self.is_4k,
            'width': self.width,
            'height': self.height
        }

def parse_filename(filename: str) -> Optional[Dict[str, str]]:
    """
    Parse filename to extract date and angle

    Examples:
        "10-2 FR.m4v" -> {"date": "10-02", "angle": "FR"}
        "10-02 FL.mp4" -> {"date": "10-02", "angle": "FL"}
        "11-15 NR.m4v" -> {"date": "11-15", "angle": "NR"}
        "10-2 FL_test.mp4" -> {"date": "10-02", "angle": "FL"}  (ignores _test)

    Returns:
        Dict with 'date' and 'angle' or None if pattern doesn't match
    """
    # Pattern: MM-DD ANGLE[_anything].ext or MM-D ANGLE[_anything].ext
    # Supports: "10-2 FR.m4v", "10-2 FL_test.mp4", "10-02 NR_backup.mov"
    pattern = r'(\d{1,2})-(\d{1,2})\s+(FR|FL|NL|NR)(?:_\w+)?\.(m4v|mp4|mov)'

    match = re.match(pattern, filename, re.IGNORECASE)
    if match:
        month = match.group(1).zfill(2)  # Pad to 2 digits
        day = match.group(2).zfill(2)
        angle = match.group(3).upper()

        return {
            'date': f"{month}-{day}",
            'angle': angle
        }

    return None

def scan_input_directory(input_dir: str = "input") -> List[InputVideo]:
    """
    Scan /input directory for video files

    Returns:
        List of InputVideo objects grouped by date
    """
    input_path = Path(input_dir)

    if not input_path.exists():
        logger.warning(f"Input directory {input_dir} does not exist")
        return []

    videos = []

    # Scan for video files
    for video_file in input_path.glob("*"):
        # Skip .crdownload (downloading files) and hidden files
        if video_file.suffix == '.crdownload' or video_file.name.startswith('.'):
            logger.info(f"Skipping incomplete/hidden file: {video_file.name}")
            continue

        # Only process video files
        if video_file.suffix.lower() not in ['.m4v', '.mp4', '.mov']:
            continue

        # Parse filename
        parsed = parse_filename(video_file.name)
        if not parsed:
            logger.warning(f"Could not parse filename: {video_file.name}")
            continue

        # Create InputVideo object
        angle_full = ANGLE_PATTERNS.get(parsed['angle'])
        if not angle_full:
            logger.warning(f"Unknown angle: {parsed['angle']}")
            continue

        video = InputVideo(
            path=str(video_file.absolute()),
            date=parsed['date'],
            angle_short=parsed['angle'],
            angle_full=angle_full
        )

        # Get file size
        try:
            video.size = video_file.stat().st_size
        except Exception as e:
            logger.error(f"Error getting file size for {video_file}: {e}")
            continue

        # Get video metadata (resolution, duration)
        try:
            metadata = get_video_metadata_extended(str(video_file))
            video.duration = metadata['duration']
            video.width = metadata['width']
            video.height = metadata['height']
            video.resolution = f"{video.width}x{video.height}"
            video.is_4k = video.width >= 3840 or video.height >= 2160

            logger.info(f"Found video: {video.filename} - {video.resolution} ({video.duration:.1f}s)")
        except Exception as e:
            logger.error(f"Error getting metadata for {video_file}: {e}")
            continue

        videos.append(video)

    # Sort by date, then by angle
    videos.sort(key=lambda v: (v.date, v.angle_short))

    return videos

def get_videos_by_date(input_dir: str = "input") -> Dict[str, List[InputVideo]]:
    """
    Get videos grouped by date

    Returns:
        Dict mapping date -> List[InputVideo]
        Example: {"10-02": [FR_video, FL_video, NL_video, NR_video]}
    """
    videos = scan_input_directory(input_dir)

    grouped = {}
    for video in videos:
        if video.date not in grouped:
            grouped[video.date] = []
        grouped[video.date].append(video)

    return grouped

def validate_date_videos(videos: List[InputVideo]) -> Dict[str, bool]:
    """
    Check which angles are present for a date

    Returns:
        Dict with validation info:
        {
            'complete': True/False (all 4 angles present),
            'missing_angles': ['FR', 'FL', ...],
            'present_angles': ['FR', 'FL', ...],
            'count': number of angles available,
            'can_process': True (always, can process with 1-4 angles)
        }
    """
    present = {v.angle_short for v in videos}
    all_angles = {'FR', 'FL', 'NL', 'NR'}
    missing = all_angles - present

    return {
        'complete': len(missing) == 0,
        'missing_angles': sorted(list(missing)),
        'present_angles': sorted(list(present)),
        'count': len(present),
        'can_process': len(present) > 0  # Can process with any number of angles
    }
