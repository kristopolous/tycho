# Tycho Frontend Integration Guide

## Quick Start

1. **Start the API server:**
   ```bash
   python api.py
   # or
   uvicorn api:app --host 0.0.0.0 --port 8000 --reload
   ```

2. **Open the frontend:**
   ```bash
   open index.html
   # or serve with a simple HTTP server
   python -m http.server 3000
   ```

3. **Access the app:** http://localhost:3000

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│  Frontend   │────▶│  Tycho API  │────▶│ 12Labs API   │
│  (HTML/JS)  │     │  (FastAPI)  │     │ (video search)│
└─────────────┘     └─────────────┘     └──────────────┘
                           │                    │
                           ▼                    ▼
                    ┌──────────────┐     ┌──────────────┐
                    │   LTX API    │     │  IMDb API    │
                    │ (video gen)  │     │  (cast data) │
                    └──────────────┘     └──────────────┘
```

## Frontend Files

| File | Description |
|------|-------------|
| `index.html` | Main HTML structure |
| `app.js` | Frontend logic, API integration |
| `style.css` | Dark theme styling |

## Key Functions

### `fetchCastFromIMDB(imdbId)`
Fetches cast information from IMDb via the API.

### `createProject(imdbId, videoPath)`
Creates a new Tycho project - indexes video and finds actors.

### `generateSpot(projectId, actorName)`
Generates a promotional video for a specific actor.

### `handleGenerateSpot(actorName, actorId)`
Global function called when user clicks "Generate" button.

## API Integration Points

The frontend connects to these API endpoints:

```javascript
const API_BASE_URL = 'http://localhost:8000';

// 1. Fetch cast preview
GET /api/imdb/cast/{imdb_title_id}

// 2. Create project (indexes video, finds actors)
POST /api/projects

// 3. Generate spot for actor
POST /api/projects/{project_id}/generate

// 4. Stream generated video
GET /api/projects/{project_id}/video/{actor_id}
```

## User Flow

1. User enters IMDb ID (e.g., `tt0058331` for Mary Poppins)
2. User specifies video file path (default: `content.mp4`)
3. Frontend fetches cast from IMDb
4. Frontend creates project (video is indexed with 12Labs)
5. Actors found in video are displayed with "Generate Spot" buttons
6. User clicks "Generate" for an actor
7. LTX generates promotional video
8. Video plays inline with download option

## State Management

```javascript
let currentProject = null;  // Current project data
let currentActors = [];     // Actors in current project
```

## Auto-Refresh

The frontend polls the API every 5 seconds to update generation status:

```javascript
setInterval(() => {
    if (currentProject) {
        refreshProjectStatus(currentProject.project_id);
    }
}, 5000);
```

## Styling

The app uses a dark theme with purple accent colors:

```css
--primary: #9E7FFF;      /* Purple */
--secondary: #38bdf8;    /* Blue */
--accent: #f472b6;       /* Pink */
--background: #171717;   /* Dark gray */
--surface: #262626;      /* Card background */
```

## Error Handling

All API calls are wrapped in try-catch blocks with user-friendly alerts:

```javascript
try {
    await generateSpot(projectId, actorName);
} catch (error) {
    updateGenerationStatus(actorName, 'error', 'Generation failed: ' + error.message);
}
```

## Video Playback

Generated videos are streamed from the API:

```html
<video controls width="100%">
    <source src="http://localhost:8000/api/projects/{id}/video/{actor_id}" type="video/mp4">
</video>
```

## CORS

The API is configured to allow all origins for development. For production, update `api.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-domain.com"],
    # ...
)
```

## Testing

### Test with Mary Poppins (1964)
- IMDb ID: `tt0058331`
- Video: `content.mp4`

### Test with known cast
1. Enter `tt0058331` in the IMDb ID field
2. Click "Find Content"
3. Wait for project creation
4. Click "Generate" for any actor found in the video

## Troubleshooting

### "Failed to fetch cast"
- Check API server is running on port 8000
- Verify IMDb API is accessible

### "Video not found"
- Ensure video file exists in the project directory
- Check file path is correct

### CORS errors
- API server must be running
- Check browser console for specific CORS errors

## Next Steps

1. **Add loading states** - Show spinners during API calls
2. **Progress indicators** - Show generation progress
3. **Video thumbnails** - Preview clips before generation
4. **Batch generation** - Generate all actors at once
5. **Export options** - Different resolutions/formats
