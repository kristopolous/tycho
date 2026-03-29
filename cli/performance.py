#!/usr/bin/env python3
"""
performance.py - Callback API for tracking spot/harness performance

This module provides callback endpoints and utilities for tracking
the performance of generated spots through the funnel convergence.

Usage:
    from cli.performance import record_spot_performance, get_spot_analytics
    
    # Record a view event
    record_spot_performance(
        harness_id="harness_tt0310917_001",
        event_type="view",
        metadata={"platform": "tiktok", "user_id": "abc123"}
    )

Events:
    - spot_generated: Spot was successfully created
    - upload_started: Upload to platform initiated
    - upload_completed: Upload finished successfully
    - view: Spot was viewed
    - like: User liked the spot
    - share: User shared the spot
    - comment: User commented on the spot
    - click: User clicked through to content
    - conversion: User took desired action (subscribe, purchase, etc.)
    - error: Error occurred during processing

API Endpoints (FastAPI):
    POST /api/v1/performance/event - Record performance event
    GET /api/v1/performance/{harness_id} - Get analytics for harness
    GET /api/v1/performance/convergence/{talent_id} - Get convergence metrics
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from contextlib import contextmanager

# Database path
DB_DIR = Path(__file__).parent.parent / ".cache"
DB_PATH = DB_DIR / "performance.db"


@dataclass
class PerformanceEvent:
    """Represents a single performance event."""
    id: int
    harness_id: str
    imdb_id: str
    talent_id: str
    event_type: str
    platform: Optional[str]
    metadata: Dict[str, Any]
    created_at: str


@dataclass
class SpotGeneration:
    """Represents a generated spot with its harness ID."""
    id: int
    harness_id: str
    imdb_id: str
    talent_id: str
    actor_name: str
    video_path: str
    spot_url: str
    platform: str
    harness_config: Dict[str, Any]
    generated_at: str


class PerformanceTracker:
    """Tracks spot performance through the funnel."""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self._init_db()
    
    def _init_db(self):
        """Initialize performance tracking database."""
        DB_DIR.mkdir(exist_ok=True)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Spot generations table - each spot gets a unique harness_id
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS spot_generations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    harness_id TEXT UNIQUE NOT NULL,
                    imdb_id TEXT NOT NULL,
                    talent_id TEXT NOT NULL,
                    actor_name TEXT NOT NULL,
                    video_path TEXT,
                    spot_url TEXT,
                    platform TEXT DEFAULT 'unknown',
                    harness_config TEXT,  -- JSON: full harness configuration
                    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Performance events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS performance_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    harness_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    platform TEXT,
                    metadata TEXT,  -- JSON: additional event data
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (harness_id) REFERENCES spot_generations(harness_id)
                )
            """)
            
            # Indexes for fast queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_harness_id 
                ON performance_events(harness_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_type 
                ON performance_events(event_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_spots_imdb 
                ON spot_generations(imdb_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_spots_talent 
                ON spot_generations(talent_id)
            """)
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def register_spot(
        self,
        harness_id: str,
        imdb_id: str,
        talent_id: str,
        actor_name: str,
        spot_url: str,
        platform: str = 'unknown',
        harness_config: Optional[Dict] = None,
        video_path: Optional[str] = None
    ) -> str:
        """
        Register a newly generated spot with its unique harness ID.
        
        Args:
            harness_id: Unique identifier for this spot (e.g., "harness_tt0310917_001")
            imdb_id: IMDb title ID
            talent_id: IMDb talent ID
            actor_name: Actor name
            spot_url: URL/path to generated spot
            platform: Target platform (tiktok, instagram, etc.)
            harness_config: Full harness configuration used
            video_path: Path to source video
        
        Returns:
            The harness_id
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO spot_generations 
                (harness_id, imdb_id, talent_id, actor_name, video_path, 
                 spot_url, platform, harness_config)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                harness_id, imdb_id, talent_id, actor_name, video_path,
                spot_url, platform, json.dumps(harness_config or {})
            ))
            conn.commit()
            
            # Also record the generation event
            self._record_event(cursor, harness_id, "spot_generated", platform, {})
            conn.commit()
            
            return harness_id
    
    def _record_event(
        self,
        cursor: sqlite3.Cursor,
        harness_id: str,
        event_type: str,
        platform: Optional[str] = None,
        metadata: Optional[Dict] = None
    ):
        """Internal: Record an event."""
        cursor.execute("""
            INSERT INTO performance_events 
            (harness_id, event_type, platform, metadata)
            VALUES (?, ?, ?, ?)
        """, (harness_id, event_type, platform, json.dumps(metadata or {})))
    
    def record_event(
        self,
        harness_id: str,
        event_type: str,
        platform: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Record a performance event for a spot.
        
        Args:
            harness_id: The spot's unique harness ID
            event_type: Type of event (view, like, share, etc.)
            platform: Platform where event occurred
            metadata: Additional event data
        
        Returns:
            True if successful
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                self._record_event(cursor, harness_id, event_type, platform, metadata)
                conn.commit()
                return True
        except Exception as e:
            print(f"[Performance] Error recording event: {e}")
            return False
    
    def get_spot_analytics(self, harness_id: str) -> Dict[str, Any]:
        """
        Get analytics for a specific spot.
        
        Returns dict with:
        - harness_id: The spot ID
        - spot_info: Spot generation details
        - events: Count of each event type
        - funnel: Conversion funnel metrics
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Get spot info
            cursor.execute("""
                SELECT * FROM spot_generations WHERE harness_id = ?
            """, (harness_id,))
            spot_row = cursor.fetchone()
            
            if not spot_row:
                return {"error": "Spot not found"}
            
            # Get event counts
            cursor.execute("""
                SELECT event_type, COUNT(*) as count
                FROM performance_events
                WHERE harness_id = ?
                GROUP BY event_type
            """, (harness_id,))
            
            events = {row['event_type']: row['count'] for row in cursor.fetchall()}
            
            # Calculate funnel
            views = events.get('view', 0)
            likes = events.get('like', 0)
            shares = events.get('share', 0)
            conversions = events.get('conversion', 0)
            
            funnel = {
                "impressions": events.get('upload_completed', 0),
                "views": views,
                "likes": likes,
                "shares": shares,
                "conversions": conversions,
                "engagement_rate": (likes + shares) / views if views > 0 else 0,
                "conversion_rate": conversions / views if views > 0 else 0
            }
            
            return {
                "harness_id": harness_id,
                "spot_info": {
                    "imdb_id": spot_row['imdb_id'],
                    "talent_id": spot_row['talent_id'],
                    "actor_name": spot_row['actor_name'],
                    "platform": spot_row['platform'],
                    "generated_at": spot_row['generated_at'],
                    "harness_config": json.loads(spot_row['harness_config'] or '{}')
                },
                "events": events,
                "funnel": funnel
            }
    
    def get_talent_convergence(self, talent_id: str, platform: Optional[str] = None) -> Dict[str, Any]:
        """
        Get convergence metrics for a talent across harnesses.
        
        This shows which harnesses perform best for this talent.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if platform:
                cursor.execute("""
                    SELECT harness_id, platform, harness_config, generated_at
                    FROM spot_generations
                    WHERE talent_id = ? AND platform = ?
                """, (talent_id, platform))
            else:
                cursor.execute("""
                    SELECT harness_id, platform, harness_config, generated_at
                    FROM spot_generations
                    WHERE talent_id = ?
                """, (talent_id,))
            
            spots = cursor.fetchall()
            
            # Get analytics for each spot
            results = []
            for spot in spots:
                analytics = self.get_spot_analytics(spot['harness_id'])
                results.append(analytics)
            
            # Calculate best performing harness
            if results:
                best = max(results, key=lambda x: x['funnel'].get('engagement_rate', 0))
            else:
                best = None
            
            return {
                "talent_id": talent_id,
                "platform": platform,
                "total_spots": len(results),
                "spots": results,
                "best_performing_harness": best['spot_info']['harness_config'] if best else None,
                "best_engagement_rate": best['funnel']['engagement_rate'] if best else 0
            }
    
    def get_platform_comparison(self, platform: str) -> Dict[str, Any]:
        """
        Compare talent performance on a specific platform.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT talent_id, actor_name, harness_id
                FROM spot_generations
                WHERE platform = ?
            """, (platform,))
            
            talent_spots = {}
            for row in cursor.fetchall():
                tid = row['talent_id']
                if tid not in talent_spots:
                    talent_spots[tid] = {
                        "name": row['actor_name'],
                        "harness_ids": []
                    }
                talent_spots[tid]["harness_ids"].append(row['harness_id'])
            
            # Calculate average engagement per talent
            results = []
            for tid, data in talent_spots.items():
                total_engagement = 0
                for hid in data["harness_ids"]:
                    analytics = self.get_spot_analytics(hid)
                    total_engagement += analytics['funnel'].get('engagement_rate', 0)
                
                avg_engagement = total_engagement / len(data["harness_ids"]) if data["harness_ids"] else 0
                
                results.append({
                    "talent_id": tid,
                    "name": data["name"],
                    "avg_engagement_rate": avg_engagement,
                    "spot_count": len(data["harness_ids"])
                })
            
            results.sort(key=lambda x: x['avg_engagement_rate'], reverse=True)
            
            return {
                "platform": platform,
                "talent_count": len(results),
                "rankings": results
            }


# Singleton instance
_tracker_instance = None

def get_tracker() -> PerformanceTracker:
    """Get singleton performance tracker."""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = PerformanceTracker()
    return _tracker_instance


# Convenience functions

def register_spot(
    harness_id: str,
    imdb_id: str,
    talent_id: str,
    actor_name: str,
    spot_url: str,
    platform: str = 'unknown',
    harness_config: Optional[Dict] = None,
    video_path: Optional[str] = None
) -> str:
    """Convenience: Register a spot."""
    return get_tracker().register_spot(
        harness_id, imdb_id, talent_id, actor_name,
        spot_url, platform, harness_config, video_path
    )


def record_spot_performance(
    harness_id: str,
    event_type: str,
    platform: Optional[str] = None,
    metadata: Optional[Dict] = None
) -> bool:
    """Convenience: Record performance event."""
    return get_tracker().record_event(harness_id, event_type, platform, metadata)


def get_spot_analytics(harness_id: str) -> Dict[str, Any]:
    """Convenience: Get spot analytics."""
    return get_tracker().get_spot_analytics(harness_id)


def get_talent_convergence(talent_id: str, platform: Optional[str] = None) -> Dict[str, Any]:
    """Convenience: Get talent convergence metrics."""
    return get_tracker().get_talent_convergence(talent_id, platform)


def get_platform_comparison(platform: str) -> Dict[str, Any]:
    """Convenience: Get platform comparison."""
    return get_tracker().get_platform_comparison(platform)


if __name__ == "__main__":
    # Test the performance tracker
    print("Testing Performance Tracker...")
    
    tracker = get_tracker()
    
    # Register a test spot
    harness_id = register_spot(
        harness_id="harness_test_001",
        imdb_id="tt0310917",
        talent_id="nm0000179",
        actor_name="Jude Law",
        spot_url="/path/to/spot.mp4",
        platform="tiktok",
        harness_config={"style": "dramatic", "music": "intense"}
    )
    print(f"Registered spot: {harness_id}")
    
    # Record some events
    record_spot_performance(harness_id, "view", "tiktok", {"user_id": "user123"})
    record_spot_performance(harness_id, "like", "tiktok")
    record_spot_performance(harness_id, "share", "tiktok")
    
    # Get analytics
    analytics = get_spot_analytics(harness_id)
    print(f"\nAnalytics for {harness_id}:")
    print(json.dumps(analytics, indent=2))
    
    print("\nPerformance Tracker test complete!")
