#!/bin/bash

# Setup script for Jetson Nano Production Environment

set -e

echo "🏀 Setting up Basketball Pipeline for Jetson Nano..."

# 1. System Dependencies
echo "📦 Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv ffmpeg libopenblas-base libopenmpi-dev

# 2. Python Environment
echo "🐍 Setting up Python environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. Directory Structure
echo "📂 Creating directory structure..."
mkdir -p logs temp input offsets

# 4. Permissions
echo "🔐 Setting permissions..."
chmod +x deploy/setup_jetson.sh

# 5. Systemd Service
echo "⚙️ Configuring systemd service..."
SERVICE_FILE="deploy/basketball-pipeline.service"
SYSTEM_SERVICE="/etc/systemd/system/basketball-pipeline.service"

if [ -f "$SERVICE_FILE" ]; then
    # Update path in service file to current directory
    CURRENT_DIR=$(pwd)
    USER_NAME=$(whoami)
    
    sed -i "s|WorkingDirectory=/home/jetson/basketball-pipeline|WorkingDirectory=$CURRENT_DIR|g" $SERVICE_FILE
    sed -i "s|ExecStart=/home/jetson/basketball-pipeline/venv/bin/uvicorn|ExecStart=$CURRENT_DIR/venv/bin/uvicorn|g" $SERVICE_FILE
    sed -i "s|User=jetson|User=$USER_NAME|g" $SERVICE_FILE
    sed -i "s|Environment=PATH=/home/jetson/basketball-pipeline/venv/bin|Environment=PATH=$CURRENT_DIR/venv/bin|g" $SERVICE_FILE

    sudo cp $SERVICE_FILE $SYSTEM_SERVICE
    sudo systemctl daemon-reload
    sudo systemctl enable basketball-pipeline
    echo "✅ Service installed and enabled"
else
    echo "⚠️ Service file not found at $SERVICE_FILE"
fi

echo "🎉 Setup complete! You can start the service with:"
echo "sudo systemctl start basketball-pipeline"
