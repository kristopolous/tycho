import json
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

class MAMIntegration:
    """Handles metadata connectivity and sidecar generation for MAM/DAM systems."""

    def __init__(self, output_dir: str = "outputs"):
        self.output_dir = Path(output_dir)

    def generate_sidecar_xml(self, project_id: str, actor_data: Dict[str, Any], title_metadata: Dict[str, Any]) -> str:
        """Generate a MAM-compatible XML sidecar (Dalet/Vantage style)."""
        root = ET.Element("MAMMetadata")
        
        # Asset Info
        asset = ET.SubElement(root, "Asset")
        ET.SubElement(asset, "Title").text = title_metadata.get("title", "Unknown")
        ET.SubElement(asset, "IMDbID").text = title_metadata.get("imdb_title_id", "Unknown")
        ET.SubElement(asset, "ProcessedDate").text = datetime.now().isoformat()
        
        # Talent Info
        talent = ET.SubElement(root, "Talent")
        ET.SubElement(talent, "Name").text = actor_data["actor_name"]
        ET.SubElement(talent, "NameID").text = actor_data["actor_id"]
        
        # Clips/Markers
        markers = ET.SubElement(root, "Markers")
        for i, clip in enumerate(actor_data.get("clips", [])):
            marker = ET.SubElement(markers, "Marker")
            ET.SubElement(marker, "ID").text = str(i)
            ET.SubElement(marker, "In").text = str(clip["start"])
            ET.SubElement(marker, "Out").text = str(clip["end"])
            ET.SubElement(marker, "Confidence").text = str(clip.get("score", 0))
            ET.SubElement(marker, "Type").text = "Actor Appearance"

        tree = ET.ElementTree(root)
        export_path = self.output_dir / project_id / f"mam_sidecar_{actor_data['actor_id']}.xml"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        
        tree.write(export_path, encoding="utf-8", xml_declaration=True)
        return str(export_path)

    def push_to_mam_mock(self, system_name: str, asset_path: str, metadata_path: str) -> Dict[str, Any]:
        """Simulate pushing assets to a MAM system (e.g., Dalet, Avid Interplay)."""
        return {
            "status": "success",
            "mam_system": system_name,
            "ingested_asset": Path(asset_path).name,
            "metadata_sync": "complete",
            "mam_asset_id": f"MAM-{datetime.now().strftime('%Y%m%d')}-{Path(asset_path).stem}"
        }
