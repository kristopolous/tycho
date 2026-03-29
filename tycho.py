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
from get_actors import fetch_cast_with_images, init_cache, get_title_metadata
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
    mise_en_scene: Optional[dict] = None  # Talent archetype: adjectives + emotional saliences
    popularity_score: Optional[float] = None
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
    status: str = "processing"  # "processing", "ready", "error"
    title_text: str = ""  # Title name (e.g., "The Crane")
    title_image_url: str = ""  # Poster/artwork from IMDB
    harness_name: Optional[str] = None  # Harness/template name (e.g., "nostalgia")
    platform: Optional[str] = None  # Target platform (e.g., "tiktok", "youtube")


class TychoOrchestrator:
    """Orchestrates the Tycho workflow."""

    # Platform to resolution mapping for aspect ratio fallback
    PLATFORM_RESOLUTION = {
        "tiktok": "1080x1920",      # 9:16 portrait
        "instagram": "1080x1920",   # 9:16 portrait (Reels)
        "youtube": "1920x1080",     # 16:9 landscape (Shorts can also be 9:16)
        "youtube_shorts": "1080x1920",  # 9:16 portrait
        "threads": "1080x1080",     # 1:1 square
        "pack": "1920x1080",        # 16:9 landscape
    }

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
        use_tmdb: bool = False,
        max_tmdb_images: int = 2,
        harness_name: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> TychoProject:
        """
        Create a Tycho project for a video.

        Args:
            video_path: Path to the source video
            imdb_title_id: IMDb title ID (e.g., tt0058331)
            actor_names: Optional list of specific actor names to focus on
            max_actors: Maximum number of actors to process
            index_name: Optional name for the 12Labs index
            harness_name: Optional harness/template name (e.g., "nostalgia")
            platform: Optional target platform (e.g., "tiktok", "youtube")

        Returns:
            TychoProject object
        """
        print(f"\n{'='*60}")
        print(f"TYCHO PROJECT")
        print(f"{'='*60}")
        print(f"Video: {video_path}")
        print(f"IMDb: {imdb_title_id}")
        print(f"{'='*60}\n")
        
        # Step 1: Get cast from IMDb and title metadata
        print("[Step 1/6] Fetching cast and title info from IMDb...")
        if use_tmdb:
            print(f"      Using TMDB for additional headshots ({max_tmdb_images} images per actor)")
        cast = fetch_cast_with_images(imdb_title_id, limit=max_actors, use_tmdb=use_tmdb, max_tmdb_images=max_tmdb_images)
        
        # Get title metadata (title text and artwork)
        title_info = get_title_metadata(imdb_title_id)
        title_text = title_info.get('title', '')
        title_image_url = title_info.get('image_url', '')
        print(f"      Title: {title_text}")
        if title_image_url:
            print(f"      Title image available")
        
        # Filter to specific actors if requested
        if actor_names:
            cast = [c for c in cast if c['name'] in actor_names]
            print(f"      Filtered to {len(cast)} specified actors")
        
        # Step 2: Get or create 12Labs index
        # IMPORTANT: The working index with 13 clips is 69c931f8dc238c7710ea7bc2
        # Use this directly - don't search by name pattern which finds wrong indexes!
        print("\n[Step 2/5] Connecting to 12Labs index...")
        
        # PRIORITY 1: Use the hardcoded working index that has all 13 clips
        # This is the index user already indexed with the full video
        working_index_id = "69c931f8dc238c7710ea7bc2"
        
        # Verify this index exists and is accessible
        try:
            indexes = list(self.twelvelabs.client.indexes.list())
            print(f"[12Labs] Found {len(indexes)} indexes")
            
            # Check if our working index is in the list - PRIORITIZE IT!
            for idx in indexes:
                if idx.id == working_index_id:
                    self.twelvelabs.set_index(working_index_id)
                    print(f"[12Labs] ✓ Using working index: {working_index_id} ({idx.index_name})")
                    break
            else:
                # Working index not found - fall back to search by tt_id name
                print(f"[12Labs] Working index {working_index_id} not found, searching...")
                for idx in indexes:
                    if not idx.id:
                        continue
                    idx_name = getattr(idx, 'index_name', '')
                    if idx_name and imdb_title_id in idx_name:
                        self.twelvelabs.set_index(str(idx.id))
                        print(f"[12Labs] ✓ Using existing index: {idx.id} ({idx_name})")
                        break
                else:
                    # Last resort - create new index
                    new_index_name = f"tycho_{imdb_title_id}"
                    self.twelvelabs.create_index(new_index_name)
                    print(f"[12Labs] Created new index: {new_index_name}")
        except Exception as e:
            print(f"[12Labs] Warning: {e}")
            # Last resort: try the working index anyway
            self.twelvelabs.set_index(working_index_id)
        
        # Get video from this index
        video_id = None
        try:
            videos = list(self.twelvelabs.client.indexes.videos.list(
                index_id=self.twelvelabs.index_id,
                page_limit=1
            ))
            if videos:
                video_id = videos[0].id
                print(f"[12Labs] ✓ Reusing existing video: {video_id}")
        except Exception as e:
            print(f"[12Labs] Warning: Could not check existing videos: {type(e).__name__}: {e}")
        
        # Step 3: Search for each actor in the video
        print("\n[Step 3/5] Searching for actors in video...")
        actor_spots = []
        
        for actor in cast:
            headshot = actor.get('primary_image')
            if not headshot:
                print(f"      Skipping {actor['name']}: No headshot available")
                continue
            
            # Use the headshot URL directly - 12Labs can handle URLs without downloading!
            # This avoids the 10.7MB file size issue with IMDb images
            headshot_url = headshot['url']
            
            # Get all headshots for multi-image search (includes TMDB if available)
            all_headshots = actor.get('all_headshots', [headshot_url]) if headshot_url else []
            
            if not all_headshots:
                print(f"      Skipping {actor['name']}: No headshots available")
                continue
            
            # Search for this actor in the video - use multi-image search for better results
            try:
                if len(all_headshots) > 1:
                    print(f"      {actor['name']}: Using {len(all_headshots)} headshots for multi-image search")
                    clips = self.twelvelabs.search_actor_with_images(
                        headshot_paths=all_headshots,
                        actor_name=actor['name'],
                        actor_id=actor['name_id'],
                        max_results=20,  # Get more results to find diverse clips
                    )
                else:
                    clips = self.twelvelabs.search_actor_in_video(
                        headshot_path=all_headshots[0],
                        actor_name=actor['name'],
                        actor_id=actor['name_id'],
                        max_results=20,
                    )
            except Exception as e:
                print(f"      {actor['name']}: Search error - {e}")
                clips = []
            
            if clips:
                birth_year = None
                if actor.get('birth_date') and actor['birth_date'].get('year'):
                    birth_year = actor['birth_date']['year']

                # Deduplicate clips by start time (API sometimes returns duplicates)
                print(f"\n[DEDUP] Processing {len(clips)} clips for {actor['name']}")
                seen_times = set()
                unique_clips = []
                for c in clips:
                    key = (round(c.start, 1), round(c.end, 1))
                    print(f"[DEDUP]   Checking: {c.start:.1f}-{c.end:.1f}s -> key={key}, seen={key in seen_times}")
                    if key not in seen_times:
                        seen_times.add(key)
                        unique_clips.append(c)
                        print(f"[DEDUP]     ✓ Added (unique)")
                    else:
                        print(f"[DEDUP]     ✗ Skipped (duplicate)")
                
                print(f"[DEDUP] Found {len(unique_clips)} unique clips out of {len(clips)} total")
                
                # Save ALL unique clips - don't limit to 3!
                # The UI should show all clips, generation will use first 3
                print(f"[DEDUP] Saving all {len(unique_clips)} unique clips for {actor['name']}")

                # Get talent archetype (mise_en_scene) from database
                mise_en_scene = None
                popularity_score = None
                try:
                    from talent_db import get_talent_with_images
                    talent_data = get_talent_with_images(actor['name_id'], max_images=1)
                    if talent_data:
                        # mise_en_scene is nested under 'talent' key
                        talent = talent_data.get('talent', {})
                        mise_en_scene = talent.mise_en_scene if hasattr(talent, 'mise_en_scene') else talent.get('mise_en_scene') if isinstance(talent, dict) else None
                        popularity_score = talent.popularity_score if hasattr(talent, 'popularity_score') else talent.get('popularity_score') if isinstance(talent, dict) else None
                except Exception as e:
                    print(f"      Warning: Could not fetch talent archetype: {e}")

                spot = ActorSpot(
                    actor_name=actor['name'],
                    actor_id=actor['name_id'],
                    birth_year=birth_year,
                    headshot_url=headshot['url'],
                    clips=[asdict(c) for c in unique_clips],  # Save ALL clips!
                    mise_en_scene=mise_en_scene,
                    popularity_score=popularity_score,
                )
                actor_spots.append(spot)
                # Print timestamps for each clip
                clip_times = ', '.join([f"{c.start:.1f}-{c.end:.1f}s" for c in unique_clips])
                print(f"      {actor['name']}: Found {len(unique_clips)} clips [{clip_times}]")
            else:
                # Include actor even if not found - UI will show "not found" state
                birth_year = None
                if actor.get('birth_date') and actor['birth_date'].get('year'):
                    birth_year = actor['birth_date']['year']

                # Get talent archetype for actors not found in video too
                mise_en_scene = None
                popularity_score = None
                try:
                    from talent_db import get_talent_with_images
                    talent_data = get_talent_with_images(actor['name_id'], max_images=1)
                    if talent_data:
                        # mise_en_scene is nested under 'talent' key
                        talent = talent_data.get('talent', {})
                        mise_en_scene = talent.mise_en_scene if hasattr(talent, 'mise_en_scene') else talent.get('mise_en_scene') if isinstance(talent, dict) else None
                        popularity_score = talent.popularity_score if hasattr(talent, 'popularity_score') else talent.get('popularity_score') if isinstance(talent, dict) else None
                except Exception:
                    pass

                spot = ActorSpot(
                    actor_name=actor['name'],
                    actor_id=actor['name_id'],
                    birth_year=birth_year,
                    headshot_url=headshot['url'],
                    clips=[],
                    mise_en_scene=mise_en_scene,
                    popularity_score=popularity_score,
                )
                actor_spots.append(spot)
                print(f"      {actor['name']}: Not found in video")
        
        # Step 4: Generate promotional videos (optional - can be done per-actor)
        print(f"\n[Step 4/6] Ready to generate spots for {len(actor_spots)} actors")
        
        # Create project object
        project = TychoProject(
            project_id=f"tycho_{imdb_title_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            source_video=video_path,
            source_video_id=video_id or "",
            imdb_title_id=imdb_title_id,
            created_at=datetime.now().isoformat(),
            actors=actor_spots,
            metadata={
                "index_name": index_name,
                "cast_count": len(cast),
                "actors_found": len(actor_spots),
            },
            title_text=title_text,
            title_image_url=title_image_url,
            harness_name=harness_name,
            platform=platform,
        )
        
        # Save project
        self._save_project(project)
        
        print(f"\n[Step 6/6] Project saved!")
        print(f"      Output: {self.output_dir / project.project_id}")
        
        return project
    
    def generate_spot(
        self,
        project: TychoProject,
        actor_name: str,
        prompt: Optional[str] = None,
        duration: int = 16,
        resolution: Optional[str] = None,  # Will be determined from platform/harness if not provided
        harness_name: Optional[str] = None,  # Override project harness if provided
        platform: Optional[str] = None,  # Override project platform if provided
    ) -> Optional[str]:
        """
        Generate a promotional spot for a specific actor.

        Structure (16 seconds total):
        - Intro: 4s LTX with title card "<actor> deep cut. Ever see <title>?"
        - Clips: 3 clips x 4s each = 12s from source video
        - Outro: 3s LTX with CTA "Watch <title> exclusively on streamplus"

        Args:
            project: TychoProject object
            actor_name: Name of the actor to create a spot for
            prompt: Optional custom prompt for video generation
            duration: Total duration target (default 16s)
            resolution: Output resolution (auto-determined from platform if not provided)
            harness_name: Override project harness name if provided
            platform: Override project platform if provided

        Returns:
            Path to generated video or None
        """
        import subprocess
        from datetime import datetime

        # Determine effective harness and platform (priority: param > project > None)
        effective_harness = harness_name or project.harness_name
        effective_platform = platform or project.platform

        # Determine resolution: explicit param > platform fallback > default
        if resolution is None:
            if effective_platform:
                resolution = self.PLATFORM_RESOLUTION.get(effective_platform, "1920x1080")
            else:
                resolution = "1920x1080"  # Default landscape

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
        
        # Get title info for intro/outro
        title_text = project.title_text or "the movie"
        title_image = project.title_image_url or actor.headshot_url
        
        # Setup logging to file in project directory
        project_dir = self.output_dir / project.project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        log_file = project_dir / f"generation_{actor.actor_id}.log"
        
        # Clear log file at start of each generation
        open(log_file, "w").close()
        
        def log(msg, explanation=None):
            """Write to both console and log file with optional explanation."""
            timestamp = datetime.now().strftime("%H:%M:%S")
            console_msg = f"[{timestamp}] {msg}"
            print(console_msg)
            with open(log_file, "a") as f:
                f.write(console_msg + "\n")
                if explanation:
                    f.write(f"         └─ {explanation}\n")
        
        log(f"Starting 16s spot generation for {actor_name}")
        log(f"Target title: {title_text}", explanation=f"Using title artwork from IMDB for intro/outro")
        log(f"Found {len(actor.clips)} clips in source video", explanation=f"These are the moments where {actor_name} appears in the film")
        
        source_video_path = project.source_video
        if not os.path.exists(source_video_path):
            log(f"ERROR: Source video not found: {source_video_path}")
            return None
        
        # Select up to 4 clips (max 3s each = 12s of content) with better variety
        MAX_CLIP_DURATION = 3
        # Select clips spread across the video for better variety
        all_clips = actor.clips[:]
        if len(all_clips) >= 4:
            # Pick first, middle-ish, and last for variety
            selected_clips = [all_clips[0], all_clips[len(all_clips)//2], all_clips[-2], all_clips[-1]][:4]
        else:
            selected_clips = all_clips[:4]
        
        processed_clips = []
        for clip in selected_clips:
            start = clip['start']
            end = clip['end']
            duration = end - start
            # Cap at 3s max for faster pacing
            if duration > MAX_CLIP_DURATION:
                end = start + MAX_CLIP_DURATION
                duration = MAX_CLIP_DURATION
            log(f"  Clip: {start:.1f}s - {end:.1f}s (duration: {duration:.1f}s)", explanation="Archival clip from movie")
            processed_clips.append({'start': start, 'end': end})
        selected_clips = processed_clips
        
        log(f"Selected {len(selected_clips)} clips (capped at 4s each = 12s total)", explanation=f"Archival clips from the movie that showcase the actor")
        
        # Step 1: Extract individual clips from source video using ffmpeg
        # We're cutting out the specific moments from the movie where this actor appears
        log(f"=== Step 1: Extracting {len(selected_clips)} clips from source video ===", explanation=f"ffmpeg cuts out each clip segment from the full movie")
        extracted_clips = []
        
        for i, clip in enumerate(selected_clips):
            start_time = clip['start']
            end_time = clip['end']
            clip_duration = end_time - start_time
            
            clip_output = project_dir / f"clip_{actor.actor_id}_{i}.mp4"
            extracted_clips.append(str(clip_output))
            
            # Skip if already extracted
            if clip_output.exists():
                log(f"  Clip {i}: {start_time:.1f}s - {end_time:.1f}s (cached)", explanation="Already extracted, using cached version")
                continue
            
            log(f"  Clip {i}: {start_time:.1f}s - {end_time:.1f}s (duration: {clip_duration:.1f}s)", explanation=f"Extracting archival footage from the movie")
            
            # Extract clip using ffmpeg
            try:
                result = subprocess.run([
                    'ffmpeg', '-y',
                    '-i', source_video_path,
                    '-ss', str(start_time),
                    '-t', str(clip_duration),
                    '-c', 'copy',  # Copy codec for speed
                    '-avoid_negative_ts', '1',
                    str(clip_output)
                ], capture_output=True, text=True, timeout=60)
                
                if result.returncode != 0:
                    print(f"    Warning: ffmpeg failed, trying with re-encode")
                    result = subprocess.run([
                        'ffmpeg', '-y',
                        '-i', source_video_path,
                        '-ss', str(start_time),
                        '-t', str(clip_duration),
                        '-c:v', 'libx264', '-c:a', 'aac',
                        '-preset', 'fast',
                        str(clip_output)
                    ], capture_output=True, text=True, timeout=120)
                
                if result.returncode == 0 and clip_output.exists():
                    log(f"    ✓ Extracted successfully", explanation="Clip saved to project directory")
                else:
                    log(f"    ✗ Failed: {result.stderr[:200]}", explanation="ffmpeg error")
                    extracted_clips.pop()
            except Exception as e:
                log(f"    ✗ Error: {e}", explanation="Exception during extraction")
                if clip_output in extracted_clips:
                    extracted_clips.pop()
        
        if not extracted_clips:
            log("ERROR: No clips could be extracted")
            return None
        
        # Step 2: Concatenate all clips with transitions and color grading
        # Add crossfade transitions between clips and apply cinematic color grading
        log(f"=== Step 2: Combining {len(extracted_clips)} clips with transitions & color grading ===", explanation="Adding professional transitions and cinematic look")
        combined_clips_path = project_dir / f"combined_{actor.actor_id}.mp4"
        
        # Use filter_complex for professional transitions and color grading
        # Crossfade transition + cinematic color grading (lifted shadows, slight teal/orange)
        filter_parts = []
        for i, clip_path in enumerate(extracted_clips):
            filter_parts.append(f"[{i}:v]")
        filter_parts.append(f"concat=n={len(extracted_clips)}:v=1:a=0[v]")
        
        # Build the full filter chain: color grading + transitions
        color_grade = " Curves=preset=cinematic:shadow_highlight=0.15:contrast=1.1, eq=brightness=0.02:contrast=1.05:saturation=1.1, colortemperature=temperature=6500, gblur=sigma=0.3"
        
        # Create a complex filter for crossfades between clips
        transition_filter = ""
        if len(extracted_clips) > 1:
            # Build crossfade chain
            for i in range(len(extracted_clips) - 1):
                transition_filter += f"[{i}]xfade=transition=fade:duration=0.5:offset={i*3 - 0.25},"
            transition_filter = transition_filter.rstrip(',')
        
        concat_list = project_dir / f"concat_{actor.actor_id}.txt"
        with open(concat_list, 'w') as f:
            for clip_path in extracted_clips:
                f.write(f"file '{clip_path}'\n")
        
        # Concatenate clips with proper scaling and higher quality encoding
        log(f"  Combining {len(extracted_clips)} clips...")
        try:
            # Scale all clips to 1080p and apply light color grading
            result = subprocess.run([
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_list),
                '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,eq=gamma=1.05:brightness=0.01:contrast=1.02:saturation=1.1',
                '-c:v', 'libx264', '-preset', 'slow', '-crf', '16',
                '-c:a', 'aac', '-b:a', '192k',
                str(combined_clips_path)
            ], capture_output=True, text=True, timeout=180)
            
            if result.returncode == 0:
                log(f"  ✓ Combined with color grading (1080p, CRF 16)")
            else:
                log(f"  ✗ {result.stderr[:100]}")
                # Fallback - just concat
                subprocess.run([
                    'ffmpeg', '-y',
                    '-f', 'concat', '-safe', '0', '-i', str(concat_list),
                    '-c', 'copy', str(combined_clips_path)
                ], capture_output=True, timeout=120)
        except Exception as e:
            log(f"  ✗ Error: {e}")
        
        # Step 3: Generate intro and outro with ffmpeg text overlays
        # TikTok-style text overlays are more reliable than LTX text generation
        log(f"=== Step 3: Generating intro (4s) and outro (3s) with ffmpeg text overlays ===", 
            explanation="ffmpeg drawtext filter creates clean, professional text overlays")

        # Use title image if available, otherwise fallback to headshot
        intro_image = title_image if title_image else actor.headshot_url

        # INTRO: "<actor> deep cut. Ever see <title>?"
        title_for_display = title_text.title()  # "The Crane" for display
        
        log(f"  Generating INTRO (4s): '{actor.actor_name} deep cut. Ever see {title_for_display}?'", 
            explanation="Hook with TikTok-style text overlay - grabs attention")
        intro_path = project_dir / f"bumper_intro_{actor.actor_id}.mp4"
        
        try:
            # Create intro with ffmpeg: solid background + text overlay
            # TikTok style: bold white text on dark gradient background
            subprocess.run([
                'ffmpeg', '-y',
                '-f', 'lavfi', '-i', 'color=c=black:s=1080x1920:d=4',
                '-vf', f'''
                    drawtext=
                        text='{actor.actor_name} Deep Cut':
                        fontsize=72:
                        fontcolor=white:
                        fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:
                        x=(w-text_w)/2:
                        y=(h-text_h)/2-50:
                        enable='between(t,0,4)',
                    drawtext=
                        text='Ever seen {title_for_display}?':
                        fontsize=48:
                        fontcolor=white:
                        fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:
                        x=(w-text_w)/2:
                        y=(h-text_h)/2+50:
                        enable='between(t,0,4)'
                ''',
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-pix_fmt', 'yuv420p',
                str(intro_path)
            ], capture_output=True, timeout=60)
            log(f"  ✓ Intro (4s) generated", explanation="TikTok-style title card with bold text")
        except Exception as e:
            log(f"  ✗ Intro failed: {e}")
            intro_path = None

        # OUTRO: "Watch <title> exclusively on streamplus"
        log(f"  Generating OUTRO (3s): 'Watch {title_for_display} exclusively on streamplus'", 
            explanation="CTA with TikTok-style text overlay - drives viewers to platform")
        outro_path = project_dir / f"bumper_outro_{actor.actor_id}.mp4"
        
        try:
            # Create outro with ffmpeg: solid background + text overlay
            subprocess.run([
                'ffmpeg', '-y',
                '-f', 'lavfi', '-i', 'color=c=black:s=1080x1920:d=3',
                '-vf', f'''
                    drawtext=
                        text='Watch {title_for_display}':
                        fontsize=56:
                        fontcolor=white:
                        fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:
                        x=(w-text_w)/2:
                        y=(h-text_h)/2-30:
                        enable='between(t,0,3)',
                    drawtext=
                        text='exclusively on':
                        fontsize=36:
                        fontcolor=#888888:
                        fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:
                        x=(w-text_w)/2:
                        y=(h-text_h)/2+30:
                        enable='between(t,0,3)',
                    drawtext=
                        text='streamplus':
                        fontsize=64:
                        fontcolor=#E50914:
                        fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:
                        x=(w-text_w)/2:
                        y=(h-text_h)/2+80:
                        enable='between(t,0,3)'
                ''',
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-pix_fmt', 'yuv420p',
                str(outro_path)
            ], capture_output=True, timeout=60)
            log(f"  ✓ Outro (3s) generated", explanation="TikTok-style end card with platform branding")
        except Exception as e:
            log(f"  ✗ Outro failed: {e}")
            outro_path = None
        
        # Step 4: Final concatenation - [intro 4s] + [clips 12s] + [outro 3s] = 16s
        # Stitch together all three parts: intro + archival clips + outro
        log(f"=== Step 4: Creating final 16s spot ===", explanation="Final ffmpeg concat: [4s intro] + [12s clips] + [3s outro]")
        final_output = project_dir / f"spot_{actor.actor_id}.mp4"
        
        final_concat_list = project_dir / f"final_concat_{actor.actor_id}.txt"
        with open(final_concat_list, 'w') as f:
            if intro_path and intro_path.exists():
                f.write(f"file '{intro_path}'\n")
            f.write(f"file '{combined_clips_path}'\n")
            if outro_path and outro_path.exists():
                f.write(f"file '{outro_path}'\n")
        
        try:
            result = subprocess.run([
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(final_concat_list),
                '-c:v', 'libx264', '-c:a', 'aac',
                '-preset', 'fast',
                '-movflags', '+faststart',
                str(final_output)
            ], capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0 and final_output.exists():
                log(f"  ✓ Final spot created: {final_output.name}", explanation=f"Full 16s promotional spot ready")
                file_size_mb = final_output.stat().st_size / (1024 * 1024)
                log(f"    File size: {file_size_mb:.1f} MB", explanation="Final deliverable")
            else:
                log(f"  ✗ Failed: {result.stderr[:200]}")
                import shutil
                shutil.copy(combined_clips_path, final_output)
                log(f"  Using combined clips as fallback")
        except Exception as e:
            log(f"  ✗ Error: {e}")
            import shutil
            shutil.copy(combined_clips_path, final_output)
        
        # Update actor spot
        actor.generated_video = str(final_output)
        actor.voiceover_script = prompt or f"{actor.actor_name} deep cut. Ever see {title_text}? Watch {title_text} exclusively on streamplus."
        
        # Save updated project
        self._save_project(project)
        
        log(f"=== COMPLETE: 16s promotional spot for {actor.actor_name} ===", explanation=f"Structure: 4s intro + {len(extracted_clips)*4}s archival clips + 3s outro")
        log(f"Log saved to: {log_file}")
        return str(final_output)
    
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
            birth_info = f"born in {actor.birth_year}, "
        
        prompt = (
            f"Cinematic promotional video featuring {actor.actor_name}, "
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
    parser = argparse.ArgumentParser(
        description="Tycho - Create actor-focused promotional videos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create project with harness and platform
  python tycho.py video.mp4 --imdb-id tt0058331 --harness nostalgia --platform tiktok
  
  # Check status of existing project
  python tycho.py --status outputs/tycho_tt0058331_20260329_123456
  
  # Output project as JSON
  python tycho.py --json outputs/tycho_tt0058331_20260329_123456
        """
    )
    parser.add_argument("video", type=str, nargs="?", help="Path to source video")
    parser.add_argument("--imdb-id", type=str, help="IMDb title ID (e.g., tt0058331)")
    parser.add_argument("--actor", type=str, action="append", help="Specific actor(s) to focus on")
    parser.add_argument("--max-actors", type=int, default=10, help="Maximum actors to process")
    parser.add_argument("--generate", type=str, help="Generate spot for specific actor(s), comma-separated")
    parser.add_argument("--duration", type=int, default=10, help="Generated video duration (seconds)")
    parser.add_argument("--output", type=str, default="outputs", help="Output directory")
    parser.add_argument("--index-name", type=str, help="Custom 12Labs index name")
    parser.add_argument("--use-tmdb", action="store_true", help="Fetch additional headshots from TMDB for better search")
    parser.add_argument("--tmdb-images", type=int, default=2, help="Number of TMDB images to fetch per actor (default: 2)")
    parser.add_argument("--harness", type=str, help="Harness/template name (e.g., 'nostalgia', 'hype')")
    parser.add_argument("--platform", type=str, help="Target platform (e.g., 'tiktok', 'youtube', 'instagram')")
    parser.add_argument("--status", type=str, metavar="PROJECT_DIR", help="Check status of existing project")
    parser.add_argument("--json", action="store_true", help="Output project data as JSON (use with --status)")
    parser.add_argument("--list", action="store_true", help="List all projects in output directory")

    args = parser.parse_args()

    # Status check mode
    if args.status:
        project_path = Path(args.status) / "project.json"
        if not project_path.exists():
            # Try direct path to json file
            project_path = Path(args.status)
            if not project_path.exists():
                print(f"Error: Project not found: {args.status}", file=sys.stderr)
                sys.exit(1)
        
        with open(project_path) as f:
            project_data = json.load(f)
        
        if args.json:
            # Output raw JSON
            print(json.dumps(project_data, indent=2))
        else:
            # Human-readable status
            print(f"\n{'='*60}")
            print(f"PROJECT STATUS: {project_data.get('project_id', 'Unknown')}")
            print(f"{'='*60}")
            print(f"IMDb ID:       {project_data.get('imdb_title_id', 'N/A')}")
            print(f"Status:        {project_data.get('status', 'unknown')}")
            print(f"Created:       {project_data.get('created_at', 'N/A')}")
            print(f"Harness:       {project_data.get('harness_name', 'None (default)')}")
            print(f"Platform:      {project_data.get('platform', 'None (default)')}")
            print(f"\nActors ({len(project_data.get('actors', []))}):")
            for actor in project_data.get('actors', []):
                status = "✓ Generated" if actor.get('generated_video') else ("✗ Not found" if not actor.get('clips') else "○ Found, not generated")
                clips = f" ({len(actor.get('clips', []))} clips)" if actor.get('clips') else ""
                print(f"  - {actor['actor_name']}{clips}: {status}")
            
            # Check if processing is complete
            actors = project_data.get('actors', [])
            generated = sum(1 for a in actors if a.get('generated_video'))
            total = len(actors)
            print(f"\nProgress: {generated}/{total} spots generated")
            
            if project_data.get('status') == 'processing':
                print("\n⚠️  Project is still processing...")
            elif generated == total and total > 0:
                print("\n✓ Project complete!")
            else:
                print(f"\n  Ready to generate {total - generated} more spots")
            print(f"{'='*60}\n")
        sys.exit(0)

    # List projects mode
    if args.list:
        output_dir = Path(args.output)
        if not output_dir.exists():
            print(f"No output directory: {output_dir}")
            sys.exit(0)
        
        projects = []
        for proj_dir in output_dir.iterdir():
            if proj_dir.is_dir():
                proj_file = proj_dir / "project.json"
                if proj_file.exists():
                    with open(proj_file) as f:
                        proj_data = json.load(f)
                        projects.append(proj_data)
        
        if not projects:
            print("No projects found")
            sys.exit(0)
        
        projects.sort(key=lambda p: p.get('created_at', ''), reverse=True)
        
        if args.json:
            print(json.dumps(projects, indent=2))
        else:
            print(f"\n{'='*60}")
            print("PROJECTS")
            print(f"{'='*60}")
            for proj in projects:
                actors = proj.get('actors', [])
                generated = sum(1 for a in actors if a.get('generated_video'))
                harness = proj.get('harness_name', 'default')
                platform = proj.get('platform', 'default')
                print(f"\n{proj.get('project_id', 'Unknown')}")
                print(f"  IMDb: {proj.get('imdb_title_id', 'N/A')} | Status: {proj.get('status', 'unknown')}")
                print(f"  Harness: {harness} | Platform: {platform}")
                print(f"  Progress: {generated}/{len(actors)} spots generated")
            print(f"{'='*60}\n")
        sys.exit(0)

    # Validate required arguments for create mode
    if not args.video or not args.imdb_id:
        parser.error("--imdb-id and VIDEO are required for creating a project")

    # Initialize orchestrator
    orchestrator = TychoOrchestrator(output_dir=args.output)

    # Create project
    project = orchestrator.create_project(
        video_path=args.video,
        imdb_title_id=args.imdb_id,
        actor_names=args.actor,
        max_actors=args.max_actors,
        index_name=args.index_name,
        use_tmdb=args.use_tmdb,
        max_tmdb_images=args.tmdb_images,
        harness_name=args.harness,
        platform=args.platform,
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
