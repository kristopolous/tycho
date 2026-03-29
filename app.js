// Tycho Frontend Application
// Connects to Tycho API for actor-focused promotional video generation

// Configuration - derive API base URL from current page location
const API_BASE_URL = window.location.origin;

// Default video for testing
const DEFAULT_VIDEO = 'coke.webm';

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
let currentImdbId = null;
let isProcessing = false;  // Prevent duplicate submissions

// Persist state to localStorage
function saveState() {
    if (currentProject) {
        localStorage.setItem('tycho_project', JSON.stringify({
            project: currentProject,
            imdbId: currentImdbId,
            timestamp: Date.now()
        }));
    }
}

// Restore state from localStorage
function restoreState() {
    try {
        const saved = localStorage.getItem('tycho_project');
        if (saved) {
            const data = JSON.parse(saved);
            // Check if state is less than 1 hour old
            if (Date.now() - data.timestamp < 3600000) {
                currentProject = data.project;
                currentImdbId = data.imdbId;
                console.log('Restored project from cache:', data.imdbId);
                return true;
            }
        }
    } catch (e) {
        console.error('Failed to restore state:', e);
    }
    return false;
}

// Process status tracking
function updateProcessStatus(steps) {
    processStatus.classList.remove('hidden');
    processSteps.innerHTML = steps.map((step, i) => `
        <div class="process-step ${step.status}">
            <div class="step-indicator ${step.status}">
                ${step.status === 'active' ? '<div class="spinner-small"></div>' : ''}
            </div>
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
    const response = await fetch(`${API_BASE_URL}/api/imdb/cast/${imdbId}?limit=12`);
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to fetch cast');
    }
    return response.json();
}

async function createProject(imdbId, videoPath = 'content.mp4') {
    const response = await fetch(`${API_BASE_URL}/api/projects`, {
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
    const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/generate`, {
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
    const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}`);
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

    // Prevent duplicate submissions
    if (isProcessing) {
        console.log('Already processing a request, ignoring duplicate click');
        return;
    }

    // Check if we already have a project for this IMDb ID (client-side cache)
    if (currentProject && currentImdbId === imdbId) {
        console.log('Already have project for this IMDb ID, restoring from memory');
        displayContent(await fetchCastFromIMDB(imdbId), currentProject, true);
        return;
    }

    isProcessing = true;
    findContentBtn.disabled = true;
    findContentBtn.textContent = 'Processing...';

    try {
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
        currentImdbId = imdbId;
        
        // Save state
        saveState();
        
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
        isProcessing = false;
        findContentBtn.disabled = false;
        findContentBtn.textContent = 'Find Content';
    }
}

// Display Functions
function displayContent(castData, project, restored = false) {
    // Display title with year only - clean and professional
    const yearInfo = castData.year ? `(${castData.year})` : '';
    
    contentTitle.innerHTML = `
        <div class="title-header">
            <h2>${castData.title} ${yearInfo}</h2>
        </div>
    `;

    // Restore IMDb input if restored from cache
    if (restored && currentImdbId) {
        imdbInput.value = currentImdbId;
        findContentBtn.disabled = false;
    }

    // Get actors found in video for the generation list
    const foundActors = project.actors?.filter(a => a.clips && a.clips.length > 0) || [];
    
    actorsGrid.innerHTML = castData.cast.map(actor => {
        const isFound = foundActors.some(a => a.actor_id === actor.name_id);
        const actorData = foundActors.find(a => a.actor_id === actor.name_id);
        const clipCount = actorData?.clips?.length || 0;
        
        // Generate thumbnail HTML for found actors
        let thumbnailsHtml = '';
        if (isFound && actorData?.clips?.length > 0) {
            const thumbnails = actorData.clips.slice(0, 3).map((clip, i) => 
                `<div class="clip-thumb-wrapper">
                    <img src="/thumbnails/${currentImdbId}_${clip.start.toFixed(1)}.jpg" 
                         class="clip-thumbnail" 
                         alt="Clip ${i + 1}"
                         onerror="this.style.display='none'">
                    <span class="clip-time">${clip.start.toFixed(1)}s - ${clip.end.toFixed(1)}s</span>
                </div>`
            ).join('');
            thumbnailsHtml = `<div class="clip-thumbnails" style="grid-template-columns: repeat(${actorData.clips.length}, 1fr);">${thumbnails}</div>`;
        }
        
        return `
        <div class="actor-card fade-in" data-actor-id="${actor.name_id}">
            <img src="${actor.headshot_url || 'https://via.placeholder.com/300x400?text=No+Image'}" 
                 alt="${actor.name}"
                 onerror="this.src='https://via.placeholder.com/300x400?text=No+Image'">
            <div class="actor-info">
                <h3>${actor.name}</h3>
                <p class="character">${actor.characters?.join(', ') || actor.category}</p>
                ${thumbnailsHtml}
                ${!isFound ? `
                    <p class="not-found">Not found in video</p>
                    <button class="use-different-image-btn" onclick="alert('Feature coming soon: Upload alternate headshot')">
                        Use Different Image
                    </button>
                ` : ''}
                ${isFound && !actorData.generated_video ? `
                    <button class="generate-btn" onclick="handleGenerateSpot('${actor.name}', '${actor.name_id}', ${clipCount})">
                        Generate Spot
                    </button>
                ` : ''}
                ${isFound && actorData.generated_video ? `
                    <div class="video-generated">
                        <span class="success-badge">✓ Spot Generated</span>
                        <video controls width="100%" style="margin-top: 0.5rem; border-radius: 4px;" autoplay>
                            <source src="${getVideoUrl(currentProject.project_id, actor.name_id)}" type="video/mp4">
                        </video>
                    </div>
                ` : ''}
            </div>
        </div>
    `}).join('');

    contentDetails.classList.remove('hidden');
    
    // Hide process status after showing results
    setTimeout(() => {
        processStatus.classList.add('hidden');
    }, 2000);
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
    return `${API_BASE_URL}/api/projects/${projectId}/video/${actorId}`;
}

// Global function for button clicks
window.handleGenerateSpot = async function(actorName, actorId, clipCount) {
    if (!currentProject) return;

    // Find the actor card and update it
    const actorCard = document.querySelector(`[data-actor-id="${actorId}"]`);
    if (!actorCard) return;

    const actorInfo = actorCard.querySelector('.actor-info');
    const originalContent = actorInfo.innerHTML;

    // Show generating state
    actorInfo.innerHTML = `
        <h3>${actorName}</h3>
        <div class="generating-state">
            <div class="spinner"></div>
            <span>Generating spot...</span>
        </div>
    `;

    try {
        // Generate the spot
        const result = await generateSpot(currentProject.project_id, actorName);

        // Refresh the project data
        currentProject = await getProject(currentProject.project_id);
        
        // Re-render with video
        const foundActors = currentProject.actors?.filter(a => a.clips && a.clips.length > 0) || [];
        const actorData = foundActors.find(a => a.actor_id === actorId);
        
        // Save state after successful generation
        saveState();
        
        actorInfo.innerHTML = `
            <h3>${actorName}</h3>
            <p class="character">${actorData?.clips[0]?.actor_name || ''}</p>
            <div class="video-generated">
                <span class="success-badge">✓ Spot Generated</span>
                <video controls width="100%" style="margin-top: 0.5rem; border-radius: 4px;" autoplay>
                    <source src="${getVideoUrl(currentProject.project_id, actorId)}" type="video/mp4">
                </video>
            </div>
        `;

    } catch (error) {
        console.error('Generation error:', error);
        // Restore original content with error
        actorInfo.innerHTML = `
            <h3>${actorName}</h3>
            <p class="error-message">Generation failed: ${error.message}</p>
            <button class="generate-btn" onclick="handleGenerateSpot('${actorName}', '${actorId}', ${clipCount})">
                Try Again
            </button>
        `;
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
