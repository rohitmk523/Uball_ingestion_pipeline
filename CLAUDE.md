# Claude Development Commands

This file contains common commands and setup instructions for developing the Basketball Video Ingestion Pipeline.

## Quick Start Commands

### Development Setup
```bash
# Clone and setup repository
git clone <repository-url>
cd Uball_ingestion_pipeline

# Copy environment template
cp .env.template .env
# Edit .env with your AWS credentials
nano .env

# Install dependencies in virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Testing Commands
```bash
# Run unit tests
pytest tests/

# Test upload with sample video
python src/upload_manager.py --file sample_videos/basketball_game_sample.mp4 --test-mode

# Test directory scan
python src/upload_manager.py --directory sample_videos --test-mode

# Run web interface locally
python src/web_ui.py
# Open: http://localhost:5000
```

### Docker Development
```bash
# Build and run container
cd docker/
cp ../.env.template .env
# Edit .env with AWS credentials
docker-compose up --build

# Development mode with live code changes
docker-compose --profile dev up dev-tools

# ARM64 build for Jetson compatibility
docker buildx build --platform=linux/arm64 -t basketball-pipeline:arm64 -f docker/Dockerfile .
```

### Production Deployment (Jetson)
```bash
# One-command deployment on Jetson
./deploy.sh

# Check service status
sudo systemctl status basketball-upload

# View live logs
sudo journalctl -u basketball-upload -f

# Manual start/stop
sudo systemctl start basketball-upload
sudo systemctl stop basketball-upload

# Restart service after changes
sudo systemctl restart basketball-upload
```

## AWS S3 Setup Commands

### Create S3 Bucket
```bash
# Set your bucket name
export BUCKET_NAME="basketball-recordings-prod"

# Create bucket
aws s3 mb s3://$BUCKET_NAME --region us-east-1

# Set bucket policy for lifecycle management
aws s3api put-bucket-lifecycle-configuration \
  --bucket $BUCKET_NAME \
  --lifecycle-configuration file://config/s3-lifecycle.json
```

### S3 Management
```bash
# List uploaded videos
aws s3 ls s3://$BUCKET_NAME/basketball_games/ --recursive

# Check bucket size
aws s3api list-objects-v2 --bucket $BUCKET_NAME \
  --query 'sum(Contents[].Size)' --output text | awk '{print $1/1024/1024/1024 " GB"}'

# Download specific game
aws s3 cp s3://$BUCKET_NAME/basketball_games/2024/01/15/ . --recursive
```

## Debugging Commands

### System Diagnostics
```bash
# Check disk space
df -h

# Check USB mounts
lsblk
mount | grep media

# Check network connectivity
ping -c 3 s3.amazonaws.com
curl -I https://s3.us-east-1.amazonaws.com

# Check service logs
sudo journalctl -u basketball-upload --since "1 hour ago"

# Check Python dependencies
pip list | grep -E "(boto3|flask)"
```

### GoPro USB Debugging
```bash
# List USB devices
lsusb
dmesg | grep -i usb | tail -10

# Check mount points
ls -la /media/
ls -la /mnt/

# Manual mount GoPro (if auto-mount fails)
sudo mkdir -p /media/gopro
sudo mount /dev/sdb1 /media/gopro
ls -la /media/gopro/DCIM/100GOPRO/
```

### Upload Troubleshooting
```bash
# Test AWS credentials
aws sts get-caller-identity

# Test S3 access
aws s3 ls s3://$BUCKET_NAME/

# Test upload single file
python src/upload_manager.py --file sample_videos/basketball_game_sample.mp4 --test-mode

# Check upload logs
tail -f /var/log/basketball/upload.log

# Monitor system resources during upload
htop
iotop
```

## Performance Monitoring

### System Resources
```bash
# Monitor CPU/Memory during upload
watch -n 1 'ps aux | grep -E "(python|upload)" | grep -v grep'

# Check network usage
iftop
nethogs

# Monitor disk I/O
iotop -o
```

### Upload Performance
```bash
# Monitor upload speed
tail -f /var/log/basketball/upload.log | grep -E "(MB/s|Upload completed)"

# Check S3 transfer acceleration
aws configure set default.s3.use_accelerate_endpoint true
```

## Common Issues & Fixes

### Permission Issues
```bash
# Fix file permissions
sudo chown -R $USER:$USER /opt/basketball-pipeline
sudo chmod +x /opt/basketball-pipeline/src/*.py

# Fix log directory permissions
sudo chown -R $USER:$USER /var/log/basketball
```

### Service Issues
```bash
# Restart service after configuration changes
sudo systemctl daemon-reload
sudo systemctl restart basketball-upload

# Check service configuration
sudo systemctl cat basketball-upload

# Reset failed service
sudo systemctl reset-failed basketball-upload
```

### AWS Connection Issues
```bash
# Test with different region
export AWS_DEFAULT_REGION=us-west-2

# Use IAM role instead of keys (recommended for EC2/Jetson)
# Remove AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY from .env
# Attach IAM role with S3 permissions to EC2 instance
```

## Development Workflow

1. **Local Development**:
   ```bash
   python src/upload_manager.py --test-mode
   python src/web_ui.py
   ```

2. **Docker Testing**:
   ```bash
   docker-compose up --build
   ```

3. **Push to Repository**:
   ```bash
   git add .
   git commit -m "Feature: description"
   git push origin main
   ```

4. **Deploy to Jetson**:
   ```bash
   # On Jetson
   git pull origin main
   ./deploy.sh
   ```

## Useful Environment Variables

```bash
# Development
export FLASK_DEBUG=1
export LOG_LEVEL=DEBUG

# Production
export S3_BUCKET_NAME=basketball-recordings-prod
export AWS_REGION=us-east-1
export MAX_FILE_SIZE_GB=6
```

## Maintenance Commands

```bash
# Update Python dependencies
pip install --upgrade -r requirements.txt

# Clean up old logs
sudo find /var/log/basketball -name "*.log" -mtime +7 -delete

# Update system packages
sudo apt update && sudo apt upgrade -y

# Backup configuration
tar -czf basketball-backup-$(date +%Y%m%d).tar.gz .env src/ config/
```