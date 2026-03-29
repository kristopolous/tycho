"""
Pytest configuration and fixtures for Tycho API tests
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_project_data():
    """Sample project data for testing."""
    return {
        "project_id": "tycho_tt0058331_20240315_abc12345",
        "source_video": "./content.mp4",
        "source_video_id": "test_video_123",
        "imdb_title_id": "tt0058331",
        "created_at": "2024-03-15T10:30:00",
        "status": "ready",
        "actors": [
            {
                "actor_name": "Marlon Brando",
                "actor_id": "nm0000001",
                "birth_year": 1924,
                "headshot_url": "https://m.media-amazon.com/images/M/MV5BMTg3MDYyMDE5OF5BMl5BanBnXkFtZTcwNjgyNTEzNA@@._V1_.jpg",
                "clips": [
                    {
                        "video_id": "vid123",
                        "start": 123.5,
                        "end": 128.2,
                        "score": 0.95,
                        "actor_name": "Marlon Brando",
                        "actor_id": "nm0000001"
                    }
                ],
                "generated_video": None,
                "voiceover_script": None
            }
        ],
        "metadata": {
            "title": "The Godfather",
            "year": 1972
        },
        "title_text": "The Godfather",
        "title_image_url": "https://example.com/godfather.jpg",
        "harness_name": "nostalgia",
        "platform": "tiktok"
    }


@pytest.fixture
def mock_cast_response():
    """Sample IMDb cast response for testing."""
    return {
        "imdb_title_id": "tt0058331",
        "title": "The Godfather",
        "year": 1972,
        "type": "movie",
        "genres": ["Crime", "Drama"],
        "rating": 9.2,
        "plot": "The aging patriarch of an organized crime dynasty...",
        "poster_url": "https://example.com/poster.jpg",
        "cast_count": 3,
        "cast": [
            {
                "name_id": "nm0000001",
                "name": "Marlon Brando",
                "category": "actor",
                "characters": ["Don Vito Corleone"],
                "birth_year": 1924,
                "headshot_url": "https://m.media-amazon.com/images/M/MV5BMTg3MDYyMDE5OF5BMl5BanBnXkFtZTcwNjgyNTEzNA@@._V1_.jpg"
            },
            {
                "name_id": "nm0000138",
                "name": "Al Pacino",
                "category": "actor",
                "characters": ["Michael Corleone"],
                "birth_year": 1940,
                "headshot_url": "https://m.media-amazon.com/images/M/MV5BMTQzMzg1ODAyNV5BMl5BanBnXkFtZTYwMjAxODQ1._V1_.jpg"
            },
            {
                "name_id": "nm0001812",
                "name": "James Caan",
                "category": "actor",
                "characters": ["Sonny Corleone"],
                "birth_year": 1940,
                "headshot_url": "https://m.media-amazon.com/images/M/MV5BMTI5NjkyNDQ3NV5BMl5BanBnXkFtZTcwNjY5NTQwMg@@._V1_.jpg"
            }
        ]
    }


@pytest.fixture
def create_project_request():
    """Sample create project request body."""
    return {
        "video_path": "./content.mp4",
        "imdb_title_id": "tt0058331",
        "actor_names": ["Marlon Brando"],
        "max_actors": 10,
        "harness_name": "nostalgia",
        "platform": "tiktok"
    }


@pytest.fixture
def generate_spot_request():
    """Sample generate spot request body."""
    return {
        "actor_name": "Marlon Brando",
        "actor_id": "nm0000001",
        "prompt": "Classic crime drama intro",
        "duration": 10,
        "resolution": "1080p",
        "harness_name": "nostalgia",
        "platform": "tiktok"
    }


@pytest.fixture
def export_request():
    """Sample export request body."""
    return {
        "actor_id": "nm0000001",
        "format": "EDL",
        "system": "Avid"
    }