# Tycho CLI Tools

Command-line interface tools for batch processing video content and managing talent databases.

## Installation

The CLI tools are part of the Tycho project. No additional installation required.

```bash
cd cli/
```

## Available Commands

### batch_process.py

Batch process multiple titles to generate promotional spots for talent.

#### Usage

```bash
python batch_process.py --input jobs.json --output results.json [options]
```

#### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--input`, `-i` | Yes | - | Input JSON file with jobs |
| `--output`, `-o` | Yes | - | Output JSON file for results |
| `--max-actors` | No | 10 | Maximum actors to process per title |
| `--use-tmdb` | No | False | Fetch additional headshots from TMDB |
| `--tmdb-images` | No | 2 | Number of TMDB images per actor |
| `--output-dir` | No | outputs | Output directory for spots |
| `--search-only` | No | False | Search only, don't generate spots |
| `--spot-duration` | No | 15 | Spot duration in seconds |
| `--verbose`, `-v` | No | False | Enable verbose output |

#### Input Format

```json
[
    {
        "imdb": "tt0310917",
        "url": "https://example.com/video1.mp4"
    },
    {
        "imdb": "tt0058331",
        "url": "/local/path/video2.mp4"
    }
]
```

**Fields:**
- `imdb` (string): IMDb title ID (e.g., "tt0310917")
- `url` (string): Video URL or local file path

#### Output Format

```json
{
    "processed_at": "2026-03-29T21:30:00",
    "total_jobs": 2,
    "successful": 1,
    "failed": 1,
    "jobs": [
        {
            "imdb": "tt0310917",
            "url": "https://example.com/video1.mp4",
            "status": "completed",
            "title": "The Crane",
            "talent_count": 3,
            "talent": [
                {
                    "imdb_id": "nm0000179",
                    "name": "Jude Law",
                    "status": "spot_generated",
                    "clips_found": 5,
                    "spot_url": "/path/to/spot.mp4"
                }
            ],
            "spots": [
                {
                    "actor_name": "Jude Law",
                    "spot_url": "/path/to/spot.mp4",
                    "duration": 15,
                    "clips_used": 3
                }
            ],
            "errors": []
        }
    ]
}
```

#### Status Values

**Job Status:**
- `pending`: Job is queued
- `processing`: Currently processing
- `completed`: All talent processed successfully
- `partial`: Some talent processed, some failed
- `failed`: Processing failed

**Talent Status:**
- `pending`: Not yet processed
- `searching`: Running 12Labs search
- `clips_found`: Actor found in video
- `no_clips`: Actor not found in video
- `spot_generated`: Promotional spot created
- `spot_failed`: Spot generation failed
- `error`: Processing error

#### Examples

**Basic batch processing:**
```bash
python batch_process.py --input jobs.json --output results.json
```

**With TMDB for better headshots:**
```bash
python batch_process.py --input jobs.json --output results.json --use-tmdb --tmdb-images 2
```

**Limit actors per title:**
```bash
python batch_process.py --input jobs.json --output results.json --max-actors 5
```

**Search only (no spot generation):**
```bash
python batch_process.py --input jobs.json --output results.json --search-only
```

**Custom spot duration:**
```bash
python batch_process.py --input jobs.json --output results.json --spot-duration 30
```

#### Workflow

1. **Load Jobs**: Reads JSON input file
2. **Fetch Cast**: Gets cast from IMDb for each title
3. **Sync Database**: Ensures talent records with mise-en-scene
4. **Search Video**: Finds talent in video using 12Labs
5. **Generate Spots**: Creates promotional videos (if enabled)
6. **Save Results**: Writes JSON output with all data

#### Error Handling

- Invalid jobs are skipped with a warning
- Failed jobs don't stop batch processing
- Errors are logged in `job.errors` array
- Exit code 1 if any job fails

#### Database Integration

The batch processor automatically:
- Creates/updates talent records
- Generates mise-en-scene via LLM (if missing)
- Syncs images from IMDB and TMDB
- Records harness performance metrics

## Environment Variables

Ensure these are set in your `.env` file:

```bash
TWELVE_LABS_API_KEY=your_key_here
LTX_API_KEY=your_key_here
TMDB_API_KEY=your_key_here
TMDB_READ_ACCESS_TOKEN=your_token_here
OPENROUTER_API_KEY=your_key_here
```

## Troubleshooting

### "No valid jobs found in input file"
- Check JSON format (must be array of objects)
- Ensure each object has `imdb` and `url` fields

### "Could not download video"
- For remote URLs, ensure URL is accessible
- Check network connectivity
- For large files, ensure adequate disk space

### "Spot generation failed"
- Check LTX_API_KEY is valid
- Verify output directory is writable

### Memory issues
- Reduce `--max-actors` to process fewer talent per title
- Process titles one at a time

## See Also

- `../database.py` - Database schema and operations
- `../talent_db.py` - Talent database wrapper
- `../openrouter_client.py` - LLM integration for mise-en-scene
