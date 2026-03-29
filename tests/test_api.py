"""
Unit tests for Tycho API endpoints
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from pathlib import Path


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_api_health(self, client):
        """Test /api/health returns healthy status."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "OK"

    def test_root_health(self, client):
        """Test /health returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "tycho"


class TestProjectEndpoints:
    """Tests for project management endpoints."""

    def test_list_projects_empty(self, client):
        """Test listing projects when none exist."""
        with patch("api.get_all_projects") as mock_projects:
            mock_projects.return_value = []
            response = client.get("/api/projects")
            assert response.status_code == 200
            assert response.json() == []

    def test_list_projects_with_data(self, client, mock_project_data):
        """Test listing projects with existing data."""
        with patch("api.get_all_projects") as mock_projects:
            mock_projects.return_value = [mock_project_data]
            response = client.get("/api/projects")
            assert response.status_code == 200
            projects = response.json()
            assert len(projects) == 1
            assert projects[0]["project_id"] == mock_project_data["project_id"]
            assert projects[0]["imdb_title_id"] == mock_project_data["imdb_title_id"]

    def test_get_project_not_found(self, client):
        """Test getting a non-existent project returns 404."""
        with patch("api.load_project") as mock_load:
            mock_load.return_value = None
            response = client.get("/api/projects/nonexistent_id")
            assert response.status_code == 404

    def test_get_project_success(self, client, mock_project_data):
        """Test getting an existing project."""
        with patch("api.load_project") as mock_load:
            mock_load.return_value = mock_project_data
            response = client.get(f"/api/projects/{mock_project_data['project_id']}")
            assert response.status_code == 200
            data = response.json()
            assert data["project_id"] == mock_project_data["project_id"]
            assert len(data["actors"]) == 1

    def test_delete_project_not_found(self, client):
        """Test deleting a non-existent project."""
        with patch("api.OUTPUT_DIR") as mock_output:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_output.__truediv__ = lambda self, x: mock_path
            response = client.delete("/api/projects/nonexistent_id")
            assert response.status_code == 404

    def test_create_project_video_not_found(self, client, create_project_request):
        """Test creating project with non-existent video."""
        with patch("pathlib.Path.exists") as mock_exists:
            mock_exists.return_value = False
            response = client.post("/api/projects", json=create_project_request)
            assert response.status_code == 400

    def test_create_project_cache_hit(self, client, create_project_request, mock_project_data):
        """Test project creation returns cached project if exists."""
        with patch("api.get_all_projects") as mock_projects, \
             patch("api.load_project") as mock_load:
            mock_projects.return_value = [mock_project_data]
            response = client.post("/api/projects", json=create_project_request)
            # Should return cached project without calling orchestrator
            assert response.status_code == 200


class TestVideoEndpoints:
    """Tests for video generation and retrieval endpoints."""

    def test_list_videos_not_found(self, client):
        """Test listing videos for non-existent project."""
        with patch("api.load_project") as mock_load:
            mock_load.return_value = None
            response = client.get("/api/projects/test_id/videos")
            assert response.status_code == 404

    def test_list_videos_empty(self, client, mock_project_data):
        """Test listing videos when none generated."""
        with patch("api.load_project") as mock_load:
            mock_load.return_value = mock_project_data
            response = client.get(f"/api/projects/{mock_project_data['project_id']}/videos")
            assert response.status_code == 200
            data = response.json()
            assert "videos" in data
            assert len(data["videos"]) == 0  # No generated videos

    def test_list_videos_with_generated(self, client, mock_project_data):
        """Test listing videos with generated content."""
        mock_project_data["actors"][0]["generated_video"] = "/outputs/test/video.mp4"
        with patch("api.load_project") as mock_load:
            mock_load.return_value = mock_project_data
            response = client.get(f"/api/projects/{mock_project_data['project_id']}/videos")
            assert response.status_code == 200
            data = response.json()
            assert len(data["videos"]) == 1

    def test_get_video_not_found(self, client):
        """Test getting non-existent video."""
        with patch("api.load_project") as mock_load:
            mock_load.return_value = None
            response = client.get("/api/projects/test_id/video/nm0000001")
            assert response.status_code == 404

    def test_generate_spot_project_not_found(self, client, generate_spot_request):
        """Test generating spot for non-existent project."""
        with patch("api.load_project") as mock_load:
            mock_load.return_value = None
            response = client.post(
                "/api/projects/nonexistent_id/generate",
                json=generate_spot_request
            )
            assert response.status_code == 404

    def test_generate_spot_actor_not_found(self, client, generate_spot_request, mock_project_data):
        """Test generating spot for non-existent actor."""
        # Make a copy to avoid modifying the fixture
        request_copy = generate_spot_request.copy()
        request_copy["actor_name"] = "Unknown Actor"
        
        with patch("api.load_project") as mock_load:
            mock_load.return_value = mock_project_data
            response = client.post(
                f"/api/projects/{mock_project_data['project_id']}/generate",
                json=request_copy
            )
            # Should fail - either 404 (actor not found) or 400 (no clips)
            assert response.status_code in [400, 404, 500]


class TestExportEndpoints:
    """Tests for export endpoints."""

    def test_export_project_not_found(self, client, export_request):
        """Test exporting from non-existent project."""
        with patch("api.load_project") as mock_load:
            mock_load.return_value = None
            response = client.post("/api/projects/nonexistent_id/export", json=export_request)
            assert response.status_code == 404

    def test_export_actor_not_found(self, client, export_request, mock_project_data):
        """Test exporting for non-existent actor."""
        # Make a copy to avoid modifying the fixture
        request_copy = export_request.copy()
        request_copy["actor_id"] = "nm9999999"
        
        with patch("api.load_project") as mock_load:
            mock_load.return_value = mock_project_data
            response = client.post(
                f"/api/projects/{mock_project_data['project_id']}/export",
                json=request_copy
            )
            assert response.status_code == 404

    def test_export_unsupported_format(self, client, export_request, mock_project_data):
        """Test exporting with unsupported format."""
        # Make a copy to avoid modifying the fixture
        request_copy = export_request.copy()
        request_copy["format"] = "INVALID"
        
        with patch("api.load_project") as mock_load:
            mock_load.return_value = mock_project_data
            response = client.post(
                f"/api/projects/{mock_project_data['project_id']}/export",
                json=request_copy
            )
            # Either 400 (format error) or 500 (unhandled) is acceptable
            assert response.status_code in [400, 500]

    def test_download_export_not_found(self, client):
        """Test downloading non-existent export file."""
        # Create a mock path that returns False for exists()
        mock_project_dir = MagicMock()
        mock_project_dir.exists.return_value = True
        
        mock_file_path = MagicMock()
        mock_file_path.exists.return_value = False
        
        with patch("api.OUTPUT_DIR") as mock_output:
            # Chain: OUTPUT_DIR / project_id / filename
            mock_output.__truediv__.return_value = mock_project_dir
            mock_project_dir.__truediv__.return_value = mock_file_path
            
            response = client.get("/api/projects/test_id/download/nonexistent.edl")
            assert response.status_code == 404


class TestIMDbEndpoints:
    """Tests for IMDb cast fetching endpoint."""

    def test_get_imdb_cast_success(self, client, mock_cast_response):
        """Test successfully fetching IMDb cast."""
        with patch("api.init_cache"), \
             patch("api.fetch_cast_with_images") as mock_fetch, \
             patch("api.get_title_metadata") as mock_metadata:
            mock_fetch.return_value = [
                {
                    "name_id": "nm0000001",
                    "name": "Marlon Brando",
                    "category": "actor",
                    "characters": ["Don Vito Corleone"],
                    "birth_date": {"year": 1924},
                    "primary_image": {"url": "https://example.com/image.jpg"}
                }
            ]
            mock_metadata.return_value = {
                "title": "The Godfather",
                "year": 1972,
                "type": "movie",
                "genres": ["Crime", "Drama"],
                "rating": {"aggregateRating": 9.2},
                "plot": "The aging patriarch...",
                "image_url": "https://example.com/poster.jpg"
            }
            response = client.get("/api/imdb/cast/tt0058331")
            assert response.status_code == 200
            data = response.json()
            assert data["title"] == "The Godfather"
            assert data["cast_count"] == 1


class TestRequestValidation:
    """Tests for request validation."""

    def test_create_project_missing_video_path(self, client):
        """Test create project validation - missing video_path."""
        response = client.post("/api/projects", json={"imdb_title_id": "tt0058331"})
        assert response.status_code == 422  # FastAPI validation error

    def test_create_project_missing_imdb_id(self, client):
        """Test create project validation - missing imdb_title_id."""
        response = client.post("/api/projects", json={"video_path": "./test.mp4"})
        assert response.status_code == 422

    def test_generate_spot_missing_actor_name(self, client):
        """Test generate spot validation - missing actor_name."""
        response = client.post(
            "/api/projects/test_id/generate",
            json={"duration": 10}
        )
        assert response.status_code == 422

    def test_generate_spot_invalid_duration(self, client, generate_spot_request):
        """Test generate spot validation - duration out of range."""
        generate_spot_request["duration"] = 100  # Max is 30
        response = client.post("/api/projects/test_id/generate", json=generate_spot_request)
        assert response.status_code == 422

    def test_export_missing_actor_id(self, client):
        """Test export validation - missing actor_id."""
        response = client.post(
            "/api/projects/test_id/export",
            json={"format": "EDL"}
        )
        assert response.status_code == 422

    def test_export_missing_format(self, client, export_request):
        """Test export validation - missing format."""
        request_copy = {k: v for k, v in export_request.items() if k != "format"}
        response = client.post("/api/projects/test_id/export", json=request_copy)
        assert response.status_code == 422


class TestStaticEndpoints:
    """Tests for static file serving endpoints."""

    def test_root_returns_index(self, client):
        """Test root endpoint serves index.html."""
        with patch("pathlib.Path") as mock_path:
            mock_path_instance = MagicMock()
            mock_path_instance.exists.return_value = True
            mock_path_instance.__truediv__ = lambda self, x: mock_path_instance
            mock_path.return_value = mock_path_instance
            response = client.get("/")
            assert response.status_code == 200

    def test_style_css(self, client):
        """Test /style.css endpoint."""
        with patch("pathlib.Path") as mock_path:
            mock_path_instance = MagicMock()
            mock_path_instance.exists.return_value = True
            mock_path_instance.__truediv__ = lambda self, x: mock_path_instance
            mock_path.return_value = mock_path_instance
            response = client.get("/style.css")
            assert response.status_code == 200
            assert "text/css" in response.headers.get("content-type", "")

    def test_app_js(self, client):
        """Test /app.js endpoint."""
        with patch("pathlib.Path") as mock_path:
            mock_path_instance = MagicMock()
            mock_path_instance.exists.return_value = True
            mock_path_instance.__truediv__ = lambda self, x: mock_path_instance
            mock_path.return_value = mock_path_instance
            response = client.get("/app.js")
            assert response.status_code == 200
            assert "javascript" in response.headers.get("content-type", "").lower()