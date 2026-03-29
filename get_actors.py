#!/usr/bin/env python3
"""
get-actors.py - Fetch cast information and headshots from IMDb API

Usage:
    python get-actors.py <title_id> [--limit N]

Example:
    python get-actors.py tt0058331 --limit 10
"""

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests

# API Configuration
BASE_URL = "https://api.imdbapi.dev"

# TMDB integration (optional)
TMDB_AVAILABLE = False
get_combined_headshots = None
init_tmdb_cache = None
try:
    from tmdb_client import get_combined_headshots, init_cache as init_tmdb_cache
    TMDB_AVAILABLE = True
except ImportError:
    pass

# Cache configuration
CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DB = CACHE_DIR / "imdb_cache.db"
CACHE_EXPIRY_HOURS = 24  # Cache expires after 24 hours


def init_cache():
    """Initialize SQLite cache database."""
    CACHE_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(CACHE_DB)
    cursor = conn.cursor()
    
    # Cache table for API responses
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL
        )
    """)
    
    # Table for cast members (normalized)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cast_members (
            title_id TEXT,
            name_id TEXT,
            name TEXT,
            category TEXT,
            characters TEXT,
            episode_count INTEGER,
            primary_image_url TEXT,
            birth_date TEXT,
            birth_date_fetched TIMESTAMP,
            PRIMARY KEY (title_id, name_id)
        )
    """)
    
    # Table for name images
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS name_images (
            name_id TEXT,
            image_url TEXT,
            image_type TEXT,
            width INTEGER,
            height INTEGER,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (name_id, image_url)
        )
    """)
    
    conn.commit()
    return conn


def get_cache(key: str) -> Optional[Any]:
    """Get cached data if not expired."""
    conn = sqlite3.connect(CACHE_DB)
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT data FROM cache WHERE key = ? AND expires_at > ?",
        (key, datetime.now().isoformat())
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return json.loads(row[0])
    return None


def set_cache(key: str, data: Any, expiry_hours: int = CACHE_EXPIRY_HOURS):
    """Store data in cache with expiration."""
    conn = sqlite3.connect(CACHE_DB)
    cursor = conn.cursor()
    
    expires_at = datetime.now().timestamp() + (expiry_hours * 3600)
    expires_at_dt = datetime.fromtimestamp(expires_at).isoformat()
    
    cursor.execute("""
        INSERT OR REPLACE INTO cache (key, data, expires_at)
        VALUES (?, ?, ?)
    """, (key, json.dumps(data), expires_at_dt))
    
    conn.commit()
    conn.close()


def cache_key(endpoint: str, params: Optional[dict] = None) -> str:
    """Generate a cache key from endpoint and params."""
    key_str = f"{endpoint}:{json.dumps(params or {}, sort_keys=True)}"
    return hashlib.sha256(key_str.encode()).hexdigest()


def api_request(endpoint: str, params: Optional[dict] = None) -> dict:
    """Make API request with caching."""
    key = cache_key(endpoint, params)
    
    # Check cache first
    cached = get_cache(key)
    if cached:
        print(f"[CACHE] {endpoint}")
        return cached
    
    # Make API request
    url = f"{BASE_URL}{endpoint}"
    print(f"[API] {url}")
    
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    
    # Cache the response
    set_cache(key, data)
    
    return data


def get_title_credits(title_id: str, categories: Optional[list] = None, limit: int = 50) -> list:
    """Get cast/credits for a title."""
    credits = []
    page_token = None
    
    while len(credits) < limit:
        params = {"pageSize": min(50, limit - len(credits))}
        if categories:
            params["categories"] = categories
        if page_token:
            params["pageToken"] = page_token
        
        response = api_request(f"/titles/{title_id}/credits", params)
        
        items = response.get("credits", [])
        credits.extend(items)
        
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    
    return credits[:limit]


def get_name_details(name_id: str) -> dict:
    """Get details for a name/person."""
    return api_request(f"/names/{name_id}")


def get_name_images(name_id: str, limit: int = 20, types: Optional[list] = None) -> list:
    """Get images for a name/person."""
    images = []
    page_token = None
    
    while len(images) < limit:
        params = {"pageSize": min(50, limit - len(images))}
        if types:
            params["types"] = types
        if page_token:
            params["pageToken"] = page_token
        
        response = api_request(f"/names/{name_id}/images", params)
        
        items = response.get("images", [])
        images.extend(items)
        
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    
    return images[:limit]


def store_cast_in_db(title_id: str, credits: list):
    """Store cast information in SQLite for later querying."""
    conn = sqlite3.connect(CACHE_DB)
    cursor = conn.cursor()
    
    for credit in credits:
        name_obj = credit.get("name", {})
        characters = credit.get("characters", [])
        
        cursor.execute("""
            INSERT OR REPLACE INTO cast_members 
            (title_id, name_id, name, category, characters, episode_count, 
             primary_image_url, birth_date, birth_date_fetched)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            title_id,
            name_obj.get("id"),
            name_obj.get("displayName"),
            credit.get("category"),
            json.dumps(characters) if characters else None,
            credit.get("episodeCount"),
            name_obj.get("primaryImage", {}).get("url"),
            None,  # Will be updated when we fetch name details
            None
        ))
    
    conn.commit()
    conn.close()


def store_name_in_db(name_id: str, name_data: dict):
    """Store name details in SQLite."""
    conn = sqlite3.connect(CACHE_DB)
    cursor = conn.cursor()
    
    birth_date = name_data.get("birthDate")
    birth_date_str = None
    if birth_date:
        # Handle precision date format
        year = birth_date.get("year")
        month = birth_date.get("month")
        day = birth_date.get("day")
        if year:
            birth_date_str = f"{year}-{month or '01'}-{day or '01'}"
    
    cursor.execute("""
        UPDATE cast_members 
        SET birth_date = ?, birth_date_fetched = ?
        WHERE name_id = ?
    """, (birth_date_str, datetime.now().isoformat(), name_id))
    
    conn.commit()
    conn.close()


def store_images_in_db(name_id: str, images: list):
    """Store name images in SQLite."""
    conn = sqlite3.connect(CACHE_DB)
    cursor = conn.cursor()
    
    for img in images:
        cursor.execute("""
            INSERT OR REPLACE INTO name_images 
            (name_id, image_url, image_type, width, height)
            VALUES (?, ?, ?, ?, ?)
        """, (
            name_id,
            img.get("url"),
            img.get("type"),
            img.get("width"),
            img.get("height")
        ))
    
    conn.commit()
    conn.close()


def get_title_metadata(title_id: str) -> dict:
    """Fetch title metadata from IMDb API."""
    response = api_request(f"/titles/{title_id}")
    return {
        "id": response.get("id"),
        "title": response.get("primaryTitle"),
        "type": response.get("type"),
        "year": response.get("startYear"),
        "runtime_seconds": response.get("runtimeSeconds"),
        "genres": response.get("genres", []),
        "rating": response.get("rating", {}),
        "plot": response.get("plot"),
        "image_url": response.get("primaryImage", {}).get("url"),
    }


def fetch_cast_with_images(title_id: str, limit: int = 20, use_tmdb: bool = False, max_tmdb_images: int = 2) -> list:
    """
    Fetch cast members with their details and headshots.
    
    Args:
        title_id: IMDb title ID
        limit: Maximum number of cast members
        use_tmdb: Whether to also fetch TMDB headshots for multi-image search
        max_tmdb_images: Number of TMDB images to fetch per actor (when use_tmdb=True)
    
    Returns a list of dicts with:
    - name_id, name, category, characters
    - primary_image (from name details)
    - birth_date (for contemporaneous matching)
    - images (list of headshots)
    - all_headshots (list of all image URLs - IMDB + TMDB for multi-image search)
    """
    print(f"\n{'='*60}")
    print(f"Fetching cast for title: {title_id}")
    if use_tmdb:
        print(f"Using TMDB for additional headshots (max {max_tmdb_images} per actor)")
    print(f"{'='*60}\n")
    
    # Initialize TMDB cache if needed
    if use_tmdb and TMDB_AVAILABLE:
        try:
            init_tmdb_cache()
        except Exception as e:
            print(f"[TMDB] Warning: Could not initialize cache: {e}")
    
    # Step 1: Get credits
    print("[1/3] Fetching credits...")
    credits = get_title_credits(title_id, categories=["actor", "actress"], limit=limit)
    print(f"      Found {len(credits)} cast members\n")
    
    # Store basic cast info
    store_cast_in_db(title_id, credits)
    
    # Step 2: Get name details and images for each cast member
    print("[2/3] Fetching name details and headshots...")
    cast_with_details = []
    
    for i, credit in enumerate(credits, 1):
        name_obj = credit.get("name", {})
        name_id = name_obj.get("id")
        actor_name = name_obj.get('displayName', 'Unknown')
        
        if not name_id:
            continue
        
        print(f"      [{i}/{len(credits)}] {actor_name} ({name_id})")
        
        # Get name details
        try:
            name_details = get_name_details(name_id)
            store_name_in_db(name_id, name_details)
        except Exception as e:
            print(f"            Error fetching name details: {e}")
            name_details = {}
        
        # Get images
        try:
            images = get_name_images(name_id, limit=10)
            store_images_in_db(name_id, images)
        except Exception as e:
            print(f"            Error fetching images: {e}")
            images = []
        
        # Get primary image URL
        primary_image_url = None
        if name_details.get("primaryImage"):
            primary_image_url = name_details["primaryImage"].get("url")
        
        # Get TMDB headshots if enabled
        all_headshots = []
        if use_tmdb and TMDB_AVAILABLE and primary_image_url:
            try:
                all_headshots = get_combined_headshots(
                    imdb_headshot_url=primary_image_url,
                    actor_name=actor_name,
                    imdb_id=name_id,
                    max_tmdb_images=max_tmdb_images
                )
                print(f"            Combined {len(all_headshots)} headshots (IMDB + TMDB)")
            except Exception as e:
                print(f"            Error fetching TMDB headshots: {e}")
                all_headshots = [primary_image_url] if primary_image_url else []
        elif primary_image_url:
            all_headshots = [primary_image_url]
        
        cast_member = {
            "name_id": name_id,
            "name": actor_name,
            "category": credit.get("category"),
            "characters": credit.get("characters", []),
            "episode_count": credit.get("episodeCount"),
            "primary_image": name_details.get("primaryImage"),
            "birth_date": name_details.get("birthDate"),
            "birth_location": name_details.get("birthLocation"),
            "primary_professions": name_details.get("primaryProfessions"),
            "images": images,
            "all_headshots": all_headshots,  # IMDB + TMDB URLs for multi-image search
        }
        
        cast_with_details.append(cast_member)
        print(f"            Images: {len(images)} | All Headshots: {len(all_headshots)}")
    
    print(f"\n[3/3] Complete! Cached {len(cast_with_details)} cast members\n")
    
    return cast_with_details


def print_cast_summary(cast_members: list, title_id: str):
    """Print a summary of the cast with headshots."""
    print(f"\n{'='*60}")
    print(f"CAST SUMMARY for {title_id}")
    print(f"{'='*60}\n")
    
    for i, member in enumerate(cast_members, 1):
        print(f"{i}. {member['name']}")
        print(f"   ID: {member['name_id']}")
        print(f"   Category: {member['category']}")
        if member.get('characters'):
            print(f"   Characters: {', '.join(member['characters'])}")
        if member.get('birth_date'):
            year = member['birth_date'].get('year')
            print(f"   Birth Year: {year}")
        
        # Primary image is the curated headshot
        if member.get('primary_image'):
            pi = member['primary_image']
            print(f"   HEADSHOT: {pi.get('url')}")
            if pi.get('width') and pi.get('height'):
                print(f"             {pi.get('width')}x{pi.get('height')}")
        
        # Additional images (for reference, may contain group shots)
        if member.get('images'):
            print(f"   Additional Images: {len(member['images'])} total")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Fetch cast information and headshots from IMDb API"
    )
    parser.add_argument(
        "title_id",
        help="IMDb title ID (e.g., tt0058331 for Mary Poppins)"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=20,
        help="Maximum number of cast members to fetch (default: 20)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Output JSON file path (optional)"
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the cache before fetching"
    )
    parser.add_argument(
        "--use-tmdb",
        action="store_true",
        help="Use TMDB to fetch additional headshots for multi-image search"
    )
    parser.add_argument(
        "--tmdb-images",
        type=int,
        default=2,
        help="Number of TMDB images to fetch per actor (default: 2)"
    )
    
    args = parser.parse_args()
    
    # Clear cache if requested
    if args.clear_cache and CACHE_DB.exists():
        CACHE_DB.unlink()
        print("Cache cleared.\n")
    
    # Initialize cache
    init_cache()
    
    # Fetch cast with images
    cast_members = fetch_cast_with_images(
        args.title_id, 
        limit=args.limit,
        use_tmdb=args.use_tmdb,
        max_tmdb_images=args.tmdb_images
    )
    
    # Print summary
    print_cast_summary(cast_members, args.title_id)
    
    # Save to JSON if requested
    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump({
                "title_id": args.title_id,
                "cast_count": len(cast_members),
                "fetched_at": datetime.now().isoformat(),
                "cast": cast_members
            }, f, indent=2)
        print(f"\nSaved to: {output_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
