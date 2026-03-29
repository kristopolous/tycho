// Tycho Frontend Application
// Connects to Tycho API for actor-focused promotional video generation

// Configuration
const API_BASE_URL = 'http://localhost:8000';

// DOM Elements
const imdbInput = document.getElementById('imdbId');
const videoPathInput = document.getElementById('videoPath');
const findContentBtn = document.getElementById('findContent');
const contentDetails = document.getElementById('contentDetails');
const contentTitle = document.getElementById('contentTitle');
const actorsGrid = document.getElementById('actorsGrid');
const generationStatus = document.getElementById('generationStatus');
const statusList = document.getElementById('statusList');

// State
let currentProject = null;
let currentActors = [];

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

async function createProject(imdbId, videoPath = 'coke.mp4') {
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
    const videoPath = videoPathInput.value.trim() || 'coke.mp4';
    if (!imdbId) return;

    try {
        findContentBtn.disabled = true;
        findContentBtn.textContent = 'Fetching Cast...';

        // Fetch cast from IMDb
        const castData = await fetchCastFromIMDB(imdbId);
        
        // Create project (this indexes the video and finds actors)
        findContentBtn.textContent = 'Creating Project...';
        currentProject = await createProject(imdbId, videoPath);

        displayContent(castData, currentProject);
        initializeGeneration(currentProject);

    } catch (error) {
        console.error('Error:', error);
        alert('Error: ' + error.message);
    } finally {
        findContentBtn.disabled = false;
        findContentBtn.textContent = 'Find Content';
    }
}

// Display Functions
function displayContent(castData, project) {
    contentTitle.textContent = `IMDb: ${castData.imdb_title_id} - ${castData.cast_count} Cast Members Found`;

    actorsGrid.innerHTML = castData.cast.map(actor => `
        <div class="actor-card fade-in" data-actor-id="${actor.name_id}">
            <img src="${actor.headshot_url || 'https://via.placeholder.com/300x400?text=No+Image'}" 
                 alt="${actor.name}"
                 onerror="this.src='https://via.placeholder.com/300x400?text=No+Image'">
            <div class="actor-info">
                <h3>${actor.name}</h3>
                <p class="character">${actor.characters?.join(', ') || actor.category}</p>
                ${actor.birth_year ? `<p class="birth-year">Born: ${actor.birth_year}</p>` : ''}
                <button class="generate-btn" 
                        onclick="handleGenerateSpot('${actor.name}', '${actor.name_id}')"
                        ${!actorHasClips(actor.name_id, project) ? 'disabled' : ''}>
                    ${actorHasClips(actor.name_id, project) ? 'Generate Spot' : 'Not Found in Video'}
                </button>
            </div>
        </div>
    `).join('');

    contentDetails.classList.remove('hidden');
    generationStatus.classList.remove('hidden');
}

function actorHasClips(actorId, project) {
    const actor = project.actors?.find(a => a.actor_id === actorId);
    return actor && actor.clips && actor.clips.length > 0;
}

function updateGenerationStatus(actorName, status, message, videoUrl = null) {
    const statusItem = document.querySelector(`[data-actor="${actorName}"]`);
    if (statusItem) {
        const indicator = statusItem.querySelector('.status-indicator');
        const messageEl = statusItem.querySelector('.status-message');
        const actionEl = statusItem.querySelector('.status-action');

        indicator.className = `status-indicator status-${status}`;
        messageEl.textContent = message;

        if (videoUrl) {
            actionEl.innerHTML = `
                <video controls width="100%" style="margin-top: 0.5rem; border-radius: 4px;">
                    <source src="${videoUrl}" type="video/mp4">
                    Your browser does not support video playback.
                </video>
                <a href="${videoUrl}" download class="download-btn" style="display: inline-block; margin-top: 0.5rem;">
                    Download Video
                </a>
            `;
        }
    }
}

function initializeGeneration(project) {
    currentActors = project.actors || [];

    statusList.innerHTML = project.actors.map(actor => `
        <div class="status-item" data-actor="${actor.actor_name}">
            <div class="status-info">
                <div class="status-indicator status-${actor.generated_video ? 'complete' : 'pending'}"></div>
                <span>${actor.actor_name}</span>
            </div>
            <div class="status-content">
                <span class="status-message">
                    ${actor.generated_video ? 'Video generated' : `Found in ${actor.clips?.length || 0} clips`}
                </span>
                <div class="status-action">
                    ${actor.generated_video ? `
                        <video controls width="200" style="margin-top: 0.5rem; border-radius: 4px;">
                            <source src="${getVideoUrl(project.project_id, actor.actor_id)}" type="video/mp4">
                        </video>
                    ` : `
                        <button onclick="handleGenerateSpot('${actor.actor_name}', '${actor.actor_id}')" 
                                class="generate-small-btn">
                            Generate
                        </button>
                    `}
                </div>
            </div>
        </div>
    `).join('');
}

function getVideoUrl(projectId, actorId) {
    return `${API_BASE_URL}/api/projects/${projectId}/video/${actorId}`;
}

// Global function for button clicks
window.handleGenerateSpot = async function(actorName, actorId) {
    if (!currentProject) return;

    try {
        // Update UI to show processing
        updateGenerationStatus(actorName, 'pending', 'Generating video...');

        // Disable the button
        const btn = event.target;
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Generating...';
        }

        // Generate the spot
        const result = await generateSpot(currentProject.project_id, actorName);

        // Update UI with success
        const videoUrl = getVideoUrl(currentProject.project_id, actorId);
        updateGenerationStatus(actorName, 'complete', 'Video generated successfully', videoUrl);

        // Refresh the project data
        currentProject = await getProject(currentProject.project_id);
        initializeGeneration(currentProject);

        // Update the actor card
        const actorCard = document.querySelector(`[data-actor-id="${actorId}"] .generate-btn`);
        if (actorCard) {
            actorCard.textContent = 'Generated!';
            actorCard.disabled = true;
        }

    } catch (error) {
        console.error('Generation error:', error);
        updateGenerationStatus(actorName, 'error', 'Generation failed: ' + error.message);
        
        // Re-enable button
        const btn = event.target;
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Try Again';
        }
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
