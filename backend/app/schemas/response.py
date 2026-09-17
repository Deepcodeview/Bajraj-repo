"""
schemas/response.py — Pydantic response models for the API.
"""

from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime


class UploadResponse(BaseModel):
    status: str
    job_id: str
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    created_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    analytics: Optional[Dict[str, Any]]


class CrossingEventOut(BaseModel):
    id: int
    job_id: str
    global_id: int
    event_type: str
    timestamp_sec: float
    wall_time: datetime


class AllJobsResponse(BaseModel):
    total: int
    jobs: List[Dict[str, Any]]