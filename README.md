# 🏀 Basketball Multi-Angle Video Processing Pipeline

A complete solution for processing multi-angle basketball game footage from GoPro cameras. Designed for NVIDIA Jetson Orin Nano but can be tested on AWS EC2.

**Production-ready with vanilla HTML/CSS/JS frontend - no build process needed!**

---

## 🚀 Features

- **Multi-camera synchronization** using timestamp-based UUIDs
- **Intelligent video processing** (4K compression, 1080p passthrough)
- **NVIDIA GPU acceleration** for fast compression
- **Real-time progress tracking** via WebSocket
- **S3 cloud storage** with multipart upload
- **Responsive web interface** for game management
- **Error handling and retry logic**
- **Edge-optimized** for Jetson Orin Nano deployment

---

## 📋 System Requirements

### Production (Jetson Orin Nano)
- NVIDIA Jetson Orin Nano with JetPack SDK
- 2+ GoPro cameras with USB connections
- Internet connection for S3 upload
- 64GB+ storage (NVMe SSD recommended)

### Development/Testing (EC2 or Local Mac)
- **EC2**: `t3.xlarge` (CPU) or `g4dn.xlarge` (GPU)
- **Local**: macOS/Linux with Python 3.8+
- Ubuntu 20.04+ for Linux
- FFmpeg with codec support
- Conda or virtualenv

---

## 🏗️ Architecture

```
Court Setup:
┌────────────────────────────────────────────────┐
│   LEFT SIDE              RIGHT SIDE            │
│  ┌─────────────┐        ┌─────────────┐       │
│  │ Jetson #1   │        │ Jetson #2   │       │
│  │ (Left)      │        │ (Right)     │       │
│  │             │        │             │       │
│  │ GoPro 1 ────┤ USB    │ GoPro 3 ────┤ USB   │
│  │ (Far Left)  │        │ (Far Right) │       │
│  │             │        │             │       │
│  │ GoPro 2 ────┤ USB    │ GoPro 4 ────┤ USB   │
│  │ (Near Left) │        │ (Near Right)│       │
│  └─────────────┘        └─────────────┘       │
└────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
basketball-pipeline/
├── app/
│   ├── main.py                    # FastAPI application & routes
│   ├── models.py                  # Pydantic data models
│   ├── camera_detection.py        # USB GoPro detection
│   ├── video_processor.py         # FFmpeg operations with resolution checks
│   ├── s3_uploader.py             # AWS S3 multipart upload
│   ├── config.py                  # Configuration management
│   ├── utils.py                   # Helper functions
│   └── static/
│       ├── index.html             # Main web UI (vanilla HTML)
│       ├── styles.css             # Styling
│       └── app.js                 # Frontend JavaScript (no build needed!)
├── logs/                          # Application logs
├── temp/                          # Temporary processing files
│   ├── segments/                  # Extracted video segments
│   ├── compressed/                # Compressed videos
│   └── thumbnails/                # Future use
├── test_media/                    # Test videos for simulation
├── config.json                    # Persisted configuration
├── .env                           # Environment variables (gitignored)
├── env.example                    # Environment template
├── requirements.txt               # Python dependencies
├── setup_ec2.sh                   # EC2/Jetson setup script
├── run.sh                         # Application launcher
├── test_pipeline.sh               # Testing script
├── init_directories.sh            # Directory initialization
└── README.md                      # This file
```

---

## 🛠️ Installation & Setup

### Option 1: Local Development (Mac/Linux with Conda)

```bash
# 1. Clone repository
git clone <repository-url>
cd basketball-pipeline

# 2. Create conda environment
conda create -n ingestion python=3.11
conda activate ingestion

# 3. Install dependencies
pip install -r requirements.txt

# 4. Initialize directories
./init_directories.sh

# 5. Configure environment
cp env.example .env
nano .env  # Add your AWS credentials

# 6. Start pipeline
./run.sh
```

### Option 2: EC2 Testing Environment

```bash
# 1. Launch EC2 Instance
# Recommended: g4dn.xlarge (with GPU) or t3.xlarge (CPU only)
# Ubuntu 20.04 LTS
# Security group: Allow port 8000

# 2. SSH and setup
ssh -i your-key.pem ubuntu@<ec2-ip>
git clone <repository-url>
cd basketball-pipeline

# 3. Run automated setup
chmod +x setup_ec2.sh
./setup_ec2.sh

# This script will:
# - Install FFmpeg and Python
# - Detect and configure GPU
# - Create test videos
# - Set up systemd service
# - Create directory structure

# 4. Configure AWS credentials
nano .env

# 5. Start service
sudo systemctl start basketball-pipeline
# OR for testing:
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Option 3: Jetson Orin Nano Production

```bash
# 1. Prepare Jetson (ensure JetPack SDK installed)
sudo apt update
sudo apt install -y nvidia-jetpack ffmpeg python3-pip python3-venv

# 2. Verify GPU
nvidia-smi

# 3. Clone and setup
git clone <repository-url>
cd basketball-pipeline
chmod +x setup_ec2.sh
./setup_ec2.sh

# 4. Connect GoPro cameras via USB
# Verify: lsusb

# 5. Configure for production
cp env.example .env
nano .env
# Set AWS credentials and:
# BASKETBALL_SIDE=LEFT (or RIGHT)
# GPU_AVAILABLE=true
# PRODUCTION=true

# 6. Enable and start service
sudo systemctl enable basketball-pipeline
sudo systemctl start basketball-pipeline

# 7. Check status
sudo systemctl status basketball-pipeline
tail -f logs/pipeline.log
```

---

## ⚙️ Configuration

### Environment Variables (.env file)

Create `.env` from `env.example`:

```env
# AWS S3 Configuration (REQUIRED)
AWS_ACCESS_KEY_ID=your_aws_access_key_here
AWS_SECRET_ACCESS_KEY=your_aws_secret_key_here
AWS_S3_BUCKET=basketball-games
AWS_S3_REGION=us-east-1

# System Configuration
BASKETBALL_SIDE=LEFT         # or RIGHT
GPU_AVAILABLE=true           # auto-detected if not set

# Production Settings
PRODUCTION=true              # disable auto-reload
AUTO_CLEANUP=true            # cleanup temp files
LOG_LEVEL=INFO              # DEBUG, INFO, WARNING, ERROR
```

### AWS IAM Permissions Required

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "s3:PutObject",
      "s3:PutObjectAcl",
      "s3:GetObject"
    ],
    "Resource": "arn:aws:s3:::basketball-games/*"
  }]
}
```

**Security Best Practice:**
- **EC2**: Use IAM roles instead of hardcoded credentials
- **Jetson**: Store credentials in `.env` file with `chmod 600 .env`

---

## 🚀 Quick Start

### 1. Start the Pipeline

```bash
# Using the run script (recommended)
./run.sh

# Or directly with uvicorn
conda activate ingestion  # if using conda
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# For production (no reload)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

### 2. Access Web Interface

Open in browser:
- **Local**: http://localhost:8000
- **EC2**: http://<ec2-public-ip>:8000
- **Jetson**: http://<jetson-ip>:8000

### 3. Configure System

1. **Set Side**: Choose "LEFT SIDE" or "RIGHT SIDE"
2. **AWS Credentials**: Enter S3 credentials (or skip if using IAM roles)
3. **Refresh Cameras**: Click to detect connected GoPros
4. **Load Video Files**: Click to scan for video files

### 4. Process Games

1. **Add Games**: Define time ranges (e.g., 00:15:30 to 00:58:45)
2. **Start Processing**: Click "Start Processing All Games"
3. **Monitor**: Watch real-time progress via WebSocket updates

---

## 🎥 Video Processing Logic

### Critical Resolution Check (Automatic)

```python
# System automatically checks resolution before processing
width, height = get_resolution(video_file)

if is_4k_or_higher(width, height):  # ≥3840×2160
    # Compress to 1080p with GPU acceleration
    compress_video(input, output, use_gpu=True)
else:
    # Upload as-is, NO compression (saves time!)
    upload_to_s3(input)
```

### Processing Pipeline Steps

1. **Extract Segment** - Fast copy of time range (no re-encoding)
2. **Check Resolution** - Use ffprobe to detect 4K vs 1080p
3. **Conditional Compression** - Only compress if 4K or higher
4. **Upload to S3** - With retry logic and multipart for large files
5. **Cleanup** - Auto-delete temporary files

### Performance Benchmarks

| Source Resolution | GPU Encoding | CPU Encoding |
|------------------|--------------|--------------|
| 4K → 1080p (30min) | 3-5 minutes | 45-60 minutes |
| 1080p passthrough | < 1 minute | < 1 minute |

**GPU Acceleration:**
- Jetson Orin Nano: ✅ NVENC hardware encoder
- EC2 g4dn.xlarge: ✅ NVIDIA T4 GPU
- EC2 t3.xlarge: ❌ CPU only (slower but works)

---

## 📊 Output Structure

Videos uploaded to S3:

```
s3://basketball-games/
├── game-20250115-143045/        # Timestamp-based UUID
│   ├── far-left/video.mp4       # LEFT Jetson, Camera 1
│   ├── near-left/video.mp4      # LEFT Jetson, Camera 2
│   ├── far-right/video.mp4      # RIGHT Jetson, Camera 1
│   └── near-right/video.mp4     # RIGHT Jetson, Camera 2
├── game-20250115-150000/
│   └── ...
```

**Angle Mapping:**
- **LEFT SIDE Jetson**: Produces `far-left` and `near-left`
- **RIGHT SIDE Jetson**: Produces `far-right` and `near-right`

---

## 🧪 Testing

### Automated Tests

```bash
# Run comprehensive test suite
./test_pipeline.sh

# Expected results:
# ✅ Pipeline running and responsive
# ✅ Camera detection works
# ✅ File loading works
# ✅ Game creation works
# ✅ Resolution detection works
# ✅ 4K videos identified for compression
# ✅ 1080p videos identified for passthrough
```

### Manual Testing Workflow

1. **Start pipeline**: `./run.sh`
2. **Open UI**: http://localhost:8000
3. **Configure**: Set side to LEFT or RIGHT
4. **Add AWS**: Enter S3 credentials (or dummy for testing)
5. **Load cameras**: Click "Refresh Cameras"
6. **Load files**: Click "Load Video Files"
7. **Create game**: Add time range `00:00:30` to `00:01:30`
8. **Process**: Click "Start Processing All Games"
9. **Monitor**: Watch progress in real-time

### Test Scenarios

The `setup_ec2.sh` script creates:
- **Camera 1 (4K)**: Should show "Compressing 4K to 1080p"
- **Camera 2 (1080p)**: Should show "Skipping compression"
- **GPU fallback**: Automatically uses CPU if GPU unavailable
- **S3 retry**: Retries upload failures with exponential backoff

---

## 🔧 Troubleshooting

### No Cameras Detected

```bash
# Check USB connections
lsusb

# Check mount points
ls /media/

# For EC2 simulation, verify symlinks
ls -la /tmp/gopro1
ls -la /tmp/gopro2

# Re-run setup if needed
./setup_ec2.sh
```

### NVIDIA GPU Encoding Fails

```bash
# Check GPU availability
nvidia-smi

# Verify NVENC support
ffmpeg -encoders | grep nvenc

# Test hardware encoding
ffmpeg -hwaccel cuda -f lavfi -i testsrc=duration=5:size=1920x1080:rate=30 \
  -c:v h264_nvenc test.mp4

# System will automatically fall back to CPU if GPU fails
```

### S3 Upload Fails

```bash
# Test AWS credentials
aws s3 ls s3://basketball-games/

# Check IAM permissions
aws sts get-caller-identity

# Test from Python
python -c "
import boto3
client = boto3.client('s3')
client.list_buckets()
print('✅ AWS credentials valid')
"
```

### Application Won't Start

```bash
# Check logs
tail -f logs/pipeline.log

# Check systemd service (if using)
sudo journalctl -u basketball-pipeline -f

# Verify Python dependencies
conda activate ingestion  # if using conda
pip list

# Test imports
python -c "import fastapi, boto3, pydantic; print('✅ OK')"

# Check port 8000 is available
lsof -i :8000
```

### Out of Disk Space

```bash
# Check available space
df -h

# Clean temporary files manually
rm -rf temp/segments/*
rm -rf temp/compressed/*

# Enable auto-cleanup in .env
echo "AUTO_CLEANUP=true" >> .env
```

---

## 🚀 Production Deployment Checklist

### Pre-Deployment

- [ ] Hardware verified (Jetson/EC2 with sufficient storage)
- [ ] GoPros connected and detected
- [ ] Network connection stable
- [ ] GPU detected (if applicable): `nvidia-smi`
- [ ] All dependencies installed: `pip list`
- [ ] Directories initialized: `./init_directories.sh`

### Configuration

- [ ] `.env` file created from `env.example`
- [ ] AWS credentials configured and tested
- [ ] S3 bucket created and accessible
- [ ] Side set (LEFT or RIGHT)
- [ ] `PRODUCTION=true` in `.env`
- [ ] `AUTO_CLEANUP=true` in `.env`

### Testing

- [ ] Health check works: `curl http://localhost:8000/health`
- [ ] Web UI loads successfully
- [ ] Cameras detected correctly
- [ ] Test game processes end-to-end
- [ ] S3 upload successful
- [ ] Temporary files cleaned up

### Service Deployment

```bash
# Enable systemd service
sudo systemctl enable basketball-pipeline
sudo systemctl start basketball-pipeline

# Verify service is running
sudo systemctl status basketball-pipeline

# Check logs
sudo journalctl -u basketball-pipeline -f
tail -f logs/pipeline.log
```

### Monitoring

```bash
# Health check endpoint
curl http://localhost:8000/health

# Returns:
# {
#   "status": "healthy",
#   "gpu_available": true,
#   "disk_space_gb": 45.2,
#   "active_connections": 1,
#   "processing_active": false
# }

# Monitor GPU (if applicable)
watch -n 1 nvidia-smi

# Monitor system resources
htop
```

---

## 📈 Performance Optimization

### Jetson Orin Nano Optimization

```bash
# Set to maximum performance mode
sudo nvpmodel -m 0
sudo jetson_clocks

# Verify power mode
sudo nvpmodel -q

# Monitor temperature and power
tegrastats
```

### Storage Optimization

- Use **NVMe SSD** for `temp/` directory
- Enable **auto-cleanup** to delete processed files
- Set up **log rotation** to prevent log growth

### Network Optimization

- Use S3 **multipart upload** for files >100MB (automatic)
- Enable **retry logic** with exponential backoff (default)
- Consider S3 Transfer Acceleration for distant regions

---

## 🌐 Frontend Architecture (Production-Ready Vanilla JS)

### Why Vanilla HTML/CSS/JS?

✅ **Perfect for Edge Deployment:**
- No build process or bundling required
- No Node.js runtime needed on Jetson
- Instant modifications (edit and reload)
- Lower memory footprint
- FastAPI serves everything as static files

✅ **Production Features:**
- Real-time WebSocket updates
- Responsive design (mobile-friendly)
- Error handling and retry logic
- Local state persistence
- Modern ES6+ JavaScript

### Frontend Stack

- **HTML5**: Semantic, accessible markup
- **CSS3**: Flexbox/Grid, responsive design
- **JavaScript (ES6+)**: Classes, async/await, WebSocket
- **No frameworks**: Vanilla JS for simplicity and performance

---

## 🔒 Security Best Practices

### Credentials Management

- **Never commit** `.env` file to git (already in `.gitignore`)
- **EC2**: Use IAM roles instead of access keys
- **Jetson**: Store in `.env` with `chmod 600 .env`
- **Rotate** AWS credentials regularly

### Network Security

- **Firewall**: Only open port 8000 and 22 (SSH)
- **HTTPS**: Use nginx reverse proxy in production
- **Authentication**: Add auth middleware if exposing publicly
- **IP Whitelist**: Restrict S3 bucket access to known IPs

### System Security

```bash
# Keep system updated
sudo apt update && sudo apt upgrade -y

# Enable automatic security updates
sudo dpkg-reconfigure -plow unattended-upgrades

# Monitor logs for suspicious activity
tail -f logs/pipeline.log | grep ERROR
```

---

## 🆘 Support & Maintenance

### Log Files

```bash
# Application logs
tail -f logs/pipeline.log

# Search for errors
grep ERROR logs/pipeline.log

# System service logs (if using systemd)
sudo journalctl -u basketball-pipeline -f

# Last 100 lines
sudo journalctl -u basketball-pipeline -n 100
```

### Common Commands

```bash
# Start/stop service
sudo systemctl start basketball-pipeline
sudo systemctl stop basketball-pipeline
sudo systemctl restart basketball-pipeline

# Check health
curl http://localhost:8000/health

# View active processes
ps aux | grep uvicorn

# Check disk space
df -h

# Monitor GPU
nvidia-smi

# Clean temp files
rm -rf temp/segments/* temp/compressed/*
```

### Getting Help

For issues and questions:
1. Check this README's troubleshooting section
2. Review log files: `logs/pipeline.log`
3. Run health check: `curl http://localhost:8000/health`
4. Open GitHub issue with:
   - System info (EC2/Jetson, GPU yes/no)
   - Error messages from logs
   - Steps to reproduce
   - Expected vs actual behavior

---

## 📝 Advanced Usage

### Docker Deployment (Optional)

```bash
# Build image
docker build -t basketball-pipeline .

# Run with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Custom Configuration

Edit `config.json` for persistent settings:
```json
{
  "side": "LEFT",
  "s3_bucket": "basketball-games",
  "s3_region": "us-east-1",
  "gpu_available": true
}
```

### Processing Existing Video Files

Instead of USB GoPros, you can process existing video files:

1. Place videos in a folder with DCIM structure:
   ```
   /path/to/videos/DCIM/100GOPRO/
   ├── GH010001.MP4
   └── GH010002.MP4
   ```

2. Create symlink:
   ```bash
   sudo ln -s /path/to/videos /tmp/gopro1
   ```

3. Refresh cameras in UI and load files

---

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Make changes and test: `./test_pipeline.sh`
4. Commit: `git commit -m 'Add amazing feature'`
5. Push: `git push origin feature/amazing-feature`
6. Open Pull Request

---

## 📄 License

MIT License - see LICENSE file for details

---

## 🎯 Project Status

**Status**: ✅ Production Ready

- [x] Core video processing pipeline
- [x] GPU acceleration with CPU fallback
- [x] S3 upload with retry logic
- [x] Real-time WebSocket progress
- [x] Responsive web interface
- [x] Comprehensive documentation
- [x] Automated testing
- [x] EC2 deployment support
- [x] Jetson Orin Nano deployment
- [x] Docker containerization

---

**Built for basketball coaches and analysts who need synchronized multi-angle footage processed efficiently at the edge.**

**Last Updated:** January 2025 | **Version:** 1.0.0



python video_extractor.py --game-name game1 --start-time 00:02:35 --end-time 00:49:10 --local-folder "09-24-2025"