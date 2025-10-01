from pydantic import BaseModel, validator
from datetime import datetime
from typing import List, Optional, Literal

class TimeRange(BaseModel):
    start: str  # Format: "HH:MM:SS"
    end: str    # Format: "HH:MM:SS"

    @validator('start', 'end')
    def validate_time_format(cls, v):
        try:
            datetime.strptime(v, "%H:%M:%S")
            return v
        except ValueError:
            raise ValueError("Time must be in HH:MM:SS format")

class Game(BaseModel):
    uuid: str
    time_range: TimeRange
    status: Literal["pending", "processing", "complete", "error"] = "pending"
    created_at: datetime = datetime.now()
    error_message: Optional[str] = None

class CameraFile(BaseModel):
    path: str
    filename: str
    size: int
    duration: float
    resolution: str  # "3840x2160" or "1920x1080"
    timestamp: datetime

class ProcessingStatus(BaseModel):
    game_uuid: str
    angle: str  # "far-left", "near-left", "far-right", "near-right"
    stage: Literal["extracting", "compressing", "uploading", "complete", "error"]
    progress: float  # 0.0 to 1.0
    eta_seconds: Optional[int] = None
    error_message: Optional[str] = None

class Config(BaseModel):
    side: Optional[Literal["LEFT", "RIGHT"]] = None
    aws_access_key: str = ""
    aws_secret_key: str = ""
    s3_bucket: str = "basketball-games"
    s3_region: str = "us-east-1"
    gpu_available: bool = False

class AngleMapping:
    @staticmethod
    def get_angles(side: str):
        if side == "LEFT":
            return ["far-left", "near-left"]
        elif side == "RIGHT":
            return ["far-right", "near-right"]
        else:
            raise ValueError("Invalid side")