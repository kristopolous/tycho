#!/usr/bin/env python3
"""
talent_db.py - Wrapper for talent and harness database operations

This module provides convenient functions to integrate the database
with the Tycho workflow for tracking talent, images, and harness performance.
"""

from typing import List, Optional, Dict, Any
from database import get_db, Talent, TalentImage, Harness, HarnessPerformance


def get_or_create_talent_from_imdb(
    imdb_id: str,
    name: str,
    tmdb_id: Optional[int] = None,
    birth_year: Optional[int] = None,
    category: str = 'actor',
    primary_professions: Optional[List[str]] = None,
    auto_generate_mise_en_scene: bool = True
) -> Talent:
    """Get or create talent from IMDb data.
    
    Args:
        auto_generate_mise_en_scene: Whether to auto-generate mise-en-scene via LLM
    """
    db = get_db()
    
    # Get popularity from TMDB if available
    popularity = 0.0
    if tmdb_id:
        try:
            from tmdb_client import search_person_by_name
            person = search_person_by_name(name)
            if person:
                popularity = person.get('popularity', 0.0)
        except Exception:
            pass
    
    talent = db.get_or_create_talent(
        imdb_id=imdb_id,
        name=name,
        tmdb_id=tmdb_id,
        birth_year=birth_year,
        category=category,
        primary_professions=primary_professions,
        popularity_score=popularity
    )
    
    # Auto-generate mise-en-scene if needed
    if auto_generate_mise_en_scene and not talent.mise_en_scene:
        try:
            from openrouter_client import get_or_generate_mise_en_scene
            print(f"[TalentDB] Generating mise-en-scene for {name}...")
            mise_en_scene = get_or_generate_mise_en_scene(
                talent_id=talent.id,
                celebrity_name=name,
                force_regenerate=False
            )
            print(f"[TalentDB] Mise-en-scene: {mise_en_scene.get('adjectives', [])}")
        except Exception as e:
            print(f"[TalentDB] Could not generate mise-en-scene: {e}")
    
    return talent


def sync_talent_images(
    talent_id: int,
    imdb_images: Optional[List[Dict]] = None,
    tmdb_images: Optional[List[Dict]] = None
) -> int:
    """
    Sync talent images from IMDB and TMDB sources.
    
    Args:
        talent_id: Database talent ID
        imdb_images: List of image dicts from IMDB API
        tmdb_images: List of image dicts from TMDB API
    
    Returns:
        Number of new images added
    """
    db = get_db()
    added = 0
    
    # Add IMDB images
    if imdb_images:
        for i, img in enumerate(imdb_images):
            if isinstance(img, dict):
                url = img.get('url', '')
                width = img.get('width')
                height = img.get('height')
            else:
                url = str(img)
                width = height = None
            
            if url:
                db.add_talent_image(
                    talent_id=talent_id,
                    source='imdb',
                    url=url,
                    width=width,
                    height=height,
                    is_primary=(i == 0)  # First image is primary
                )
                added += 1
    
    # Add TMDB images
    if tmdb_images:
        for i, img in enumerate(tmdb_images):
            if isinstance(img, dict):
                file_path = img.get('file_path', '')
                if file_path:
                    from tmdb_client import build_image_url
                    url = build_image_url(file_path)
                    width = img.get('width')
                    height = img.get('height')
                    vote_average = img.get('vote_average')
                    
                    db.add_talent_image(
                        talent_id=talent_id,
                        source='tmdb',
                        url=url,
                        width=width,
                        height=height,
                        file_path=file_path,
                        vote_average=vote_average,
                        is_primary=False  # IMDB images are primary by default
                    )
                    added += 1
    
    return added


def get_talent_headshots_for_search(
    imdb_id: str,
    max_images: int = 5,
    prefer_tmdb: bool = False
) -> List[str]:
    """
    Get headshot URLs for 12Labs search.
    
    Args:
        imdb_id: IMDb ID (e.g., 'nm0000179')
        max_images: Maximum number of images to return
        prefer_tmdb: Whether to prioritize TMDB images
    
    Returns:
        List of image URLs
    """
    db = get_db()
    
    # Get talent by IMDB ID
    talent = db.get_talent_by_imdb_id(imdb_id)
    if not talent:
        return []
    
    # Get images from database
    images = db.get_talent_images(talent.id, limit=max_images)
    
    # Sort by preference
    if prefer_tmdb:
        images.sort(key=lambda x: (x.source != 'tmdb', not x.is_primary))
    else:
        images.sort(key=lambda x: (not x.is_primary, x.source != 'imdb'))
    
    return [img.url for img in images[:max_images]]


def get_talent_with_images(
    imdb_id: str,
    max_images: int = 5
) -> Optional[Dict[str, Any]]:
    """
    Get talent info with all images for workflow.
    
    Returns dict with:
    - talent: Talent object
    - headshots: List of image URLs
    - primary_headshot: Primary image URL
    """
    db = get_db()
    
    talent = db.get_talent_by_imdb_id(imdb_id)
    if not talent:
        return None
    
    images = db.get_talent_images(talent.id, limit=max_images)
    headshots = [img.url for img in images]
    primary = next((img.url for img in images if img.is_primary), headshots[0] if headshots else None)
    
    return {
        'talent': talent,
        'headshots': headshots,
        'primary_headshot': primary,
        'image_count': len(images)
    }


def record_search_performance(
    imdb_id: str,
    video_id: str,
    clips_found: int,
    image_count: int,
    avg_confidence: float,
    index_id: Optional[str] = None
) -> bool:
    """
    Record search performance for a talent.
    
    Args:
        imdb_id: IMDb ID of the talent
        video_id: 12Labs video ID
        clips_found: Number of clips found
        image_count: Number of images used for search
        avg_confidence: Average confidence score
        index_id: 12Labs index ID
    
    Returns:
        True if recorded successfully
    """
    db = get_db()
    
    talent = db.get_talent_by_imdb_id(imdb_id)
    if not talent:
        return False
    
    db.record_search(
        talent_id=talent.id,
        video_id=video_id,
        index_id=index_id,
        image_count=image_count,
        clips_found=clips_found,
        avg_confidence=avg_confidence
    )
    
    return True


def record_harness_performance(
    imdb_id: str,
    harness_name: str,
    platform: str,
    clips_found: int = 0,
    avg_clip_score: float = 0.0,
    spots_generated: int = 0,
    spots_successful: int = 0,
    notes: str = ''
) -> bool:
    """
    Record harness performance for a talent-platform combination.
    
    Args:
        imdb_id: IMDb ID of the talent
        harness_name: Name of the harness used
        platform: Platform name (e.g., 'tiktok', 'instagram')
        clips_found: Number of clips found in search
        avg_clip_score: Average clip confidence score
        spots_generated: Number of spots generated
        spots_successful: Number of successful generations
        notes: Additional notes
    
    Returns:
        True if recorded successfully
    """
    db = get_db()
    
    # Get talent
    talent = db.get_talent_by_imdb_id(imdb_id)
    if not talent:
        return False
    
    # Get platform
    platform_obj = db.get_platform_by_name(platform)
    if not platform_obj:
        return False
    
    # Get or create harness
    cursor = db._get_connection().__enter__().cursor()
    cursor.execute(
        "SELECT id FROM harnesses WHERE name = ? AND platform_id = ?",
        (harness_name, platform_obj.id)
    )
    row = cursor.fetchone()
    
    if row:
        harness_id = row[0]
    else:
        # Create default harness
        harness_id = db.create_harness(
            name=harness_name,
            platform_id=platform_obj.id,
            config={}
        )
    
    # Record performance
    db.record_performance(
        talent_id=talent.id,
        harness_id=harness_id,
        platform_id=platform_obj.id,
        clips_found=clips_found,
        avg_clip_score=avg_clip_score,
        spots_generated=spots_generated,
        spots_successful=spots_successful,
        notes=notes
    )
    
    return True


def get_best_harness_for_talent(
    imdb_id: str,
    platform: str,
    min_runs: int = 1
) -> Optional[Dict[str, Any]]:
    """
    Get the best performing harness for a talent on a platform.
    
    Args:
        imdb_id: IMDb ID of the talent
        platform: Platform name
        min_runs: Minimum number of test runs required
    
    Returns:
        Best harness performance dict or None
    """
    db = get_db()
    
    talent = db.get_talent_by_imdb_id(imdb_id)
    if not talent:
        return None
    
    performances = db.get_best_harnesses_for_talent(
        talent_id=talent.id,
        platform_name=platform,
        min_runs=min_runs,
        limit=1
    )
    
    return performances[0] if performances else None


def get_talent_comparison(
    platform: str,
    min_runs: int = 1,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Get comparison of all talents on a platform.
    
    Useful for identifying which talents have best convergence
    and which harnesses work best for different talent types.
    
    Args:
        platform: Platform name
        min_runs: Minimum test runs
        limit: Maximum results
    
    Returns:
        List of talent performance dicts
    """
    db = get_db()
    return db.get_talent_platform_comparison(platform, min_runs, limit)


def get_harness_recommendation(
    imdb_id: str,
    platform: str,
    talent_metadata: Optional[Dict] = None
) -> Optional[str]:
    """
    Get harness recommendation for a talent based on historical data.
    
    This is the key function for harness convergence optimization.
    It considers:
    - Past performance of this talent with different harnesses
    - Performance of similar talents (by age, profession, etc.)
    - Platform-specific best practices
    
    Args:
        imdb_id: IMDb ID of the talent
        platform: Target platform
        talent_metadata: Additional metadata (birth_year, category, etc.)
    
    Returns:
        Recommended harness name or None
    """
    db = get_db()
    
    # Get talent
    talent = db.get_talent_by_imdb_id(imdb_id)
    if not talent:
        return None
    
    # First, check if this talent has been tested before
    best = get_best_harness_for_talent(imdb_id, platform, min_runs=1)
    if best:
        return best['harness_name']
    
    # If no data, use platform defaults
    harnesses = db.get_harnesses_for_platform(platform)
    if harnesses:
        # Return first active harness
        return harnesses[0].name
    
    return None


class TalentImageCache:
    """Convenience class for managing talent images across workflow."""
    
    def __init__(self):
        self.db = get_db()
    
    def ensure_talent_in_db(
        self,
        imdb_data: Dict[str, Any],
        fetch_tmdb: bool = True
    ) -> Dict[str, Any]:
        """
        Ensure talent is in database with images from all sources.
        
        Args:
            imdb_data: Dict with imdb_id, name, birth_date, etc.
            fetch_tmdb: Whether to fetch from TMDB
        
        Returns:
            Dict with talent info and all_headshots list
        """
        imdb_id = imdb_data.get('name_id')
        name = imdb_data.get('name')
        birth_date = imdb_data.get('birth_date')
        birth_year = birth_date.get('year') if isinstance(birth_date, dict) else None
        category = imdb_data.get('category', 'actor')
        professions = imdb_data.get('primary_professions', [])
        
        # Get or create talent
        talent = get_or_create_talent_from_imdb(
            imdb_id=imdb_id,
            name=name,
            birth_year=birth_year,
            category=category,
            primary_professions=professions
        )
        
        # Get existing images
        existing = self.db.get_talent_images(talent.id)
        
        # If no images, sync from sources
        if not existing:
            imdb_images = imdb_data.get('images', [])
            primary_image = imdb_data.get('primary_image', {})
            if primary_image and primary_image not in imdb_images:
                imdb_images.insert(0, primary_image)
            
            tmdb_images = []
            if fetch_tmdb:
                try:
                    from tmdb_client import get_person_images, search_person_by_name
                    person = search_person_by_name(name)
                    if person:
                        # Update talent with TMDB ID
                        self.db.get_or_create_talent(
                            imdb_id=imdb_id,
                            name=name,
                            tmdb_id=person['id'],
                            birth_year=birth_year,
                            category=category,
                            primary_professions=professions
                        )
                        tmdb_images = get_person_images(person['id'])
                except Exception as e:
                    print(f"[TalentDB] Could not fetch TMDB images: {e}")
            
            sync_talent_images(talent.id, imdb_images, tmdb_images)
        
        # Return talent with headshots
        return get_talent_with_images(imdb_id, max_images=10)


if __name__ == "__main__":
    # Test the module
    print("Testing talent_db module...")
    
    # Test talent creation
    talent = get_or_create_talent_from_imdb(
        imdb_id="nm0000206",
        name="Tom Cruise",
        birth_year=1962,
        category="actor",
        primary_professions=["Actor", "Producer"]
    )
    print(f"Created talent: {talent.name} (ID: {talent.id})")
    
    # Test image retrieval
    headshots = get_talent_headshots_for_search("nm0000206", max_images=3)
    print(f"Found {len(headshots)} headshots")
    
    # Test harness recommendation
    harness = get_harness_recommendation("nm0000206", "tiktok")
    print(f"Recommended harness: {harness}")
    
    print("\nModule test complete!")
