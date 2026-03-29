#!/usr/bin/env python3
"""
Tycho API - REST API for creating actor-focused promotional videos

Endpoints:
- POST /api/projects - Create a new Tycho project
- GET /api/projects - List all projects
- GET /api/projects/{project_id} - Get project details
- POST /api/projects/{project_id}/generate - Generate a spot for an actor
- GET /api/projects/{project_id}/videos - List generated videos
- DELETE /api/projects/{project_id} - Delete a project
"""

import json
import os
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from get_actors import fetch_cast_with_images, init_cache
from twelvelabs_client import TwelveLabsClient
from ltx_client import LTXClient
from tycho import TychoOrchestrator, TychoProject, ActorSpot

# Initialize FastAPI app
app = FastAPI(
    title="Tycho API",
    description="Create actor-focused promotional videos from archival content",
    version="1.0.0",
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
OUTPUT_DIR = Path(__file__).parent / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Mount static files for video playback
app.mount("/videos", StaticFiles(directory=str(OUTPUT_DIR)), name="videos")

# Initialize orchestrator
orchestrator = TychoOrchestrator(output_dir=str(OUTPUT_DIR))


# ============== Pydantic Models ==============

class CreateProjectRequest(BaseModel):
    """Request to create a new Tycho project."""
    video_path: str = Field(..., description="Path to source video file")
    imdb_title_id: str = Field(..., description="IMDb title ID (e.g., tt0058331)")
    actor_names: Optional[List[str]] = Field(None, description="Specific actors to focus on")
    max_actors: int = Field(10, ge=1, le=50, description="Maximum actors to process")
    index_name: Optional[str] = Field(None, description="Custom 12Labs index name")


class GenerateSpotRequest(BaseModel):
    """Request to generate a promotional spot."""
    actor_name: str = Field(..., description="Name of the actor")
    actor_id: Optional[str] = Field(None, description="IMDb actor ID")
    prompt: Optional[str] = Field(None, description="Custom prompt for video generation")
    duration: int = Field(10, ge=3, le=30, description="Video duration in seconds")
    resolution: str = Field("1920x1080", description="Output resolution")


class ClipMatchResponse(BaseModel):
    """A clip where an actor was found."""
    video_id: str
    start: float
    end: float
    score: float
    actor_name: str
    actor_id: str


class ActorSpotResponse(BaseModel):
    """An actor's spot in a project."""
    actor_name: str
    actor_id: str
    birth_year: Optional[int]
    headshot_url: str
    clips: List[ClipMatchResponse]
    generated_video: Optional[str]
    voiceover_script: Optional[str]


class ProjectResponse(BaseModel):
    """A Tycho project."""
    project_id: str
    source_video: str
    source_video_id: str
    imdb_title_id: str
    created_at: str
    status: str  # "processing", "ready", "error"
    actors: List[ActorSpotResponse]
    metadata: dict


class ProjectListItem(BaseModel):
    """Summary of a project for listing."""
    project_id: str
    imdb_title_id: str
    created_at: str
    status: str
    actors_count: int
    generated_count: int


class MessageResponse(BaseModel):
    """Simple message response."""
    message: str
    success: bool = True


# ============== Helper Functions ==============

def load_project(project_id: str) -> Optional[dict]:
    """Load a project from disk."""
    project_path = OUTPUT_DIR / project_id / "project.json"
    if not project_path.exists():
        return None
    with open(project_path) as f:
        return json.load(f)


def save_project(project_id: str, data: dict):
    """Save a project to disk."""
    project_path = OUTPUT_DIR / project_id / "project.json"
    project_path.parent.mkdir(parents=True, exist_ok=True)
    with open(project_path, "w") as f:
        json.dump(data, f, indent=2)


def get_all_projects() -> List[dict]:
    """Get all projects from the output directory."""
    projects = []
    for project_dir in OUTPUT_DIR.iterdir():
        if project_dir.is_dir():
            project_file = project_dir / "project.json"
            if project_file.exists():
                with open(project_file) as f:
                    projects.append(json.load(f))
    return sorted(projects, key=lambda p: p.get("created_at", ""), reverse=True)


# ============== API Endpoints ==============

@app.get("/", response_model=MessageResponse)
async def root():
    """API health check."""
    return {"message": "Tycho API is running", "success": True}


@app.get("/api/health", response_model=MessageResponse)
async def health_check():
    """Health check endpoint."""
    return {"message": "OK", "success": True}


@app.post("/api/projects", response_model=ProjectResponse)
async def create_project(request: CreateProjectRequest):
    """
    Create a new Tycho project.
    
    This initiates the full workflow:
    1. Fetch cast from IMDb
    2. Index video with 12Labs
    3. Search for actors in video
    4. Return project with found actors (generation is separate)
    """
    # Validate video exists
    video_path = Path(request.video_path)
    if not video_path.exists():
        # Try relative to current directory
        video_path = Path(__file__).parent / request.video_path
        if not video_path.exists():
            raise HTTPException(status_code=400, detail=f"Video not found: {request.video_path}")
    
    project_id = f"tycho_{request.imdb_title_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    try:
        # Create project (without generation)
        # Use tt_id-based index name for consistency and reuse
        index_name = request.index_name or f"tycho_{request.imdb_title_id}"
        
        project = orchestrator.create_project(
            video_path=str(video_path),
            imdb_title_id=request.imdb_title_id,
            actor_names=request.actor_names,
            max_actors=request.max_actors,
            index_name=index_name,
        )
        
        # Rename project directory to match our ID
        old_dir = OUTPUT_DIR / project.project_id
        new_dir = OUTPUT_DIR / project_id
        if old_dir.exists() and old_dir != new_dir:
            shutil.move(str(old_dir), str(new_dir))
        
        # Load and update project
        project_data = load_project(project_id)
        project_data["project_id"] = project_id
        project_data["status"] = "ready"
        save_project(project_id, project_data)
        
        return ProjectResponse(**project_data)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/projects", response_model=List[ProjectListItem])
async def list_projects():
    """List all Tycho projects."""
    projects = get_all_projects()
    return [
        ProjectListItem(
            project_id=p["project_id"],
            imdb_title_id=p["imdb_title_id"],
            created_at=p["created_at"],
            status=p.get("status", "ready"),
            actors_count=len(p.get("actors", [])),
            generated_count=sum(1 for a in p.get("actors", []) if a.get("generated_video")),
        )
        for p in projects
    ]


@app.get("/api/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str):
    """Get details for a specific project."""
    project_data = load_project(project_id)
    if not project_data:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse(**project_data)


@app.post("/api/projects/{project_id}/generate", response_model=ActorSpotResponse)
async def generate_spot(project_id: str, request: GenerateSpotRequest):
    """
    Generate a promotional spot for a specific actor.
    
    This creates a short video featuring the actor using LTX.
    """
    project_data = load_project(project_id)
    if not project_data:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Find the actor in the project
    actor = None
    for a in project_data.get("actors", []):
        if a["actor_name"] == request.actor_name or a["actor_id"] == request.actor_id:
            actor = a
            break
    
    if not actor:
        raise HTTPException(status_code=404, detail=f"Actor not found: {request.actor_name}")
    
    if not actor.get("clips"):
        raise HTTPException(status_code=400, detail="No clips found for this actor")
    
    try:
        # Generate the spot
        video_path = orchestrator.generate_spot(
            project_id=project_id,
            actor_name=actor["actor_name"],
            prompt=request.prompt,
            duration=request.duration,
            resolution=request.resolution,
        )
        
        if not video_path:
            raise HTTPException(status_code=500, detail="Failed to generate video")
        
        # Update project data
        for a in project_data["actors"]:
            if a["actor_name"] == actor["actor_name"]:
                a["generated_video"] = video_path
                a["voiceover_script"] = request.prompt or orchestrator._generate_voiceover_prompt(
                    type('ActorSpot', (), actor)()
                )
                break
        
        save_project(project_id, project_data)
        
        return ActorSpotResponse(**a)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/projects/{project_id}/videos")
async def list_videos(project_id: str):
    """List all generated videos for a project."""
    project_data = load_project(project_id)
    if not project_data:
        raise HTTPException(status_code=404, detail="Project not found")
    
    videos = []
    project_dir = OUTPUT_DIR / project_id
    
    for actor in project_data.get("actors", []):
        if actor.get("generated_video"):
            video_path = Path(actor["generated_video"])
            videos.append({
                "actor_name": actor["actor_name"],
                "actor_id": actor["actor_id"],
                "video_path": str(video_path),
                "video_url": f"/videos/{project_id}/{video_path.name}",
                "voiceover_script": actor.get("voiceover_script"),
            })
    
    return {"videos": videos}


@app.get("/api/projects/{project_id}/video/{actor_id}")
async def get_video(project_id: str, actor_id: str):
    """Stream a specific actor's generated video."""
    project_data = load_project(project_id)
    if not project_data:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Find the actor's video
    video_path = None
    for actor in project_data.get("actors", []):
        if actor["actor_id"] == actor_id:
            if actor.get("generated_video"):
                video_path = Path(actor["generated_video"])
            break
    
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    
    return FileResponse(
        str(video_path),
        media_type="video/mp4",
        filename=video_path.name,
    )


@app.delete("/api/projects/{project_id}", response_model=MessageResponse)
async def delete_project(project_id: str):
    """Delete a project and all its assets."""
    project_dir = OUTPUT_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        shutil.rmtree(str(project_dir))
        return {"message": f"Project {project_id} deleted", "success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/imdb/cast/{imdb_title_id}")
async def get_imdb_cast(imdb_title_id: str, limit: int = 20):
    """
    Fetch cast information from IMDb for a title.

    This is a standalone endpoint to preview cast before creating a project.
    """
    try:
        init_cache()
        cast = fetch_cast_with_images(imdb_title_id, limit=limit)

        return {
            "imdb_title_id": imdb_title_id,
            "cast_count": len(cast),
            "cast": [
                {
                    "name_id": c["name_id"],
                    "name": c["name"],
                    "category": c["category"],
                    "characters": c.get("characters", []),
                    "birth_year": c.get("birth_date", {}).get("year") if c.get("birth_date") else None,
                    "headshot_url": c["primary_image"].get("url") if c.get("primary_image") else None,
                }
                for c in cast
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Error Handlers ==============

@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"detail": "Not found", "success": False},
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "success": False},
    )


# ============== Main ==============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
