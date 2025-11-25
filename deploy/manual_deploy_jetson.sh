#!/bin/bash

# Configuration
JETSON_USER="developer"
# List of Jetson hosts (IPs or MagicDNS names)
HOSTS=("100.106.30.98" "100.87.190.71")
SSH_KEY_PATH="jetson-key.pem"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if SSH key exists
if [ ! -f "$SSH_KEY_PATH" ]; then
    echo -e "${RED}Error: SSH key not found at $SSH_KEY_PATH${NC}"
    exit 1
fi

# Ensure correct permissions on key
chmod 600 "$SSH_KEY_PATH"

echo "Starting manual deployment to Jetson devices..."

for HOST in "${HOSTS[@]}"; do
    echo -e "\n--------------------------------------------------"
    echo -e "Deploying to ${GREEN}$HOST${NC}..."
    echo -e "--------------------------------------------------"

    # Check connectivity
    if ping -c 1 -W 2 "$HOST" &> /dev/null; then
        echo -e "${GREEN}Host is online.${NC}"
        
        # 1. Update Code
        ssh -o StrictHostKeyChecking=no -i "$SSH_KEY_PATH" "$JETSON_USER@$HOST" "
            echo 'Connected to $HOST'
            
            # Navigate to project directory
            if [ ! -d ~/Uball_ingestion_pipeline ]; then
                echo 'Cloning repository...'
                git clone https://github.com/rohitmk523/Uball_ingestion_pipeline.git ~/Uball_ingestion_pipeline
            fi
            
            cd ~/Uball_ingestion_pipeline
            echo 'Pulling latest changes...'
            git pull origin main
        "

        # 2. Copy .env file (Run locally and pipe to remote)
        echo 'Updating .env file...'
        cat .env | ssh -o StrictHostKeyChecking=no -i "$SSH_KEY_PATH" "$JETSON_USER@$HOST" "cat > ~/Uball_ingestion_pipeline/.env"

        # 3. Install Dependencies & Restart Service
        ssh -o StrictHostKeyChecking=no -i "$SSH_KEY_PATH" "$JETSON_USER@$HOST" "
            cd ~/Uball_ingestion_pipeline
            
            echo 'Updating dependencies...'
            source venv/bin/activate 2>/dev/null || python3 -m venv venv && source venv/bin/activate
            pip install -r requirements.txt
            
            echo 'Restarting service...'
            # Check if service exists, if not run setup
            if ! systemctl list-unit-files | grep -q basketball-pipeline.service; then
                echo 'Service not found, running setup script...'
                chmod +x deploy/setup_jetson.sh
                ./deploy/setup_jetson.sh
            else
                sudo systemctl restart basketball-pipeline
            fi
            
            echo 'Deployment complete!'
        "
        
        if [ $? -eq 0 ]; then
             echo -e "${GREEN}Successfully deployed to $HOST${NC}"
        else
             echo -e "${RED}Failed to deploy to $HOST${NC}"
        fi
        
    else
        echo -e "${RED}Host $HOST is unreachable (Offline). Skipping.${NC}"
    fi
done

echo -e "\nManual deployment finished."
