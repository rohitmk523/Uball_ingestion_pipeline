import json
import os
from pathlib import Path
from typing import Optional
from .models import Config

CONFIG_FILE = "config.json"

def load_config() -> Config:
    """
    Load configuration from environment variables first, then config.json
    Environment variables take priority over config file
    """
    # Load from config file first
    config_path = Path(CONFIG_FILE)

    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            config = Config(**data)
        except Exception as e:
            # Use default if config is corrupted
            config = Config()
    else:
        # Create default config
        config = Config()
        save_config(config)

    # Override with environment variables if present
    # This allows .env file to take priority
    if os.getenv('AWS_ACCESS_KEY_ID'):
        config.aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')

    if os.getenv('AWS_SECRET_ACCESS_KEY'):
        config.aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')

    if os.getenv('AWS_S3_BUCKET'):
        config.s3_bucket = os.getenv('AWS_S3_BUCKET')

    if os.getenv('AWS_S3_REGION'):
        config.s3_region = os.getenv('AWS_S3_REGION')

    return config

def save_config(config: Config):
    """Save configuration to file"""
    with open(CONFIG_FILE, 'w') as f:
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