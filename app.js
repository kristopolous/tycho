// Tycho Frontend Application
// Connects to Tycho API for actor-focused promotional video generation

// Configuration
const API_BASE_URL = 'http://localhost:8000';

// Default video for testing (under 5.2 MB limit for 12Labs)
const DEFAULT_VIDEO = 'coke.webm';

// Auto-detect API port if 8000 is not available
async function detectApiPort() {
    const ports = [8000, 8001, 8002, 8003, 8004, 8005];
    for (const port of ports) {
        try {
            const response = await fetch(`http://localhost:${port}/api/health`, { method: 'HEAD' });
            if (response.ok) {
                console.log(`API detected on port ${port}`);
                return `http://localhost:${port}`;
            }
        } catch (e) {
            // Try next port
        }
    }
    return 'http://localhost:8000'; // Default fallback
}

// Initialize API URL on load
detectApiPort().then(url => {
    window.API_BASE_URL = url;
});

// DOM Elements
const imdbInput = document.getElementById('imdbId');
const videoPathInput = document.getElementById('videoPath');
const findContentBtn = document.getElementById('findContent');
const contentDetails = document.getElementById('contentDetails');
const contentTitle = document.getElementById('contentTitle');
const actorsGrid = document.getElementById('actorsGrid');
const generationStatus = document.getElementById('generationStatus');
const statusList = document.getElementById('statusList');
const processStatus = document.getElementById('processStatus');
const processSteps = document.getElementById('processSteps');

// State
let currentProject = null;
let currentActors = [];

// Process status tracking
function updateProcessStatus(steps) {
    processStatus.classList.remove('hidden');
    processSteps.innerHTML = steps.map((step, i) => `
        <div class="process-step ${step.status}">
            <div class="step-indicator ${step.status}"></div>
            <span class="step-text">${step.text}</span>
            ${step.detail ? `<span class="step-detail">${step.detail}</span>` : ''}
        </div>
    `).join('');
}

// Event Listeners
findContentBtn.addEventListener('click', handleContentSearch);
imdbInput.addEventListener('input', validateImdbId);
imdbInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && findContentBtn.disabled === false) {
        handleContentSearch();
    }
});

// Validation
function validateImdbId(event) {
    const value = event.target.value.trim();
    const isValid = /^tt\d+$/.test(value);
    findContentBtn.disabled = !isValid;

    if (value && !isValid) {
        imdbInput.setCustomValidity('Please enter a valid IMDB ID (e.g., tt0111161)');
    } else {
        imdbInput.setCustomValidity('');
    }
}

// API Functions
async function fetchCastFromIMDB(imdbId) {
    const baseUrl = window.API_BASE_URL || API_BASE_URL;
    const response = await fetch(`${baseUrl}/api/imdb/cast/${imdbId}?limit=12`);
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to fetch cast');
    }
    return response.json();
}

async function createProject(imdbId, videoPath = 'content.mp4') {
    const baseUrl = window.API_BASE_URL || API_BASE_URL;
    const response = await fetch(`${baseUrl}/api/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            video_path: videoPath,
            imdb_title_id: imdbId,
            max_actors: 10,
        }),
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to create project');
    }
    return response.json();
}

async function generateSpot(projectId, actorName, duration = 10) {
    const baseUrl = window.API_BASE_URL || API_BASE_URL;
    const response = await fetch(`${baseUrl}/api/projects/${projectId}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            actor_name: actorName,
            duration: duration,
            resolution: '1920x1080',
        }),
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to generate spot');
    }
    return response.json();
}

async function getProject(projectId) {
    const baseUrl = window.API_BASE_URL || API_BASE_URL;
    const response = await fetch(`${baseUrl}/api/projects/${projectId}`);
    if (!response.ok) {
        throw new Error('Failed to fetch project');
    }
    return response.json();
}

// Content Search
async function handleContentSearch() {
    const imdbId = imdbInput.value.trim();
    const videoPath = videoPathInput.value.trim() || DEFAULT_VIDEO;
    if (!imdbId) return;

    try {
        findContentBtn.disabled = true;
        
        // Show process status
        updateProcessStatus([
            { status: 'active', text: 'Fetching cast from IMDb...', detail: '' },
            { status: 'pending', text: 'Creating video index', detail: '' },
            { status: 'pending', text: 'Searching for actors in video', detail: '' },
        ]);

        // Fetch cast from IMDb
        const castData = await fetchCastFromIMDB(imdbId);
        
        updateProcessStatus([
            { status: 'complete', text: 'Fetching cast from IMDb...', detail: `Found ${castData.cast_count} actors with photos` },
            { status: 'active', text: 'Creating video index', detail: '' },
            { status: 'pending', text: 'Searching for actors in video', detail: '' },
        ]);

        // Create project (this indexes the video and finds actors)
        currentProject = await createProject(imdbId, videoPath);
        
        updateProcessStatus([
            { status: 'complete', text: 'Fetching cast from IMDb...', detail: `Found ${castData.cast_count} actors with photos` },
            { status: 'complete', text: 'Video indexed', detail: '' },
            { status: 'complete', text: 'Search complete', detail: `${currentProject.actors.filter(a => a.clips?.length > 0).length} actors found in video` },
        ]);

        displayContent(castData, currentProject);

    } catch (error) {
        console.error('Error:', error);
        alert('Error: ' + error.message);
        updateProcessStatus([
            { status: 'error', text: 'Error: ' + error.message, detail: '' },
        ]);
    } finally {
        findContentBtn.disabled = false;
        findContentBtn.textContent = 'Find Content';
    }
}

// Display Functions
function displayContent(castData, project) {
    // Display title with year only - clean and professional
    const yearInfo = castData.year ? `(${castData.year})` : '';
    
    contentTitle.innerHTML = `
        <div class="title-header">
            <h2>${castData.title} ${yearInfo}</h2>
        </div>
    `;

    actorsGrid.innerHTML = castData.cast.map(actor => {
        const clipCount = getActorClipCount(actor.name_id, project);
        const isFound = clipCount > 0;
        
        return `
        <div class="actor-card fade-in" data-actor-id="${actor.name_id}">
            <img src="${actor.headshot_url || 'https://via.placeholder.com/300x400?text=No+Image'}" 
                 alt="${actor.name}"
                 onerror="this.src='https://via.placeholder.com/300x400?text=No+Image'">
            <div class="actor-info">
                <h3>${actor.name}</h3>
                <p class="character">${actor.characters?.join(', ') || actor.category}</p>
                ${actor.birth_year ? `<p class="birth-year">Born: ${actor.birth_year}</p>` : ''}
                ${!isFound ? `<p class="not-found">Not found in video</p>` : ''}
            </div>
        </div>
    `}).join('');

    contentDetails.classList.remove('hidden');
    generationStatus.classList.remove('hidden');
    
    // Initialize status list with actors found in video
    initializeGeneration(project);
}

function actorHasClips(actorId, project) {
    const actor = project.actors?.find(a => a.actor_id === actorId);
    return actor && actor.clips && actor.clips.length > 0;
}

function getActorClipCount(actorId, project) {
    const actor = project.actors?.find(a => a.actor_id === actorId);
    return actor ? (actor.clips?.length || 0) : 0;
}

function updateGenerationStatus(actorName, status, message, videoUrl = null) {
    const statusItem = document.querySelector(`[data-actor="${actorName}"]`);
    if (statusItem) {
        const indicator = statusItem.querySelector('.status-indicator');
        const clipCountEl = statusItem.querySelector('.clip-count');
        const actionEl = statusItem.querySelector('.status-action');

        indicator.className = `status-indicator status-${status}`;
        
        if (status === 'pending') {
            // Show generating message
            if (clipCountEl) {
                clipCountEl.textContent = message;
                clipCountEl.className = 'clip-count generating';
            }
            // Disable button during generation
            const btn = actionEl.querySelector('button');
            if (btn) {
                btn.disabled = true;
                btn.textContent = 'Generating...';
            }
        } else if (status === 'complete' && videoUrl) {
            // Show video player
            actionEl.innerHTML = `
                <video controls width="240" style="border-radius: 4px;">
                    <source src="${videoUrl}" type="video/mp4">
                </video>
            `;
        } else if (status === 'error') {
            // Show error and retry button
            if (clipCountEl) {
                clipCountEl.textContent = message;
                clipCountEl.className = 'clip-count error';
            }
            actionEl.innerHTML = `
                <button onclick="handleGenerateSpot('${actorName}', '${actorName}')" 
                        class="generate-btn status-generate-btn">
                    Try Again
                </button>
            `;
        }
    }
}

function initializeGeneration(project) {
    currentActors = project.actors || [];

    // Only show actors who were found in the video (have clips)
    const foundActors = project.actors.filter(actor => actor.clips && actor.clips.length > 0);
    
    if (foundActors.length === 0) {
        statusList.innerHTML = `
            <div class="status-item status-complete">
                <div class="status-info">
                    <div class="status-indicator status-complete"></div>
                    <span>No actors found in video. Try a different title or video.</span>
                </div>
            </div>
        `;
        return;
    }

    statusList.innerHTML = foundActors.map(actor => `
        <div class="status-item" data-actor="${actor.actor_name}">
            <div class="status-info">
                <div class="status-indicator status-${actor.generated_video ? 'complete' : 'pending'}"></div>
                <div class="actor-status-content">
                    <span class="actor-name">${actor.actor_name}</span>
                    <span class="clip-count">Found in ${actor.clips.length} clip${actor.clips.length > 1 ? 's' : ''}</span>
                </div>
            </div>
            <div class="status-action">
                ${actor.generated_video ? `
                    <video controls width="240" style="border-radius: 4px;">
                        <source src="${getVideoUrl(project.project_id, actor.actor_id)}" type="video/mp4">
                    </video>
                ` : `
                    <button onclick="handleGenerateSpot('${actor.actor_name}', '${actor.actor_id}')" 
                            class="generate-btn status-generate-btn">
                        Generate Spot
                    </button>
                `}
            </div>
        </div>
    `).join('');
}

function getVideoUrl(projectId, actorId) {
    const baseUrl = window.API_BASE_URL || API_BASE_URL;
    return `${baseUrl}/api/projects/${projectId}/video/${actorId}`;
}

// Global function for button clicks
window.handleGenerateSpot = async function(actorName, actorId) {
    if (!currentProject) return;

    try {
        // Update UI to show processing
        updateGenerationStatus(actorName, 'pending', 'Generating video...');

        // Generate the spot
        const result = await generateSpot(currentProject.project_id, actorName);

        // Update UI with success
        const videoUrl = getVideoUrl(currentProject.project_id, actorId);
        updateGenerationStatus(actorName, 'complete', 'Video generated successfully', videoUrl);

        // Refresh the project data
        currentProject = await getProject(currentProject.project_id);
        initializeGeneration(currentProject);

    } catch (error) {
        console.error('Generation error:', error);
        updateGenerationStatus(actorName, 'error', 'Generation failed: ' + error.message);
    }
};

// Auto-refresh for long-running generations
async function refreshProjectStatus(projectId) {
    try {
        const project = await getProject(projectId);
        if (project !== currentProject) {
            currentProject = project;
            initializeGeneration(project);
        }
    } catch (error) {
        console.error('Refresh error:', error);
    }
}

// Poll for updates every 5 seconds if there's an active project
setInterval(() => {
    if (currentProject) {
        refreshProjectStatus(currentProject.project_id);
    }
}, 5000);
