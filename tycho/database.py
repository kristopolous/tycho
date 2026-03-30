#!/usr/bin/env python3
"""
database.py - Comprehensive SQLite database for Tycho talent and harness tracking

Tables:
- talent: Core actor information (IMDB ID, TMDB ID, name, metadata)
- talent_images: Image URLs from various sources (IMDB, TMDB, etc.)
- harnesses: Spot generation formulas/templates
- harness_performance: Performance metrics per talent-harness combination
- searches: 12Labs search history
- platforms: Social media platforms (TikTok, Instagram, etc.)
- audiences: Audience segments for A/B testing
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from contextlib import contextmanager

# Database path
DB_DIR = Path(__file__).parent / ".cache"
DB_PATH = DB_DIR / "tycho.db"


@dataclass
class Talent:
    """Represents an actor/talent in the database."""
    id: int
    imdb_id: str
    tmdb_id: Optional[int]
    name: str
    birth_year: Optional[int]
    category: str  # actor, actress, etc.
    primary_professions: List[str]
    popularity_score: float  # TMDB popularity
    mise_en_scene: str  # JSON: top 5 adjectives + emotional saliences for bumper styling
    created_at: str
    updated_at: str


@dataclass
class TalentImage:
    """Represents an image for a talent."""
    id: int
    talent_id: int
    source: str  # 'imdb', 'tmdb', 'manual', etc.
    url: str
    width: Optional[int]
    height: Optional[int]
    file_path: Optional[str]  # For TMDB file_path
    vote_average: Optional[float]  # TMDB vote score
    is_primary: bool
    fetched_at: str


@dataclass
class Harness:
    """Represents a spot generation formula/template."""
    id: int
    name: str
    platform: str  # tiktok, instagram, youtube, etc.
    description: str
    config: Dict[str, Any]  # JSON config for the harness
    target_duration: int  # seconds
    intro_style: str
    outro_style: str
    music_genre: Optional[str]
    text_overlay_style: Optional[str]
    created_at: str
    updated_at: str


@dataclass
class HarnessPerformance:
    """Performance metrics for a talent-harness-platform combination."""
    id: int
    talent_id: int
    harness_id: int
    platform_id: int
    
    # Search metrics
    clips_found: int
    avg_clip_score: float
    search_success_rate: float
    
    # Generation metrics
    spots_generated: int
    spots_successful: int
    generation_success_rate: float
    
    # Engagement metrics (if available)
    views: Optional[int]
    likes: Optional[int]
    shares: Optional[int]
    comments: Optional[int]
    engagement_rate: Optional[float]
    
    # Convergence score (our internal metric)
    convergence_score: float
    
    # Metadata
    test_runs: int
    last_run_at: Optional[str]
    notes: str
    created_at: str
    updated_at: str


@dataclass
class Platform:
    """Social media platform."""
    id: int
    name: str
    display_name: str
    optimal_duration_min: int
    optimal_duration_max: int
    aspect_ratio: str
    config: Dict[str, Any]


@dataclass
class SearchHistory:
    """Record of 12Labs searches."""
    id: int
    talent_id: int
    video_id: str
    image_count: int
    clips_found: int
    avg_confidence: float
    search_duration_ms: Optional[int]
    search_params: Dict[str, Any]
    created_at: str


class Database:
    """Main database interface for Tycho."""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self._init_db()
    
    def _init_db(self):
        """Initialize database tables."""
        DB_DIR.mkdir(exist_ok=True)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Talent table - core actor information
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS talent (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    imdb_id TEXT UNIQUE NOT NULL,
                    tmdb_id INTEGER UNIQUE,
                    name TEXT NOT NULL,
                    birth_year INTEGER,
                    category TEXT DEFAULT 'actor',
                    primary_professions TEXT,  -- JSON array
                    popularity_score REAL DEFAULT 0.0,
                    mise_en_scene TEXT,  -- JSON: top 5 adjectives + emotional saliences for bumper styling
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Migrate existing database to add mise_en_scene column if needed
            try:
                cursor.execute("SELECT mise_en_scene FROM talent LIMIT 1")
            except sqlite3.OperationalError:
                cursor.execute("ALTER TABLE talent ADD COLUMN mise_en_scene TEXT")
                print("[DB] Migrated: Added mise_en_scene column to talent table")
            
            # Talent images table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS talent_images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    talent_id INTEGER NOT NULL,
                    source TEXT NOT NULL,  -- 'imdb', 'tmdb', 'manual'
                    url TEXT NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    file_path TEXT,  -- TMDB file_path
                    vote_average REAL,
                    is_primary BOOLEAN DEFAULT FALSE,
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (talent_id) REFERENCES talent(id) ON DELETE CASCADE
                )
            """)
            
            # Create index on talent_images
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_talent_images_talent_id 
                ON talent_images(talent_id)
            """)
            
            # Platforms table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS platforms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,  -- 'tiktok', 'instagram', etc.
                    display_name TEXT NOT NULL,
                    optimal_duration_min INTEGER DEFAULT 10,
                    optimal_duration_max INTEGER DEFAULT 60,
                    aspect_ratio TEXT DEFAULT '9:16',
                    config TEXT DEFAULT '{}'  -- JSON
                )
            """)
            
            # Harnesses table - spot generation formulas
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS harnesses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    platform_id INTEGER NOT NULL,
                    description TEXT,
                    config TEXT NOT NULL,  -- JSON harness configuration
                    target_duration INTEGER DEFAULT 15,
                    intro_style TEXT DEFAULT 'standard',
                    outro_style TEXT DEFAULT 'standard',
                    music_genre TEXT,
                    text_overlay_style TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (platform_id) REFERENCES platforms(id)
                )
            """)
            
            # Harness performance table - convergence tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS harness_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    talent_id INTEGER NOT NULL,
                    harness_id INTEGER NOT NULL,
                    platform_id INTEGER NOT NULL,
                    
                    -- Search metrics
                    clips_found INTEGER DEFAULT 0,
                    avg_clip_score REAL DEFAULT 0.0,
                    search_success_rate REAL DEFAULT 0.0,
                    
                    -- Generation metrics
                    spots_generated INTEGER DEFAULT 0,
                    spots_successful INTEGER DEFAULT 0,
                    generation_success_rate REAL DEFAULT 0.0,
                    
                    -- Engagement metrics
                    views INTEGER,
                    likes INTEGER,
                    shares INTEGER,
                    comments INTEGER,
                    engagement_rate REAL,
                    
                    -- Convergence score (internal metric)
                    convergence_score REAL DEFAULT 0.0,
                    
                    -- Metadata
                    test_runs INTEGER DEFAULT 0,
                    last_run_at TIMESTAMP,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    FOREIGN KEY (talent_id) REFERENCES talent(id) ON DELETE CASCADE,
                    FOREIGN KEY (harness_id) REFERENCES harnesses(id) ON DELETE CASCADE,
                    FOREIGN KEY (platform_id) REFERENCES platforms(id) ON DELETE CASCADE,
                    UNIQUE(talent_id, harness_id, platform_id)
                )
            """)
            
            # Search history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    talent_id INTEGER NOT NULL,
                    video_id TEXT NOT NULL,
                    index_id TEXT,
                    image_count INTEGER DEFAULT 1,
                    clips_found INTEGER DEFAULT 0,
                    avg_confidence REAL DEFAULT 0.0,
                    search_duration_ms INTEGER,
                    search_params TEXT,  -- JSON
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (talent_id) REFERENCES talent(id) ON DELETE CASCADE
                )
            """)
            
            # Title/Cast cache (for IMDb data)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS title_cast_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title_id TEXT NOT NULL,
                    talent_id INTEGER NOT NULL,
                    character_name TEXT,
                    episode_count INTEGER,
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (talent_id) REFERENCES talent(id) ON DELETE CASCADE,
                    UNIQUE(title_id, talent_id)
                )
            """)
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Get a database connection as a context manager."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    # ==================== Talent Operations ====================
    
    def get_or_create_talent(
        self,
        imdb_id: str,
        name: str,
        tmdb_id: Optional[int] = None,
        birth_year: Optional[int] = None,
        category: str = 'actor',
        primary_professions: Optional[List[str]] = None,
        popularity_score: float = 0.0
    ) -> Talent:
        """Get existing talent or create new one."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if talent exists
            cursor.execute("SELECT * FROM talent WHERE imdb_id = ?", (imdb_id,))
            row = cursor.fetchone()
            
            if row:
                # Update TMDB ID if provided
                if tmdb_id and not row['tmdb_id']:
                    cursor.execute("""
                        UPDATE talent 
                        SET tmdb_id = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (tmdb_id, row['id']))
                    conn.commit()
                
                return self._row_to_talent(row)
            
            # Create new talent
            cursor.execute("""
                INSERT INTO talent (imdb_id, tmdb_id, name, birth_year, category, 
                                  primary_professions, popularity_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                imdb_id, tmdb_id, name, birth_year, category,
                json.dumps(primary_professions or []),
                popularity_score
            ))
            conn.commit()
            
            return self.get_talent_by_id(cursor.lastrowid)
    
    def get_talent_by_id(self, talent_id: int) -> Optional[Talent]:
        """Get talent by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM talent WHERE id = ?", (talent_id,))
            row = cursor.fetchone()
            return self._row_to_talent(row) if row else None
    
    def get_talent_by_imdb_id(self, imdb_id: str) -> Optional[Talent]:
        """Get talent by IMDb ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM talent WHERE imdb_id = ?", (imdb_id,))
            row = cursor.fetchone()
            return self._row_to_talent(row) if row else None
    
    def get_talent_by_tmdb_id(self, tmdb_id: int) -> Optional[Talent]:
        """Get talent by TMDB ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM talent WHERE tmdb_id = ?", (tmdb_id,))
            row = cursor.fetchone()
            return self._row_to_talent(row) if row else None
    
    def _row_to_talent(self, row: sqlite3.Row) -> Talent:
        """Convert database row to Talent dataclass."""
        return Talent(
            id=row['id'],
            imdb_id=row['imdb_id'],
            tmdb_id=row['tmdb_id'],
            name=row['name'],
            birth_year=row['birth_year'],
            category=row['category'],
            primary_professions=json.loads(row['primary_professions'] or '[]'),
            popularity_score=row['popularity_score'],
            mise_en_scene=row['mise_en_scene'] or '',
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )
    
    # ==================== Talent Image Operations ====================
    
    def add_talent_image(
        self,
        talent_id: int,
        source: str,
        url: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        file_path: Optional[str] = None,
        vote_average: Optional[float] = None,
        is_primary: bool = False
    ) -> int:
        """Add an image for a talent."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # If setting as primary, unset other primaries
            if is_primary:
                cursor.execute("""
                    UPDATE talent_images 
                    SET is_primary = FALSE 
                    WHERE talent_id = ?
                """, (talent_id,))
            
            cursor.execute("""
                INSERT INTO talent_images 
                (talent_id, source, url, width, height, file_path, vote_average, is_primary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (talent_id, source, url, width, height, file_path, vote_average, is_primary))
            
            conn.commit()
            return cursor.lastrowid
    
    def get_talent_images(
        self,
        talent_id: int,
        source: Optional[str] = None,
        limit: int = 10
    ) -> List[TalentImage]:
        """Get images for a talent, optionally filtered by source."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if source:
                cursor.execute("""
                    SELECT * FROM talent_images 
                    WHERE talent_id = ? AND source = ?
                    ORDER BY is_primary DESC, vote_average DESC NULLS LAST
                    LIMIT ?
                """, (talent_id, source, limit))
            else:
                cursor.execute("""
                    SELECT * FROM talent_images 
                    WHERE talent_id = ?
                    ORDER BY is_primary DESC, vote_average DESC NULLS LAST
                    LIMIT ?
                """, (talent_id, limit))
            
            rows = cursor.fetchall()
            return [self._row_to_talent_image(row) for row in rows]
    
    def get_talent_headshots(self, talent_id: int, max_images: int = 5) -> List[str]:
        """Get headshot URLs for a talent from all sources."""
        images = self.get_talent_images(talent_id, limit=max_images)
        return [img.url for img in images]
    
    def _row_to_talent_image(self, row: sqlite3.Row) -> TalentImage:
        """Convert database row to TalentImage dataclass."""
        return TalentImage(
            id=row['id'],
            talent_id=row['talent_id'],
            source=row['source'],
            url=row['url'],
            width=row['width'],
            height=row['height'],
            file_path=row['file_path'],
            vote_average=row['vote_average'],
            is_primary=row['is_primary'],
            fetched_at=row['fetched_at']
        )
    
    # ==================== Platform Operations ====================
    
    def init_default_platforms(self):
        """Initialize default platforms."""
        platforms = [
            ('tiktok', 'TikTok', 10, 60, '9:16'),
            ('instagram', 'Instagram Reels', 15, 90, '9:16'),
            ('youtube', 'YouTube Shorts', 15, 60, '9:16'),
            ('pack', 'Platform Pack', 15, 60, '16:9'),  # Multi-platform pack
        ]
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for name, display_name, min_dur, max_dur, ratio in platforms:
                cursor.execute("""
                    INSERT OR IGNORE INTO platforms 
                    (name, display_name, optimal_duration_min, optimal_duration_max, aspect_ratio)
                    VALUES (?, ?, ?, ?, ?)
                """, (name, display_name, min_dur, max_dur, ratio))
            conn.commit()
    
    def get_platform_by_name(self, name: str) -> Optional[Platform]:
        """Get platform by name."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM platforms WHERE name = ?", (name,))
            row = cursor.fetchone()
            return self._row_to_platform(row) if row else None
    
    def _row_to_platform(self, row: sqlite3.Row) -> Platform:
        """Convert database row to Platform dataclass."""
        return Platform(
            id=row['id'],
            name=row['name'],
            display_name=row['display_name'],
            optimal_duration_min=row['optimal_duration_min'],
            optimal_duration_max=row['optimal_duration_max'],
            aspect_ratio=row['aspect_ratio'],
            config=json.loads(row['config'] or '{}')
        )
    
    # ==================== Harness Operations ====================
    
    def create_harness(
        self,
        name: str,
        platform_id: int,
        config: Dict[str, Any],
        description: str = '',
        target_duration: int = 15,
        intro_style: str = 'standard',
        outro_style: str = 'standard',
        music_genre: Optional[str] = None,
        text_overlay_style: Optional[str] = None
    ) -> int:
        """Create a new harness."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO harnesses 
                (name, platform_id, description, config, target_duration, 
                 intro_style, outro_style, music_genre, text_overlay_style)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name, platform_id, description, json.dumps(config), target_duration,
                intro_style, outro_style, music_genre, text_overlay_style
            ))
            conn.commit()
            return cursor.lastrowid
    
    def get_harness_by_id(self, harness_id: int) -> Optional[Harness]:
        """Get harness by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT h.*, p.name as platform_name 
                FROM harnesses h
                JOIN platforms p ON h.platform_id = p.id
                WHERE h.id = ?
            """, (harness_id,))
            row = cursor.fetchone()
            return self._row_to_harness(row) if row else None
    
    def get_harnesses_for_platform(self, platform_name: str) -> List[Harness]:
        """Get all harnesses for a platform."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT h.*, p.name as platform_name 
                FROM harnesses h
                JOIN platforms p ON h.platform_id = p.id
                WHERE p.name = ? AND h.is_active = TRUE
            """, (platform_name,))
            rows = cursor.fetchall()
            return [self._row_to_harness(row) for row in rows]
    
    def _row_to_harness(self, row: sqlite3.Row) -> Harness:
        """Convert database row to Harness dataclass."""
        return Harness(
            id=row['id'],
            name=row['name'],
            platform=row['platform_name'] if 'platform_name' in row.keys() else '',
            description=row['description'],
            config=json.loads(row['config']),
            target_duration=row['target_duration'],
            intro_style=row['intro_style'],
            outro_style=row['outro_style'],
            music_genre=row['music_genre'],
            text_overlay_style=row['text_overlay_style'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )
    
    # ==================== Performance Tracking ====================
    
    def record_performance(
        self,
        talent_id: int,
        harness_id: int,
        platform_id: int,
        clips_found: int = 0,
        avg_clip_score: float = 0.0,
        spots_generated: int = 0,
        spots_successful: int = 0,
        notes: str = ''
    ) -> int:
        """Record performance for a talent-harness-platform combination."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if record exists
            cursor.execute("""
                SELECT * FROM harness_performance 
                WHERE talent_id = ? AND harness_id = ? AND platform_id = ?
            """, (talent_id, harness_id, platform_id))
            
            existing = cursor.fetchone()
            
            if existing:
                # Update existing record
                cursor.execute("""
                    UPDATE harness_performance
                    SET clips_found = clips_found + ?,
                        avg_clip_score = (avg_clip_score * test_runs + ?) / (test_runs + 1),
                        spots_generated = spots_generated + ?,
                        spots_successful = spots_successful + ?,
                        test_runs = test_runs + 1,
                        last_run_at = CURRENT_TIMESTAMP,
                        notes = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (clips_found, avg_clip_score, spots_generated, spots_successful, 
                      notes, existing['id']))
                conn.commit()
                return existing['id']
            else:
                # Create new record
                cursor.execute("""
                    INSERT INTO harness_performance
                    (talent_id, harness_id, platform_id, clips_found, avg_clip_score,
                     spots_generated, spots_successful, test_runs, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                """, (talent_id, harness_id, platform_id, clips_found, avg_clip_score,
                      spots_generated, spots_successful, notes))
                conn.commit()
                return cursor.lastrowid
    
    def get_best_harnesses_for_talent(
        self,
        talent_id: int,
        platform_name: Optional[str] = None,
        min_runs: int = 1,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get best performing harnesses for a talent."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if platform_name:
                cursor.execute("""
                    SELECT hp.*, h.name as harness_name, p.name as platform_name,
                           t.name as talent_name
                    FROM harness_performance hp
                    JOIN harnesses h ON hp.harness_id = h.id
                    JOIN platforms p ON hp.platform_id = p.id
                    JOIN talent t ON hp.talent_id = t.id
                    WHERE hp.talent_id = ? AND p.name = ? AND hp.test_runs >= ?
                    ORDER BY hp.convergence_score DESC, hp.avg_clip_score DESC
                    LIMIT ?
                """, (talent_id, platform_name, min_runs, limit))
            else:
                cursor.execute("""
                    SELECT hp.*, h.name as harness_name, p.name as platform_name,
                           t.name as talent_name
                    FROM harness_performance hp
                    JOIN harnesses h ON hp.harness_id = h.id
                    JOIN platforms p ON hp.platform_id = p.id
                    JOIN talent t ON hp.talent_id = t.id
                    WHERE hp.talent_id = ? AND hp.test_runs >= ?
                    ORDER BY hp.convergence_score DESC, hp.avg_clip_score DESC
                    LIMIT ?
                """, (talent_id, min_runs, limit))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_talent_platform_comparison(
        self,
        platform_name: str,
        min_runs: int = 1,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get comparison of talent performance on a specific platform."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    t.id as talent_id,
                    t.name,
                    t.imdb_id,
                    COUNT(DISTINCT hp.harness_id) as harnesses_tested,
                    AVG(hp.convergence_score) as avg_convergence,
                    AVG(hp.avg_clip_score) as avg_clip_score,
                    SUM(hp.clips_found) as total_clips,
                    MAX(hp.last_run_at) as last_tested
                FROM talent t
                JOIN harness_performance hp ON t.id = hp.talent_id
                JOIN platforms p ON hp.platform_id = p.id
                WHERE p.name = ? AND hp.test_runs >= ?
                GROUP BY t.id
                ORDER BY avg_convergence DESC
                LIMIT ?
            """, (platform_name, min_runs, limit))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    # ==================== Search History ====================
    
    def record_search(
        self,
        talent_id: int,
        video_id: str,
        image_count: int,
        clips_found: int,
        avg_confidence: float,
        index_id: Optional[str] = None,
        search_duration_ms: Optional[int] = None,
        search_params: Optional[Dict] = None
    ) -> int:
        """Record a 12Labs search."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO search_history
                (talent_id, video_id, index_id, image_count, clips_found,
                 avg_confidence, search_duration_ms, search_params)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (talent_id, video_id, index_id, image_count, clips_found,
                  avg_confidence, search_duration_ms, json.dumps(search_params or {})))
            conn.commit()
            return cursor.lastrowid
    
    def get_search_history_for_talent(
        self,
        talent_id: int,
        limit: int = 50
    ) -> List[SearchHistory]:
        """Get search history for a talent."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM search_history
                WHERE talent_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (talent_id, limit))
            
            rows = cursor.fetchall()
            return [self._row_to_search_history(row) for row in rows]
    
    def _row_to_search_history(self, row: sqlite3.Row) -> SearchHistory:
        """Convert database row to SearchHistory dataclass."""
        return SearchHistory(
            id=row['id'],
            talent_id=row['talent_id'],
            video_id=row['video_id'],
            image_count=row['image_count'],
            clips_found=row['clips_found'],
            avg_confidence=row['avg_confidence'],
            search_duration_ms=row['search_duration_ms'],
            search_params=json.loads(row['search_params'] or '{}'),
            created_at=row['created_at']
        )


# Singleton instance
_db_instance = None

def get_db() -> Database:
    """Get the singleton database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
        _db_instance.init_default_platforms()
    return _db_instance


def init_database():
    """Initialize the database with default data."""
    db = get_db()
    db.init_default_platforms()
    return db


if __name__ == "__main__":
    # Test the database
    db = init_database()
    
    # Test talent operations
    print("Testing talent operations...")
    talent = db.get_or_create_talent(
        imdb_id="nm0000179",
        name="Jude Law",
        tmdb_id=9642,
        birth_year=1972,
        category="actor",
        primary_professions=["Actor", "Producer"],
        popularity_score=6.5
    )
    print(f"Created/Found talent: {talent}")
    
    # Test image operations
    print("\nTesting image operations...")
    img_id = db.add_talent_image(
        talent_id=talent.id,
        source="imdb",
        url="https://example.com/jude.jpg",
        width=800,
        height=1000,
        is_primary=True
    )
    print(f"Added image with ID: {img_id}")
    
    images = db.get_talent_images(talent.id)
    print(f"Found {len(images)} images")
    
    # Test harness operations
    print("\nTesting harness operations...")
    platform = db.get_platform_by_name("tiktok")
    if platform:
        harness_id = db.create_harness(
            name="Classic Actor Spotlight",
            platform_id=platform.id,
            config={"style": "documentary", "pace": "slow"},
            description="Classic documentary-style actor profile"
        )
        print(f"Created harness with ID: {harness_id}")
    
    print("\nDatabase test complete!")
