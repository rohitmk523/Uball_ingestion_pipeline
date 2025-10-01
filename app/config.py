import json
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from .models import Config

CONFIG_FILE = "config.json"

def load_config() -> Config:
    """Load configuration from environment variables and file (env takes priority)"""
    # Load .env file if it exists
    load_dotenv()

    # Start with file-based config
    config_data = {}
    config_path = Path(CONFIG_FILE)

    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
        except Exception:
            # Use empty dict if config is corrupted
            config_data = {}

    # Override with environment variables (priority) - essential AWS config
    if os.getenv("AWS_ACCESS_KEY_ID"):
        config_data["aws_access_key"] = os.getenv("AWS_ACCESS_KEY_ID")

    if os.getenv("AWS_SECRET_ACCESS_KEY"):
        config_data["aws_secret_key"] = os.getenv("AWS_SECRET_ACCESS_KEY")

    if os.getenv("AWS_S3_BUCKET"):
        config_data["s3_bucket"] = os.getenv("AWS_S3_BUCKET")

    if os.getenv("AWS_S3_REGION"):
        config_data["s3_region"] = os.getenv("AWS_S3_REGION")

    # GPU detection (from environment or system detection)
    if os.getenv("GPU_AVAILABLE"):
        config_data["gpu_available"] = os.getenv("GPU_AVAILABLE").lower() == "true"
    elif "gpu_available" not in config_data:
        # Auto-detect GPU if not specified
        try:
            import subprocess
            result = subprocess.run(['nvidia-smi'], capture_output=True, timeout=5)
            config_data["gpu_available"] = result.returncode == 0
        except:
            config_data["gpu_available"] = False

    # Create config object
    try:
        config = Config(**config_data)
    except Exception:
        # Fallback to default config
        config = Config()

    # Save merged config back to file (without sensitive data)
    save_config_safe(config)

    return config

def save_config(config: Config):
    """Save configuration to file (including sensitive data - use save_config_safe for production)"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config.dict(), f, indent=2, default=str)

def save_config_safe(config: Config):
    """Save configuration to file without sensitive AWS credentials"""
    config_data = config.dict()

    # Remove sensitive data if it comes from environment variables
    if os.getenv("AWS_ACCESS_KEY_ID"):
        config_data["aws_access_key"] = ""
    if os.getenv("AWS_SECRET_ACCESS_KEY"):
        config_data["aws_secret_key"] = ""

    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=2, default=str)

def update_side(side: str) -> Config:
    """Update side configuration"""
    config = load_config()
    config.side = side

    # Only save to file if not set via environment variable
    if not os.getenv("BASKETBALL_SIDE"):
        save_config_safe(config)

    return config

def update_aws_config(aws_access_key: str, aws_secret_key: str, s3_bucket: str, s3_region: str) -> Config:
    """Update AWS configuration (prefer environment variables in production)"""
    config = load_config()

    # Only update if not overridden by environment variables
    if not os.getenv("AWS_ACCESS_KEY_ID"):
        config.aws_access_key = aws_access_key
    if not os.getenv("AWS_SECRET_ACCESS_KEY"):
        config.aws_secret_key = aws_secret_key
    if not os.getenv("AWS_S3_BUCKET"):
        config.s3_bucket = s3_bucket
    if not os.getenv("AWS_S3_REGION"):
        config.s3_region = s3_region

    # Save to file (credentials will be hidden if from env)
    save_config_safe(config)
    return config

def get_config_source() -> dict:
    """Get information about where each config value comes from"""
    return {
        "aws_access_key": "environment" if os.getenv("AWS_ACCESS_KEY_ID") else "config_file",
        "aws_secret_key": "environment" if os.getenv("AWS_SECRET_ACCESS_KEY") else "config_file",
        "s3_bucket": "environment" if os.getenv("AWS_S3_BUCKET") else "config_file",
        "s3_region": "environment" if os.getenv("AWS_S3_REGION") else "config_file",
        "side": "config_file",
        "gpu_available": "auto_detected"
    }