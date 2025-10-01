#!/bin/bash

# Basketball Video Processing Pipeline Launcher

echo "🏀 Basketball Video Processing Pipeline"
echo "======================================"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Run setup_ec2.sh first."
    exit 1
fi

# Activate virtual environment
echo "🐍 Activating Python environment..."
source venv/bin/activate

# Check if required packages are installed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "❌ Dependencies not installed. Run:"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# Check if config exists
if [ ! -f "config.json" ]; then
    echo "📝 Creating default config..."
    cat > config.json << EOF
{
    "side": null,
    "aws_access_key": "",
    "aws_secret_key": "",
    "s3_bucket": "basketball-games",
    "s3_region": "us-east-1",
    "gpu_available": false
}
EOF
fi

# Create directories if they don't exist
mkdir -p temp/segments temp/compressed temp/thumbnails logs

echo "🚀 Starting pipeline..."
echo ""
echo "Access the web interface at:"
echo "  http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Start the application
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000