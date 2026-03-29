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

import os
import subprocess
import sys
import requests
import threading
from pathlib import Path
from typing import Optional, Set

from fastapi import FastAPI, HTTPException, BackgroundTasks, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Import Tycho components
from api import router as api_router
from database import get_db
from brave_client import get_brave_headshot
from tmdb_client import get_headshots_for_actor

# Global set to track in-progress discoveries to avoid redundant jobs
discovery_in_progress: Set[str] = set()

# Create main app
app = FastAPI(
    title="Tycho",
    description="Create actor-focused promotional videos from archival content",
    version="1.0.0",
)

# ... CORS ...

# ============== Image Discovery Worker ==============

def discover_image_worker(imdb_id: str, source: str, talent_name: str, save_path: Path, imdb_image_url: str = None):
    """Worker function to fetch and save missing headshots.

    Args:
        imdb_id: IMDb ID (e.g., nm0706977) - the primary unique identifier
        source: Image source ('imdb', 'tmdb', 'brave')
        talent_name: Human-readable name for API lookups (TMDB, Brave)
        save_path: Where to save the downloaded image
        imdb_image_url: Optional pre-computed IMDb URL (only used for source='imdb')
    """
    job_key = f"{imdb_id}_{source}"
    try:
        url = None
        if source == "imdb":
            # Use the provided IMDb URL from project data
            url = imdb_image_url
            if not url:
                print(f"[Discovery] No IMDb URL provided for {imdb_id}")
        elif source == "tmdb":
            # Fetch from TMDB API using talent name
            urls = get_headshots_for_actor(talent_name, imdb_id, max_images=1)
            if urls:
                url = urls[0]
        elif source == "brave":
            # Fetch from Brave Image Search using talent name
            url = get_brave_headshot(talent_name)

        if url:
            print(f"[Discovery] Fetching {source} image for {imdb_id}: {url[:80]}...")
            res = requests.get(url, timeout=15)
            res.raise_for_status()
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, 'wb') as f:
                f.write(res.content)
            print(f"[Discovery] Saved: {save_path}")

    except Exception as e:
        print(f"[Discovery] Error discovering {source} for {imdb_id}: {e}")
    finally:
        if job_key in discovery_in_progress:
            discovery_in_progress.remove(job_key)

# ============== Dynamic Talent Images ==============

@app.get("/images/{filename}")
async def get_talent_image(filename: str):
    """
    Serve a talent headshot or trigger discovery if missing.
    Filename format: {imdb_id}_{source}.jpg

    Also supports legacy format: {imdb_id}.jpg (returns any available source)
    """
    image_dir = OUTPUT_DIR / "images"
    image_path = image_dir / filename

    if image_path.exists():
        return FileResponse(str(image_path), media_type="image/jpeg")

    # Trigger Discovery
    try:
        parts = filename.replace(".jpg", "").split("_")
        if len(parts) == 2:
            imdb_id, source = parts
            job_key = f"{imdb_id}_{source}"

            if job_key not in discovery_in_progress:
                # Look up actor data from project files first (using IMDb ID as key)
                actor_data = None
                try:
                    for proj_dir in sorted(OUTPUT_DIR.iterdir(), reverse=True):
                        if proj_dir.is_dir() and proj_dir.name.startswith('tycho_'):
                            proj_file = proj_dir / "project.json"
                            if proj_file.exists():
                                import json
                                with open(proj_file) as f:
                                    proj_data = json.load(f)
                                for actor in proj_data.get('actors', []):
                                    if actor.get('actor_id') == imdb_id:
                                        actor_data = actor
                                        print(f"[Discovery] Found {actor_data.get('actor_name')} ({imdb_id}) in {proj_dir.name}")
                                        break
                                if actor_data:
                                    break
                except Exception as e:
                    print(f"[Discovery] Error looking up project data: {e}")

                talent_name = actor_data.get('actor_name') or actor_data.get('name') if actor_data else None
                imdb_image_url = actor_data.get('headshot_url') if actor_data else None

                # Get or create talent in DB
                db = get_db()
                talent = db.get_talent_by_imdb_id(imdb_id)

                if not talent and talent_name:
                    from talent_db import get_or_create_talent_from_imdb
                    talent = get_or_create_talent_from_imdb(
                        imdb_id=imdb_id,
                        name=talent_name
                    )
                    print(f"[Discovery] Created talent: {talent_name} ({imdb_id})")

                if talent:
                    discovery_in_progress.add(job_key)
                    # Use threading directly instead of BackgroundTasks for more reliable execution
                    thread = threading.Thread(
                        target=discover_image_worker,
                        args=(imdb_id, source, talent.name, image_path, imdb_image_url),
                        daemon=True
                    )
                    thread.start()
                    print(f"[Discovery] Queued {source} discovery for {imdb_id} (name: {talent.name})")
        elif len(parts) == 1:
            # Legacy format: {imdb_id}.jpg - try to find any available image
            imdb_id = parts[0]
            for source in ['imdb', 'tmdb', 'brave']:
                legacy_path = image_dir / f"{imdb_id}_{source}.jpg"
                if legacy_path.exists():
                    return FileResponse(str(legacy_path), media_type="image/jpeg")
    except Exception as e:
        print(f"[Discovery] Job trigger failed: {e}")

    raise HTTPException(status_code=404, detail="Image not found yet - discovery triggered")


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
