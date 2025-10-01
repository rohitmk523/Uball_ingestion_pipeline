from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
import json
import asyncio
import logging
from pathlib import Path
from typing import List, Dict
from datetime import datetime

from .models import Game, TimeRange, Config, AngleMapping, ProcessingStatus
from .camera_detection import detect_gopro_devices, get_all_camera_files
from .config import load_config, save_config, update_side, update_aws_config, get_config_source
from .utils import generate_game_uuid, validate_time_range, cleanup_temp_files
from .video_processor import extract_segment, get_resolution, is_4k_or_higher, compress_video
from .s3_uploader import upload_to_s3, validate_aws_credentials

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
        "processing_active": processing_active
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)