from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, Response
import json
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import time
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from .models import Game, TimeRange, Config, AngleMapping, ProcessingStatus
from .camera_detection import detect_gopro_devices, get_all_camera_files
from .config import load_config, save_config, update_side, update_aws_config
from .utils import generate_game_uuid, validate_time_range, cleanup_temp_files
from .video_processor import extract_segment, get_resolution, is_4k_or_higher, compress_video
from .s3_uploader import upload_to_s3, validate_aws_credentials
from .input_video_scanner import scan_input_directory, get_videos_by_date, validate_date_videos
from .parallel_processor import ParallelProcessor, GameJob, ResourceManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/pipeline.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Basketball Video Processing Pipeline", version="1.0.0")

# Global state
games: Dict[str, Game] = {}
processing_active = False

# Input video workflow state
input_video_jobs: Dict[str, GameJob] = {}  # game_id -> GameJob
input_processing_active = False

# Video scan cache (to avoid re-scanning on every video stream request)
_video_scan_cache = {
    'videos': None,
    'timestamp': 0,
    'ttl': 60  # Cache for 60 seconds
}

def get_cached_videos():
    """Get cached video scan results or perform new scan if cache expired"""
    current_time = time.time()

    if (_video_scan_cache['videos'] is None or
        current_time - _video_scan_cache['timestamp'] > _video_scan_cache['ttl']):
        # Cache expired or empty, perform new scan
        _video_scan_cache['videos'] = scan_input_directory("input")
        _video_scan_cache['timestamp'] = current_time
        logger.debug(f"Video scan cache refreshed ({len(_video_scan_cache['videos'])} videos)")

    return _video_scan_cache['videos']

def invalidate_video_cache():
    """Invalidate video scan cache (call when files change)"""
    _video_scan_cache['videos'] = None
    _video_scan_cache['timestamp'] = 0

class ProgressTracker:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.current_status = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        # Send current status immediately
        if self.current_status:
            await websocket.send_text(json.dumps(self.current_status))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        self.current_status = message
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except:
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)

progress_tracker = ProgressTracker()

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
async def read_root():
    return FileResponse('app/static/index.html')

@app.get("/input-videos")
async def input_videos_page():
    """Serve the input videos workflow UI"""
    return FileResponse('app/static/input-videos.html')

@app.get("/api/config")
async def get_config():
    """Get current configuration"""
    config = load_config()
    # Don't expose AWS credentials
    safe_config = config.dict()
    safe_config["aws_access_key"] = "***" if config.aws_access_key else ""
    safe_config["aws_secret_key"] = "***" if config.aws_secret_key else ""
    return safe_config

@app.put("/api/config/side")
async def set_side(request: dict):
    """Set side (LEFT/RIGHT)"""
    side = request.get("side")
    if side not in ["LEFT", "RIGHT"]:
        raise HTTPException(status_code=400, detail="Side must be LEFT or RIGHT")

    config = update_side(side)
    logger.info(f"Side set to {side}")
    return {"success": True, "side": side}

@app.put("/api/config/aws")
async def set_aws_config(request: dict):
    """Update AWS credentials"""
    try:
        config = update_aws_config(
            request.get("aws_access_key", ""),
            request.get("aws_secret_key", ""),
            request.get("s3_bucket", "basketball-games"),
            request.get("s3_region", "us-east-1")
        )

        # Test credentials
        await validate_aws_credentials(config)

        logger.info("AWS configuration updated and validated")
        return {"success": True, "message": "AWS configuration updated"}

    except Exception as e:
        logger.error(f"AWS configuration failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/cameras")
async def list_cameras():
    """List detected GoPro devices"""
    try:
        devices = detect_gopro_devices()
        return {"cameras": devices}
    except Exception as e:
        logger.error(f"Error detecting cameras: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/files")
async def list_files():
    """List video files from all cameras"""
    try:
        files = get_all_camera_files()
        return {"files": [file.dict() for file in files]}
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/games")
async def list_games():
    """List all defined games"""
    return {"games": [game.dict() for game in games.values()]}

@app.post("/api/games")
async def create_game(request: dict):
    """Create new game"""
    try:
        time_range = TimeRange(**request["time_range"])

        # Validate time range
        validate_time_range(
            time_range.start,
            time_range.end,
            list(games.values())
        )

        # Generate UUID
        uuid = generate_game_uuid(time_range.start)

        # Create game
        game = Game(uuid=uuid, time_range=time_range)
        games[uuid] = game

        logger.info(f"Created game {uuid} ({time_range.start} - {time_range.end})")
        return game.dict()

    except Exception as e:
        logger.error(f"Error creating game: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/games/{uuid}")
async def delete_game(uuid: str):
    """Delete game"""
    if uuid not in games:
        raise HTTPException(status_code=404, detail="Game not found")

    if games[uuid].status == "processing":
        raise HTTPException(status_code=400, detail="Cannot delete game being processed")

    del games[uuid]
    logger.info(f"Deleted game {uuid}")
    return {"success": True}

@app.post("/api/process/start")
async def start_processing():
    """Start processing all pending games"""
    global processing_active

    if processing_active:
        raise HTTPException(status_code=400, detail="Processing already active")

    # Check configuration
    config = load_config()
    if not config.side:
        raise HTTPException(status_code=400, detail="Side not configured")

    if not config.aws_access_key or not config.aws_secret_key:
        raise HTTPException(status_code=400, detail="AWS credentials not configured")

    # Get camera files
    camera_files = get_all_camera_files()
    if len(camera_files) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 camera files")

    # Get pending games
    pending_games = [game for game in games.values() if game.status == "pending"]
    if not pending_games:
        raise HTTPException(status_code=400, detail="No pending games to process")

    # Start processing in background
    processing_active = True
    asyncio.create_task(process_all_games(pending_games, camera_files, config))

    logger.info(f"Started processing {len(pending_games)} games")
    return {"success": True, "games_count": len(pending_games)}

@app.get("/api/process/status")
async def get_processing_status():
    """Get overall processing status"""
    total_games = len(games)
    completed = len([g for g in games.values() if g.status == "complete"])
    in_progress = len([g for g in games.values() if g.status == "processing"])
    pending = len([g for g in games.values() if g.status == "pending"])
    error = len([g for g in games.values() if g.status == "error"])

    return {
        "processing_active": processing_active,
        "total_games": total_games,
        "completed": completed,
        "in_progress": in_progress,
        "pending": pending,
        "error": error
    }

@app.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket):
    await progress_tracker.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep connection alive
    except WebSocketDisconnect:
        progress_tracker.disconnect(websocket)

async def process_all_games(games_list: List[Game], camera_files: List, config: Config):
    """Process games sequentially, but angles in parallel"""
    global processing_active

    try:
        for game in games_list:
            # Update status
            game.status = "processing"
            await progress_tracker.broadcast({
                "message": f"Processing game {game.uuid}",
                "game_uuid": game.uuid,
                "stage": "starting"
            })

            try:
                # Process both angles in parallel
                await process_game(game, camera_files[:2], config)  # Use first 2 cameras
                game.status = "complete"
                logger.info(f"Completed game {game.uuid}")

            except Exception as e:
                game.status = "error"
                game.error_message = str(e)
                logger.error(f"Error processing game {game.uuid}: {e}")

                await progress_tracker.broadcast({
                    "game_uuid": game.uuid,
                    "stage": "error",
                    "error_message": str(e)
                })

    finally:
        processing_active = False
        await progress_tracker.broadcast({
            "message": "Processing completed",
            "processing_active": False
        })

async def process_game(game: Game, camera_files: List, config: Config):
    """Process one game with both camera angles"""
    angles = AngleMapping.get_angles(config.side)

    tasks = []
    for camera_file, angle in zip(camera_files, angles):
        task = process_single_angle(game, camera_file.path, angle, config)
        tasks.append(task)

    # Process both angles in parallel
    await asyncio.gather(*tasks)

async def process_single_angle(game: Game, camera_file: str, angle: str, config: Config):
    """Process one angle of one game with critical resolution check"""
    temp_dir = Path("temp")
    segments_dir = temp_dir / "segments"
    compressed_dir = temp_dir / "compressed"

    segments_dir.mkdir(parents=True, exist_ok=True)
    compressed_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Step 1: Extract segment (fast, copy codec)
        logger.info(f"Extracting segment for {game.uuid} - {angle}")
        segment_path = segments_dir / f"{game.uuid}_{angle}_segment.mp4"

        await progress_tracker.broadcast({
            "game_uuid": game.uuid,
            "angle": angle,
            "stage": "extracting",
            "progress": 0.1
        })

        await extract_segment(
            camera_file,
            str(segment_path),
            game.time_range.start,
            game.time_range.end
        )

        # Step 2: Check resolution - CRITICAL CHECK
        logger.info(f"Checking resolution for {game.uuid} - {angle}")
        width, height = get_resolution(str(segment_path))

        if width is None or height is None:
            raise ValueError(f"Could not determine resolution for {segment_path}")

        logger.info(f"Video resolution: {width}x{height}")

        await progress_tracker.broadcast({
            "game_uuid": game.uuid,
            "angle": angle,
            "stage": "checking_resolution",
            "progress": 0.2,
            "resolution": f"{width}x{height}"
        })

        # Step 3: Compress ONLY if 4K
        if is_4k_or_higher(width, height):
            logger.info(f"Video is 4K ({width}x{height}) - compressing to 1080p")

            await progress_tracker.broadcast({
                "game_uuid": game.uuid,
                "angle": angle,
                "stage": "compressing",
                "progress": 0.3,
                "message": "Compressing 4K to 1080p..."
            })

            compressed_path = compressed_dir / f"{game.uuid}_{angle}.mp4"
            await compress_video(
                str(segment_path),
                str(compressed_path),
                use_gpu=config.gpu_available
            )

            # Use compressed file for upload
            final_path = compressed_path

            # Delete original segment to save space
            segment_path.unlink()

        else:
            logger.info(f"Video is {width}x{height} (not 4K) - uploading as-is, no compression needed")

            await progress_tracker.broadcast({
                "game_uuid": game.uuid,
                "angle": angle,
                "stage": "skipping_compression",
                "progress": 0.5,
                "message": "Video already 1080p or lower, skipping compression"
            })

            # Use original segment for upload (no compression needed)
            final_path = segment_path

        # Step 4: Upload to S3
        logger.info(f"Uploading {final_path} to S3")

        await progress_tracker.broadcast({
            "game_uuid": game.uuid,
            "angle": angle,
            "stage": "uploading",
            "progress": 0.7
        })

        s3_key = f"{game.uuid}/{angle}/video.mp4"
        await upload_to_s3(str(final_path), s3_key, config)

        # Step 5: Cleanup
        final_path.unlink()

        await progress_tracker.broadcast({
            "game_uuid": game.uuid,
            "angle": angle,
            "stage": "complete",
            "progress": 1.0
        })

        logger.info(f"Successfully processed {game.uuid} - {angle}")

    except Exception as e:
        logger.error(f"Error processing {game.uuid} - {angle}: {e}")

        await progress_tracker.broadcast({
            "game_uuid": game.uuid,
            "angle": angle,
            "stage": "error",
            "progress": 0,
            "error_message": str(e)
        })

        raise

# ============================================================================
# INPUT VIDEO WORKFLOW ENDPOINTS (New /input directory workflow)
# ============================================================================

@app.get("/api/input-videos/scan")
async def scan_input_videos(force_refresh: bool = False):
    """
    Scan /input directory for video files grouped by date

    Args:
        force_refresh: If True, bypass cache and force fresh scan
    """
    try:
        # Force refresh cache if requested
        if force_refresh:
            invalidate_video_cache()

        videos_by_date = get_videos_by_date("input")

        # Add validation info for each date
        result = {}
        for date, videos in videos_by_date.items():
            validation = validate_date_videos(videos)
            result[date] = {
                'videos': [v.to_dict() for v in videos],
                'validation': validation
            }

        return {
            'success': True,
            'dates': result,
            'total_videos': sum(len(v) for v in videos_by_date.values())
        }

    except Exception as e:
        logger.error(f"Error scanning input videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/input-videos/preview/{date}/{angle}")
async def get_video_preview_url(date: str, angle: str):
    """
    Get preview URL for a specific video

    Args:
        date: Date in MM-DD format (e.g., "10-02")
        angle: Angle short name (FR, FL, NL, NR)
    """
    try:
        videos = get_cached_videos()

        # Find matching video
        matching = [v for v in videos if v.date == date and v.angle_short == angle]

        if not matching:
            raise HTTPException(
                status_code=404,
                detail=f"No video found for date {date}, angle {angle}"
            )

        video = matching[0]

        return {
            'success': True,
            'video': video.to_dict(),
            'preview_url': f"/api/input-videos/stream/{date}/{angle}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting preview URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/input-videos/stream/{date}/{angle}")
async def stream_video(date: str, angle: str, request: Request):
    """
    Stream video file with HTTP Range Request support for smooth seeking.

    Supports partial content requests (206) for instant seeking without buffering,
    perfect for remote deployments on EC2/Jetson Nano.
    """
    try:
        videos = get_cached_videos()
        matching = [v for v in videos if v.date == date and v.angle_short == angle]

        if not matching:
            raise HTTPException(status_code=404, detail="Video not found")

        video = matching[0]
        video_path = Path(video.path)

        if not video_path.exists():
            raise HTTPException(status_code=404, detail="Video file not found on disk")

        file_size = video_path.stat().st_size
        range_header = request.headers.get("range")

        # Determine media type based on file extension
        media_type_map = {
            '.mp4': 'video/mp4',
            '.m4v': 'video/mp4',
            '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo',
            '.mkv': 'video/x-matroska',
        }
        media_type = media_type_map.get(video_path.suffix.lower(), 'video/mp4')

        # Handle range requests for seeking
        if range_header:
            # Parse range header (format: "bytes=start-end")
            range_match = range_header.replace("bytes=", "").split("-")
            start = int(range_match[0]) if range_match[0] else 0
            end = int(range_match[1]) if len(range_match) > 1 and range_match[1] else file_size - 1

            # Validate range
            if start >= file_size or end >= file_size or start > end:
                raise HTTPException(
                    status_code=416,
                    detail="Requested range not satisfiable",
                    headers={"Content-Range": f"bytes */{file_size}"}
                )

            chunk_size = end - start + 1

            def iter_file():
                """Stream file in chunks for the requested range"""
                with open(video_path, "rb") as video_file:
                    video_file.seek(start)
                    remaining = chunk_size
                    while remaining > 0:
                        read_size = min(8192, remaining)  # Read in 8KB chunks
                        data = video_file.read(read_size)
                        if not data:
                            break
                        remaining -= len(data)
                        yield data

            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
                "Content-Type": media_type,
                "Cache-Control": "public, max-age=3600",
            }

            return StreamingResponse(
                iter_file(),
                status_code=206,  # Partial Content
                headers=headers,
                media_type=media_type
            )

        # No range request - return full file
        return FileResponse(
            video_path,
            media_type=media_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Type": media_type,
                "Cache-Control": "public, max-age=3600",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming video: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/input-videos/jobs")
async def list_input_jobs():
    """List all defined input video jobs"""
    return {
        'success': True,
        'jobs': [job.to_dict() for job in input_video_jobs.values()]
    }

@app.post("/api/input-videos/jobs")
async def create_input_job(request: dict):
    """
    Create new input video job

    Request body:
    {
        "date": "10-02",
        "game_number": 1,
        "time_start": "00:15:30",
        "time_end": "00:45:00"
    }
    """
    try:
        date = request.get('date')
        game_number = request.get('game_number')
        time_start = request.get('time_start')
        time_end = request.get('time_end')

        # Validate required fields
        if not all([date, game_number, time_start, time_end]):
            raise HTTPException(
                status_code=400,
                detail="Missing required fields: date, game_number, time_start, time_end"
            )

        # Get videos for this date
        videos_by_date = get_videos_by_date("input")

        if date not in videos_by_date:
            raise HTTPException(
                status_code=404,
                detail=f"No videos found for date {date}"
            )

        videos = videos_by_date[date]

        # Check which angles are present (can process with 1-4 angles)
        validation = validate_date_videos(videos)
        if not validation['can_process']:
            raise HTTPException(
                status_code=400,
                detail=f"No videos found for date {date}"
            )

        # Log warning if not all angles present
        if not validation['complete']:
            logger.warning(
                f"Processing with {validation['count']} angles only. "
                f"Missing: {', '.join(validation['missing_angles'])}"
            )

        # Build video_files dict (only for available angles)
        video_files = {}
        for video in videos:
            video_files[video.angle_full] = video.path

        # Create GameJob
        job = GameJob(
            date=date,
            game_number=game_number,
            time_start=time_start,
            time_end=time_end,
            video_files=video_files
        )

        # Check for duplicate game_id
        if job.game_id in input_video_jobs:
            raise HTTPException(
                status_code=400,
                detail=f"Game {job.game_id} already exists"
            )

        input_video_jobs[job.game_id] = job

        logger.info(f"Created input video job: {job.game_id}")

        return {
            'success': True,
            'job': job.to_dict()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating input job: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/input-videos/jobs/{game_id}")
async def delete_input_job(game_id: str):
    """Delete input video job"""
    if game_id not in input_video_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = input_video_jobs[game_id]

    if job.status == "processing":
        raise HTTPException(status_code=400, detail="Cannot delete job being processed")

    del input_video_jobs[game_id]
    logger.info(f"Deleted input video job: {game_id}")

    return {"success": True}

@app.post("/api/input-videos/process")
async def process_input_videos():
    """Start processing all pending input video jobs in parallel"""
    global input_processing_active

    if input_processing_active:
        raise HTTPException(status_code=400, detail="Processing already active")

    # Check configuration
    config = load_config()

    if not config.aws_access_key or not config.aws_secret_key:
        raise HTTPException(status_code=400, detail="AWS credentials not configured")

    # Get pending jobs
    pending_jobs = [job for job in input_video_jobs.values() if job.status == "pending"]

    if not pending_jobs:
        raise HTTPException(status_code=400, detail="No pending jobs to process")

    # Start processing in background
    input_processing_active = True
    asyncio.create_task(process_input_jobs_parallel(pending_jobs, config))

    logger.info(f"Started parallel processing of {len(pending_jobs)} input video jobs")

    return {
        "success": True,
        "jobs_count": len(pending_jobs),
        "max_concurrent": ResourceManager.get_max_concurrent_ffmpeg()
    }

@app.get("/api/input-videos/status")
async def get_input_processing_status():
    """Get overall input video processing status"""
    total_jobs = len(input_video_jobs)
    completed = len([j for j in input_video_jobs.values() if j.status == "completed"])
    in_progress = len([j for j in input_video_jobs.values() if j.status == "processing"])
    pending = len([j for j in input_video_jobs.values() if j.status == "pending"])
    error = len([j for j in input_video_jobs.values() if j.status == "error"])

    return {
        "processing_active": input_processing_active,
        "total_jobs": total_jobs,
        "completed": completed,
        "in_progress": in_progress,
        "pending": pending,
        "error": error,
        "max_concurrent": ResourceManager.get_max_concurrent_ffmpeg()
    }

async def process_input_jobs_parallel(jobs: List[GameJob], config: Config):
    """Process input video jobs in parallel with concurrency control"""
    global input_processing_active

    try:
        # Create processor with progress callback
        async def progress_callback(message: dict):
            await progress_tracker.broadcast(message)

        processor = ParallelProcessor(
            config=config,
            max_concurrent=None,  # Auto-detect
            progress_callback=progress_callback
        )

        # Process all jobs in parallel
        await processor.process_games(jobs)

        logger.info("Input video processing completed")

    except Exception as e:
        logger.error(f"Error in parallel processing: {e}")

    finally:
        input_processing_active = False
        await progress_tracker.broadcast({
            "message": "Input video processing completed",
            "processing_active": False
        })

# ============================================================================
# HEALTH & SYSTEM ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    from .video_processor import check_gpu_available
    import shutil

    return {
        "status": "healthy",
        "gpu_available": check_gpu_available(),
        "disk_space_gb": shutil.disk_usage("/").free / (1024**3),
        "active_connections": len(progress_tracker.active_connections),
        "processing_active": processing_active,
        "input_processing_active": input_processing_active,
        "max_concurrent_ffmpeg": ResourceManager.get_max_concurrent_ffmpeg()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)