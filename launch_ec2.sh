#!/bin/bash

echo "🚀 Basketball Pipeline - EC2 Instance Launcher"
echo "=============================================="

# Configuration
REGION="us-east-1"
INSTANCE_TYPE="t3.large"
KEY_NAME="uball-basketball-key"
SECURITY_GROUP_NAME="uball-basketball-sg"
INSTANCE_NAME="uball-basketball-pipeline"
EBS_SIZE=100

# AWS Credentials - Must be set via environment variables or AWS CLI config
# Option 1: Set environment variables before running:
#   export AWS_ACCESS_KEY_ID="your_key_here"
#   export AWS_SECRET_ACCESS_KEY="your_secret_here"
# Option 2: Configure AWS CLI:
#   aws configure
export AWS_DEFAULT_REGION="$REGION"

# Check if AWS credentials are configured
if [ -z "$AWS_ACCESS_KEY_ID" ] && [ ! -f ~/.aws/credentials ]; then
    echo "❌ AWS credentials not found!"
    echo ""
    echo "Please configure AWS credentials using one of these methods:"
    echo ""
    echo "Method 1: Environment variables (recommended for this script)"
    echo "  export AWS_ACCESS_KEY_ID=\"your_key_here\""
    echo "  export AWS_SECRET_ACCESS_KEY=\"your_secret_here\""
    echo "  ./launch_ec2.sh"
    echo ""
    echo "Method 2: AWS CLI configuration"
    echo "  aws configure"
    echo "  # Then enter your credentials when prompted"
    echo ""
    exit 1
fi

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found. Installing..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install awscli
    else
        echo "Please install AWS CLI manually: https://aws.amazon.com/cli/"
        exit 1
    fi
fi

echo "✓ AWS CLI found"

# Step 1: Create EC2 Key Pair
echo ""
echo "📋 Step 1: Creating EC2 Key Pair..."
if aws ec2 describe-key-pairs --key-names "$KEY_NAME" --region "$REGION" &>/dev/null; then
    echo "⚠️  Key pair '$KEY_NAME' already exists. Skipping creation."
    echo "   If you need a new key, delete the old one first:"
    echo "   aws ec2 delete-key-pair --key-name $KEY_NAME --region $REGION"
else
    aws ec2 create-key-pair \
        --key-name "$KEY_NAME" \
        --region "$REGION" \
        --query 'KeyMaterial' \
        --output text > "${KEY_NAME}.pem"

    chmod 400 "${KEY_NAME}.pem"
    echo "✅ Key pair created and saved to ${KEY_NAME}.pem"
fi

# Step 2: Create Security Group
echo ""
echo "📋 Step 2: Creating Security Group..."
SECURITY_GROUP_ID=$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=$SECURITY_GROUP_NAME" \
    --region "$REGION" \
    --query 'SecurityGroups[0].GroupId' \
    --output text 2>/dev/null)

if [ "$SECURITY_GROUP_ID" != "None" ] && [ -n "$SECURITY_GROUP_ID" ]; then
    echo "⚠️  Security group '$SECURITY_GROUP_NAME' already exists: $SECURITY_GROUP_ID"
else
    SECURITY_GROUP_ID=$(aws ec2 create-security-group \
        --group-name "$SECURITY_GROUP_NAME" \
        --description "Security group for Basketball Pipeline" \
        --region "$REGION" \
        --query 'GroupId' \
        --output text)

    echo "✅ Security group created: $SECURITY_GROUP_ID"

    # Add SSH rule (port 22)
    aws ec2 authorize-security-group-ingress \
        --group-id "$SECURITY_GROUP_ID" \
        --protocol tcp \
        --port 22 \
        --cidr 0.0.0.0/0 \
        --region "$REGION" &>/dev/null
    echo "  ✓ SSH access (port 22) enabled"

    # Add FastAPI rule (port 8000)
    aws ec2 authorize-security-group-ingress \
        --group-id "$SECURITY_GROUP_ID" \
        --protocol tcp \
        --port 8000 \
        --cidr 0.0.0.0/0 \
        --region "$REGION" &>/dev/null
    echo "  ✓ FastAPI access (port 8000) enabled"
fi

# Step 3: Get Ubuntu 22.04 LTS AMI
echo ""
echo "📋 Step 3: Finding Ubuntu 22.04 LTS AMI..."
AMI_ID=$(aws ec2 describe-images \
    --owners 099720109477 \
    --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
    --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
    --region "$REGION" \
    --output text)

echo "✅ Using AMI: $AMI_ID (Ubuntu 22.04 LTS)"

# Step 4: Launch EC2 Instance
echo ""
echo "📋 Step 4: Launching EC2 Instance..."
echo "  Instance Type: $INSTANCE_TYPE"
echo "  Region: $REGION"
echo "  EBS Volume: ${EBS_SIZE}GB gp3"

INSTANCE_ID=$(aws ec2 run-instances \
    --image-id "$AMI_ID" \
    --instance-type "$INSTANCE_TYPE" \
    --key-name "$KEY_NAME" \
    --security-group-ids "$SECURITY_GROUP_ID" \
    --block-device-mappings "[{\"DeviceName\":\"/dev/sda1\",\"Ebs\":{\"VolumeSize\":$EBS_SIZE,\"VolumeType\":\"gp3\"}}]" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME}]" \
    --region "$REGION" \
    --query 'Instances[0].InstanceId' \
    --output text)

echo "✅ Instance launched: $INSTANCE_ID"

# Step 5: Wait for instance to be running
echo ""
echo "📋 Step 5: Waiting for instance to start..."
aws ec2 wait instance-running \
    --instance-ids "$INSTANCE_ID" \
    --region "$REGION"

echo "✅ Instance is running!"

# Step 6: Get instance details
echo ""
echo "📋 Step 6: Retrieving instance details..."
PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --region "$REGION" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

echo ""
echo "=============================================="
echo "✅ EC2 Instance Successfully Launched!"
echo "=============================================="
echo ""
echo "Instance ID:   $INSTANCE_ID"
echo "Public IP:     $PUBLIC_IP"
echo "Instance Type: $INSTANCE_TYPE"
echo "Region:        $REGION"
echo "Key Pair:      ${KEY_NAME}.pem"
echo ""
echo "🔐 SSH Connection:"
echo "   ssh -i ${KEY_NAME}.pem ubuntu@${PUBLIC_IP}"
echo ""
echo "📝 Next Steps:"
echo "1. Wait 1-2 minutes for instance to fully initialize"
echo "2. Run: ./transfer_videos.sh $PUBLIC_IP"
echo "3. SSH into instance and add .env file"
echo "4. Install dependencies:"
echo "   sudo apt update && sudo apt install -y python3-pip python3-venv ffmpeg"
echo "   cd ~/Uball_ingestion_pipeline"
echo "   python3 -m venv venv"
echo "   source venv/bin/activate"
echo "   pip install -r requirements.txt"
echo "5. Start the server:"
echo "   uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo "6. Access via SSH tunnel:"
echo "   ssh -L 8000:localhost:8000 -i ${KEY_NAME}.pem ubuntu@${PUBLIC_IP}"
echo "   Then open: http://localhost:8000"
echo ""
echo "💾 Instance details saved to: ec2_instance_info.txt"

# Save instance info to file
cat > ec2_instance_info.txt << EOF
Instance ID: $INSTANCE_ID
Public IP: $PUBLIC_IP
Region: $REGION
Instance Type: $INSTANCE_TYPE
Key Pair: ${KEY_NAME}.pem
SSH Command: ssh -i ${KEY_NAME}.pem ubuntu@${PUBLIC_IP}
Tunnel Command: ssh -L 8000:localhost:8000 -i ${KEY_NAME}.pem ubuntu@${PUBLIC_IP}
EOF

echo "📄 To stop instance: aws ec2 stop-instances --instance-ids $INSTANCE_ID --region $REGION"
echo "📄 To terminate instance: aws ec2 terminate-instances --instance-ids $INSTANCE_ID --region $REGION"
