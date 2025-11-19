#!/bin/bash

# Initialize Directory Structure for Basketball Pipeline
# Run this before first start

echo "📁 Initializing directory structure..."

# Create application directories
mkdir -p logs
mkdir -p temp/segments
mkdir -p temp/compressed
mkdir -p temp/thumbnails

# Create test media directories (for simulation)
mkdir -p test_media/gopro1/DCIM/100GOPRO
mkdir -p test_media/gopro2/DCIM/100GOPRO

# Set permissions
chmod 755 logs
chmod 755 temp
chmod 755 temp/segments
chmod 755 temp/compressed
chmod 755 temp/thumbnails

# Create placeholder log file
touch logs/pipeline.log
chmod 644 logs/pipeline.log

# Create config.json if it doesn't exist
if [ ! -f "config.json" ]; then
    echo "📝 Creating default config.json..."
    cat > config.json << 'EOF'
{
  "side": null,
  "aws_access_key": "",
  "aws_secret_key": "",
  "s3_bucket": "basketball-games",
  "s3_region": "us-east-1",
  "gpu_available": false
}
EOF
    chmod 644 config.json
fi

# Create .env from example if it doesn't exist
if [ ! -f ".env" ] && [ -f "env.example" ]; then
    echo "📝 Creating .env from template..."
    cp env.example .env
    chmod 600 .env
    echo "⚠️  Please edit .env file with your actual credentials"
fi

echo "✅ Directory structure initialized!"
echo ""
echo "Directory tree:"
ls -R logs temp 2>/dev/null | grep ":$" | sed -e 's/:$//' -e 's/[^-][^\/]*\//--/g' -e 's/^/  /' -e 's/-/|/'
echo ""
echo "Next steps:"
echo "  1. Edit .env file with your AWS credentials"
echo "  2. Run: ./run.sh (or use systemd service)"
echo "  3. Access UI at http://localhost:8000"

