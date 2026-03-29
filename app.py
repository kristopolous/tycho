#!/usr/bin/env python3
"""
Tycho App - Main application server

Serves:
- API endpoints
- Static frontend files
- Thumbnail images (generated on-demand with ffmpeg)
"""

import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Import API router
from api import router as api_router

# Create main app
app = FastAPI(
    title="Tycho",
    description="Create actor-focused promotional videos from archival content",
    version="1.0.0",
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "outputs"
THUMBNAIL_CACHE_DIR = OUTPUT_DIR / "thumbnails"
FRONTEND_DIR = BASE_DIR

# Create directories
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
THUMBNAIL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Mount static files for videos
app.mount("/videos", StaticFiles(directory=str(OUTPUT_DIR)), name="videos")

# Include API routes (they already have /api prefix in their paths)
app.include_router(api_router)


# ============== Frontend Routes ==============

@app.get("/")
async def root():
    """Serve the main frontend page."""
    return FileResponse(str(FRONTEND_DIR / "index.html"))

# Serve static frontend files (CSS, JS, etc.)
@app.get("/style.css")
async def style_css():
    return FileResponse(str(FRONTEND_DIR / "style.css"))

@app.get("/app.js")
async def app_js():
    return FileResponse(str(FRONTEND_DIR / "app.js"))


# ============== Thumbnail Generation ==============

@app.get("/thumbnails/{filename}")
async def get_thumbnail(filename: str):
    """
    Serve or generate a thumbnail.
    
    Filename format: {imdb_id}_{offset_seconds}.jpg
    Example: tt0310917_13.5.jpg
    
    If thumbnail doesn't exist, generates it from content.mp4 using ffmpeg.
    """
    # Parse filename
    if not filename.endswith(".jpg"):
        raise HTTPException(status_code=400, detail="Invalid filename format")
    
    # Parse IMDb ID and offset
    parts = filename.rsplit("_", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid filename format")
    
    imdb_id = parts[0]
    offset_str = parts[1].replace(".jpg", "")
    
    try:
        offset = float(offset_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid offset value")
    
    # Check if thumbnail already exists
    thumb_path = THUMBNAIL_CACHE_DIR / filename
    if thumb_path.exists():
        return FileResponse(str(thumb_path), media_type="image/jpeg")
    
    # Generate thumbnail from content.mp4
    source_video = BASE_DIR / "content.mp4"
    if not source_video.exists():
        raise HTTPException(status_code=404, detail="Source video not found")
    
    # Create temp file for thumbnail
    temp_path = THUMBNAIL_CACHE_DIR / f"temp_{filename}"
    
    try:
        # Generate thumbnail with ffmpeg
        subprocess.run([
            "ffmpeg",
            "-ss", str(offset),
            "-i", str(source_video),
            "-vframes", "1",
            "-vf", "scale=320:-1",
            "-y",
            str(temp_path)
        ], check=True, capture_output=True, timeout=30)
        
        # Rename temp file to final name
        temp_path.rename(thumb_path)
        
        return FileResponse(str(thumb_path), media_type="image/jpeg")
        
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500, 
            detail=f"ffmpeg error: {e.stderr.decode() if e.stderr else str(e)}"
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Thumbnail generation timeout")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="ffmpeg not installed")


# ============== Health Check ==============

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "tycho"}


@app.get("/api/health")
async def api_health():
    """API health check endpoint."""
    return {"status": "ok", "service": "tycho-api"}


# ============== Main ==============

if __name__ == "__main__":
    import socket
    import uvicorn
    
    # Find available port starting from 8000
    def find_free_port(start_port=8000, max_port=8100):
        for port in range(start_port, max_port):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind(('', port))
                    return port
                except OSError:
                    continue
        raise RuntimeError(f"No available ports in range {start_port}-{max_port}")
    
    port = find_free_port()
    print(f"\n{'='*60}")
    print(f"  TYCHO")
    print(f"  Create actor-focused promotional videos")
    print(f"{'='*60}")
    print(f"\n  Starting server on http://localhost:{port}")
    print(f"  API docs: http://localhost:{port}/api/docs")
    print(f"\n  Press CTRL+C to stop\n")
    
    uvicorn.run(app, host="0.0.0.0", port=port)
