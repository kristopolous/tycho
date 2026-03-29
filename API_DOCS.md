# Tycho API Documentation

**Base URL:** `http://localhost:8000`

**API Version:** 1.0.0

## Overview

The Tycho API enables creating actor-focused promotional videos from archival content. It integrates with:
- **IMDb API** (via imdbapi.dev) - Cast information and headshots
- **12Labs API** - Visual search to find actors in videos
- **LTX API** - AI video generation for promotional spots

## Authentication

Currently, the API does not require authentication. For production use, add API key validation.

## Quick Start

```bash
# Start the API server
python api.py

# Or with uvicorn directly
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

---

## Endpoints

### Health Check

#### `GET /`

Basic health check.

**Response:**
```json
{
  "message": "Tycho API is running",
  "success": true
}
```

#### `GET /api/health`

API health check endpoint.

**Response:**
```json
{
  "message": "OK",
  "success": true
}
```

---

### Projects

#### `POST /api/projects`

Create a new Tycho project. This initiates the full workflow:
1. Fetches cast from IMDb
2. Indexes the video with 12Labs
3. Searches for each actor in the video using their headshot

**Request Body:**
```json
{
  "video_path": "coke.mp4",
  "imdb_title_id": "tt0058331",
  "actor_names": null,
  "max_actors": 10,
  "index_name": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `video_path` | string | Yes | Path to source video file |
| `imdb_title_id` | string | Yes | IMDb title ID (e.g., `tt0058331`) |
| `actor_names` | string[] | No | Specific actor names to focus on |
| `max_actors` | integer | No | Maximum actors to process (default: 10) |
| `index_name` | string | No | Custom 12Labs index name |

**Response (200 OK):**
```json
{
  "project_id": "tycho_tt0058331_20260329_120000_abc123",
  "source_video": "/path/to/coke.mp4",
  "source_video_id": "vid_12345",
  "imdb_title_id": "tt0058331",
  "created_at": "2026-03-29T12:00:00",
  "status": "ready",
  "actors": [
    {
      "actor_name": "Julie Andrews",
      "actor_id": "nm0000267",
      "birth_year": 1935,
      "headshot_url": "https://m.media-amazon.com/images/M/MV5BMjExMTYyODA2Ml5BMl5BanBnXkFtZTYwMTgyMDA0._V1_.jpg",
      "clips": [
        {
          "video_id": "vid_12345",
          "start": 12.5,
          "end": 18.3,
          "score": 0.92,
          "actor_name": "Julie Andrews",
          "actor_id": "nm0000267"
        }
      ],
      "generated_video": null,
      "voiceover_script": null
    }
  ],
  "metadata": {
    "index_name": "tycho_tt0058331",
    "cast_count": 10,
    "actors_found": 5
  }
}
```

---

#### `GET /api/projects`

List all Tycho projects.

**Response (200 OK):**
```json
[
  {
    "project_id": "tycho_tt0058331_20260329_120000_abc123",
    "imdb_title_id": "tt0058331",
    "created_at": "2026-03-29T12:00:00",
    "status": "ready",
    "actors_count": 5,
    "generated_count": 2
  }
]
```

---

#### `GET /api/projects/{project_id}`

Get details for a specific project.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `project_id` | string | The project ID |

**Response (200 OK):**
```json
{
  "project_id": "tycho_tt0058331_20260329_120000_abc123",
  "source_video": "/path/to/coke.mp4",
  "source_video_id": "vid_12345",
  "imdb_title_id": "tt0058331",
  "created_at": "2026-03-29T12:00:00",
  "status": "ready",
  "actors": [...],
  "metadata": {...}
}
```

---

#### `POST /api/projects/{project_id}/generate`

Generate a promotional spot for a specific actor.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `project_id` | string | The project ID |

**Request Body:**
```json
{
  "actor_name": "Julie Andrews",
  "actor_id": "nm0000267",
  "prompt": "Cinematic promotional video with warm nostalgic lighting",
  "duration": 10,
  "resolution": "1920x1080"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `actor_name` | string | Yes | Name of the actor |
| `actor_id` | string | No | IMDb actor ID (alternative lookup) |
| `prompt` | string | No | Custom prompt for video generation |
| `duration` | integer | No | Video duration in seconds (3-30, default: 10) |
| `resolution` | string | No | Output resolution (default: "1920x1080") |

**Response (200 OK):**
```json
{
  "actor_name": "Julie Andrews",
  "actor_id": "nm0000267",
  "birth_year": 1935,
  "headshot_url": "https://...",
  "clips": [...],
  "generated_video": "/path/to/outputs/.../spot_nm0000267.mp4",
  "voiceover_script": "Cinematic promotional video featuring Julie Andrews..."
}
```

---

#### `GET /api/projects/{project_id}/videos`

List all generated videos for a project.

**Response (200 OK):**
```json
{
  "videos": [
    {
      "actor_name": "Julie Andrews",
      "actor_id": "nm0000267",
      "video_path": "/path/to/spot_nm0000267.mp4",
      "video_url": "/videos/tycho_tt0058331_20260329_120000_abc123/spot_nm0000267.mp4",
      "voiceover_script": "Cinematic promotional video featuring..."
    }
  ]
}
```

---

#### `GET /api/projects/{project_id}/video/{actor_id}`

Stream a specific actor's generated video.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `project_id` | string | The project ID |
| `actor_id` | string | The IMDb actor ID (e.g., `nm0000267`) |

**Response:** Video file (MP4)

**Example:**
```bash
curl http://localhost:8000/api/projects/tycho_tt0058331_20260329_120000_abc123/video/nm0000267 \
  --output julie_andrews_spot.mp4
```

---

#### `DELETE /api/projects/{project_id}`

Delete a project and all its assets.

**Response (200 OK):**
```json
{
  "message": "Project tycho_tt0058331_20260329_120000_abc123 deleted",
  "success": true
}
```

---

### IMDb Cast Lookup

#### `GET /api/imdb/cast/{imdb_title_id}`

Fetch cast information from IMDb for a title. Useful for previewing cast before creating a project.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `imdb_title_id` | string | IMDb title ID (e.g., `tt0058331`) |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 20 | Maximum cast members to fetch |

**Response (200 OK):**
```json
{
  "imdb_title_id": "tt0058331",
  "cast_count": 5,
  "cast": [
    {
      "name_id": "nm0000267",
      "name": "Julie Andrews",
      "category": "actress",
      "characters": ["Mary Poppins"],
      "birth_year": 1935,
      "headshot_url": "https://m.media-amazon.com/images/M/MV5BMjExMTYyODA2Ml5BMl5BanBnXkFtZTYwMTgyMDA0._V1_.jpg"
    }
  ]
}
```

---

## Frontend Integration Examples

### Create a Project (React/TypeScript)

```typescript
interface CreateProjectRequest {
  video_path: string;
  imdb_title_id: string;
  actor_names?: string[];
  max_actors?: number;
}

interface Project {
  project_id: string;
  imdb_title_id: string;
  status: 'ready' | 'processing' | 'error';
  actors: ActorSpot[];
}

async function createProject(data: CreateProjectRequest): Promise<Project> {
  const response = await fetch('http://localhost:8000/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail);
  }
  
  return response.json();
}
```

### Generate a Spot

```typescript
async function generateSpot(
  projectId: string, 
  actorName: string
): Promise<void> {
  const response = await fetch(
    `http://localhost:8000/api/projects/${projectId}/generate`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        actor_name: actorName,
        duration: 10,
        resolution: '1920x1080',
      }),
    }
  );
  
  return response.json();
}
```

### List Projects with Polling

```typescript
async function listProjects(): Promise<Project[]> {
  const response = await fetch('http://localhost:8000/api/projects');
  return response.json();
}

// Poll for project status
async function waitForProject(projectId: string, interval = 5000) {
  while (true) {
    const projects = await listProjects();
    const project = projects.find(p => p.project_id === projectId);
    
    if (project?.status === 'ready') {
      return project;
    }
    
    await new Promise(resolve => setTimeout(resolve, interval));
  }
}
```

### Video Player Component

```tsx
function VideoPlayer({ projectId, actorId }: { projectId: string; actorId: string }) {
  const videoUrl = `http://localhost:8000/api/projects/${projectId}/video/${actorId}`;
  
  return (
    <video controls width="100%">
      <source src={videoUrl} type="video/mp4" />
      Your browser does not support video playback.
    </video>
  );
}
```

---

## Error Responses

All errors return a JSON response with the following structure:

```json
{
  "detail": "Error message describing what went wrong",
  "success": false
}
```

**Common HTTP Status Codes:**
| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Bad Request (invalid parameters) |
| 404 | Not Found (project/actor/video not found) |
| 500 | Internal Server Error |

---

## CORS Configuration

The API is configured to allow all origins for development. For production, update the CORS middleware in `api.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend.com"],  # Restrict to your domain
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)
```

---

## Running the Server

### Development Mode (with auto-reload)

```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

### Production Mode

```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --workers 4
```

### With Gunicorn (recommended for production)

```bash
gunicorn api:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

---

## API Schema

The OpenAPI schema is available at:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI JSON:** `http://localhost:8000/openapi.json`
