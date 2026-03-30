#!/usr/bin/env python3
"""
twelvelabs_client.py - 12Labs API integration for Tycho

Handles:
- Creating video indexes
- Uploading videos for indexing
- Searching for actors in videos using headshot images
"""

import os
import time
from dataclasses import dataclass
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

try:
    from twelvelabs import TwelveLabs
except ImportError:
    print("Installing twelvelabs package...")
    os.system("pip install twelvelabs")
    from twelvelabs import TwelveLabs


@dataclass
class ClipMatch:
    """Represents a clip where an actor was found."""
    video_id: str
    start: float  # seconds
    end: float    # seconds
    score: float
    actor_name: str
    actor_id: str


class TwelveLabsClient:
    """Wrapper around 12Labs API for Tycho workflow."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("TWELVE_LABS_API_KEY")
        if not self.api_key:
            raise ValueError("TWELVE_LABS_API_KEY not found in .env or environment")
        
        self.client = TwelveLabs(api_key=self.api_key)
        self._index_id = None
        self._video_id = None
        self._checked_for_video = False  # Cache flag
    
    def create_index(self, index_name: str = "tycho_index") -> str:
        """
        Create a new video index for storing and searching videos.
        
        Args:
            index_name: Name for the index
        
        Returns:
            index_id: Unique identifier for the index
        """
        # First check if index already exists
        try:
            existing_indexes = list(self.client.indexes.list())
            for idx in existing_indexes:
                if getattr(idx, 'index_name', None) == index_name:
                    print(f"[12Labs] Using existing index: {idx.id}")
                    self._index_id = idx.id
                    return idx.id
        except Exception as e:
            print(f"[12Labs] Error checking existing indexes: {e}")
        
        print(f"[12Labs] Creating index: {index_name}")
        
        index = self.client.indexes.create(
            index_name=index_name,
            models=[{"model_name": "marengo3.0", "model_options": ["visual", "audio"]}],
        )
        
        self._index_id = index.id
        print(f"[12Labs] Index created: id={index.id}")
        return index.id
    
    def set_index(self, index_id: str):
        """Use an existing index."""
        self._index_id = index_id
    
    @property
    def index_id(self) -> str:
        if not self._index_id:
            # Try to find or create default index
            try:
                indexes = list(self.client.indexes.list())
                if indexes:
                    self._index_id = indexes[0].id
                    print(f"[12Labs] Using existing index: {self._index_id}")
                else:
                    self._index_id = self.create_index()
            except Exception as e:
                print(f"[12Labs] Error listing indexes: {e}")
                self._index_id = self.create_index()
        return self._index_id
    
    def upload_video(self, video_path: str, wait_for_ready: bool = True) -> str:
        """
        Upload a video file to the index for processing.
        Skips upload if we already have a video_id cached.

        Args:
            video_path: Path to the video file
            wait_for_ready: If True, wait for indexing to complete

        Returns:
            video_id: Unique identifier for the uploaded video
        """
        # Return cached video_id if we have one
        if self._video_id:
            print(f"[12Labs] Using cached video_id: {self._video_id}")
            return self._video_id
        
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")
        
        print(f"[12Labs] Uploading video: {video_path}")

        # Step 1: Create asset from file
        asset = self.client.assets.create(
            method="direct",
            file=open(video_path, "rb"),
        )
        print(f"[12Labs] Asset created: id={asset.id}")

        # Step 2: Index the asset
        indexed_asset = self.client.indexes.indexed_assets.create(
            index_id=self.index_id,
            asset_id=asset.id,
        )

        if wait_for_ready:
            print("[12Labs] Waiting for indexing to complete...")
            while True:
                indexed_asset = self.client.indexes.indexed_assets.retrieve(
                    index_id=self.index_id,
                    indexed_asset_id=indexed_asset.id,
                )
                print(f"  Status: {indexed_asset.status}")
                
                if indexed_asset.status == "ready":
                    print(f"[12Labs] Video indexed: video_id={indexed_asset.id}")
                    self._video_id = indexed_asset.id
                    break
                elif indexed_asset.status == "failed":
                    raise RuntimeError("Indexing failed")
                
                time.sleep(5)
        else:
            self._video_id = indexed_asset.id
        
        return self._video_id
    
    def search_actor_in_video(
        self,
        headshot_path: str,
        actor_name: str,
        actor_id: str,
        max_results: int = 20
    ) -> List[ClipMatch]:
        """
        Search for an actor in indexed videos using their headshot.
        
        Args:
            headshot_path: Can be a local file path OR a URL to an image
        """
        return self.search_actor_with_images(
            headshot_paths=[headshot_path],
            actor_name=actor_name,
            actor_id=actor_id,
            max_results=max_results
        )
    
    def search_actor_with_images(
        self,
        headshot_paths: List[str],
        actor_name: str,
        actor_id: str,
        max_results: int = 20
    ) -> List[ClipMatch]:
        """
        Search for an actor in indexed videos using multiple headshots.
        
        Args:
            headshot_paths: List of local file paths OR URLs to images
            actor_name: Actor name for logging
            actor_id: Actor ID for result
            max_results: Maximum number of results
            
        Returns:
            List of ClipMatch objects with timestamps where actor appears
        """
        print(f"\n[12Labs] {'='*60}")
        print(f"[12Labs] Searching for {actor_name} in video...")
        print(f"[12Labs] Using {len(headshot_paths)} image(s)")
        
        for i, path in enumerate(headshot_paths, 1):
            print(f"  [{i}] {path}")

        try:
            # Separate URLs from local files
            urls = []
            local_files = []
            
            for path in headshot_paths:
                if path.startswith('http://') or path.startswith('https://'):
                    urls.append(path)
                else:
                    local_files.append(path)
            
            # Validate local files exist
            for path in local_files:
                if not os.path.exists(path):
                    raise FileNotFoundError(f"Headshot not found: {path}")
            
            # Build search query based on what we have
            search_kwargs = {
                "index_id": self.index_id,
                "search_options": ["visual"],
                "query_media_type": "image",
            }
            
            # Add URLs or files to search
            if len(urls) == 1 and not local_files:
                # Single URL - use query_media_url
                print(f"[12Labs] Using single URL directly")
                search_kwargs["query_media_url"] = urls[0]
            elif len(urls) > 1 and not local_files:
                # Multiple URLs - use query_media_urls (Marengo 3.0 feature)
                print(f"[12Labs] Using {len(urls)} URLs for multi-image search")
                search_kwargs["query_media_urls"] = urls
            elif len(local_files) == 1 and not urls:
                # Single local file
                file_size_mb = os.path.getsize(local_files[0]) / (1024 * 1024)
                print(f"[12Labs] Headshot file size: {file_size_mb:.1f} MB")
                if file_size_mb > 5.2:
                    print(f"[12Labs] WARNING: File too large for 12Labs (max 5.2MB), trying anyway...")
                
                search_kwargs["query_media_file"] = open(local_files[0], "rb")
            elif len(local_files) > 1 and not urls:
                # Multiple local files
                print(f"[12Labs] Using {len(local_files)} local files for multi-image search")
                search_kwargs["query_media_files"] = [
                    open(f, "rb") for f in local_files
                ]
            else:
                # Mixed URLs and files - not supported by 12Labs, convert files to URLs or just use URLs
                print(f"[12Labs] Mixed URLs and files - using URLs only ({len(urls)} URLs)")
                if len(urls) == 1:
                    search_kwargs["query_media_url"] = urls[0]
                else:
                    search_kwargs["query_media_urls"] = urls
            
            # Execute search
            search_results = self.client.search.query(**search_kwargs)
            
            # Close file handles if we opened them
            if "query_media_file" in search_kwargs and hasattr(search_kwargs["query_media_file"], 'close'):
                search_kwargs["query_media_file"].close()
            if "query_media_files" in search_kwargs:
                for f in search_kwargs["query_media_files"]:
                    if hasattr(f, 'close'):
                        f.close()

            # LOG EVERY SINGLE CLIP FROM API
            print(f"[12Labs] RAW API RESPONSE - All clips:")
            raw_clips = []
            for i, clip in enumerate(search_results):
                start = getattr(clip, 'start', None)
                end = getattr(clip, 'end', None)
                video_id = getattr(clip, 'video_id', None)
                rank = getattr(clip, 'rank', None)
                raw_clips.append({'i': i, 'start': start, 'end': end, 'video_id': video_id, 'rank': rank})
                print(f"[12Labs]   [{i:2d}] start={start:7.2f}  end={end:7.2f}  video={video_id[:12] if video_id else 'N/A':12}  rank={rank}")
            
            print(f"[12Labs] Total from API: {len(raw_clips)} clips")
            print(f"[12Labs] {'='*60}\n")

            # Process into ClipMatch
            clips = []
            for i, clip in enumerate(search_results):
                if i >= max_results:
                    break

                confidence = getattr(clip, 'rank', getattr(clip, 'score', 0))
                if hasattr(clip, 'rank') and clip.rank:
                    confidence = 1.0 / clip.rank

                clips.append(ClipMatch(
                    video_id=clip.video_id,
                    start=clip.start,
                    end=clip.end,
                    score=confidence,
                    actor_name=actor_name,
                    actor_id=actor_id,
                ))
        except Exception as e:
            print(f"[12Labs] Search failed: {e}")
            import traceback
            traceback.print_exc()
            clips = []

        print(f"[12Labs] Processed into {len(clips)} ClipMatch objects")
        return clips
    
    def list_videos(self) -> List[dict]:
        """List all videos in the index."""
        videos = self.client.video.list(index_id=self.index_id)
        return [
            {"video_id": v.id, "filename": v.filename, "duration": v.duration}
            for v in videos.data
        ]
    
    def delete_index(self, index_id: Optional[str] = None):
        """Delete an index and all its videos."""
        idx = index_id or self._index_id
        if idx:
            print(f"[12Labs] Deleting index: {idx}")
            self.client.indexes.delete(idx)
            self._index_id = None


def main():
    """Test the 12Labs client."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test 12Labs integration")
    parser.add_argument("--video", type=str, help="Video file to upload")
    parser.add_argument("--headshot", type=str, help="Headshot image to search")
    parser.add_argument("--headshots", type=str, nargs="+", help="Multiple headshot images for multi-image search")
    parser.add_argument("--actor", type=str, default="Test Actor", help="Actor name")
    parser.add_argument("--cleanup", action="store_true", help="Delete index after test")
    
    args = parser.parse_args()
    
    client = TwelveLabsClient()
    
    try:
        # Upload video if provided
        video_id = None
        if args.video:
            video_id = client.upload_video(args.video)
            print(f"\nUploaded video: {video_id}")
        
        # Search with headshot(s) if provided
        if video_id and (args.headshot or args.headshots):
            # Determine which images to use
            if args.headshots:
                headshot_paths = args.headshots
            else:
                headshot_paths = [args.headshot]
            
            # Use multi-image search if more than one image
            if len(headshot_paths) > 1:
                print(f"\nUsing multi-image search with {len(headshot_paths)} images...")
                clips = client.search_actor_with_images(
                    headshot_paths=headshot_paths,
                    actor_name=args.actor,
                    actor_id="nm0000000",
                )
            else:
                clips = client.search_actor_in_video(
                    headshot_path=headshot_paths[0],
                    actor_name=args.actor,
                    actor_id="nm0000000",
                )
            
            print(f"\nFound {len(clips)} clips:")
            for clip in clips:
                print(f"  {clip.start:.1f}s - {clip.end:.1f}s (score: {clip.score:.2f})")
    
    finally:
        if args.cleanup:
            client.delete_index()


if __name__ == "__main__":
    main()
