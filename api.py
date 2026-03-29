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

from fastapi import FastAPI, HTTPException, BackgroundTasks, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from get_actors import fetch_cast_with_images, init_cache, get_title_metadata
from twelvelabs_client import TwelveLabsClient
from ltx_client import LTXClient
from tycho import TychoOrchestrator, TychoProject, ActorSpot
from exports import ExportEngine
from mam_dam import MAMIntegration

# Create API router with /api prefix
router = APIRouter()

# Configuration
OUTPUT_DIR = Path(__file__).parent / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Thumbnail cache directory
THUMBNAIL_CACHE_DIR = OUTPUT_DIR / "thumbnails"
THUMBNAIL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Initialize engines
orchestrator = TychoOrchestrator(output_dir=str(OUTPUT_DIR))
export_engine = ExportEngine(output_dir=str(OUTPUT_DIR))
mam_engine = MAMIntegration(output_dir=str(OUTPUT_DIR))


# ============== Pydantic Models ==============

class CreateProjectRequest(BaseModel):
    """Request to create a new Tycho project."""
    video_path: str = Field(..., description="Path to source video file")
    imdb_title_id: str = Field(..., description="IMDb title ID (e.g., tt0058331)")
    actor_names: Optional[List[str]] = Field(None, description="Specific actors to focus on")
    max_actors: int = Field(10, ge=1, le=50, description="Maximum actors to process")
    index_name: Optional[str] = Field(None, description="Custom 12Labs index name")
    harness_name: Optional[str] = Field(None, description="Harness/template name (e.g., 'nostalgia')")
    platform: Optional[str] = Field(None, description="Target platform (e.g., 'tiktok', 'youtube')")
    use_tmdb: bool = Field(True, description="Use TMDB for additional headshots (multi-image search)")
    max_tmdb_images: int = Field(3, ge=1, le=10, description="Max TMDB images per actor for multi-image search")


class GenerateSpotRequest(BaseModel):
    """Request to generate a promotional spot."""
    actor_name: str = Field(..., description="Name of the actor")
    actor_id: Optional[str] = Field(None, description="IMDb actor ID")
    prompt: Optional[str] = Field(None, description="Custom prompt for video generation")
    duration: int = Field(10, ge=3, le=30, description="Video duration in seconds")
    resolution: Optional[str] = Field(None, description="Output resolution (auto-determined from platform if not provided)")
    harness_name: Optional[str] = Field(None, description="Override harness name for this generation")
    platform: Optional[str] = Field(None, description="Override platform for this generation (determines aspect ratio)")


class ExportRequest(BaseModel):
    """Request to export clips in a specific format."""
    actor_id: str = Field(..., description="IMDb actor ID")
    format: str = Field(..., description="Format: EDL, AAF, or MAM")
    system: Optional[str] = Field("Generic", description="Target system (e.g., Avid, Dalet)")


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
    source_video_id: Optional[str] = None
    imdb_title_id: str
    created_at: str
    status: str  # "processing", "ready", "error"
    actors: List[ActorSpotResponse]
    metadata: dict
    title_text: str = ""
    title_image_url: str = ""
    harness_name: Optional[str] = None
    platform: Optional[str] = None


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


@router.get("/api/health", response_model=MessageResponse)
async def health_check():
    """Health check endpoint."""
    return {"message": "OK", "success": True}


@router.post("/api/projects", response_model=ProjectResponse)
async def create_project(request: CreateProjectRequest):
    """
    Create a new Tycho project.

    This initiates the full workflow:
    1. Fetch cast from IMDb
    2. Index video with 12Labs
    3. Search for actors in video
    4. Return project with found actors (generation is separate)
    """
    # CRITICAL: Check if project already exists - PREVENTS DUPLICATE 12LABS API CALLS
    existing_projects = get_all_projects()
    print(f"\n{'='*60}")
    print(f"[CACHE CHECK] imdb_title_id={request.imdb_title_id}")
    print(f"[CACHE CHECK] Found {len(existing_projects)} existing projects")
    for proj in existing_projects:
        proj_id = proj.get("imdb_title_id")
        print(f"[CACHE CHECK]   Checking: {proj_id}")
        if proj_id == request.imdb_title_id:
            print(f"[CACHE HIT] ✓✓✓ RETURNING CACHED PROJECT ✓✓✓")
            print(f"{'='*60}\n")
            return ProjectResponse(**proj)
    print(f"[CACHE MISS] No cache found - proceeding with 12Labs API calls")
    print(f"{'='*60}\n")

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
            harness_name=request.harness_name,
            platform=request.platform,
            use_tmdb=request.use_tmdb,
            max_tmdb_images=request.max_tmdb_images,
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
        # Ensure source_video_id is set (may be None when using existing index)
        if not project_data.get("source_video_id"):
            project_data["source_video_id"] = "existing_index_video"
        save_project(project_id, project_data)
        
        return ProjectResponse(**project_data)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/projects", response_model=List[ProjectListItem])
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


@router.get("/api/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str):
    """Get details for a specific project."""
    project_data = load_project(project_id)
    if not project_data:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse(**project_data)


@router.post("/api/projects/{project_id}/generate", response_model=ActorSpotResponse)
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
        # Load project object - need to convert dict actors to ActorSpot objects
        from tycho import TychoProject, ActorSpot
        
        # Convert actors dicts to ActorSpot objects
        actors_list = []
        for a in project_data.get("actors", []):
            actor_spot = ActorSpot(
                actor_name=a["actor_name"],
                actor_id=a["actor_id"],
                birth_year=a.get("birth_year"),
                headshot_url=a["headshot_url"],
                clips=a.get("clips", []),
                generated_video=a.get("generated_video"),
                voiceover_script=a.get("voiceover_script"),
            )
            actors_list.append(actor_spot)
        
        project_obj = TychoProject(
            project_id=project_data["project_id"],
            source_video=project_data["source_video"],
            source_video_id=project_data["source_video_id"],
            imdb_title_id=project_data["imdb_title_id"],
            created_at=project_data["created_at"],
            actors=actors_list,
            metadata=project_data.get("metadata", {}),
            status=project_data.get("status", "ready"),
            title_text=project_data.get("title_text", ""),
            title_image_url=project_data.get("title_image_url", ""),
            harness_name=project_data.get("harness_name"),
            platform=project_data.get("platform"),
        )

        # Generate the spot
        video_path = orchestrator.generate_spot(
            project=project_obj,
            actor_name=actor["actor_name"],
            prompt=request.prompt,
            duration=request.duration,
            resolution=request.resolution,
            harness_name=request.harness_name,
            platform=request.platform,
        )

        if not video_path:
            raise HTTPException(status_code=500, detail="Failed to generate video")
        
        # Update project data
        for a in project_data["actors"]:
            if a["actor_name"] == actor["actor_name"]:
                a["generated_video"] = video_path
                # Create proper ActorSpot object for voiceover generation
                actor_spot = ActorSpot(
                    actor_name=actor["actor_name"],
                    actor_id=actor["actor_id"],
                    birth_year=actor.get("birth_year"),
                    headshot_url=actor["headshot_url"],
                    clips=actor.get("clips", []),
                )
                a["voiceover_script"] = request.prompt or orchestrator._generate_voiceover_prompt(actor_spot)
                break
        
        save_project(project_id, project_data)
        
        return ActorSpotResponse(**a)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/projects/{project_id}/export")
async def export_assets(project_id: str, request: ExportRequest):
    """
    Export actor clips in industry-standard formats (EDL, AAF, or MAM XML).
    """
    project_data = load_project(project_id)
    if not project_data:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Find the actor
    actor = None
    for a in project_data.get("actors", []):
        if a["actor_id"] == request.actor_id:
            actor = a
            break
    
    if not actor:
        raise HTTPException(status_code=404, detail=f"Actor not found: {request.actor_id}")
    
    if not actor.get("clips"):
        raise HTTPException(status_code=400, detail="No clips found for this actor")

    try:
        file_path = ""
        format_type = request.format.upper()
        
        if format_type == "EDL":
            file_path = export_engine.generate_edl(
                project_id, actor["actor_id"], actor["actor_name"], 
                actor["clips"], project_data["source_video"]
            )
        elif format_type == "AAF":
            file_path = export_engine.generate_aaf(
                project_id, actor["actor_id"], actor["actor_name"], 
                actor["clips"], project_data["source_video"]
            )
        elif format_type == "MAM":
            file_path = mam_engine.generate_sidecar_xml(
                project_id, actor, project_data
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {request.format}")

        return {
            "success": True,
            "format": format_type,
            "file_path": str(file_path),
            "file_url": f"/api/projects/{project_id}/download/{Path(file_path).name}"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/projects/{project_id}/download/{filename}")
async def download_export(project_id: str, filename: str):
    """Download a generated export file."""
    file_path = OUTPUT_DIR / project_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        str(file_path),
        filename=filename
    )


@router.get("/api/projects/{project_id}/videos")
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


@router.get("/api/projects/{project_id}/video/{actor_id}")
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


@router.delete("/api/projects/{project_id}", response_model=MessageResponse)
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


@router.get("/api/imdb/cast/{imdb_title_id}")
async def get_imdb_cast(imdb_title_id: str, limit: int = 20):
    """
    Fetch cast information from IMDb for a title.
    Only returns actors with headshots for professional presentation.
    """
    try:
        init_cache()
        cast = fetch_cast_with_images(imdb_title_id, limit=limit)
        metadata = get_title_metadata(imdb_title_id)

        # Filter to only actors with headshots
        cast_with_photos = [c for c in cast if c.get("primary_image")]

        return {
            "imdb_title_id": imdb_title_id,
            "title": metadata.get("title"),
            "year": metadata.get("year"),
            "type": metadata.get("type"),
            "genres": metadata.get("genres"),
            "rating": metadata.get("rating", {}).get("aggregateRating"),
            "plot": metadata.get("plot"),
            "poster_url": metadata.get("image_url"),
            "cast_count": len(cast_with_photos),
            "cast": [
                {
                    "name_id": c["name_id"],
                    "name": c["name"],
                    "category": c["category"],
                    "characters": c.get("characters", []),
                    "birth_year": c.get("birth_date", {}).get("year") if c.get("birth_date") else None,
                    "headshot_url": c["primary_image"].get("url"),
                }
                for c in cast_with_photos
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Main ==============

if __name__ == "__main__":
    import uvicorn
    import socket
    
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
    print(f"Starting Tycho API on port {port}...")
    # Get the current filename without extension
    module_name = Path(__file__).stem
    uvicorn.run(f"{module_name}:app", host="0.0.0.0", port=port, reload=True)
