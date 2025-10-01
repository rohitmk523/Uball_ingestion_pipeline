import json
from pathlib import Path
from typing import Optional
from .models import Config

CONFIG_FILE = "config.json"

def load_config() -> Config:
    """Load configuration from file"""
    config_path = Path(CONFIG_FILE)

    if not config_path.exists():
        # Create default config
        default_config = Config()
        save_config(default_config)
        return default_config

    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
        return Config(**data)
    except Exception as e:
        # Return default if config is corrupted
        return Config()

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