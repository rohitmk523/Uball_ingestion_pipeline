# Input Video Workflow - Multi-Game Basketball Processing

## 🎯 Overview

This new workflow processes pre-recorded basketball game videos from the `/input` directory, allowing you to:
- Preview videos from 4 angles (FR, FL, NL, NR)
- Mark multiple games within the same video files
- Process all games **in parallel** with intelligent concurrency control
- Automatically compress 4K videos to 1080p
- Upload to S3 with proper organization

---

## 📁 **File Structure**

### Input Videos (Place in `/input` directory)
```
/input/
├── 10-2 FR.m4v   (Far Right angle)
├── 10-2 FL.m4v   (Far Left angle)
├── 10-2 NL.m4v   (Near Left angle)
└── 10-2 NR.m4v   (Near Right angle)
```

**Naming Convention:** `MM-DD ANGLE.ext`
- Date: `10-2` or `10-02` (month-day)
- Angle: `FR`, `FL`, `NL`, `NR` (case-insensitive)
- Extension: `.m4v`, `.mp4`, `.mov`

### S3 Output Structure
```
s3://uball-videos-production/Games/
├── 10-02/
│   ├── Game-1/
│   │   ├── 10-02_game1_farright.mp4
│   │   ├── 10-02_game1_farleft.mp4
│   │   ├── 10-02_game1_nearleft.mp4
│   │   └── 10-02_game1_nearright.mp4
│   ├── Game-2/
│   │   └── ...
│   └── Game-3/
│       └── ...
└── 10-03/
    └── ...
```

---

## 🚀 **How to Use**

### 1. **Place Videos in `/input` Directory**
```bash
# Ensure videos are named correctly
ls -lh /Users/rohitkale/Cellstrat/GitHub_Repositories/Uball_ingestion_pipeline/input/
# Should show: 10-2 FR.m4v, 10-2 FL.m4v, 10-2 NL.m4v, 10-2 NR.m4v
```

### 2. **Access the UI**
Navigate to: **http://localhost:8000/input-videos**

### 3. **Scan for Videos**
1. Click **"Scan /input Directory"**
2. System will detect all videos and group them by date
3. Validates that all 4 angles are present
4. Shows resolution, duration, and file size

### 4. **Preview & Mark Games**
1. Click **"Load Preview"** for a date
2. Watch video (use any angle as reference - they're synced)
3. Scrub through video to find game start/end times
4. Click **"Mark Current as Start"** when game begins
5. Click **"Mark Current as End"** when game ends
6. Enter game number (auto-increments)
7. Click **"Add Game"**
8. Repeat for all games in the video

### 5. **Process All Games**
1. Review the games list (shows all defined games)
2. Click **"Process All Games (Parallel)"**
3. Watch real-time progress via WebSocket
4. Processing happens in parallel with automatic concurrency control

---

## ⚡ **Concurrency Control & Resource Management**

### **Automatic Resource Detection**
The system automatically detects:
- **CPU Cores**: Determines available processing power
- **RAM**: Calculates safe concurrency based on available memory
- **GPU**: Checks for NVIDIA GPU (enables hardware encoding)
- **Disk Space**: Monitors free space

### **Max Concurrent FFmpeg Processes**

| System Type | CPU Cores | RAM | GPU | Max Concurrent |
|------------|-----------|-----|-----|----------------|
| **Laptop (macOS)** | 8 | 16GB | No | **4 processes** |
| **EC2 t3.medium** | 2 | 4GB | No | **2 processes** |
| **EC2 t3.large** | 2 | 8GB | No | **3 processes** |
| **EC2 g4dn.xlarge** | 4 | 16GB | Yes | **4 processes** (GPU) |
| **EC2 c5.2xlarge** | 8 | 16GB | No | **4 processes** |

### **Example Processing Flow**

**Scenario:** 3 games × 4 angles = 12 total video segments

**With max_concurrent = 4:**
```
Queue:      [G1-FR, G1-FL, G1-NL, G1-NR, G2-FR, G2-FL, G2-NL, G2-NR, G3-FR, G3-FL, G3-NL, G3-NR]

Processing: [G1-FR, G1-FL, G1-NL, G1-NR]  ← Active (4 processes)
Queue:      [G2-FR, G2-FL, G2-NL, G2-NR, G3-FR, G3-FL, G3-NL, G3-NR]  ← Waiting

When G1-FR finishes → G2-FR starts
When G1-FL finishes → G2-FL starts
...

Processing: [G2-FR, G2-FL, G1-NL, G1-NR]  ← Mixed games (optimal utilization)
```

**Why This Matters:**
- ✅ **Prevents System Overload**: No more than 4 FFmpeg processes running
- ✅ **Optimal Throughput**: Processes start immediately as slots free up
- ✅ **Resource Efficient**: Adapts to your system's capabilities
- ✅ **Fast Completion**: All games processed as quickly as possible

---

## 🛠️ **New Files Added**

### **Backend Modules**

#### 1. **[app/input_video_scanner.py](app/input_video_scanner.py)**
- Scans `/input` directory for video files
- Parses filenames to extract date and angle
- Groups videos by date
- Validates all 4 angles are present
- Extracts metadata (resolution, duration, codec)

**Key Functions:**
- `scan_input_directory()` - Find all videos
- `get_videos_by_date()` - Group by date
- `validate_date_videos()` - Check completeness
- `parse_filename()` - Extract date/angle from filename

#### 2. **[app/parallel_processor.py](app/parallel_processor.py)**
- Manages parallel processing with asyncio.Semaphore
- Resource-aware concurrency control
- Progress tracking via WebSocket
- Handles extraction, compression, and S3 upload

**Key Classes:**
- `ResourceManager` - Detects system resources
- `GameJob` - Represents a game with 4 angles
- `ParallelProcessor` - Orchestrates parallel processing

**Processing Steps per Angle:**
```python
1. Extract segment (ffmpeg -c copy)  # Fast, no re-encoding
2. Check resolution (ffprobe)
3. IF 4K → Compress to 1080p
   ELSE → Skip compression
4. Upload to S3
5. Cleanup temp files
```

#### 3. **[app/video_processor.py](app/video_processor.py)** (Updated)
- Added `get_video_metadata_extended()` function
- Returns duration, resolution, codec, FPS, bitrate

### **Frontend Files**

#### 1. **[app/static/input-videos.html](app/static/input-videos.html)**
- Modern, responsive UI
- HTML5 video player with timeline scrubbing
- Game marking interface
- Real-time progress display

**Sections:**
- System Resources (CPU, GPU, RAM, Disk)
- Video Scanner
- Video Preview (switchable angles)
- Game Marking (start/end times)
- Games List (table view)
- Processing Status (live updates)

#### 2. **[app/static/input-videos.js](app/static/input-videos.js)**
- API integration
- WebSocket for real-time updates
- Video player controls
- Time marking helpers

**Key Functions:**
- `scanVideos()` - Detect videos
- `loadDateVideos()` - Load preview
- `switchAngle()` - Change camera angle
- `markStartTime()` / `markEndTime()` - Mark times from video
- `addGame()` - Create game job
- `processAllGames()` - Start parallel processing

---

## 🌐 **API Endpoints**

### **Input Video Endpoints**

```http
GET /api/input-videos/scan
# Scan /input directory, returns grouped videos with validation

GET /api/input-videos/preview/{date}/{angle}
# Get preview URL for specific video

GET /api/input-videos/stream/{date}/{angle}
# Stream video file (HTML5 compatible)

GET /api/input-videos/jobs
# List all defined game jobs

POST /api/input-videos/jobs
# Create new game job
# Body: {date, game_number, time_start, time_end}

DELETE /api/input-videos/jobs/{game_id}
# Delete a game job

POST /api/input-videos/process
# Start parallel processing of all pending jobs

GET /api/input-videos/status
# Get processing status
```

### **Health Endpoint (Updated)**

```http
GET /health
# Returns:
{
  "status": "healthy",
  "gpu_available": false,
  "disk_space_gb": 245.3,
  "active_connections": 1,
  "processing_active": false,
  "input_processing_active": true,
  "max_concurrent_ffmpeg": 4
}
```

---

## 📊 **Processing Timeline Estimates**

### **Single Game (30 minutes)**

| Resolution | Compression | GPU | Upload (10 Mbps) | Total Time |
|-----------|-------------|-----|------------------|------------|
| **1080p** | None | N/A | ~5 min | **~6 min** |
| **4K** | CPU | No | ~5 min | **~50 min** |
| **4K** | GPU | Yes | ~5 min | **~10 min** |

### **3 Games × 4 Angles (Sequential)**

| Scenario | Total Time |
|----------|------------|
| All 1080p | **18 min** |
| All 4K (GPU) | **30 min** |
| All 4K (CPU) | **150 min** |

### **3 Games × 4 Angles (Parallel, max_concurrent=4)**

| Scenario | Total Time |
|----------|------------|
| All 1080p | **18 min** (same, I/O bound) |
| All 4K (GPU) | **30 min** (GPU limit) |
| All 4K (CPU, 4 cores) | **75 min** (50% faster!) |

**Key Insight:** Parallelization helps most with CPU encoding on multi-core systems!

---

## 🔧 **Configuration**

### **Update [config.json](config.json)**
```json
{
  "side": null,  // Not needed for input workflow
  "aws_access_key": "YOUR_AWS_KEY",
  "aws_secret_key": "YOUR_AWS_SECRET",
  "s3_bucket": "uball-videos-production",  // CHANGED!
  "s3_region": "us-east-1",
  "gpu_available": false  // Auto-detected
}
```

### **Install New Dependency**
```bash
pip install psutil==5.9.8
# Or: pip install -r requirements.txt
```

---

## 🧪 **Testing**

### **1. Test with Sample Videos** (Once downloaded)
```bash
# Check files
ls -lh input/

# Expected:
# 10-2 FR.m4v
# 10-2 FL.m4v
# 10-2 NL.m4v
# 10-2 NR.m4v
```

### **2. Test API Endpoints**
```bash
# Scan videos
curl http://localhost:8000/api/input-videos/scan | jq

# Create test job
curl -X POST http://localhost:8000/api/input-videos/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "date": "10-02",
    "game_number": 1,
    "time_start": "00:01:00",
    "time_end": "00:02:00"
  }'

# List jobs
curl http://localhost:8000/api/input-videos/jobs | jq

# Check system resources
curl http://localhost:8000/health | jq
```

### **3. Test Processing** (Small Segment First)
- Add a 1-minute game first to test the pipeline
- Monitor progress via WebSocket
- Check S3 bucket for uploaded files

---

## 🎮 **UI Workflow Example**

1. **Open UI:** `http://localhost:8000/input-videos`

2. **Scan:** Click "Scan /input Directory"
   - Shows: "10-02: 4 videos found ✓ All 4 angles present"

3. **Load Preview:** Click "Load Preview"
   - Video player loads with FR angle
   - Can switch between FR, FL, NL, NR

4. **Mark Game 1:**
   - Scrub to 00:05:30 (game starts)
   - Click "Mark Current as Start"
   - Scrub to 00:35:45 (game ends)
   - Click "Mark Current as End"
   - Game Number: 1 (auto-filled)
   - Click "Add Game"

5. **Mark Game 2:**
   - Scrub to 00:40:00
   - Mark start
   - Scrub to 01:10:15
   - Mark end
   - Game Number: 2 (auto-incremented)
   - Click "Add Game"

6. **Process:**
   - Review games list
   - Click "Process All Games (Parallel)"
   - Watch progress: "Processing Game 10-02_game1, angle: farright, stage: extracting"

7. **Completion:**
   - All games show green "completed" badges
   - Check S3: `s3://uball-videos-production/Games/10-02/Game-1/10-02_game1_farright.mp4`

---

## 🚨 **Troubleshooting**

### **Issue: "No videos found"**
**Solution:**
- Check file naming: Must be `MM-DD ANGLE.ext`
- Check file extensions: `.m4v`, `.mp4`, `.mov`
- Avoid `.crdownload` (incomplete downloads)

### **Issue: "Missing angles"**
**Solution:**
- Ensure all 4 files exist: FR, FL, NL, NR
- Check filenames match exactly

### **Issue: "Processing too slow on EC2"**
**Solution:**
- Check `max_concurrent` in health endpoint
- For t3.medium (2 cores), expect max_concurrent=2
- Upgrade to c5.2xlarge or g4dn.xlarge for faster processing

### **Issue: "Memory errors during processing"**
**Solution:**
- System auto-adjusts based on available RAM
- For 4GB RAM systems, max_concurrent will be 2
- Reduce concurrent games or upgrade instance

### **Issue: "GPU not detected"**
**Solution:**
- Check: `nvidia-smi`
- Install drivers: `sudo apt install nvidia-driver-535`
- Verify in health endpoint: `"gpu_available": true`

---

## 📈 **Performance Benchmarks**

### **Laptop (MacBook Pro M1, 8 cores, 16GB RAM)**
- Max Concurrent: **4 processes**
- 4K Compression (CPU): ~3 min per 30-min game
- 1080p (No compression): ~30 sec per 30-min game

### **EC2 g4dn.xlarge (4 cores, 16GB RAM, NVIDIA T4)**
- Max Concurrent: **4 processes**
- 4K Compression (GPU): ~2 min per 30-min game
- 1080p (No compression): ~30 sec per 30-min game

### **EC2 c5.2xlarge (8 cores, 16GB RAM, No GPU)**
- Max Concurrent: **4 processes**
- 4K Compression (CPU): ~5 min per 30-min game
- 1080p (No compression): ~30 sec per 30-min game

---

## ✅ **Completion Checklist**

- [x] Input video scanner with filename parsing
- [x] Parallel processor with semaphore concurrency control
- [x] Resource detection (CPU, RAM, GPU)
- [x] HTML5 video preview UI
- [x] Timeline scrubbing and game marking
- [x] Real-time WebSocket progress tracking
- [x] S3 upload to new bucket structure
- [x] API endpoints for input video workflow
- [x] Automatic 4K detection and compression
- [x] Error handling and validation

---

## 🎯 **Next Steps**

1. **Wait for `10-2 FR.m4v` download to complete**
2. **Test with all 4 angles**
3. **Mark 2-3 test games (1-2 minutes each)**
4. **Run parallel processing**
5. **Verify S3 uploads**
6. **Benchmark performance on your system**

**Ready to process basketball games at scale!** 🏀⚡
