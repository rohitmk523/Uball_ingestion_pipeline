#!/usr/bin/env python3
"""Quick test of input video scanner"""

from app.input_video_scanner import parse_filename, scan_input_directory, get_videos_by_date

# Test filename parsing
test_files = [
    "10-2 FL_test.mp4",
    "10-2 FR.m4v",
    "10-02 NL.mp4",
    "11-15 NR_backup.mov"
]

print("=" * 60)
print("Testing Filename Parsing")
print("=" * 60)

for filename in test_files:
    result = parse_filename(filename)
    if result:
        print(f"✓ {filename:25} → Date: {result['date']}, Angle: {result['angle']}")
    else:
        print(f"✗ {filename:25} → FAILED TO PARSE")

print("\n" + "=" * 60)
print("Scanning /input Directory")
print("=" * 60)

videos = scan_input_directory("input")
print(f"\nFound {len(videos)} video(s):\n")

for video in videos:
    print(f"  Date: {video.date}")
    print(f"  Angle: {video.angle_short} ({video.angle_full})")
    print(f"  File: {video.filename}")
    print(f"  Resolution: {video.resolution} {'[4K - will compress]' if video.is_4k else '[will NOT compress]'}")
    print(f"  Duration: {video.duration:.1f}s ({video.duration/60:.1f} min)")
    print(f"  Size: {video.size / (1024**2):.1f} MB")
    print()

print("=" * 60)
print("Videos Grouped by Date")
print("=" * 60)

videos_by_date = get_videos_by_date("input")
for date, date_videos in videos_by_date.items():
    angles = [v.angle_short for v in date_videos]
    print(f"\n{date}: {len(date_videos)} video(s) - Angles: {', '.join(angles)}")

    from app.input_video_scanner import validate_date_videos
    validation = validate_date_videos(date_videos)

    if validation['complete']:
        print(f"  ✓ All 4 angles present - READY TO PROCESS")
    else:
        print(f"  ⚠️  {validation['count']} angle(s) only - Missing: {', '.join(validation['missing_angles'])}")
        print(f"  → Can still process with available angles")

print("\n" + "=" * 60)
print("READY TO TEST!")
print("=" * 60)
print("\nNext steps:")
print("1. Start server: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
print("2. Open UI: http://localhost:8000/input-videos")
print("3. Click 'Scan /input Directory'")
print("4. Load preview for date 10-02")
print("5. Mark a short game (e.g., 00:00:10 to 00:00:30)")
print("6. Process and verify!")
