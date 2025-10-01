#!/bin/bash

echo "🏀 Basketball Pipeline Setup for EC2 (Jetson Simulation)"
echo "========================================================="

# 1. Detect instance type
echo "📋 Detecting EC2 instance..."
if curl -s --max-time 5 http://169.254.169.254/latest/meta-data/instance-type > /dev/null 2>&1; then
    INSTANCE_TYPE=$(curl -s http://169.254.169.254/latest/meta-data/instance-type)
    echo "Instance type: $INSTANCE_TYPE"
else
    echo "Not running on EC2 or local development"
    INSTANCE_TYPE="local"
fi

# 2. Update system
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# 3. Install FFmpeg (CPU version for EC2 testing)
echo "📦 Installing FFmpeg..."
sudo apt install -y ffmpeg python3-pip python3-venv git curl

# 4. Check if NVIDIA GPU is available (for GPU instances)
echo "🎮 Checking for NVIDIA GPU..."
if command -v nvidia-smi &> /dev/null; then
    echo "✅ NVIDIA GPU detected!"
    nvidia-smi

    # Install NVIDIA drivers if not already installed
    if ! nvidia-smi &> /dev/null; then
        echo "📦 Installing NVIDIA drivers..."
        sudo apt install -y nvidia-driver-535 nvidia-cuda-toolkit
    fi

    GPU_AVAILABLE=true
else
    echo "⚠️  No NVIDIA GPU detected - will use CPU encoding"
    echo "   (This is slower but works for testing)"
    GPU_AVAILABLE=false
fi

# 5. Create Python virtual environment
echo "🐍 Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate

# 6. Install Python packages
echo "📦 Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

# 7. Create directories
echo "📁 Creating directories..."
mkdir -p temp/segments temp/compressed temp/thumbnails logs
mkdir -p test_media/gopro1/DCIM/100GOPRO
mkdir -p test_media/gopro2/DCIM/100GOPRO

# 8. Create symlinks to simulate USB mount points
echo "🔗 Creating symlinks for simulation..."
sudo mkdir -p /tmp/gopro1 /tmp/gopro2
sudo ln -sf $(pwd)/test_media/gopro1/DCIM /tmp/gopro1/DCIM
sudo ln -sf $(pwd)/test_media/gopro2/DCIM /tmp/gopro2/DCIM

# 9. Update config file with GPU availability
echo "📝 Updating configuration..."
if [ -f config.json ]; then
    # Update existing config
    python3 -c "
import json
with open('config.json', 'r') as f:
    config = json.load(f)
config['gpu_available'] = $GPU_AVAILABLE
with open('config.json', 'w') as f:
    json.dump(config, f, indent=2)
"
else
    # Create new config
    cat > config.json << EOF
{
    "side": null,
    "aws_access_key": "",
    "aws_secret_key": "",
    "s3_bucket": "basketball-games",
    "s3_region": "us-east-1",
    "gpu_available": $GPU_AVAILABLE
}
EOF
fi

# 10. Create systemd service
echo "⚙️  Creating systemd service..."
sudo tee /etc/systemd/system/basketball-pipeline.service > /dev/null << EOF
[Unit]
Description=Basketball Video Processing Pipeline
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
Environment="PATH=$(pwd)/venv/bin"
Environment="AWS_ACCESS_KEY_ID="
Environment="AWS_SECRET_ACCESS_KEY="
ExecStart=$(pwd)/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 11. Enable service
sudo systemctl daemon-reload
sudo systemctl enable basketball-pipeline.service

# 12. Test FFmpeg encoding
echo "🎬 Testing FFmpeg encoding capabilities..."
if [ "$GPU_AVAILABLE" = true ]; then
    echo "Testing NVIDIA hardware encoding..."
    ffmpeg -encoders 2>/dev/null | grep nvenc
else
    echo "Testing CPU encoding with libx264..."
    ffmpeg -encoders 2>/dev/null | grep libx264
fi

# 13. Create test videos (simulating GoPro footage)
echo "🎥 Creating test videos for simulation..."

# Camera 1: 4K video (should be compressed)
echo "Creating 4K test video (Camera 1)..."
ffmpeg -f lavfi -i testsrc=duration=120:size=3840x2160:rate=30 \
    -f lavfi -i sine=frequency=1000:duration=120 \
    -pix_fmt yuv420p -c:v libx264 -preset ultrafast \
    -metadata creation_time="2025-01-15T14:30:00Z" \
    test_media/gopro1/DCIM/100GOPRO/GH010001.MP4 -y

# Camera 2: 1080p video (should NOT be compressed)
echo "Creating 1080p test video (Camera 2)..."
ffmpeg -f lavfi -i testsrc=duration=120:size=1920x1080:rate=30 \
    -f lavfi -i sine=frequency=1000:duration=120 \
    -pix_fmt yuv420p -c:v libx264 -preset ultrafast \
    -metadata creation_time="2025-01-15T14:30:00Z" \
    test_media/gopro2/DCIM/100GOPRO/GH010001.MP4 -y

# Additional test videos with different start times
echo "Creating additional test videos..."
ffmpeg -f lavfi -i testsrc=duration=180:size=3840x2160:rate=30 \
    -f lavfi -i sine=frequency=800:duration=180 \
    -pix_fmt yuv420p -c:v libx264 -preset ultrafast \
    -metadata creation_time="2025-01-15T15:00:00Z" \
    test_media/gopro1/DCIM/100GOPRO/GH010002.MP4 -y

ffmpeg -f lavfi -i testsrc=duration=180:size=1920x1080:rate=30 \
    -f lavfi -i sine=frequency=800:duration=180 \
    -pix_fmt yuv420p -c:v libx264 -preset ultrafast \
    -metadata creation_time="2025-01-15T15:00:00Z" \
    test_media/gopro2/DCIM/100GOPRO/GH010002.MP4 -y

echo ""
echo "✅ Setup complete!"
echo ""
echo "GPU Available: $GPU_AVAILABLE"
echo ""
echo "📁 Test videos created:"
echo "  Camera 1 (4K): test_media/gopro1/DCIM/100GOPRO/"
echo "  Camera 2 (1080p): test_media/gopro2/DCIM/100GOPRO/"
echo ""
echo "🔗 Simulated mount points:"
echo "  /tmp/gopro1 -> $(pwd)/test_media/gopro1"
echo "  /tmp/gopro2 -> $(pwd)/test_media/gopro2"
echo ""
echo "🚀 To start the pipeline:"
echo "  source venv/bin/activate"
echo "  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "🌐 Access the UI at:"
if [ "$INSTANCE_TYPE" != "local" ]; then
    PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "localhost")
    echo "  http://$PUBLIC_IP:8000"
else
    echo "  http://localhost:8000"
fi
echo ""
echo "🧪 Test scenario:"
echo "  1. Set side to LEFT or RIGHT"
echo "  2. Configure AWS credentials (use dummy for testing)"
echo "  3. Load cameras and files"
echo "  4. Add game: 00:00:30 to 00:01:30 (1 minute segment)"
echo "  5. Start processing"
echo ""
echo "📋 Expected behavior:"
echo "  - Camera 1 (4K): Should compress to 1080p"
echo "  - Camera 2 (1080p): Should upload as-is (no compression)"