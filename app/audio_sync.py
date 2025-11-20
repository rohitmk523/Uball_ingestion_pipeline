"""
Audio-based video synchronization using cross-correlation.

This module extracts audio from video files and uses cross-correlation
to find time offsets between multiple camera angles.
"""

import subprocess
import numpy as np
from pathlib import Path
import tempfile
import logging
from scipy import signal
from scipy.io import wavfile
import shutil

logger = logging.getLogger(__name__)


class AudioSyncError(Exception):
    """Custom exception for audio sync errors"""
    pass


def extract_audio_segment(video_path: str, output_path: str, duration: int = 60, sample_rate: int = 16000):
    """
    Extract audio from video file using FFmpeg.

    Args:
        video_path: Path to input video file
        output_path: Path to output WAV file
        duration: Duration in seconds to extract (default: 60)
        sample_rate: Audio sample rate in Hz (default: 16000)

    Raises:
        AudioSyncError: If FFmpeg extraction fails
    """
    try:
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-t', str(duration),          # Extract first N seconds
            '-vn',                         # No video
            '-acodec', 'pcm_s16le',       # PCM 16-bit audio
            '-ar', str(sample_rate),       # Sample rate
            '-ac', '1',                    # Mono channel
            '-y',                          # Overwrite output
            output_path
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )

        if not Path(output_path).exists():
            raise AudioSyncError(f"Failed to create audio file: {output_path}")

        logger.info(f"Extracted audio from {video_path} ({duration}s)")

    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg audio extraction failed: {e.stderr}")
        raise AudioSyncError(f"Audio extraction failed: {e.stderr}")
    except Exception as e:
        logger.error(f"Error extracting audio: {e}")
        raise AudioSyncError(str(e))


def load_audio(wav_path: str) -> tuple[int, np.ndarray]:
    """
    Load audio from WAV file.

    Args:
        wav_path: Path to WAV file

    Returns:
        Tuple of (sample_rate, audio_data)

    Raises:
        AudioSyncError: If audio loading fails
    """
    try:
        sample_rate, audio_data = wavfile.read(wav_path)

        # Convert to float32 and normalize
        if audio_data.dtype == np.int16:
            audio_data = audio_data.astype(np.float32) / 32768.0
        elif audio_data.dtype == np.int32:
            audio_data = audio_data.astype(np.float32) / 2147483648.0

        logger.info(f"Loaded audio: {wav_path} ({len(audio_data)} samples @ {sample_rate} Hz)")
        return sample_rate, audio_data

    except Exception as e:
        logger.error(f"Error loading audio: {e}")
        raise AudioSyncError(f"Failed to load audio: {e}")


def find_offset_cross_correlation(reference_audio: np.ndarray, target_audio: np.ndarray,
                                   sample_rate: int) -> float:
    """
    Find time offset between two audio signals using cross-correlation.

    Args:
        reference_audio: Reference audio signal (numpy array)
        target_audio: Target audio signal to align (numpy array)
        sample_rate: Audio sample rate in Hz

    Returns:
        Time offset in seconds (positive means target is ahead of reference)

    Raises:
        AudioSyncError: If correlation computation fails
    """
    try:
        # Ensure both signals have the same length
        min_len = min(len(reference_audio), len(target_audio))
        reference_audio = reference_audio[:min_len]
        target_audio = target_audio[:min_len]

        # Compute cross-correlation using FFT (faster for large signals)
        correlation = signal.correlate(target_audio, reference_audio, mode='full', method='fft')

        # Find the peak (maximum correlation)
        peak_index = np.argmax(np.abs(correlation))

        # Convert peak index to time offset
        # The correlation has length 2*len-1, centered at len-1
        center_index = len(reference_audio) - 1
        offset_samples = peak_index - center_index

        # Convert samples to seconds
        offset_seconds = offset_samples / sample_rate

        logger.info(f"Cross-correlation peak at offset: {offset_seconds:.3f}s ({offset_samples} samples)")

        return offset_seconds

    except Exception as e:
        logger.error(f"Error computing cross-correlation: {e}")
        raise AudioSyncError(f"Cross-correlation failed: {e}")


def synchronize_videos(video_files: dict[str, str], duration: int = 60,
                       reference_angle: str = 'FR') -> dict[str, float]:
    """
    Synchronize multiple video files using audio cross-correlation.

    Args:
        video_files: Dictionary mapping angle names to video file paths
                    Example: {'FR': '/path/to/fr.mp4', 'FL': '/path/to/fl.mp4', ...}
        duration: Duration in seconds to analyze (default: 60)
        reference_angle: Angle to use as reference (default: 'FR')

    Returns:
        Dictionary mapping angle names to offset values in seconds
        Example: {'FL': 0.5, 'NL': -0.25, 'NR': 1.0}
        (FR is always 0 as it's the reference)

    Raises:
        AudioSyncError: If synchronization fails
    """
    if reference_angle not in video_files:
        raise AudioSyncError(f"Reference angle '{reference_angle}' not found in video files")

    temp_dir = Path(tempfile.mkdtemp(prefix='audio_sync_'))
    logger.info(f"Created temp directory for audio sync: {temp_dir}")

    try:
        # Extract audio from all videos
        audio_files = {}
        audio_data = {}

        for angle, video_path in video_files.items():
            if not Path(video_path).exists():
                logger.warning(f"Video file not found: {video_path} (angle: {angle})")
                continue

            # Extract audio to temp WAV file
            wav_path = temp_dir / f"{angle}.wav"
            extract_audio_segment(video_path, str(wav_path), duration=duration)
            audio_files[angle] = str(wav_path)

            # Load audio data
            sample_rate, audio = load_audio(str(wav_path))
            audio_data[angle] = audio

        if reference_angle not in audio_data:
            raise AudioSyncError(f"Failed to extract audio from reference angle: {reference_angle}")

        # Use reference angle audio for correlation
        reference_audio = audio_data[reference_angle]
        reference_sample_rate = sample_rate

        # Calculate offsets for each angle
        offsets = {}

        for angle in video_files.keys():
            if angle == reference_angle:
                # Reference angle always has 0 offset
                offsets[angle] = 0.0
                continue

            if angle not in audio_data:
                logger.warning(f"Skipping angle {angle} (no audio data)")
                continue

            # Find offset using cross-correlation
            offset = find_offset_cross_correlation(
                reference_audio,
                audio_data[angle],
                reference_sample_rate
            )

            # Negative offset because we want to know how much to shift the target
            # to align with reference
            offsets[angle] = -offset

            logger.info(f"Calculated offset for {angle}: {offsets[angle]:.3f}s")

        # Remove reference angle from results (it's always 0)
        if reference_angle in offsets:
            del offsets[reference_angle]

        return offsets

    except AudioSyncError:
        raise
    except Exception as e:
        logger.error(f"Error during video synchronization: {e}")
        raise AudioSyncError(f"Synchronization failed: {e}")

    finally:
        # Cleanup temp directory
        try:
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temp directory: {temp_dir}")
        except Exception as e:
            logger.warning(f"Failed to cleanup temp directory {temp_dir}: {e}")
