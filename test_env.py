#!/usr/bin/env python3
"""Test if .env file loads correctly"""

import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

print("=" * 60)
print("Testing .env File Loading")
print("=" * 60)

# Check environment variables
aws_key = os.getenv('AWS_ACCESS_KEY_ID')
aws_secret = os.getenv('AWS_SECRET_ACCESS_KEY')
aws_bucket = os.getenv('AWS_S3_BUCKET')
aws_region = os.getenv('AWS_S3_REGION')

print(f"\nAWS_ACCESS_KEY_ID: {aws_key[:10] + '***' if aws_key else 'NOT SET'}")
print(f"AWS_SECRET_ACCESS_KEY: {aws_secret[:10] + '***' if aws_secret else 'NOT SET'}")
print(f"AWS_S3_BUCKET: {aws_bucket}")
print(f"AWS_S3_REGION: {aws_region}")

# Now test config loading
print("\n" + "=" * 60)
print("Testing Config Loading")
print("=" * 60)

from app.config import load_config

config = load_config()

print(f"\nconfig.aws_access_key: {config.aws_access_key[:10] + '***' if config.aws_access_key else 'NOT SET'}")
print(f"config.aws_secret_key: {config.aws_secret_key[:10] + '***' if config.aws_secret_key else 'NOT SET'}")
print(f"config.s3_bucket: {config.s3_bucket}")
print(f"config.s3_region: {config.s3_region}")

print("\n" + "=" * 60)

if config.aws_access_key and config.aws_secret_key:
    print("✅ AWS credentials loaded successfully!")
else:
    print("❌ AWS credentials NOT loaded!")

print("=" * 60)
