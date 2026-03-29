#!/usr/bin/env python3
"""
batch_process.py - Batch processing CLI for Tycho video generation

Processes multiple titles from JSON input and generates promotional spots
for each talent found in the video.

Usage:
    python batch_process.py --input jobs.json --output results.json
    python batch_process.py --input jobs.json --output results.json --max-actors 5
    python batch_process.py --input jobs.json --output results.json --use-tmdb --tmdb-images 2

Input JSON Format:
    [
        {
            "imdb": "tt0310917",
            "url": "https://example.com/video1.mp4"
        },
        {
            "imdb": "tt0058331",
            "url": "https://example.com/video2.mp4"
        }
    ]

Output JSON Format:
    {
        "processed_at": "2026-03-29T21:30:00",
        "total_jobs": 2,
        "successful": 1,
        "failed": 1,
        "jobs": [
            {
                "imdb": "tt0310917",
                "url": "https://example.com/video1.mp4",
                "status": "completed",
                "title": "The Crane",
                "talent_count": 3,
                "talent": [
                    {
                        "imdb_id": "nm0000179",
                        "name": "Jude Law",
                        "clips_found": 5,
                        "spot_url": "/path/to/spot.mp4",
                        "status": "spot_generated"
                    }
                ],
                "spots": [
                    {
                        "actor_name": "Jude Law",
                        "spot_url": "/path/to/spot.mp4",
                        "duration": 15,
                        "clips_used": 3
                    }
                ],
                "errors": []
            }
        ]
    }

Status Values:
    - pending: Job is queued
    - processing: Currently processing
    - completed: Successfully completed
    - failed: Processing failed
    - partial: Some talent processed, some failed

Talent Status Values:
    - pending: Not yet processed
    - searched: 12Labs search completed
    - clips_found: Actor found in video
    - no_clips: Actor not found
    - spot_generated: Promotional spot created
    - spot_failed: Spot generation failed
"""

import argparse
import json
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_db, init_database
from talent_db import get_or_create_talent_from_imdb, sync_talent_images, get_talent_with_images
from get_actors import fetch_cast_with_images, get_title_metadata
from twelvelabs_client import TwelveLabsClient
from tycho import TychoOrchestrator, TychoProject


@dataclass
class BatchJob:
    """Represents a single batch job."""
    imdb: str
    url: str
    status: str = "pending"
    title: Optional[str] = None
    talent_count: int = 0
    talent: List[Dict] = None
    spots: List[Dict] = None
    errors: List[str] = None
    
    def __post_init__(self):
        if self.talent is None:
            self.talent = []
        if self.spots is None:
            self.spots = []
        if self.errors is None:
            self.errors = []


@dataclass
class BatchResult:
    """Represents the complete batch processing result."""
    processed_at: str
    total_jobs: int
    successful: int
    failed: int
    jobs: List[Dict]


class BatchProcessor:
    """Processes batch jobs for video generation."""
    
    def __init__(
        self,
        max_actors: int = 10,
        use_tmdb: bool = False,
        tmdb_images: int = 2,
        output_dir: str = "outputs",
        generate_spots: bool = True,
        spot_duration: int = 15
    ):
        self.max_actors = max_actors
        self.use_tmdb = use_tmdb
        self.tmdb_images = tmdb_images
        self.output_dir = Path(output_dir)
        self.generate_spots = generate_spots
        self.spot_duration = spot_duration
        
        # Initialize clients
        self.orchestrator = TychoOrchestrator(output_dir=output_dir)
        self.twelvelabs = TwelveLabsClient()
        
        # Initialize database
        init_database()
    
    def process_job(self, job: BatchJob) -> BatchJob:
        """Process a single batch job."""
        print(f"\n{'='*60}")
        print(f"Processing: {job.imdb}")
        print(f"URL: {job.url}")
        print(f"{'='*60}\n")
        
        job.status = "processing"
        
        try:
            # Step 1: Get cast and metadata
            print(f"[1/4] Fetching cast for {job.imdb}...")
            cast = fetch_cast_with_images(
                job.imdb,
                limit=self.max_actors,
                use_tmdb=self.use_tmdb,
                max_tmdb_images=self.tmdb_images
            )
            
            title_info = get_title_metadata(job.imdb)
            job.title = title_info.get('title', 'Unknown')
            job.talent_count = len(cast)
            
            print(f"      Title: {job.title}")
            print(f"      Found {len(cast)} cast members\n")
            
            # Step 2: Ensure talent in database with mise-en-scene
            print(f"[2/4] Syncing talent to database...")
            for actor_data in cast:
                if not actor_data.get('name_id'):
                    continue
                
                talent = get_or_create_talent_from_imdb(
                    imdb_id=actor_data['name_id'],
                    name=actor_data['name'],
                    tmdb_id=None,  # Will be fetched if needed
                    birth_year=actor_data.get('birth_date', {}).get('year') if isinstance(actor_data.get('birth_date'), dict) else None,
                    category=actor_data.get('category', 'actor'),
                    primary_professions=actor_data.get('primary_professions', []),
                    auto_generate_mise_en_scene=True
                )
                
                # Sync images
                imdb_images = actor_data.get('images', [])
                if actor_data.get('primary_image'):
                    imdb_images.insert(0, actor_data['primary_image'])
                
                sync_talent_images(talent.id, imdb_images=imdb_images)
                
                # Add to job talent list
                job.talent.append({
                    "imdb_id": actor_data['name_id'],
                    "name": actor_data['name'],
                    "status": "pending",
                    "clips_found": 0,
                    "spot_url": None
                })
            
            print(f"      Synced {len(job.talent)} talent records\n")
            
            # Step 3: Process each talent
            print(f"[3/4] Searching for talent in video...")
            
            # Download video if URL is remote
            video_path = job.url
            if job.url.startswith('http://') or job.url.startswith('https://'):
                video_path = self._download_video(job.url, job.imdb)
            
            # Create project
            project = self.orchestrator.create_project(
                video_path=video_path,
                imdb_title_id=job.imdb,
                actor_names=None,
                use_tmdb=self.use_tmdb,
                max_tmdb_images=self.tmdb_images
            )
            
            # Initialize performance tracking
            from cli.performance import get_tracker
            performance_tracker = get_tracker()
            
            # Process each actor
            for talent_info in job.talent:
                try:
                    self._process_talent(talent_info, project, job, performance_tracker)
                except Exception as e:
                    talent_info['status'] = 'error'
                    talent_info['error'] = str(e)
                    job.errors.append(f"{talent_info['name']}: {str(e)}")
            
            # Step 4: Finalize
            print(f"\n[4/4] Finalizing...")
            job.status = self._determine_status(job)
            
            print(f"      Status: {job.status}")
            print(f"      Spots generated: {len([s for s in job.spots if s.get('spot_url')])}")
            
        except Exception as e:
            job.status = "failed"
            job.errors.append(str(e))
            print(f"\n[ERROR] Job failed: {str(e)}")
        
        return job
    
    def _process_talent(self, talent_info: Dict, project: TychoProject, job: BatchJob, performance_tracker):
        """Process a single talent within a job."""
        import uuid
        from cli.performance import register_spot
        
        actor_name = talent_info['name']
        print(f"\n  Processing {actor_name}...")
        
        talent_info['status'] = 'searching'
        
        # Find actor in project
        actor = next((a for a in project.actors if a.actor_name == actor_name), None)
        if not actor:
            talent_info['status'] = 'no_clips'
            print(f"    No clips found")
            return
        
        talent_info['clips_found'] = len(actor.clips)
        talent_info['status'] = 'clips_found'
        
        print(f"    Found {len(actor.clips)} clips")
        
        # Generate spot if requested
        if self.generate_spots and actor.clips:
            try:
                print(f"    Generating spot...")
                spot_path = self.orchestrator.generate_spot(
                    project=project,
                    actor_name=actor_name,
                    duration=self.spot_duration
                )
                
                if spot_path:
                    # Generate unique harness ID
                    harness_id = f"harness_{job.imdb}_{talent_info['imdb_id']}_{uuid.uuid4().hex[:8]}"
                    
                    # Register spot with performance tracker
                    register_spot(
                        harness_id=harness_id,
                        imdb_id=job.imdb,
                        talent_id=talent_info['imdb_id'],
                        actor_name=actor_name,
                        spot_url=str(spot_path),
                        platform='unknown',  # Will be set when uploaded
                        harness_config={
                            'title': job.title,
                            'clips_found': len(actor.clips),
                            'duration': self.spot_duration
                        },
                        video_path=project.source_video
                    )
                    
                    talent_info['spot_url'] = str(spot_path)
                    talent_info['harness_id'] = harness_id
                    talent_info['status'] = 'spot_generated'
                    
                    job.spots.append({
                        'actor_name': actor_name,
                        'spot_url': str(spot_path),
                        'harness_id': harness_id,
                        'duration': self.spot_duration,
                        'clips_used': min(len(actor.clips), 3)
                    })
                    
                    print(f"    ✓ Spot generated: {spot_path}")
                    print(f"    ✓ Harness ID: {harness_id}")
                else:
                    talent_info['status'] = 'spot_failed'
                    print(f"    ✗ Spot generation failed")
                    
            except Exception as e:
                talent_info['status'] = 'spot_failed'
                talent_info['error'] = str(e)
                print(f"    ✗ Error: {str(e)}")
    
    def _determine_status(self, job: BatchJob) -> str:
        """Determine final job status based on results."""
        if not job.talent:
            return "failed"
        
        statuses = [t['status'] for t in job.talent]
        
        if all(s == 'spot_generated' for s in statuses):
            return "completed"
        elif any(s == 'spot_generated' for s in statuses):
            return "partial"
        elif any('error' in s for s in statuses):
            return "partial"
        else:
            return "failed"
    
    def _download_video(self, url: str, imdb_id: str) -> str:
        """Download video from URL to local path."""
        import requests
        
        print(f"    Downloading video from {url}...")
        
        # Create download directory
        download_dir = self.output_dir / "downloads"
        download_dir.mkdir(parents=True, exist_ok=True)
        
        # Download file
        local_path = download_dir / f"{imdb_id}.mp4"
        
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()
        
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"    Downloaded to {local_path}")
        return str(local_path)
    
    def process_batch(self, jobs: List[BatchJob]) -> BatchResult:
        """Process all jobs in batch."""
        print(f"\n{'='*60}")
        print(f"BATCH PROCESSING")
        print(f"Total jobs: {len(jobs)}")
        print(f"{'='*60}\n")
        
        successful = 0
        failed = 0
        
        for i, job in enumerate(jobs, 1):
            print(f"\n[Job {i}/{len(jobs)}]")
            processed_job = self.process_job(job)
            
            if processed_job.status in ["completed", "partial"]:
                successful += 1
            else:
                failed += 1
        
        result = BatchResult(
            processed_at=datetime.now().isoformat(),
            total_jobs=len(jobs),
            successful=successful,
            failed=failed,
            jobs=[asdict(job) for job in jobs]
        )
        
        return result


def load_jobs(input_path: str) -> List[BatchJob]:
    """Load jobs from JSON file."""
    with open(input_path, 'r') as f:
        data = json.load(f)
    
    jobs = []
    for item in data:
        if 'imdb' in item and 'url' in item:
            jobs.append(BatchJob(
                imdb=item['imdb'],
                url=item['url']
            ))
        else:
            print(f"[WARNING] Skipping invalid job: {item}")
    
    return jobs


def save_results(result: BatchResult, output_path: str):
    """Save results to JSON file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(asdict(result), f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Batch process videos for talent spot generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic usage
    python batch_process.py --input jobs.json --output results.json
    
    # Process with TMDB for additional headshots
    python batch_process.py --input jobs.json --output results.json --use-tmdb --tmdb-images 2
    
    # Limit actors per title
    python batch_process.py --input jobs.json --output results.json --max-actors 5
    
    # Search only (no spot generation)
    python batch_process.py --input jobs.json --output results.json --search-only
    
    # Custom output directory
    python batch_process.py --input jobs.json --output results.json --output-dir ./my_outputs

Input JSON Format:
    [
        {"imdb": "tt0310917", "url": "https://example.com/video1.mp4"},
        {"imdb": "tt0058331", "url": "/local/path/video2.mp4"}
    ]
        """
    )
    
    parser.add_argument(
        '--input', '-i',
        type=str,
        required=True,
        help='Input JSON file with jobs (array of {imdb, url})'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        required=True,
        help='Output JSON file for results'
    )
    
    parser.add_argument(
        '--max-actors',
        type=int,
        default=10,
        help='Maximum actors to process per title (default: 10)'
    )
    
    parser.add_argument(
        '--use-tmdb',
        action='store_true',
        help='Fetch additional headshots from TMDB for better search'
    )
    
    parser.add_argument(
        '--tmdb-images',
        type=int,
        default=2,
        help='Number of TMDB images to fetch per actor (default: 2)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='outputs',
        help='Output directory for generated spots (default: outputs)'
    )
    
    parser.add_argument(
        '--search-only',
        action='store_true',
        help='Only search for talent, do not generate spots'
    )
    
    parser.add_argument(
        '--spot-duration',
        type=int,
        default=15,
        help='Duration of generated spots in seconds (default: 15)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    # Load jobs
    try:
        jobs = load_jobs(args.input)
        print(f"Loaded {len(jobs)} jobs from {args.input}")
    except Exception as e:
        print(f"Error loading jobs: {e}")
        sys.exit(1)
    
    if not jobs:
        print("No valid jobs found in input file")
        sys.exit(1)
    
    # Process batch
    processor = BatchProcessor(
        max_actors=args.max_actors,
        use_tmdb=args.use_tmdb,
        tmdb_images=args.tmdb_images,
        output_dir=args.output_dir,
        generate_spots=not args.search_only,
        spot_duration=args.spot_duration
    )
    
    result = processor.process_batch(jobs)
    
    # Save results
    save_results(result, args.output)
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"BATCH PROCESSING COMPLETE")
    print(f"{'='*60}")
    print(f"Total jobs: {result.total_jobs}")
    print(f"Successful: {result.successful}")
    print(f"Failed: {result.failed}")
    print(f"{'='*60}")
    
    # Exit with error code if any failed
    if result.failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
