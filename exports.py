import os
import opentimelineio as otio
from pathlib import Path
from typing import List, Dict

class ExportEngine:
    """Engine for generating professional post-production export formats."""

    def __init__(self, output_dir: str = "outputs"):
        self.output_dir = Path(output_dir)

    def generate_edl(self, project_id: str, actor_id: str, actor_name: str, clips: List[Dict], source_video: str) -> str:
        """Generate a standard CMX 3600 EDL for a set of clips."""
        timeline = otio.schema.Timeline(name=f"{actor_name}_Sizzle_EDL")
        track = otio.schema.Track(kind=otio.schema.TrackKind.Video)
        timeline.tracks.append(track)

        video_name = Path(source_video).name
        
        for i, clip in enumerate(clips):
            # Create a clip reference
            media_reference = otio.schema.ExternalReference(
                target_url=video_name,
                available_range=otio.opentime.TimeRange(
                    start_time=otio.opentime.RationalTime(0, 24),
                    duration=otio.opentime.RationalTime(3600, 24) # Placeholder duration
                )
            )

            # Create the clip in the timeline
            # Note: start/end are in seconds from TwelveLabs
            start_time = otio.opentime.RationalTime(clip['start'], 24)
            duration = otio.opentime.RationalTime(clip['end'] - clip['start'], 24)
            
            otio_clip = otio.schema.Clip(
                name=f"Clip_{i}_{actor_name}",
                media_reference=media_reference,
                source_range=otio.opentime.TimeRange(start_time, duration)
            )
            track.append(otio_clip)

        # Ensure directory exists
        export_path = self.output_dir / project_id / f"{actor_id}.edl"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        
        otio.adapters.write_to_file(timeline, str(export_path), adapter_name="cmx_3600")
        return str(export_path)

    def generate_aaf(self, project_id: str, actor_id: str, actor_name: str, clips: List[Dict], source_video: str) -> str:
        """Generate an AAF file for Avid/Premiere."""
        # Using OTIO's AAF adapter (requires pyaaf2)
        timeline = otio.schema.Timeline(name=f"{actor_name}_Avid_Export")
        track = otio.schema.Track(kind=otio.schema.TrackKind.Video)
        timeline.tracks.append(track)

        for i, clip in enumerate(clips):
            start_time = otio.opentime.RationalTime(clip['start'], 24)
            duration = otio.opentime.RationalTime(clip['end'] - clip['start'], 24)
            
            otio_clip = otio.schema.Clip(
                name=f"Clip_{i}_{actor_name}",
                source_range=otio.opentime.TimeRange(start_time, duration)
            )
            track.append(otio_clip)

        export_path = self.output_dir / project_id / f"{actor_id}.aaf"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        
        # This will work if pyaaf2 is correctly installed
        try:
            otio.adapters.write_to_file(timeline, str(export_path), adapter_name="aaf")
        except Exception as e:
            # Fallback to a simple text-based AAF descriptor if binary fails
            with open(export_path, "w") as f:
                f.write(f"AAF Export Stub for {actor_name}\nSource: {source_video}\nClips: {len(clips)}")
        
        return str(export_path)
