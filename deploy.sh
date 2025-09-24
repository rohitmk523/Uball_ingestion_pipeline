#!/bin/bash

# Basketball Video Pipeline Deployment Script for Jetson Orin Nano
# This script sets up the complete ingestion pipeline on the target device

set -e  # Exit on any error

echo "🏀 Basketball Video Pipeline - Jetson Deployment"
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if running on Jetson
check_jetson() {
    if [[ -f "/etc/nv_tegra_release" ]] || [[ -f "/opt/nvidia/l4t-usb-device-mode/nv-l4t-usb-device-mode.sh" ]]; then
        log_success "Running on NVIDIA Jetson device"
    else
        log_warning "This script is designed for Jetson devices, but continuing anyway..."
    fi
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check for required commands
    for cmd in python3 pip3 git systemctl; do
        if ! command -v $cmd &> /dev/null; then
            log_error "$cmd is not installed"
            exit 1
        fi
    done

    # Check Python version
    python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    if [[ "$(printf '%s\n' "3.8" "$python_version" | sort -V | head -n1)" != "3.8" ]]; then
        log_error "Python 3.8+ required, found $python_version"
        exit 1
    fi

    log_success "Prerequisites check passed"
}

# Update system packages
update_system() {
    log_info "Updating system packages..."
    sudo apt update
    sudo apt install -y \
        python3-pip \
        python3-venv \
        git \
        curl \
        wget \
        unzip \
        libmagic1 \
        ffmpeg \
        systemd
    log_success "System packages updated"
}

# Setup Python environment
setup_python_env() {
    log_info "Setting up Python virtual environment..."

    # Create virtual environment if it doesn't exist
    if [[ ! -d "venv" ]]; then
        python3 -m venv venv
    fi

    # Activate virtual environment
    source venv/bin/activate

    # Upgrade pip and install requirements
    pip install --upgrade pip
    pip install -r requirements.txt

    log_success "Python environment configured"
}

# Setup configuration
setup_config() {
    log_info "Setting up configuration..."

    # Create .env file if it doesn't exist
    if [[ ! -f ".env" ]]; then
        cp .env.template .env
        log_warning "Created .env file from template. Please update with your AWS credentials!"
        echo ""
        echo "Edit .env file with your settings:"
        echo "  nano .env"
        echo ""
        read -p "Press Enter to continue after updating .env file..."
    fi

    # Create necessary directories
    sudo mkdir -p /var/log/basketball
    sudo mkdir -p /opt/basketball-pipeline

    # Copy application files
    sudo cp -r src/ /opt/basketball-pipeline/
    sudo cp .env /opt/basketball-pipeline/
    sudo cp requirements.txt /opt/basketball-pipeline/

    # Set permissions
    sudo chown -R $USER:$USER /opt/basketball-pipeline
    sudo chmod +x /opt/basketball-pipeline/src/*.py

    log_success "Configuration setup completed"
}

# Create systemd service
create_service() {
    log_info "Creating systemd service..."

    # Create service file
    sudo tee /etc/systemd/system/basketball-upload.service > /dev/null <<EOF
[Unit]
Description=Basketball Video Upload Service
After=network.target
Wants=network.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=/opt/basketball-pipeline
ExecStart=/opt/basketball-pipeline/venv/bin/python src/web_ui.py
Restart=always
RestartSec=10
Environment=PYTHONPATH=/opt/basketball-pipeline/src

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=basketball-upload

# Security settings
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/basketball-pipeline /var/log/basketball /media /mnt

[Install]
WantedBy=multi-user.target
EOF

    log_success "Systemd service created"
}

# Setup auto-mount for USB devices
setup_usb_automount() {
    log_info "Setting up USB auto-mount for GoPro devices..."

    # Create udev rule for GoPro auto-mount
    sudo tee /etc/udev/rules.d/99-gopro-automount.rules > /dev/null <<EOF
# Auto-mount GoPro USB devices
SUBSYSTEM=="block", ATTRS{idVendor}=="2672", ACTION=="add", RUN+="/bin/mkdir -p /media/gopro", RUN+="/bin/mount -o uid=$USER,gid=$USER,dmask=0022,fmask=0133 %N /media/gopro"
SUBSYSTEM=="block", ATTRS{idVendor}=="2672", ACTION=="remove", RUN+="/bin/umount /media/gopro"

# General USB storage auto-mount
KERNEL=="sd[a-z][0-9]", SUBSYSTEM=="block", ACTION=="add", PROGRAM="/sbin/blkid -o value -s LABEL %N", RESULT=="?*", RUN+="/bin/mkdir -p /media/%c", RUN+="/bin/mount -o uid=$USER,gid=$USER,dmask=0022,fmask=0133 %N /media/%c"
KERNEL=="sd[a-z][0-9]", SUBSYSTEM=="block", ACTION=="remove", RUN+="/bin/umount /media/%c", RUN+="/bin/rmdir /media/%c"
EOF

    # Reload udev rules
    sudo udevadm control --reload-rules
    sudo udevadm trigger

    log_success "USB auto-mount configured"
}

# Setup log rotation
setup_logging() {
    log_info "Setting up log rotation..."

    sudo tee /etc/logrotate.d/basketball > /dev/null <<EOF
/var/log/basketball/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    create 644 $USER $USER
    postrotate
        systemctl reload basketball-upload.service
    endscript
}
EOF

    log_success "Log rotation configured"
}

# Setup firewall rules
setup_firewall() {
    log_info "Setting up firewall rules..."

    if command -v ufw &> /dev/null; then
        sudo ufw allow 5000/tcp comment "Basketball Upload Web Interface"
        log_success "Firewall rules added for web interface (port 5000)"
    else
        log_warning "UFW not installed, skipping firewall configuration"
    fi
}

# Start services
start_services() {
    log_info "Starting services..."

    # Copy virtual environment to system location
    sudo cp -r venv /opt/basketball-pipeline/

    # Reload systemd and enable service
    sudo systemctl daemon-reload
    sudo systemctl enable basketball-upload.service
    sudo systemctl start basketball-upload.service

    # Check service status
    if sudo systemctl is-active --quiet basketball-upload.service; then
        log_success "Basketball upload service started successfully"
    else
        log_error "Failed to start basketball upload service"
        sudo systemctl status basketball-upload.service
        exit 1
    fi
}

# Display final information
show_completion_info() {
    echo ""
    echo "🎉 Basketball Video Pipeline Deployment Complete!"
    echo "================================================="
    echo ""
    echo "📱 Web Interface: http://$(hostname -I | awk '{print $1}'):5000"
    echo "📱 Local Access:  http://localhost:5000"
    echo ""
    echo "🔧 Service Management:"
    echo "  Status:  sudo systemctl status basketball-upload"
    echo "  Stop:    sudo systemctl stop basketball-upload"
    echo "  Start:   sudo systemctl start basketball-upload"
    echo "  Restart: sudo systemctl restart basketball-upload"
    echo "  Logs:    sudo journalctl -u basketball-upload -f"
    echo ""
    echo "📁 GoPro Mount Points:"
    echo "  /media/gopro (auto-mounted)"
    echo "  /media/usb"
    echo "  /media/usb0"
    echo ""
    echo "📋 Next Steps:"
    echo "  1. Connect GoPro SD card or USB device"
    echo "  2. Open web interface in browser"
    echo "  3. Click 'Scan for Videos' to check detection"
    echo "  4. Click 'Upload All Videos' to start batch upload"
    echo ""
    echo "⚙️  Configuration: /opt/basketball-pipeline/.env"
    echo "📄 Logs: /var/log/basketball/"
    echo ""
}

# Main deployment function
main() {
    echo "Starting deployment at $(date)"

    check_jetson
    check_prerequisites
    update_system
    setup_python_env
    setup_config
    create_service
    setup_usb_automount
    setup_logging
    setup_firewall
    start_services
    show_completion_info

    log_success "Deployment completed successfully!"
}

# Handle script interruption
trap 'log_error "Deployment interrupted"; exit 1' INT TERM

# Run main function
main "$@"