# Basketball Video Ingestion Pipeline

A robust video ingestion pipeline for automatically uploading basketball game footage from NVIDIA Jetson Orin Nano to AWS S3. Designed specifically for processing GoPro recordings (2-5GB MP4/M4A files) with batch upload capabilities and web-based management interface.

## 🏀 Features

- **Automated GoPro Video Processing**: Handles large video files (2-5GB) from SD cards
- **AWS S3 Integration**: Secure cloud storage with configurable bucket management
- **Web Interface**: Simple UI for manual upload triggers and progress monitoring
- **Batch Processing**: Upload multiple videos efficiently with progress tracking
- **ARM64 Optimized**: Built for NVIDIA Jetson Orin Nano performance
- **Auto-cleanup**: Removes local files after successful upload to save storage
- **Robust Error Handling**: Comprehensive logging and retry mechanisms

## 📋 Requirements

- **Hardware**: NVIDIA Jetson Orin Nano (or ARM64 compatible device)
- **OS**: Ubuntu 22.04 LTS (ARM64)
- **Python**: 3.8+
- **Storage**: Sufficient space for temporary video processing
- **Network**: Reliable internet connection for AWS uploads
- **AWS Account**: With S3 access permissions

## 🚀 Quick Start

### 1. Clone Repository
```bash
git clone <repository-url>
cd Uball_ingestion_pipeline
```

### 2. Configure AWS Credentials
```bash
cp .env.template .env
nano .env  # Add your AWS credentials and bucket name
```

### 3. Deploy to Jetson (Production)
```bash
chmod +x deploy.sh
./deploy.sh
```

### 4. Access Web Interface
Open browser to: `http://<jetson-ip>:5000`

## 🛠️ Development Setup

### Local Testing with Docker
```bash
# Copy and configure environment
cp .env.template .env
# Edit .env with your AWS credentials

# Build and run
cd docker/
docker-compose up --build

# Access at http://localhost:5000
```

### Manual Development Setup
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/

# Test upload with sample video
python src/upload_manager.py --file sample_videos/basketball_game_sample.mp4 --test-mode

# Start web interface
python src/web_ui.py
```

## 📁 Project Structure

```
├── src/
│   ├── upload_manager.py    # Core upload logic
│   └── web_ui.py           # Flask web interface
├── tests/
│   └── test_upload.py      # Unit tests
├── docker/
│   ├── Dockerfile          # Container definition
│   └── docker-compose.yml  # Development environment
├── sample_videos/          # Test video files
├── config/                 # Configuration files
├── logs/                   # Application logs
├── deploy.sh              # One-command Jetson deployment
├── requirements.txt       # Python dependencies
├── .env.template         # Environment configuration template
└── CLAUDE.md            # Development commands reference
```

## 🔧 Configuration

### Environment Variables (.env)
```bash
# AWS Configuration
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
S3_BUCKET_NAME=basketball-recordings-prod

# GoPro Mount Paths
GOPRO_MOUNT_PATH=/media/usb/DCIM/100GOPRO

# Upload Settings
MAX_FILE_SIZE_GB=6
UPLOAD_CHUNK_SIZE_MB=50
```

## 🎯 Usage

### Web Interface Operations
1. **Scan for Videos**: Detect GoPro files in mounted devices
2. **Upload All Videos**: Batch upload with progress tracking
3. **Monitor Progress**: Real-time upload status and logs

### Command Line Usage
```bash
# Upload single file
python src/upload_manager.py --file /path/to/video.mp4

# Upload directory
python src/upload_manager.py --directory /media/usb/DCIM/100GOPRO

# Test mode (no file deletion)
python src/upload_manager.py --directory sample_videos --test-mode
```

### Service Management (Post-Deployment)
```bash
# Check status
sudo systemctl status basketball-upload

# View logs
sudo journalctl -u basketball-upload -f

# Restart service
sudo systemctl restart basketball-upload
```

## 🔍 Monitoring & Troubleshooting

### Log Locations
- **Service Logs**: `/var/log/basketball/`
- **System Logs**: `sudo journalctl -u basketball-upload`
- **Web Interface**: Built-in log viewer

### Common Issues
- **USB Mount Issues**: Check `/media/` and `/mnt/` directories
- **AWS Connection**: Verify credentials and S3 bucket permissions
- **Disk Space**: Ensure sufficient storage for video processing
- **Network**: Confirm stable internet for large file uploads

### Performance Monitoring
```bash
# Check upload performance
tail -f /var/log/basketball/upload.log | grep "MB/s"

# Monitor system resources
htop
iotop
```

## 📊 Technical Specifications

- **Supported Formats**: MP4, M4A, MOV
- **File Size Limit**: 6GB per video
- **Upload Method**: Multipart upload with progress tracking
- **Cleanup**: Automatic local file removal after successful upload
- **Concurrent Uploads**: Single-threaded for stability
- **Error Handling**: Retry logic with exponential backoff

## 🔐 Security

- **AWS IAM**: Use least-privilege access policies
- **Environment Variables**: Secure credential storage
- **Local Network**: Web interface accessible on local network only
- **File Permissions**: Proper user/group ownership

## 📈 AWS S3 Configuration

### Recommended S3 Bucket Structure
```
basketball-recordings-prod/
└── basketball_games/
    └── YYYY/MM/DD/HHMMSS/
        └── [hash]_video_filename.mp4
```

### S3 Lifecycle Policy (Optional)
- Transition to IA after 30 days
- Archive to Glacier after 90 days
- Delete after 365 days (configure as needed)

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📞 Support

For issues, questions, or contributions:
- Create GitHub issue for bugs/features
- Check `CLAUDE.md` for development commands
- Review logs in `/var/log/basketball/` for troubleshooting

## 🎥 Demo

1. Connect GoPro SD card to Jetson
2. Open `http://<jetson-ip>:5000`
3. Click "Scan for Videos" to detect files
4. Click "Upload All Videos" to start batch processing
5. Monitor progress in real-time
6. Videos automatically appear in S3 bucket