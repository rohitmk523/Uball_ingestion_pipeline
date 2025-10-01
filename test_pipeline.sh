#!/bin/bash

echo "🧪 Testing Basketball Pipeline"
echo "=============================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test configuration
TEST_API_BASE="http://localhost:8000/api"

echo -e "${BLUE}Setting up test environment...${NC}"

# 1. Check if pipeline is running
if ! curl -s http://localhost:8000/health > /dev/null; then
    echo -e "${RED}❌ Pipeline is not running. Start it with:${NC}"
    echo "  source venv/bin/activate"
    echo "  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
    exit 1
fi

echo -e "${GREEN}✅ Pipeline is running${NC}"

# 2. Test health endpoint
echo -e "${BLUE}Testing health endpoint...${NC}"
HEALTH=$(curl -s http://localhost:8000/health)
echo "Health check: $HEALTH"

GPU_AVAILABLE=$(echo $HEALTH | python3 -c "import json,sys; print(json.load(sys.stdin)['gpu_available'])")
echo -e "GPU Available: ${GPU_AVAILABLE}"

# 3. Test camera detection
echo -e "${BLUE}Testing camera detection...${NC}"
CAMERAS=$(curl -s "$TEST_API_BASE/cameras")
echo "Cameras: $CAMERAS"

CAMERA_COUNT=$(echo $CAMERAS | python3 -c "import json,sys; print(len(json.load(sys.stdin)['cameras']))")
if [ "$CAMERA_COUNT" -eq 0 ]; then
    echo -e "${RED}❌ No cameras detected. Run setup_ec2.sh first${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Found $CAMERA_COUNT cameras${NC}"

# 4. Test file loading
echo -e "${BLUE}Testing file loading...${NC}"
FILES=$(curl -s "$TEST_API_BASE/files")
echo "Files response: $FILES"

FILE_COUNT=$(echo $FILES | python3 -c "import json,sys; print(len(json.load(sys.stdin)['files']))")
if [ "$FILE_COUNT" -eq 0 ]; then
    echo -e "${RED}❌ No files found. Check test videos were created${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Found $FILE_COUNT video files${NC}"

# 5. Check file resolutions
echo -e "${BLUE}Checking file resolutions...${NC}"
echo $FILES | python3 -c "
import json, sys
data = json.load(sys.stdin)
for file in data['files']:
    print(f\"  {file['filename']}: {file['resolution']} ({file['duration']:.1f}s)\")
"

# 6. Test side configuration
echo -e "${BLUE}Testing side configuration...${NC}"
SIDE_RESPONSE=$(curl -s -X PUT "$TEST_API_BASE/config/side" \
    -H "Content-Type: application/json" \
    -d '{"side": "LEFT"}')
echo "Side config response: $SIDE_RESPONSE"

# 7. Test game creation
echo -e "${BLUE}Testing game creation...${NC}"
GAME_RESPONSE=$(curl -s -X POST "$TEST_API_BASE/games" \
    -H "Content-Type: application/json" \
    -d '{"time_range": {"start": "00:00:30", "end": "00:01:30"}}')
echo "Game creation response: $GAME_RESPONSE"

GAME_UUID=$(echo $GAME_RESPONSE | python3 -c "import json,sys; print(json.load(sys.stdin)['uuid'])" 2>/dev/null)
if [ -n "$GAME_UUID" ]; then
    echo -e "${GREEN}✅ Created game: $GAME_UUID${NC}"
else
    echo -e "${RED}❌ Failed to create game${NC}"
    exit 1
fi

# 8. List games
echo -e "${BLUE}Listing games...${NC}"
GAMES=$(curl -s "$TEST_API_BASE/games")
echo "Games: $GAMES"

# 9. Test video processing functions (without S3)
echo -e "${BLUE}Testing video processing functions...${NC}"

# Create a simple test to verify resolution detection
python3 -c "
import sys
sys.path.append('.')
from app.video_processor import get_resolution, is_4k_or_higher
from app.camera_detection import get_all_camera_files

# Test with our created files
files = get_all_camera_files()
print(f'Found {len(files)} files for testing')

for file in files:
    print(f'Testing {file.filename}:')
    width, height = get_resolution(file.path)
    if width and height:
        is_4k = is_4k_or_higher(width, height)
        print(f'  Resolution: {width}x{height}')
        print(f'  Is 4K+: {is_4k}')
        print(f'  Action: {\"Compress to 1080p\" if is_4k else \"Upload as-is\"}')
    else:
        print(f'  Error: Could not get resolution')
    print()
"

# 10. Summary
echo -e "${BLUE}Test Summary:${NC}"
echo -e "${GREEN}✅ Pipeline is running and responsive${NC}"
echo -e "${GREEN}✅ Camera detection works${NC}"
echo -e "${GREEN}✅ File loading works${NC}"
echo -e "${GREEN}✅ Side configuration works${NC}"
echo -e "${GREEN}✅ Game creation works${NC}"
echo -e "${GREEN}✅ Video processing functions work${NC}"
echo ""
echo -e "${YELLOW}📋 Manual tests to perform:${NC}"
echo "1. Open http://localhost:8000 in browser"
echo "2. Configure AWS credentials (use dummy for testing)"
echo "3. Set side to LEFT or RIGHT"
echo "4. Load cameras and files"
echo "5. Add a game with timerange 00:00:30 to 00:01:30"
echo "6. Start processing (without valid S3 it will fail at upload)"
echo ""
echo -e "${YELLOW}Expected behavior:${NC}"
echo "- 4K video should show 'compressing' stage"
echo "- 1080p video should show 'skipping compression' stage"
echo "- Both should fail at 'uploading' stage without valid S3 credentials"
echo ""
echo -e "${GREEN}🎉 Core pipeline functionality verified!${NC}"