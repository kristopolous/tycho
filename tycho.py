#!/usr/bin/env python3
"""
tycho.py - Main workflow orchestrator for Tycho

Tycho creates short promotional videos featuring actors from archival content.

Workflow:
1. Fetch cast from IMDb for a title
2. Index the source video with 12Labs
3. Search for each actor in the video using their headshot
4. Generate promotional clips using LTX for each actor found

Usage:
    python tycho.py <video_path> --imdb-id <tt_id> --actor <actor_name>
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

# Import our modules
from get_actors import fetch_cast_with_images, init_cache
from twelvelabs_client import TwelveLabsClient, ClipMatch
from ltx_client import LTXClient


@dataclass
class ActorSpot:
    """Represents a promotional spot for an actor."""
    actor_name: str
    actor_id: str
    birth_year: Optional[int]
    headshot_url: str
    clips: List[dict]  # Timestamps where actor appears
    generated_video: Optional[str] = None
    voiceover_script: Optional[str] = None


@dataclass
class TychoProject:
    """Represents a complete Tycho project."""
    project_id: str
    source_video: str
    source_video_id: str
    imdb_title_id: str
    created_at: str
    actors: List[ActorSpot]
    metadata: dict


class TychoOrchestrator:
    """Orchestrates the Tycho workflow."""
    
    def __init__(self, output_dir: str = "outputs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize clients
        self.twelvelabs = TwelveLabsClient()
        self.ltx = LTXClient()
        
        # Initialize IMDb cache
        init_cache()
    
    def create_project(
        self,
        video_path: str,
        imdb_title_id: str,
        actor_names: Optional[List[str]] = None,
        max_actors: int = 10,
        index_name: Optional[str] = None,
    ) -> TychoProject:
        """
        Create a Tycho project for a video.
        
        Args:
            video_path: Path to the source video
            imdb_title_id: IMDb title ID (e.g., tt0058331)
            actor_names: Optional list of specific actor names to focus on
            max_actors: Maximum number of actors to process
            index_name: Optional name for the 12Labs index
        
        Returns:
            TychoProject object
        """
        print(f"\n{'='*60}")
        print(f"TYCHO PROJECT")
        print(f"{'='*60}")
        print(f"Video: {video_path}")
        print(f"IMDb: {imdb_title_id}")
        print(f"{'='*60}\n")
        
        # Step 1: Get cast from IMDb
        print("[Step 1/5] Fetching cast from IMDb...")
        cast = fetch_cast_with_images(imdb_title_id, limit=max_actors)
        
        # Filter to specific actors if requested
        if actor_names:
            cast = [c for c in cast if c['name'] in actor_names]
            print(f"      Filtered to {len(cast)} specified actors")
        
        # Step 2: Index the video with 12Labs
        print("\n[Step 2/5] Indexing video with 12Labs...")
        if index_name is None:
            # Use consistent index name based on tt_id for reuse
            index_name = f"tycho_{imdb_title_id}"
        
        self.twelvelabs.create_index(index_name)
        
        # Check if we already have a video indexed (from previous run)
        # by checking if any videos exist in the index
        try:
            videos = list(self.twelvelabs.client.indexes.videos.list(
                index_id=self.twelvelabs.index_id,
                page_limit=1
            ))
            if videos:
                video_id = videos[0].id
                print(f"[12Labs] Reusing existing video: {video_id}")
            else:
                # No existing video, upload new one
                video_id = self.twelvelabs.upload_video(video_path)
        except Exception as e:
            print(f"[12Labs] Could not check existing videos: {e}")
            video_id = self.twelvelabs.upload_video(video_path)
        
        # Step 3: Search for each actor in the video
        print("\n[Step 3/5] Searching for actors in video...")
        actor_spots = []
        
        for actor in cast:
            headshot = actor.get('primary_image')
            if not headshot:
                print(f"      Skipping {actor['name']}: No headshot available")
                continue
            
            # Download headshot if it's a URL
            headshot_path = self._download_image(headshot['url'], actor['name_id'])
            
            # Search for this actor in the video
            try:
                clips = self.twelvelabs.search_actor_in_video(
                    headshot_path=headshot_path,
                    actor_name=actor['name'],
                    actor_id=actor['name_id'],
                    max_results=5,
                )
            except Exception as e:
                print(f"      {actor['name']}: Search error - {e}")
                clips = []
            
            if clips:
                birth_year = None
                if actor.get('birth_date') and actor['birth_date'].get('year'):
                    birth_year = actor['birth_date']['year']

                spot = ActorSpot(
                    actor_name=actor['name'],
                    actor_id=actor['name_id'],
                    birth_year=birth_year,
                    headshot_url=headshot['url'],
                    clips=[asdict(c) for c in clips],
                )
                actor_spots.append(spot)
                print(f"      {actor['name']}: Found {len(clips)} clips")
            else:
                # Include actor even if not found - UI will show "not found" state
                birth_year = None
                if actor.get('birth_date') and actor['birth_date'].get('year'):
                    birth_year = actor['birth_date']['year']
                
                spot = ActorSpot(
                    actor_name=actor['name'],
                    actor_id=actor['name_id'],
                    birth_year=birth_year,
                    headshot_url=headshot['url'],
                    clips=[],
                )
                actor_spots.append(spot)
                print(f"      {actor['name']}: Not found in video")
        
        # Step 4: Generate promotional videos (optional - can be done per-actor)
        print(f"\n[Step 4/5] Ready to generate spots for {len(actor_spots)} actors")
        
        # Create project object
        project = TychoProject(
            project_id=f"tycho_{imdb_title_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            source_video=video_path,
            source_video_id=video_id,
            imdb_title_id=imdb_title_id,
            created_at=datetime.now().isoformat(),
            actors=actor_spots,
            metadata={
                "index_name": index_name,
                "cast_count": len(cast),
                "actors_found": len(actor_spots),
            }
        )
        
        # Save project
        self._save_project(project)
        
        print(f"\n[Step 5/5] Project saved!")
        print(f"      Output: {self.output_dir / project.project_id}")
        
        return project
    
    def generate_spot(
        self,
        project: TychoProject,
        actor_name: str,
        prompt: Optional[str] = None,
        duration: int = 10,
        resolution: str = "1920x1080",
    ) -> Optional[str]:
        """
        Generate a promotional spot for a specific actor.
        
        Args:
            project: TychoProject object
            actor_name: Name of the actor to create a spot for
            prompt: Optional custom prompt for video generation
            duration: Duration of generated video in seconds
            resolution: Output resolution
        
        Returns:
            Path to generated video or None
        """
        # Find the actor
        actor = None
        for a in project.actors:
            if a.actor_name == actor_name:
                actor = a
                break
        
        if not actor:
            print(f"Actor {actor_name} not found in project")
            return None
        
        if not actor.clips:
            print(f"No clips found for {actor_name}")
            return None
        
        # Download headshot
        headshot_path = self._download_image(actor.headshot_url, actor.actor_id)
        
        # Generate prompt if not provided
        if prompt is None:
            prompt = self._generate_voiceover_prompt(actor)
        
        print(f"\nGenerating spot for {actor_name}...")
        print(f"  Prompt: {prompt}")
        
        # Generate video
        output_path = str(self.output_dir / project.project_id / f"spot_{actor.actor_id}.mp4")
        
        try:
            video = self.ltx.generate_video(
                image_path=headshot_path,
                prompt=prompt,
                duration=duration,
                resolution=resolution,
                output_path=output_path,
            )
            
            # Update actor spot
            actor.generated_video = video.video_path
            actor.voiceover_script = prompt
            
            # Save updated project
            self._save_project(project)
            
            return video.video_path
            
        except Exception as e:
            print(f"Error generating video: {e}")
            return None
    
    def _download_image(self, url: str, name_id: str) -> str:
        """Download an image from URL and save locally."""
        import requests
        
        cache_dir = self.output_dir / "images"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        image_path = cache_dir / f"{name_id}.jpg"
        
        if image_path.exists():
            return str(image_path)
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            with open(image_path, "wb") as f:
                f.write(response.content)
            
            return str(image_path)
        except Exception as e:
            print(f"Warning: Could not download image: {e}")
            return str(image_path)  # Return path anyway
    
    def _generate_voiceover_prompt(self, actor: ActorSpot) -> str:
        """Generate a voiceover prompt for an actor spot."""
        birth_info = ""
        if actor.birth_year:
            birth_info = f"born in {birth_year}, "
        
        prompt = (
            f"Cinematic promotional video featuring {actor.name}, "
            f"{birth_info}showing early career footage. "
            f"Warm nostalgic lighting, dramatic reveals, "
            f"professional documentary style, high quality production."
        )
        
        return prompt
    
    def _save_project(self, project: TychoProject):
        """Save project to disk."""
        project_dir = self.output_dir / project.project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # Save as JSON
        with open(project_dir / "project.json", "w") as f:
            json.dump(asdict(project), f, indent=2)
        
        # Save as markdown summary
        md_content = self._project_to_markdown(project)
        with open(project_dir / "README.md", "w") as f:
            f.write(md_content)
    
    def _project_to_markdown(self, project: TychoProject) -> str:
        """Convert project to markdown summary."""
        md = f"""# Tycho Project: {project.project_id}

**Created:** {project.created_at}
**Source Video:** {project.source_video}
**IMDb Title:** {project.imdb_title_id}

## Summary
- **Cast Processed:** {project.metadata.get('cast_count', 0)}
- **Actors Found:** {project.metadata.get('actors_found', 0)}

## Actors
"""
        for actor in project.actors:
            md += f"""
### {actor.actor_name}
- **IMDb ID:** {actor.actor_id}
- **Birth Year:** {actor.birth_year or 'Unknown'}
- **Clips Found:** {len(actor.clips)}
- **Generated Video:** {actor.generated_video or 'Not generated'}
"""
            if actor.clips:
                md += "\n**Clip Timestamps:**\n"
                for i, clip in enumerate(actor.clips[:5], 1):
                    md += f"  {i}. {clip['start']:.1f}s - {clip['end']:.1f}s (score: {clip['score']:.2f})\n"
        
        return md


def main():
    parser = argparse.ArgumentParser(description="Tycho - Create actor-focused promotional videos")
    parser.add_argument("video", type=str, help="Path to source video")
    parser.add_argument("--imdb-id", type=str, required=True, help="IMDb title ID (e.g., tt0058331)")
    parser.add_argument("--actor", type=str, action="append", help="Specific actor(s) to focus on")
    parser.add_argument("--max-actors", type=int, default=10, help="Maximum actors to process")
    parser.add_argument("--generate", type=str, help="Generate spot for specific actor")
    parser.add_argument("--duration", type=int, default=10, help="Generated video duration (seconds)")
    parser.add_argument("--output", type=str, default="outputs", help="Output directory")
    parser.add_argument("--index-name", type=str, help="Custom 12Labs index name")
    
    args = parser.parse_args()
    
    # Initialize orchestrator
    orchestrator = TychoOrchestrator(output_dir=args.output)
    
    # Create project
    project = orchestrator.create_project(
        video_path=args.video,
        imdb_title_id=args.imdb_id,
        actor_names=args.actor,
        max_actors=args.max_actors,
        index_name=args.index_name,
    )
    
    # Generate spot for specific actor if requested
    if args.generate:
        for actor_name in args.generate.split(","):
            actor_name = actor_name.strip()
            video_path = orchestrator.generate_spot(
                project=project,
                actor_name=actor_name,
                duration=args.duration,
            )
            if video_path:
                print(f"\nGenerated spot: {video_path}")
    
    print(f"\n{'='*60}")
    print("TYCHO COMPLETE")
    print(f"{'='*60}")
    print(f"Project directory: {orchestrator.output_dir / project.project_id}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
