"""
routers/chunker.py — REST API for Video Chunker & Background Zone Worker
========================================================================
Endpoints:
- POST /api/chunker/start         : Start 1-2 min chunk recording & background AI
- POST /api/chunker/stop          : Stop recording for a camera
- GET  /api/chunker/status        : Real-time health, queue depth, chunker stats
- GET  /api/chunker/chunks        : List recorded video chunks
- GET  /api/chunker/live-frame/{camera_id} : Instant zero-delay preview frame
- POST /api/chunker/zones         : Set/update polygon zones for a camera
"""

import cv2
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from app.services.video_chunker import video_chunk_manager, RECORDINGS_DIR
from app.services.chunk_ai_worker import chunk_ai_worker

router = APIRouter(prefix="/api/chunker", tags=["video-chunker"])


class StartChunkerRequest(BaseModel):
    camera_id: str = Field(..., example="cam1")
    source: str = Field(..., example="rtsp://192.168.1.100:554/ch0_0")
    chunk_duration_sec: int = Field(120, ge=15, le=600, description="Chunk length in seconds (default 2 min)")
    record_fps: int = Field(15, ge=5, le=30, description="Recording FPS")
    sample_fps: int = Field(4, ge=1, le=15, description="AI Sampling FPS (lower = less server load)")
    zones: Optional[List[dict]] = Field(default=[], description="Polygon zones: [{'name': 'Checkout', 'points': [[x,y],...]}]")


class StopChunkerRequest(BaseModel):
    camera_id: str = Field(..., example="cam1")


class SetZonesRequest(BaseModel):
    camera_id: str = Field(..., example="cam1")
    zones: List[dict] = Field(..., description="List of polygon zones")


@router.post("/start")
async def start_chunker(req: StartChunkerRequest):
    """Start RTSP chunk recording (1-2 min) and background zone AI worker."""
    # Ensure worker is running
    if not chunk_ai_worker._running:
        chunk_ai_worker.sample_fps = req.sample_fps
        chunk_ai_worker.start()

    # Configure custom zones if provided
    if req.zones:
        chunk_ai_worker.set_camera_zones(req.camera_id, req.zones)

    res = video_chunk_manager.start_camera(
        camera_id=req.camera_id,
        source=req.source,
        chunk_duration_sec=req.chunk_duration_sec,
        record_fps=req.record_fps,
    )
    return res


@router.post("/stop")
async def stop_chunker(req: StopChunkerRequest):
    """Stop chunk recording for a specific camera."""
    return video_chunk_manager.stop_camera(req.camera_id)


@router.get("/status")
async def chunker_status():
    """Get system health, active chunkers, worker queue, and recent chunk analytics."""
    return {
        "chunkers": video_chunk_manager.get_status(),
        "worker": chunk_ai_worker.stats,
        "recent_chunk_analytics": chunk_ai_worker.recent_results[:10],
    }


@router.get("/live-frame/{camera_id}")
async def chunker_live_frame(camera_id: str):
    """Zero-delay latest frame preview (bypasses OpenCV buffer bloat)."""
    frame = video_chunk_manager.get_latest_frame(camera_id)
    if frame is None:
        raise HTTPException(status_code=404, detail="No active stream frame available for this camera")

    ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ret:
        raise HTTPException(status_code=500, detail="Frame encoding error")

    return Response(content=buf.tobytes(), media_type="image/jpeg")


@router.post("/zones")
async def set_camera_zones(req: SetZonesRequest):
    """Update custom polygon zones for a camera in real time."""
    chunk_ai_worker.set_camera_zones(req.camera_id, req.zones)
    return {
        "ok": True,
        "camera_id": req.camera_id,
        "zones_count": len(req.zones),
    }


@router.get("/chunks")
async def list_chunks(camera_id: Optional[str] = None):
    """List available recorded chunk MP4 files on disk."""
    if not RECORDINGS_DIR.exists():
        return {"chunks": []}

    target_dir = RECORDINGS_DIR / camera_id if camera_id else RECORDINGS_DIR
    chunks = []
    for f in target_dir.glob("**/*.mp4"):
        if f.is_file():
            stat = f.stat()
            chunks.append({
                "camera_id": f.parent.name if f.parent != RECORDINGS_DIR else "unknown",
                "filename": f.name,
                "path": str(f).replace("\\", "/"),
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "modified_time": stat.st_mtime,
            })

    chunks.sort(key=lambda c: c["modified_time"], reverse=True)
    return {"total": len(chunks), "chunks": chunks[:50]}
