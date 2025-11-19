# S3 Download Script - Usage Guide

## 🎯 Purpose
Download video files from S3 to local `input/` directory with **automatic resume** for unstable internet connections.

## 🚀 Quick Start

### 1. Run the Download Script
```bash
python3 download_from_s3.py
```

### 2. What It Does
- Lists all files in `s3://uball-videos-production/videos/Processed+Videos/10-2/`
- Downloads each file to `input/` directory
- **Automatically resumes** if connection drops
- **Retries up to 10 times** with exponential backoff
- Shows real-time progress bar

---

## ✨ Features

### **1. Resume Capability**
If your internet drops during download:
- Script saves progress
- Re-run the script: `python3 download_from_s3.py`
- It will **resume from where it stopped** (doesn't re-download completed parts)

### **2. Smart Retry Logic**
- Retries failed downloads up to **10 times**
- Uses **exponential backoff** (2s, 4s, 8s, 16s, ...)
- Handles connection errors, timeouts, etc.

### **3. Progress Tracking**
```
[1/4] 10-2 FR.m4v
  Size: 4.1 GB
  Downloading: 45% |████████░░░░░░░░| 1.8 GB/4.1 GB [02:15<02:30, 15.2MB/s]
```

### **4. Skips Completed Files**
If file already downloaded with correct size:
```
[2/4] 10-2 FL.m4v
  ✓ Already downloaded, skipping
```

---

## 🛠️ Configuration

Edit these variables in `download_from_s3.py`:

```python
S3_BUCKET = "uball-videos-production"
S3_PREFIX = "videos/Processed+Videos/10-2/"  # Change date as needed
LOCAL_DIR = "input"  # Change destination directory
MAX_RETRIES = 10  # Increase for very unstable connections
CHUNK_SIZE = 8 * 1024 * 1024  # 8MB chunks
```

---

## 📋 Example Usage

### **Download All Files from 10-2:**
```bash
python3 download_from_s3.py
```

**Output:**
```
============================================================
🏀 Basketball Video S3 Downloader (Resume-Capable)
============================================================

📂 Scanning S3: s3://uball-videos-production/videos/Processed+Videos/10-2/
============================================================
✓ Found 4 files
✓ Total size: 8.5 GB

📥 Starting downloads to: input/
============================================================

[1/4] 10-2 FR.m4v
  Size: 4.1 GB
  Downloading: 100% |████████████████| 4.1 GB/4.1 GB [05:30<00:00, 12.4MB/s]
  ✓ Download complete! (4.1 GB)

[2/4] 10-2 FL.m4v
  Size: 2.8 GB
  Downloading: 100% |████████████████| 2.8 GB/2.8 GB [03:45<00:00, 12.7MB/s]
  ✓ Download complete! (2.8 GB)

...

============================================================
📊 Download Summary
============================================================
Total files: 4
✓ Successful: 4
❌ Failed: 0
⏱️  Time: 652.3 seconds (10.9 minutes)

🎉 All files downloaded successfully!
```

---

## 🔄 Handling Interruptions

### **Internet Disconnects:**
```
[1/4] 10-2 FR.m4v
  Size: 4.1 GB
  Downloading: 45% |████████░░░░░░░░| 1.8 GB/4.1 GB
  ⚠️  Connection error (attempt 1/10): EndpointConnectionError
  ⏳ Retrying in 2 seconds...
```

### **Manual Stop (Ctrl+C):**
```
^C
⚠️  Download interrupted by user
  Progress saved: 1.8 GB
  Run script again to resume from this point
```

**Resume by running again:**
```bash
python3 download_from_s3.py
```

```
[1/4] 10-2 FR.m4v
  Size: 4.1 GB
  ⚠️  Resuming from 1.8 GB (43.9%)
  Downloading: 100% |████████████████| 4.1 GB/4.1 GB [03:15<00:00, 12.1MB/s]
  ✓ Download complete! (4.1 GB)
```

---

## ❌ Troubleshooting

### **Issue: "No files found"**
**Solution:**
- Check S3 path is correct
- Verify AWS credentials in `.env`
- Check bucket permissions

### **Issue: "Access Denied"**
**Solution:**
```bash
# Verify credentials
cat .env | grep AWS

# Test AWS connection
aws s3 ls s3://uball-videos-production/videos/Processed+Videos/10-2/
```

### **Issue: Downloads keep failing**
**Solution:**
- Increase `MAX_RETRIES` to 20 or 30
- Increase `RETRY_DELAY` to 5 seconds
- Check internet stability

### **Issue: File size mismatch**
**Solution:**
- Script will auto-retry and re-download
- Corrupted partial files are deleted and re-downloaded

---

## 🎯 Different S3 Paths

### **Download from Different Date:**
Edit `download_from_s3.py`:
```python
S3_PREFIX = "videos/Processed+Videos/10-3/"  # Changed to 10-3
```

### **Download to Different Directory:**
```python
LOCAL_DIR = "downloads"  # Instead of "input"
```

### **Download Specific Files Only:**
Modify the `list_s3_files()` function to filter:
```python
if '10-2 FR' in obj['Key']:  # Only download FR angle
    files.append(...)
```

---

## 📊 Performance Tips

### **For Slow/Unstable Connection:**
```python
CHUNK_SIZE = 4 * 1024 * 1024  # 4MB chunks (smaller = more resume points)
MAX_RETRIES = 20  # More retries
RETRY_DELAY = 5  # Longer initial delay
```

### **For Fast/Stable Connection:**
```python
CHUNK_SIZE = 16 * 1024 * 1024  # 16MB chunks (faster)
MAX_RETRIES = 5  # Fewer retries needed
```

---

## ✅ After Download Complete

Once downloads finish, verify files:

```bash
# Check downloaded files
ls -lh input/

# Expected output:
# -rw-r--r--  1 user  staff   4.1G  10-2 FR.m4v
# -rw-r--r--  1 user  staff   2.8G  10-2 FL.m4v
# -rw-r--r--  1 user  staff   1.2G  10-2 NL.m4v
# -rw-r--r--  1 user  staff   1.5G  10-2 NR.m4v
```

Then use the video processing pipeline:
```bash
# Start server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Open UI
# http://localhost:8000/input-videos
```

---

**The script is designed to handle the worst internet connections!** 🌐💪
