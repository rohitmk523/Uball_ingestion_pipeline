#!/usr/bin/env python3

from flask import Flask, render_template_string, request, jsonify, redirect, url_for
from flask_cors import CORS
import os
import json
from pathlib import Path
from upload_manager import BasketballUploader
import threading
import time
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Global state for upload progress
upload_status = {
    'is_uploading': False,
    'current_file': '',
    'progress': 0,
    'message': '',
    'last_upload': None
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Basketball Video Upload</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #333;
        }

        .container {
            background: white;
            border-radius: 15px;
            padding: 2rem;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            min-width: 400px;
            max-width: 600px;
        }

        .header {
            text-align: center;
            margin-bottom: 2rem;
        }

        .header h1 {
            color: #333;
            margin-bottom: 0.5rem;
            font-size: 2rem;
        }

        .header p {
            color: #666;
            font-size: 0.9rem;
        }

        .status-card {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            border-left: 4px solid #28a745;
        }

        .status-card.uploading {
            border-left-color: #ffc107;
        }

        .status-card.error {
            border-left-color: #dc3545;
        }

        .upload-section {
            margin-bottom: 2rem;
        }

        .upload-section h3 {
            margin-bottom: 1rem;
            color: #555;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .btn {
            background: linear-gradient(135deg, #28a745, #20c997);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1rem;
            font-weight: 500;
            transition: all 0.3s ease;
            width: 100%;
            margin: 0.5rem 0;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(40, 167, 69, 0.3);
        }

        .btn:disabled {
            background: #6c757d;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }

        .progress-bar {
            width: 100%;
            height: 20px;
            background: #e9ecef;
            border-radius: 10px;
            overflow: hidden;
            margin: 1rem 0;
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #28a745, #20c997);
            transition: width 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 0.8rem;
            font-weight: bold;
        }

        .file-info {
            background: #e3f2fd;
            border-radius: 8px;
            padding: 1rem;
            margin: 1rem 0;
            border-left: 4px solid #2196f3;
        }

        .emoji {
            font-size: 1.2em;
            margin-right: 0.5rem;
        }

        .refresh-btn {
            background: #6c757d;
            font-size: 0.9rem;
            padding: 8px 16px;
            margin-top: 1rem;
        }

        .logs {
            background: #2d3748;
            color: #e2e8f0;
            border-radius: 8px;
            padding: 1rem;
            font-family: 'Courier New', monospace;
            font-size: 0.8rem;
            max-height: 200px;
            overflow-y: auto;
            margin-top: 1rem;
        }

        .hidden { display: none; }

        @media (max-width: 500px) {
            .container {
                margin: 1rem;
                min-width: auto;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><span class="emoji">🏀</span>Basketball Video Upload</h1>
            <p>Jetson Orin → AWS S3 Pipeline</p>
        </div>

        <div id="status-card" class="status-card">
            <div id="status-message">
                <span class="emoji">✅</span>
                <strong>Ready to upload</strong><br>
                <small id="status-detail">System ready. Click upload to process GoPro videos.</small>
            </div>

            <div id="progress-container" class="hidden">
                <div class="progress-bar">
                    <div id="progress-fill" class="progress-fill" style="width: 0%">0%</div>
                </div>
                <div id="current-file" class="file-info hidden">
                    Processing: <strong>video.mp4</strong>
                </div>
            </div>
        </div>

        <div class="upload-section">
            <h3><span class="emoji">📁</span>Upload GoPro Videos</h3>

            <button id="upload-btn" class="btn" onclick="startUpload()">
                <span class="emoji">🚀</span>Upload All Videos
            </button>

            <button id="scan-btn" class="btn" onclick="scanVideos()">
                <span class="emoji">🔍</span>Scan for Videos
            </button>

            <button class="btn refresh-btn" onclick="location.reload()">
                <span class="emoji">🔄</span>Refresh Status
            </button>
        </div>

        <div id="logs-section" class="hidden">
            <h3><span class="emoji">📝</span>Upload Logs</h3>
            <div id="logs" class="logs"></div>
        </div>
    </div>

    <script>
        let statusPolling;

        function updateStatus() {
            fetch('/status')
                .then(response => response.json())
                .then(data => {
                    const statusCard = document.getElementById('status-card');
                    const statusMessage = document.getElementById('status-message');
                    const statusDetail = document.getElementById('status-detail');
                    const progressContainer = document.getElementById('progress-container');
                    const progressFill = document.getElementById('progress-fill');
                    const currentFile = document.getElementById('current-file');
                    const uploadBtn = document.getElementById('upload-btn');
                    const scanBtn = document.getElementById('scan-btn');

                    if (data.is_uploading) {
                        statusCard.className = 'status-card uploading';
                        statusMessage.innerHTML = '<span class="emoji">⏳</span><strong>Uploading...</strong>';
                        statusDetail.textContent = data.message;
                        progressContainer.classList.remove('hidden');
                        progressFill.style.width = data.progress + '%';
                        progressFill.textContent = Math.round(data.progress) + '%';

                        if (data.current_file) {
                            currentFile.classList.remove('hidden');
                            currentFile.innerHTML = 'Processing: <strong>' + data.current_file + '</strong>';
                        }

                        uploadBtn.disabled = true;
                        scanBtn.disabled = true;
                    } else {
                        statusCard.className = 'status-card';
                        statusMessage.innerHTML = '<span class="emoji">✅</span><strong>Ready to upload</strong>';
                        statusDetail.textContent = data.message || 'System ready. Click upload to process GoPro videos.';
                        progressContainer.classList.add('hidden');
                        currentFile.classList.add('hidden');
                        uploadBtn.disabled = false;
                        scanBtn.disabled = false;

                        if (data.last_upload) {
                            statusDetail.textContent = 'Last upload: ' + data.last_upload;
                        }
                    }
                })
                .catch(error => console.error('Status update failed:', error));
        }

        function startUpload() {
            fetch('/upload', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        startStatusPolling();
                        document.getElementById('logs-section').classList.remove('hidden');
                    } else {
                        alert('Failed to start upload: ' + data.error);
                    }
                })
                .catch(error => {
                    console.error('Upload failed:', error);
                    alert('Upload request failed');
                });
        }

        function scanVideos() {
            fetch('/scan', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.found > 0) {
                        alert(`Found ${data.found} video files ready for upload`);
                    } else {
                        alert('No video files found in GoPro directories');
                    }
                })
                .catch(error => {
                    console.error('Scan failed:', error);
                    alert('Scan request failed');
                });
        }

        function startStatusPolling() {
            if (statusPolling) clearInterval(statusPolling);
            statusPolling = setInterval(updateStatus, 1000);
        }

        // Initial status update
        updateStatus();

        // Auto-refresh every 5 seconds when not uploading
        setInterval(() => {
            if (!statusPolling) {
                updateStatus();
            }
        }, 5000);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/status')
def get_status():
    return jsonify(upload_status)

@app.route('/scan', methods=['POST'])
def scan_videos():
    try:
        uploader = BasketballUploader(test_mode=True)

        # Common GoPro paths
        gopro_paths = [
            '/media/usb/DCIM/100GOPRO',
            '/media/usb0/DCIM/100GOPRO',
            '/mnt/gopro/DCIM/100GOPRO',
            './sample_videos'  # For testing
        ]

        total_found = 0
        for path in gopro_paths:
            if Path(path).exists():
                video_files = []
                for ext in uploader.supported_formats:
                    video_files.extend(Path(path).glob(f"*{ext}"))
                    video_files.extend(Path(path).glob(f"*{ext.upper()}"))
                total_found += len(video_files)

        return jsonify({'success': True, 'found': total_found})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/upload', methods=['POST'])
def start_upload():
    global upload_status

    if upload_status['is_uploading']:
        return jsonify({'success': False, 'error': 'Upload already in progress'})

    try:
        # Start upload in background thread
        upload_thread = threading.Thread(target=upload_worker)
        upload_thread.daemon = True
        upload_thread.start()

        return jsonify({'success': True, 'message': 'Upload started'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def upload_worker():
    global upload_status

    upload_status.update({
        'is_uploading': True,
        'current_file': '',
        'progress': 0,
        'message': 'Initializing upload...'
    })

    try:
        uploader = BasketballUploader(test_mode=False)

        # Common GoPro paths
        gopro_paths = [
            '/media/usb/DCIM/100GOPRO',
            '/media/usb0/DCIM/100GOPRO',
            '/mnt/gopro/DCIM/100GOPRO',
            './sample_videos'  # For testing
        ]

        uploaded_files = []

        for path in gopro_paths:
            if Path(path).exists():
                upload_status['message'] = f'Scanning {path}...'

                # Get list of video files
                video_files = []
                for ext in uploader.supported_formats:
                    video_files.extend(Path(path).glob(f"*{ext}"))
                    video_files.extend(Path(path).glob(f"*{ext.upper()}"))

                if video_files:
                    total_files = len(video_files)

                    for i, video_file in enumerate(video_files):
                        upload_status.update({
                            'current_file': video_file.name,
                            'progress': (i / total_files) * 100,
                            'message': f'Uploading {i+1}/{total_files}'
                        })

                        if uploader.upload_video(str(video_file)):
                            uploaded_files.append(str(video_file))

                        # Small delay to show progress
                        time.sleep(0.5)

                break  # Found videos, stop searching other paths

        # Upload complete
        upload_status.update({
            'is_uploading': False,
            'current_file': '',
            'progress': 100,
            'message': f'Upload complete! {len(uploaded_files)} files uploaded.',
            'last_upload': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        upload_status.update({
            'is_uploading': False,
            'current_file': '',
            'progress': 0,
            'message': f'Upload failed: {str(e)}'
        })

if __name__ == '__main__':
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()

    print("🏀 Starting Basketball Video Upload Web Interface...")
    print("📱 Open your browser to: http://localhost:5000")

    # Run on all interfaces so Jetson can be accessed remotely
    app.run(host='0.0.0.0', port=5000, debug=False)