import json
import os
from pathlib import Path
from typing import Optional
from .models import Config

CONFIG_FILE = "config.json"

def get_project_root() -> Path:
    """Get the absolute path to the project root"""
    return Path(__file__).parent.parent.absolute()

def load_config() -> Config:
    """
    Load configuration from environment variables first, then config.json
    Environment variables take priority over config file
    """
    # Load from config file first
    config_path = get_project_root() / CONFIG_FILE
    
    config_data = {}
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load config file: {e}")

    # Create config object with defaults
    config = Config(**config_data)

    # Override with environment variables if present
    if os.getenv('AWS_ACCESS_KEY_ID'):
        config.aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')

    if os.getenv('AWS_SECRET_ACCESS_KEY'):
        config.aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')

    if os.getenv('AWS_S3_BUCKET'):
        config.s3_bucket = os.getenv('AWS_S3_BUCKET')

    if os.getenv('AWS_S3_REGION'):
        config.s3_region = os.getenv('AWS_S3_REGION')
        
    # Ensure directories exist
    _ensure_directories()

    return config

def _ensure_directories():
    """Ensure critical directories exist"""
    root = get_project_root()
    (root / "logs").mkdir(exist_ok=True)
    (root / "temp").mkdir(exist_ok=True)
    (root / "input").mkdir(exist_ok=True)
    (root / "offsets").mkdir(exist_ok=True)

def save_config(config: Config):
    """Save configuration to file"""
    config_path = get_project_root() / CONFIG_FILE
    with open(config_path, 'w') as f:
        json.dump(config.dict(), f, indent=2, default=str)

def update_side(side: str) -> Config:
    """Update side configuration"""
    config = load_config()
    config.side = side
    save_config(config)
    return config

def update_aws_config(aws_access_key: str, aws_secret_key: str, s3_bucket: str, s3_region: str) -> Config:
    """Update AWS configuration"""
    config = load_config()
    config.aws_access_key = aws_access_key
    config.aws_secret_key = aws_secret_key
    config.s3_bucket = s3_bucket
    config.s3_region = s3_region
    save_config(config)
    return config