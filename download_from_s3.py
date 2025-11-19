#!/usr/bin/env python3
"""
Robust S3 Downloader with Resume & Retry for Unstable Connections
Downloads all files from S3 to local input directory
"""

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError
import os
from pathlib import Path
import time
from dotenv import load_dotenv
from tqdm import tqdm
import hashlib

# Load environment variables
load_dotenv()

# Configuration
S3_BUCKET = "uball-videos-production"
S3_PREFIX = "videos/Processed+Videos/10-2/"  # Note: + is URL encoded space
LOCAL_DIR = "input"
MAX_RETRIES = 10  # More retries for unstable connection
CHUNK_SIZE = 8 * 1024 * 1024  # 8MB chunks for better resume capability
RETRY_DELAY = 2  # Initial delay in seconds (exponential backoff)

# Initialize S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_S3_REGION', 'us-east-1')
)

def format_bytes(bytes_size):
    """Format bytes to human readable"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"

def list_s3_files(bucket, prefix):
    """List all files in S3 bucket with prefix"""
    print(f"\n📂 Scanning S3: s3://{bucket}/{prefix}")
    print("=" * 60)

    files = []
    paginator = s3_client.get_paginator('list_objects_v2')

    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            if 'Contents' in page:
                for obj in page['Contents']:
                    # Skip directories (keys ending with /)
                    if not obj['Key'].endswith('/'):
                        files.append({
                            'key': obj['Key'],
                            'size': obj['Size'],
                            'etag': obj['ETag'].strip('"')
                        })

        print(f"✓ Found {len(files)} files")
        total_size = sum(f['size'] for f in files)
        print(f"✓ Total size: {format_bytes(total_size)}")

        return files

    except Exception as e:
        print(f"❌ Error listing files: {e}")
        return []

def check_file_exists(local_path, expected_size):
    """Check if file exists and has correct size"""
    if not os.path.exists(local_path):
        return False, 0

    local_size = os.path.getsize(local_path)

    if local_size == expected_size:
        return True, local_size  # Complete
    elif local_size < expected_size:
        return False, local_size  # Partial download
    else:
        # Local file is larger (corrupted?)
        print(f"  ⚠️  Local file larger than expected, re-downloading")
        os.remove(local_path)
        return False, 0

def download_file_with_resume(bucket, s3_key, local_path, expected_size, file_num, total_files):
    """
    Download file with resume capability and retry logic
    """
    # Get filename for display
    filename = os.path.basename(s3_key)

    print(f"\n[{file_num}/{total_files}] {filename}")
    print(f"  Size: {format_bytes(expected_size)}")

    # Check if already downloaded
    exists, local_size = check_file_exists(local_path, expected_size)

    if exists:
        print(f"  ✓ Already downloaded, skipping")
        return True

    if local_size > 0:
        print(f"  ⚠️  Resuming from {format_bytes(local_size)} ({(local_size/expected_size*100):.1f}%)")

    # Create parent directory
    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    # Download with retries
    for attempt in range(MAX_RETRIES):
        try:
            # Check current file size for resume
            exists, local_size = check_file_exists(local_path, expected_size)

            if exists:
                print(f"  ✓ Download complete!")
                return True

            # Prepare range for resume
            if local_size > 0:
                byte_range = f"bytes={local_size}-"
                mode = 'ab'  # Append mode
            else:
                byte_range = None
                mode = 'wb'  # Write mode

            # Download
            if byte_range:
                response = s3_client.get_object(
                    Bucket=bucket,
                    Key=s3_key,
                    Range=byte_range
                )
            else:
                response = s3_client.get_object(
                    Bucket=bucket,
                    Key=s3_key
                )

            # Stream download with progress
            content_length = response['ContentLength']
            remaining = content_length

            # Progress bar
            with open(local_path, mode) as f:
                with tqdm(total=expected_size, initial=local_size, unit='B', unit_scale=True, desc=f"  Downloading") as pbar:
                    for chunk in response['Body'].iter_chunks(chunk_size=CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))

            # Verify size
            final_size = os.path.getsize(local_path)
            if final_size == expected_size:
                print(f"  ✓ Download complete! ({format_bytes(final_size)})")
                return True
            else:
                print(f"  ⚠️  Size mismatch: {final_size} vs {expected_size}, retrying...")

        except (ClientError, EndpointConnectionError, ConnectionError, TimeoutError) as e:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                print(f"  ⚠️  Connection error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                print(f"  ⏳ Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print(f"  ❌ Failed after {MAX_RETRIES} attempts: {e}")
                return False

        except KeyboardInterrupt:
            print(f"\n⚠️  Download interrupted by user")
            print(f"  Progress saved: {format_bytes(os.path.getsize(local_path) if os.path.exists(local_path) else 0)}")
            print(f"  Run script again to resume from this point")
            raise

        except Exception as e:
            print(f"  ❌ Unexpected error: {e}")
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY * (2 ** attempt)
                print(f"  ⏳ Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                return False

    return False

def main():
    print("\n" + "=" * 60)
    print("🏀 Basketball Video S3 Downloader (Resume-Capable)")
    print("=" * 60)

    # List files
    files = list_s3_files(S3_BUCKET, S3_PREFIX)

    if not files:
        print("\n❌ No files found to download")
        return

    # Prepare local directory
    Path(LOCAL_DIR).mkdir(exist_ok=True)

    # Download each file
    print(f"\n📥 Starting downloads to: {LOCAL_DIR}/")
    print("=" * 60)

    total_files = len(files)
    successful = 0
    failed = []
    skipped = 0

    start_time = time.time()

    for idx, file_info in enumerate(files, 1):
        s3_key = file_info['key']
        size = file_info['size']

        # Get relative path (remove prefix)
        relative_path = s3_key.replace(S3_PREFIX, '')
        local_path = os.path.join(LOCAL_DIR, relative_path)

        # Download
        success = download_file_with_resume(
            S3_BUCKET,
            s3_key,
            local_path,
            size,
            idx,
            total_files
        )

        if success:
            successful += 1
        else:
            failed.append(relative_path)

    # Summary
    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print("📊 Download Summary")
    print("=" * 60)
    print(f"Total files: {total_files}")
    print(f"✓ Successful: {successful}")
    print(f"❌ Failed: {len(failed)}")
    print(f"⏱️  Time: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")

    if failed:
        print(f"\n❌ Failed files:")
        for f in failed:
            print(f"  - {f}")
        print(f"\n💡 Tip: Run this script again to retry failed downloads")
    else:
        print(f"\n🎉 All files downloaded successfully!")

    # Show what was downloaded
    print(f"\n📁 Downloaded to: {LOCAL_DIR}/")
    print("\nFiles:")
    for file_info in files:
        relative_path = file_info['key'].replace(S3_PREFIX, '')
        local_path = os.path.join(LOCAL_DIR, relative_path)
        status = "✓" if os.path.exists(local_path) else "✗"
        print(f"  {status} {relative_path} ({format_bytes(file_info['size'])})")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Download interrupted by user")
        print("Run script again to resume from where you left off")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
