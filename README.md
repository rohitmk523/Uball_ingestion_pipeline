# 🏀 Basketball Multi-Angle Video Processing Pipeline

A complete solution for processing multi-angle basketball game footage from GoPro cameras. Designed for NVIDIA Jetson Orin Nano but can be tested on AWS EC2.

## 🚀 Features

- **Multi-camera synchronization** using timestamp-based UUIDs
- **Intelligent video processing** (4K compression, 1080p passthrough)
- **NVIDIA GPU acceleration** for fast compression
- **Real-time progress tracking** via WebSocket
- **S3 cloud storage** with multipart upload
- **Responsive web interface** for game management
- **Error handling and retry logic**

## 📋 System Requirements

### Production (Jetson Orin Nano)
- NVIDIA Jetson Orin Nano with JetPack SDK
- 2+ GoPro cameras with USB connections
- Internet connection for S3 upload
- 64GB+ storage (for temporary processing)

### Development/Testing (EC2)
- EC2 instance: `t3.xlarge` (CPU) or `g4dn.xlarge` (GPU)
- Ubuntu 20.04+
- FFmpeg with codec support
- Python 3.8+

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
│       ├── index.html             # Main web UI
│       ├── styles.css             # Styling
│       └── app.js                 # Frontend JavaScript
├── temp/                          # Temporary processing files
├── test_media/                    # Test videos for simulation
├── logs/                          # Application logs
├── config.json                    # Persisted configuration
├── requirements.txt               # Python dependencies
├── setup_ec2.sh                   # EC2 setup script
├── test_pipeline.sh               # Testing script
└── README.md                      # This file
```

## 🛠️ Installation

### Option 1: EC2 Testing Environment

1. **Launch EC2 Instance**
   ```bash
   # Recommended: g4dn.xlarge (with GPU) or t3.xlarge (CPU only)
   # Ubuntu 20.04 LTS
   # Security group: Allow port 8000
   ```

2. **Clone and Setup**
   ```bash
   git clone <repository-url>
   cd basketball-pipeline

   # Run setup script
   chmod +x setup_ec2.sh
   ./setup_ec2.sh
   ```

3. **Activate Environment**
   ```bash
   source venv/bin/activate
   ```

### Option 2: Jetson Orin Nano Production

1. **Prepare Jetson**
   ```bash
   # Install JetPack SDK first
   # Connect GoPros via USB
   ```

2. **Clone and Setup**
   ```bash
   git clone <repository-url>
   cd basketball-pipeline

   # Modify setup script for Jetson
   chmod +x setup_ec2.sh
   ./setup_ec2.sh
   ```

## 🚀 Quick Start

### 1. Start the Pipeline
```bash
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Access Web Interface
```
http://localhost:8000          # Local development
http://<ec2-public-ip>:8000    # EC2 instance
```

### 3. Configure System

1. **Set Side**: Choose "LEFT SIDE" or "RIGHT SIDE"
2. **AWS Credentials**: Enter S3 access credentials
3. **Load Cameras**: Click "Refresh Cameras" and "Load Video Files"

### 4. Process Games

1. **Define Games**: Add time ranges (e.g., 00:15:30 to 00:58:45)
2. **Start Processing**: Click "Start Processing All Games"
3. **Monitor Progress**: Watch real-time updates

## ⚙️ Configuration

### AWS S3 Setup
```json
{
  "aws_access_key": "AKIA...",
  "aws_secret_key": "...",
  "s3_bucket": "basketball-games",
  "s3_region": "us-east-1"
}
```

### IAM Permissions Required
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:PutObjectAcl",
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::basketball-games/*"
    }
  ]
}
```

## 🎥 Video Processing Logic

### Critical Resolution Check
```python
# ALWAYS check resolution before processing
width, height = get_resolution(video_file)

if is_4k_or_higher(width, height):  # ≥3840×2160
    # Compress to 1080p
    compress_video(input, output, use_gpu=True)
else:
    # Upload as-is, NO compression
    upload_to_s3(input)
```

### Processing Pipeline
1. **Extract Segment** (fast, copy codec)
2. **Check Resolution** (ffprobe)
3. **Conditional Compression** (only if 4K+)
4. **Upload to S3** (with retry logic)
5. **Cleanup** temporary files

### GPU vs CPU Performance
- **With GPU**: 3-5 minutes for 30 min of 4K footage
- **Without GPU**: 45-60 minutes for 30 min of 4K footage

## 📊 Output Structure

```
s3://basketball-games/
├── game-20250115-143045/        # Timestamp-based UUID
│   ├── far-left/video.mp4       # Jetson #1, Camera 1
│   ├── near-left/video.mp4      # Jetson #1, Camera 2
│   ├── far-right/video.mp4      # Jetson #2, Camera 1
│   └── near-right/video.mp4     # Jetson #2, Camera 2
├── game-20250115-150000/
│   └── ...
```

## 🧪 Testing

### Automated Tests
```bash
# Run comprehensive test suite
./test_pipeline.sh
```

### Manual Testing
1. Open web interface
2. Configure side and AWS credentials
3. Load test videos (created by setup script)
4. Add game: 00:00:30 to 00:01:30
5. Start processing
6. Verify 4K compression and 1080p passthrough

### Test Scenarios
- **Camera 1 (4K)**: Should compress to 1080p
- **Camera 2 (1080p)**: Should upload as-is
- **GPU fallback**: Test CPU encoding when GPU unavailable
- **Network errors**: Test S3 retry logic

## 🔧 Troubleshooting

### Common Issues

**No cameras detected**
```bash
# Check USB connections
lsusb
ls /media/

# For testing, ensure symlinks exist
ls -la /tmp/gopro*
```

**NVIDIA encoding fails**
```bash
# Check GPU
nvidia-smi
ffmpeg -encoders | grep nvenc

# Test hardware encoding
ffmpeg -hwaccel cuda -f lavfi -i testsrc=duration=5:size=1920x1080:rate=30 -c:v h264_nvenc test.mp4
```

**S3 upload fails**
```bash
# Test credentials
aws s3 ls s3://basketball-games/

# Check IAM permissions
aws sts get-caller-identity
```

### Log Files
```bash
# Application logs
tail -f logs/pipeline.log

# System service logs
sudo journalctl -u basketball-pipeline -f
```

## 🚀 Production Deployment

### Systemd Service
```bash
# Start service
sudo systemctl start basketball-pipeline

# Enable auto-start
sudo systemctl enable basketball-pipeline

# Check status
sudo systemctl status basketball-pipeline
```

### Health Monitoring
```bash
# Health check endpoint
curl http://localhost:8000/health
```

### Security Considerations
- Use IAM roles instead of hardcoded credentials
- Restrict S3 bucket access
- Use HTTPS in production
- Regular log rotation

## 📈 Performance Optimization

### Hardware Recommendations
- **Jetson Orin Nano**: Optimal for production use
- **EC2 g4dn.xlarge**: Best for testing with GPU
- **Storage**: NVMe SSD for temporary files

### Processing Optimization
- Process angles in parallel
- Use hardware encoding when available
- Immediate cleanup of temporary files
- Efficient S3 multipart uploads

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit pull request

## 📄 License

MIT License - see LICENSE file for details

## 🆘 Support

For issues and questions:
- Check troubleshooting section
- Review log files
- Open GitHub issue with:
  - System configuration
  - Error messages
  - Steps to reproduce

---

**Built for basketball coaches and analysts who need synchronized multi-angle footage processed efficiently at the edge.**