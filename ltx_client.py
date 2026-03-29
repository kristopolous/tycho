#!/usr/bin/env python3
"""
ltx_client.py - LTX API integration for Tycho

Handles:
- Image-to-video generation for creating ad spots
- Uploading assets (images/video clips)
"""

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()


@dataclass
class GeneratedVideo:
    """Represents a generated video."""
    video_path: str
    prompt: str
    model: str
    duration: float
    resolution: str


class LTXClient:
    """Wrapper around LTX API for Tycho workflow."""
    
    # API Configuration
    BASE_URL = "https://api.ltx.video/v1"
    
    # Supported models
    MODELS = {
        "fast": "ltx-2-3-fast",
        "pro": "ltx-2-3-pro",
    }
    
    # Supported resolutions
    RESOLUTIONS = [
        "1920x1080",  # Full HD landscape
        "1080x1920",  # Full HD portrait (Instagram/TikTok)
        "1280x720",   # HD landscape
        "720x1280",   # HD portrait
    ]
    
    # Camera motions
    CAMERA_MOTIONS = [
        "static",
        "dolly_in",
        "dolly_out",
        "dolly_left",
        "dolly_right",
        "jib_up",
        "jib_down",
        "focus_shift",
    ]
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("LTX_API_KEY")
        if not self.api_key:
            raise ValueError("LTX_API_KEY not found in .env or environment")
        
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })
    
    def generate_video(
        self,
        image_path: str,
        prompt: str,
        duration: int = 5,
        resolution: str = "1920x1080",
        model: str = "pro",
        fps: int = 24,
        generate_audio: bool = True,
        camera_motion: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> GeneratedVideo:
        """
        Generate a video from an image using LTX.
        
        Args:
            image_path: Path to the source image (first frame)
            prompt: Text description of the animation
            duration: Video duration in seconds (default: 5)
            resolution: Output resolution (default: 1920x1080)
            model: Model to use - "fast" or "pro" (default: "pro")
            fps: Frame rate (default: 24)
            generate_audio: Whether to generate AI audio (default: True)
            camera_motion: Optional camera motion effect
            output_path: Where to save the generated video
        
        Returns:
            GeneratedVideo object with path to the video
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        # Validate parameters
        model_name = self.MODELS.get(model, self.MODELS["pro"])
        if resolution not in self.RESOLUTIONS:
            raise ValueError(f"Resolution must be one of: {self.RESOLUTIONS}")
        if camera_motion and camera_motion not in self.CAMERA_MOTIONS:
            raise ValueError(f"Camera motion must be one of: {self.CAMERA_MOTIONS}")
        
        # Read image and convert to base64 or use file upload
        # For LTX API, we need to upload the image first or use a URL
        image_uri = self._upload_asset(image_path) if self._is_local_file(image_path) else image_path
        
        print(f"[LTX] Generating video with model={model_name}, duration={duration}s")
        print(f"      Prompt: {prompt[:80]}...")
        
        payload = {
            "image_uri": image_uri,
            "prompt": prompt,
            "model": model_name,
            "duration": duration,
            "resolution": resolution,
            "fps": fps,
            "generate_audio": generate_audio,
        }
        
        if camera_motion:
            payload["camera_motion"] = camera_motion
        
        response = self.session.post(
            f"{self.BASE_URL}/image-to-video",
            json=payload,
            timeout=300,  # 5 minute timeout for generation
        )
        
        if response.status_code != 200:
            raise RuntimeError(f"LTX API error: {response.status_code} - {response.text}")
        
        # Response is binary video data
        if output_path is None:
            output_path = f"generated_video_{int(time.time())}.mp4"
        
        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "wb") as f:
            f.write(response.content)
        
        print(f"[LTX] Video saved to: {output_path}")
        
        return GeneratedVideo(
            video_path=output_path,
            prompt=prompt,
            model=model_name,
            duration=duration,
            resolution=resolution,
        )
    
    def generate_video_from_url(
        self,
        image_url: str,
        prompt: str,
        duration: int = 5,
        resolution: str = "1920x1080",
        model: str = "pro",
        output_path: Optional[str] = None,
    ) -> GeneratedVideo:
        """
        Generate a video from an image URL.
        
        Args:
            image_url: Public URL of the source image
            prompt: Text description of the animation
            duration: Video duration in seconds
            resolution: Output resolution
            model: Model to use - "fast" or "pro"
            output_path: Where to save the generated video
        
        Returns:
            GeneratedVideo object
        """
        return self.generate_video(
            image_path=image_url,  # Will be treated as URL
            prompt=prompt,
            duration=duration,
            resolution=resolution,
            model=model,
            output_path=output_path,
        )
    
    def _is_local_file(self, path: str) -> bool:
        """Check if path is a local file."""
        return os.path.exists(path)
    
    def _upload_asset(self, file_path: str) -> str:
        """
        Upload an asset to LTX and return the URI.
        
        Args:
            file_path: Path to the file
        
        Returns:
            Asset URI for use in generation requests
        """
        print(f"[LTX] Uploading asset: {file_path}")
        
        # First, create an upload request
        response = self.session.post(
            f"{self.BASE_URL}/upload/create-upload",
            json={"filename": os.path.basename(file_path)},
        )
        
        if response.status_code != 200:
            raise RuntimeError(f"Failed to create upload: {response.text}")
        
        upload_data = response.json()
        upload_url = upload_data.get("upload_url")
        asset_id = upload_data.get("asset_id")
        
        # Upload the file
        with open(file_path, "rb") as f:
            upload_response = requests.put(upload_url, data=f)
        
        if upload_response.status_code not in (200, 201):
            raise RuntimeError(f"Failed to upload file: {upload_response.text}")
        
        # Return the asset URI
        return f"asset://{asset_id}"
    
    def test_connection(self) -> bool:
        """Test the API connection."""
        try:
            # Make a simple request to verify auth
            response = self.session.get(f"{self.BASE_URL}/models")
            return response.status_code == 200
        except Exception as e:
            print(f"[LTX] Connection test failed: {e}")
            return False


def main():
    """Test the LTX client."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test LTX integration")
    parser.add_argument("--image", type=str, required=True, help="Source image")
    parser.add_argument("--prompt", type=str, default="Subtle animation", help="Animation prompt")
    parser.add_argument("--duration", type=int, default=5, help="Duration in seconds")
    parser.add_argument("--output", type=str, help="Output video path")
    parser.add_argument("--model", choices=["fast", "pro"], default="pro", help="Model to use")
    parser.add_argument("--resolution", choices=LTXClient.RESOLUTIONS, default="1920x1080")
    
    args = parser.parse_args()
    
    client = LTXClient()
    
    if not client.test_connection():
        print("Failed to connect to LTX API. Check your API key.")
        return 1
    
    video = client.generate_video(
        image_path=args.image,
        prompt=args.prompt,
        duration=args.duration,
        resolution=args.resolution,
        model=args.model,
        output_path=args.output,
    )
    
    print(f"\nGenerated: {video.video_path}")
    print(f"  Model: {video.model}")
    print(f"  Duration: {video.duration}s")
    print(f"  Resolution: {video.resolution}")
    
    return 0


if __name__ == "__main__":
    exit(main())
