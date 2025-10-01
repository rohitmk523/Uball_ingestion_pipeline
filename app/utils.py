from datetime import datetime
import shutil
import logging
from pathlib import Path
from typing import List
from .models import Game, TimeRange

logger = logging.getLogger(__name__)

def generate_game_uuid(start_time: str) -> str:
    """
    Generate deterministic UUID from start timestamp

    Args:
        start_time: Format "HH:MM:SS" or datetime object

    Returns:
        UUID string like "game-20250115-143045"
    """
    if isinstance(start_time, str):
        # Parse time string (assumes today's date)
        time_obj = datetime.strptime(start_time, "%H:%M:%S")
        timestamp = datetime.now().replace(
            hour=time_obj.hour,
            minute=time_obj.minute,
            second=time_obj.second,
            microsecond=0
        )
    else:
        timestamp = start_time

    # Format: game-YYYYMMDD-HHMMSS
    uuid = timestamp.strftime("game-%Y%m%d-%H%M%S")
    return uuid

def check_disk_space(required_bytes: int, path: str = "/") -> bool:
    """Check if sufficient disk space is available"""
    stat = shutil.disk_usage(path)
    available = stat.free

    if available < required_bytes:
        logger.error(f"Insufficient disk space. Required: {required_bytes}, Available: {available}")
        raise RuntimeError(
            f"Need {required_bytes / (1024**3):.2f} GB, "
            f"only {available / (1024**3):.2f} GB available"
        )

    return True

def validate_time_range(start: str, end: str, existing_games: List[Game] = None) -> bool:
    """Validate time range doesn't overlap with existing games"""
    if existing_games is None:
        existing_games = []

    # Parse times
    start_time = datetime.strptime(start, "%H:%M:%S")
    end_time = datetime.strptime(end, "%H:%M:%S")

    # Check if end is after start
    if end_time <= start_time:
        raise ValueError("End time must be after start time")

    # Check for overlaps
    for game in existing_games:
        game_start = datetime.strptime(game.time_range.start, "%H:%M:%S")
        game_end = datetime.strptime(game.time_range.end, "%H:%M:%S")

        # Check overlap
        if not (end_time <= game_start or start_time >= game_end):
            raise ValueError(f"Time range overlaps with existing game {game.uuid}")

    return True

def cleanup_temp_files():
    """Clean up temporary files"""
    temp_dirs = ['temp/segments', 'temp/compressed', 'temp/thumbnails']

    for temp_dir in temp_dirs:
        temp_path = Path(temp_dir)
        if temp_path.exists():
            for file in temp_path.glob('*'):
                try:
                    if file.is_file():
                        file.unlink()
                        logger.info(f"Cleaned up temp file: {file}")
                except Exception as e:
                    logger.warning(f"Could not delete {file}: {e}")

def format_duration(seconds: float) -> str:
    """Format duration in seconds to HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def format_file_size(bytes_size: int) -> str:
    """Format file size in bytes to human readable"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"