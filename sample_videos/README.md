# Sample Videos Directory

This directory contains sample video files for testing the basketball upload pipeline.

## Files:

- `basketball_game_sample.mp4` - 10MB sample file for testing uploads
- Add your own GoPro video files here for development testing

## Usage:

```bash
# Test single file upload
python src/upload_manager.py --file sample_videos/basketball_game_sample.mp4 --test-mode

# Test directory scan and upload
python src/upload_manager.py --directory sample_videos --test-mode

# Run web interface (will scan this directory)
python src/web_ui.py
```

## For Real GoPro Testing:

1. Copy actual GoPro files (2-5GB MP4/M4A) to this directory
2. Test with `--test-mode` first to avoid accidental deletions
3. Remove `--test-mode` for production testing with cleanup