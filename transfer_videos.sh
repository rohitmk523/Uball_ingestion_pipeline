#!/bin/bash

echo "📹 Basketball Pipeline - Video Transfer Script"
echo "=============================================="

# Configuration
KEY_NAME="uball-basketball-key"
REMOTE_USER="ubuntu"
REMOTE_DIR="/home/ubuntu/Uball_ingestion_pipeline/input"
LOCAL_DIR="./input"

# Check if EC2 IP is provided
if [ -z "$1" ]; then
    echo "❌ Error: EC2 instance IP address required"
    echo ""
    echo "Usage: ./transfer_videos.sh <EC2_PUBLIC_IP>"
    echo ""
    echo "Example: ./transfer_videos.sh 3.84.123.45"
    echo ""

    # Try to read from saved instance info
    if [ -f "ec2_instance_info.txt" ]; then
        PUBLIC_IP=$(grep "Public IP:" ec2_instance_info.txt | cut -d' ' -f3)
        echo "💡 Hint: Found saved instance IP: $PUBLIC_IP"
        echo "   Run: ./transfer_videos.sh $PUBLIC_IP"
    fi
    exit 1
fi

EC2_IP="$1"

# Check if key file exists
if [ ! -f "${KEY_NAME}.pem" ]; then
    echo "❌ Error: Key file '${KEY_NAME}.pem' not found"
    echo "   Run ./launch_ec2.sh first to create the key pair"
    exit 1
fi

# Check if local input directory exists
if [ ! -d "$LOCAL_DIR" ]; then
    echo "❌ Error: Local input directory '$LOCAL_DIR' not found"
    exit 1
fi

# Count files in local directory
FILE_COUNT=$(find "$LOCAL_DIR" -type f \( -name "*.mp4" -o -name "*.m4v" -o -name "*.mov" \) | wc -l | tr -d ' ')

if [ "$FILE_COUNT" -eq 0 ]; then
    echo "❌ Error: No video files found in '$LOCAL_DIR'"
    echo "   Looking for: *.mp4, *.m4v, *.mov"
    exit 1
fi

echo "✓ Found $FILE_COUNT video file(s) to transfer"
echo "✓ Key file: ${KEY_NAME}.pem"
echo "✓ Target: $REMOTE_USER@$EC2_IP:$REMOTE_DIR"
echo ""

# Calculate total size
TOTAL_SIZE=$(du -sh "$LOCAL_DIR" | cut -f1)
echo "📊 Total data to transfer: $TOTAL_SIZE"
echo ""

# Test SSH connection
echo "🔍 Testing SSH connection..."
if ! ssh -i "${KEY_NAME}.pem" -o ConnectTimeout=10 -o StrictHostKeyChecking=no "$REMOTE_USER@$EC2_IP" "echo 'Connection successful'" &>/dev/null; then
    echo "❌ Error: Cannot connect to EC2 instance"
    echo "   Make sure:"
    echo "   1. Instance is running (check AWS console)"
    echo "   2. IP address is correct: $EC2_IP"
    echo "   3. Security group allows SSH (port 22)"
    echo "   4. Wait 1-2 minutes after launching for instance to fully initialize"
    exit 1
fi

echo "✅ SSH connection successful"
echo ""

# Create remote directory if it doesn't exist
echo "📁 Creating remote directory structure..."
ssh -i "${KEY_NAME}.pem" -o StrictHostKeyChecking=no "$REMOTE_USER@$EC2_IP" "mkdir -p $REMOTE_DIR"

echo "✅ Remote directory ready"
echo ""

# Start transfer
echo "🚀 Starting video transfer..."
echo "   This may take several hours depending on file size and network speed"
echo "   Transfer is resumable - you can Ctrl+C and re-run this script to continue"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Use rsync with progress and partial transfer support
rsync -avzP --partial \
    -e "ssh -i ${KEY_NAME}.pem -o StrictHostKeyChecking=no" \
    "$LOCAL_DIR/" \
    "$REMOTE_USER@$EC2_IP:$REMOTE_DIR/"

RSYNC_EXIT=$?

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ $RSYNC_EXIT -eq 0 ]; then
    echo "✅ Transfer completed successfully!"
    echo ""

    # Verify files on remote
    echo "🔍 Verifying files on remote instance..."
    REMOTE_FILE_COUNT=$(ssh -i "${KEY_NAME}.pem" -o StrictHostKeyChecking=no "$REMOTE_USER@$EC2_IP" \
        "find $REMOTE_DIR -type f \( -name '*.mp4' -o -name '*.m4v' -o -name '*.mov' \) | wc -l" | tr -d ' ')

    echo "   Local files:  $FILE_COUNT"
    echo "   Remote files: $REMOTE_FILE_COUNT"

    if [ "$FILE_COUNT" -eq "$REMOTE_FILE_COUNT" ]; then
        echo "✅ File count matches!"
        echo ""
        echo "=============================================="
        echo "🎉 Video Transfer Complete!"
        echo "=============================================="
        echo ""
        echo "📝 Next Steps:"
        echo ""
        echo "1. SSH into the instance:"
        echo "   ssh -i ${KEY_NAME}.pem $REMOTE_USER@$EC2_IP"
        echo ""
        echo "2. Clone the repository (if not already done):"
        echo "   git clone https://github.com/yourusername/Uball_ingestion_pipeline.git"
        echo "   cd Uball_ingestion_pipeline"
        echo ""
        echo "3. Copy videos to the cloned repository:"
        echo "   mkdir -p input"
        echo "   cp $REMOTE_DIR/* input/"
        echo ""
        echo "4. Create .env file with AWS credentials:"
        echo "   cat > .env << 'EOF'"
        echo "   AWS_ACCESS_KEY_ID=your_key_here"
        echo "   AWS_SECRET_ACCESS_KEY=your_secret_here"
        echo "   S3_BUCKET=your_bucket_name"
        echo "   S3_REGION=us-east-1"
        echo "   EOF"
        echo ""
        echo "5. Install dependencies:"
        echo "   sudo apt update && sudo apt install -y python3-pip python3-venv ffmpeg"
        echo "   python3 -m venv venv"
        echo "   source venv/bin/activate"
        echo "   pip install -r requirements.txt"
        echo ""
        echo "6. Start the server (in a screen session for persistence):"
        echo "   screen -S basketball"
        echo "   source venv/bin/activate"
        echo "   uvicorn app.main:app --host 0.0.0.0 --port 8000"
        echo "   # Press Ctrl+A then D to detach"
        echo ""
        echo "7. From your laptop, create SSH tunnel:"
        echo "   ssh -L 8000:localhost:8000 -i ${KEY_NAME}.pem $REMOTE_USER@$EC2_IP"
        echo ""
        echo "8. Open in browser:"
        echo "   http://localhost:8000/static/input-videos.html"
        echo ""
        echo "💡 Tips:"
        echo "   - Use 'screen -r basketball' to reattach to server session"
        echo "   - Transfer speed can vary - overnight transfer recommended for large files"
        echo "   - HTTP Range Requests enabled for smooth video seeking"
    else
        echo "⚠️  Warning: File count mismatch!"
        echo "   Some files may not have transferred correctly"
        echo "   Re-run this script to resume transfer"
    fi
else
    echo "⚠️  Transfer interrupted or failed (exit code: $RSYNC_EXIT)"
    echo ""
    echo "Don't worry! The transfer is resumable."
    echo "Simply re-run this script to continue from where it left off:"
    echo "   ./transfer_videos.sh $EC2_IP"
fi

echo ""
echo "📄 Transfer details:"
echo "   Source: $LOCAL_DIR"
echo "   Destination: $REMOTE_USER@$EC2_IP:$REMOTE_DIR"
echo "   Files transferred: $FILE_COUNT"
echo ""
