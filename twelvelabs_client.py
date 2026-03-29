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
        """
        if not os.path.exists(headshot_path):
            raise FileNotFoundError(f"Headshot not found: {headshot_path}")

        print(f"\n[12Labs] {'='*60}")
        print(f"[12Labs] Searching for {actor_name} in video...")
        print(f"[12Labs] Headshot: {headshot_path}")

        try:
            with open(headshot_path, "rb") as f:
                search_results = self.client.search.query(
                    index_id=self.index_id,
                    search_options=["visual"],
                    query_media_type="image",
                    query_media_file=f,
                )

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
        
        # Search with headshot if provided
        if args.headshot and video_id:
            clips = client.search_actor_in_video(
                headshot_path=args.headshot,
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
