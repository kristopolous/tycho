# Tycho Technical Documentation: The Archival Monetization Engine

Tycho is an IMDb-driven orchestration system that automates the discovery, localization, and packaging of archival media assets into high-performance social marketing funnels.

## 1. System Architecture Overview

The Tycho workflow is designed to bridge the gap between structured metadata (IMDb) and unstructured video archives.

```
[IMDb tt_id] → [Orchestrator]
                     ↓
[Metadata Enrichment] ← (IMDb API: Cast, Headshots, Titles)
                     ↓
[Semantic Indexing] ← (TwelveLabs Marengo 3.0 via Bedrock)
                     ↓
[Probabilistic Localization] ← (Visual Search with IMDb Seeds)
                     ↓
[Modular Packaging] ← (LTX Video AI + Modular "Formulas")
                     ↓
[Distribution Assets] → (TikTok, IG, Threads, Creator Kits)
```

## 2. Core Components

### 2.1 IMDb-First Orchestration (`tycho.py`, `get_actors.py`)
Unlike traditional "blind" face detection, Tycho uses IMDb as its ground truth. 
*   **Seed Injection:** By inputting a `tt_id`, the system automatically fetches the full cast list and high-fidelity headshots.
*   **Target Selection:** Media managers can filter for specific stars or let the system automatically process every "Guest Star" who is now a "Name."

### 2.2 Semantic Search Integration (`twelvelabs_client.py`)
Tycho leverages **TwelveLabs Marengo 3.0** (via AWS Bedrock/SaaS) for multimodal video understanding.
*   **Multimodal Search:** We use IMDb headshots as visual queries against the indexed archival video. 
*   **Low-Res Robustness:** Marengo’s embedding-based search is significantly more resilient to the grain, low resolution, and lighting challenges of 1970s/80s archival footage than traditional geometric face-matching.
*   **Temporal Understanding:** The system identifies precise start/end timestamps for every actor's appearance, facilitating automated clip extraction.

### 2.3 Channel & Harness Optimization Model
A core design principle of Tycho is the decoupling of **Discovery** (finding the talent) from the **Harness** (the creative formula) and the **Channel** (the distribution platform).

*   **Distribution Channels:** Define the platform-specific constraints (e.g., **TikTok** 9:16, **Instagram** 1:1, **YouTube** 16:9).
*   **Creative Harnesses:** Defined in `/harnesses`, these JSON formulas specify the "beat sheet" of the asset:
    - **Generative Beats**: AI-generated hooks (LTX) tailored to the strategy (e.g., "Nostalgic" vs "Hype").
    - **Clip Beats**: Specific archival segments selected based on search confidence and "guidance" strings.
*   **Convergence Architecture:** The system is designed to facilitate click-tracking and engagement analysis. By generating multiple **Harness + Channel** variants for a single actor, media managers can identify which "Formula" converges best for specific talent types (e.g., "Action Stars" vs "Character Actors").

### 2.4 Creator Enablement Pipeline
To drive organic traffic, Tycho can be configured to output "Clip Kits."
*   **Automated Curation:** The system selects the top 5 highest-confidence scenes for a star.
*   **Package Delivery:** These clips are bundled with metadata and "Did You Know?" facts from IMDb, ready to be sent to content creators and influencers for organic reviews.

### 2.5 MAM/DAM System Integration
Tycho is designed to operate as a "MAM-Native" service, automating the bridge between deep archives and modern distribution.
*   **Automated Ingestion:** Support for direct ingestion from **MAM/DAM** systems (e.g., Dalet, Vantage) via watch folders or API triggers.
*   **Metadata Round-Tripping:** Every generated asset includes a sidecar XML file (XMP/IPTC compliant) that maps IMDb metadata and TwelveLabs search confidence scores back into the parent MAM.
*   **Direct Export to Production:** Beyond social assets, Tycho can push high-resolution clip sequences directly into **Avid Interplay** or **Adobe Premiere Pro Productions** via the generated AAF/EDL and sidecar metadata.

## 3. Implementation Details

### TwelveLabs + Bedrock Integration
The system uses the TwelveLabs Python SDK to interact with Marengo 3.0.
1.  **Indexing:** Source videos are uploaded and indexed with `visual` and `audio` models enabled.
2.  **Search:** IMDb headshots are passed as `query_media_file` to the `search.query` endpoint.
3.  **Refinement:** Results are deduplicated and ranked to ensure a diverse range of clips (e.g., not just 3 seconds from the same scene).

### Automated Video Assembly
Tycho uses **LTX Video AI** for generative intro/outro bumpers and **FFmpeg** for high-speed concatenation.
*   **Generative Branding:** LTX creates cinematic title cards based on the actor and show name.
*   **Dynamic Voiceover:** Prompts are generated based on IMDb data (e.g., "See [Actor Name] in their early career on [Show Name]").

## 4. Performance Benchmarks

| Operation | Performance Target |
| :--- | :--- |
| **IMDb Enrichment** | ~2 seconds |
| **Video Indexing (45m Ep)** | ~5-8 minutes (Parallelizable) |
| **Actor Search (per Star)** | ~1.5 seconds |
| **Social Asset Generation** | ~30-60 seconds |
| **End-to-End (Ready to Post)** | **< 2 minutes** (once indexed) |

## 5. Setup & Usage

### Prerequisites
- Python 3.9+
- TwelveLabs API Key
- LTX Video API Key
- FFmpeg

### Execution
```bash
# Generate optimized assets for a specific IMDb title
python tycho.py path/to/video.mp4 --imdb-id tt0075532 --generate "Actor Name"
```

The resulting assets will be stored in `outputs/<project_id>/`, organized by platform and harness.
