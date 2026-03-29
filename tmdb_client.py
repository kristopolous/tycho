#!/usr/bin/env python3
"""
tmdb_client.py - TMDB API integration for fetching secondary headshots

This module fetches actor images from TMDB as secondary sources for 12Labs search.
"""

import os
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, List

import requests
from dotenv import load_dotenv

load_dotenv()

# API Configuration
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p"

# Cache configuration
CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DB = CACHE_DIR / "tmdb_cache.db"
CACHE_EXPIRY_HOURS = 24


def get_api_token() -> str:
    """Get TMDB read access token from environment."""
    token = os.getenv("TMDB_READ_ACCESS_TOKEN")
    if not token:
        raise ValueError("TMDB_READ_ACCESS_TOKEN not found in .env or environment")
    return token


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
    
    # Table for person images
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS person_images (
            person_id INTEGER PRIMARY KEY,
            name TEXT,
            imdb_id TEXT,
            profile_paths TEXT,  -- JSON array of profile image paths
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    key_str = f"tmdb:{endpoint}:{json.dumps(params or {}, sort_keys=True)}"
    return hashlib.sha256(key_str.encode()).hexdigest()


def get_api_key() -> str:
    """Get TMDB API key from environment."""
    key = os.getenv("TMDB_API_KEY")
    if not key:
        raise ValueError("TMDB_API_KEY not found in .env or environment")
    return key


def make_request(endpoint: str, params: Optional[dict] = None) -> dict:
    """Make API request with caching."""
    key = cache_key(endpoint, params)
    
    # Check cache first
    cached = get_cache(key)
    if cached:
        print(f"[TMDB CACHE] {endpoint}")
        return cached
    
    # Build request - TMDB v3 API uses api_key as query param
    url = f"{BASE_URL}{endpoint}"
    
    # Add API key to params
    request_params = params or {}
    request_params["api_key"] = get_api_key()
    
    print(f"[TMDB API] {url}")
    
    response = requests.get(url, params=request_params, timeout=30)
    response.raise_for_status()
    data = response.json()
    
    # Cache the response
    set_cache(key, data)
    
    return data


def search_person_by_name(name: str) -> Optional[dict]:
    """
    Search for a person by name.
    
    Returns the best match or None if not found.
    """
    response = make_request("/search/person", {
        "query": name,
        "include_adult": "false"
    })
    
    results = response.get("results", [])
    if not results:
        return None
    
    # Return first (best) result
    return results[0]


def get_person_images(person_id: int) -> List[dict]:
    """
    Get profile images for a person.
    
    Returns list of image info dicts with:
    - file_path: path to image (use with IMAGE_BASE_URL)
    - width, height: dimensions
    - aspect_ratio: aspect ratio
    - vote_average: popularity score
    """
    response = make_request(f"/person/{person_id}/images")
    
    profiles = response.get("profiles", [])
    
    # Sort by vote_average (popularity) descending
    profiles.sort(key=lambda x: x.get("vote_average", 0), reverse=True)
    
    return profiles


def get_person_external_ids(person_id: int) -> dict:
    """Get external IDs (IMDB, etc.) for a person."""
    return make_request(f"/person/{person_id}/external_ids")


def build_image_url(file_path: str, size: str = "original") -> str:
    """Build full image URL from file path."""
    return f"{IMAGE_BASE_URL}/{size}{file_path}"


def find_person_by_imdb_id(imdb_id: str) -> Optional[dict]:
    """
    Find a person on TMDB using their IMDB ID.
    
    Note: The /find endpoint requires v4 API which needs different authentication.
    For v3 API, we skip this and rely on name matching.
    
    Returns person info with 'id', 'name', etc., or None if not found.
    """
    # v3 API doesn't support external ID lookup reliably
    # We'll use name search instead
    return None


def get_headshots_for_actor(name: str, imdb_id: Optional[str] = None, 
                            max_images: int = 3) -> List[str]:
    """
    Get headshot URLs from TMDB for an actor.
    
    Args:
        name: Actor name
        imdb_id: Optional IMDB ID (not used with v3 API)
        max_images: Maximum number of headshots to return
    
    Returns:
        List of image URLs (best ones first)
    """
    # Search by name
    person = search_person_by_name(name)
    
    if not person:
        print(f"[TMDB] Could not find person: {name}")
        return []
    
    person_id = person["id"]
    person_name = person.get("name", name)
    
    print(f"[TMDB] Found person: {person_name} (ID: {person_id})")
    
    # Get images
    images = get_person_images(person_id)
    
    if not images:
        print(f"[TMDB] No images found for: {person_name}")
        return []
    
    # Build URLs
    image_urls = []
    for img in images[:max_images]:
        file_path = img.get("file_path")
        if file_path:
            url = build_image_url(file_path, size="original")
            image_urls.append(url)
    
    print(f"[TMDB] Found {len(image_urls)} images for {person_name}")
    
    return image_urls


def get_combined_headshots(imdb_headshot_url: Optional[str], 
                         actor_name: str, 
                         imdb_id: Optional[str] = None,
                         max_tmdb_images: int = 2) -> List[str]:
    """
    Combine IMDB and TMDB headshots for best 12Labs search results.
    
    Args:
        imdb_headshot_url: Primary headshot from IMDB (can be None)
        actor_name: Actor name for TMDB search
        imdb_id: IMDB ID for precise matching
        max_tmdb_images: Number of additional TMDB images to fetch
    
    Returns:
        List of image URLs to use for 12Labs search (IMDB first, then TMDB)
    """
    urls = []
    
    # Add IMDB headshot first
    if imdb_headshot_url:
        urls.append(imdb_headshot_url)
    
    # Get TMDB headshots
    tmdb_urls = get_headshots_for_actor(actor_name, imdb_id, max_images=max_tmdb_images)
    
    # Add TMDB URLs that are different from IMDB
    for url in tmdb_urls:
        if url not in urls:
            urls.append(url)
    
    return urls


if __name__ == "__main__":
    # Test the client
    import argparse
    
    parser = argparse.ArgumentParser(description="Test TMDB integration")
    parser.add_argument("--name", type=str, required=True, help="Actor name")
    parser.add_argument("--imdb-id", type=str, help="IMDB ID (e.g., nm0000179)")
    
    args = parser.parse_args()
    
    # Initialize cache
    init_cache()
    
    print(f"\nSearching for: {args.name}")
    
    # Get combined headshots
    urls = get_combined_headshots(
        imdb_headshot_url=None,
        actor_name=args.name,
        imdb_id=args.imdb_id
    )
    
    print(f"\nFound {len(urls)} headshots:")
    for i, url in enumerate(urls, 1):
        print(f"  {i}. {url}")
