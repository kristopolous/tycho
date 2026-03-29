// Tycho Frontend Application
// Connects to Tycho API for actor-focused promotional video generation

// Configuration - derive API base URL from current page location
const API_BASE_URL = window.location.origin;

// Default video for testing
const DEFAULT_VIDEO = 'content.mp4';

// DOM Elements
const imdbInput = document.getElementById('imdbId');
const videoPathInput = document.getElementById('videoPath');
const videoUploadInput = document.getElementById('videoUpload');
const uploadLabel = document.querySelector('.upload-btn-label');
const findContentBtn = document.getElementById('findContent');
const contentDetails = document.getElementById('contentDetails');
const contentTitle = document.getElementById('contentTitle');
const actorsGrid = document.getElementById('actorsGrid');
const processStatus = document.getElementById('processStatus');
const processSteps = document.getElementById('processSteps');

// State
let currentProject = null;
let currentImdbId = null;
let isProcessing = false;
let selectedFile = null;

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
            if (Date.now() - data.timestamp < 3600000) {
                currentProject = data.project;
                currentImdbId = data.imdbId;
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
    processSteps.innerHTML = steps.map(step => `
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

// Handle Video Upload Selection
videoUploadInput?.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        selectedFile = e.target.files[0];
        uploadLabel?.classList.add('file-selected');
        const span = uploadLabel?.querySelector('span');
        if (span) span.textContent = 'Selected';
        videoPathInput.value = selectedFile.name;
        videoPathInput.disabled = true;
    }
});

// Harness Library Interactivity
document.querySelectorAll('.harness-card').forEach(card => {
    card.addEventListener('click', () => {
        document.querySelectorAll('.harness-card').forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');
        const harnessSelect = document.getElementById('harnessSelect');
        if (harnessSelect) harnessSelect.value = card.dataset.harness;
    });
});

// Initialize first harness as selected
document.querySelector('.harness-card[data-harness="nostalgia"]')?.classList.add('selected');

imdbInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !findContentBtn.disabled) {
        handleContentSearch();
    }
});

// Validation
function validateImdbId(event) {
    const value = event.target.value.trim();
    const isValid = /^tt\d+$/.test(value);
    findContentBtn.disabled = !isValid;
}

// API Functions
async function fetchCastFromIMDB(imdbId) {
    const response = await fetch(`${API_BASE_URL}/api/imdb/cast/${imdbId}?limit=12`);
    if (!response.ok) throw new Error('Failed to fetch cast');
    return response.json();
}

async function createProject(imdbId, videoSource) {
    let response;
    
    // Note: Since we are restricted from editing Python, we MUST send as JSON
    // for compatibility with the existing CreateProjectRequest model.
    // If it's a File, we would normally use FormData, but we stick to the 
    // current API spec which expects a string 'video_path'.
    
    const pathValue = (videoSource instanceof File) ? videoSource.name : videoSource;

    response = await fetch(`${API_BASE_URL}/api/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            video_path: pathValue,
            imdb_title_id: imdbId,
            max_actors: 10,
        }),
    });
    
    if (!response.ok) throw new Error('Failed to create project');
    return response.json();
}

async function generateSpot(projectId, actorName) {
    const channel = document.getElementById('channelSelect')?.value || 'tiktok';
    const harness = document.getElementById('harnessSelect')?.value || 'nostalgia';
    
    const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            actor_name: actorName,
            channel: channel,
            harness: harness,
        }),
    });
    if (!response.ok) throw new Error('Failed to generate spot');
    return response.json();
}

async function getProject(projectId) {
    const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}`);
    if (!response.ok) throw new Error('Failed to fetch project');
    return response.json();
}

function getVideoUrl(projectId, actorId) {
    return `${API_BASE_URL}/api/projects/${projectId}/video/${actorId}`;
}

// Content Search
async function handleContentSearch() {
    const imdbId = imdbInput.value.trim();
    const videoSource = selectedFile || videoPathInput.value.trim() || DEFAULT_VIDEO;
    if (!imdbId || isProcessing) return;

    isProcessing = true;
    findContentBtn.disabled = true;

    try {
        updateProcessStatus([
            { status: 'active', text: 'Fetching cast from IMDb...', detail: '' },
            { status: 'pending', text: 'Creating video index', detail: '' },
            { status: 'pending', text: 'Searching for actors in video', detail: '' },
        ]);

        const castData = await fetchCastFromIMDB(imdbId);
        
        updateProcessStatus([
            { status: 'complete', text: 'Fetching cast from IMDb...', detail: `Found ${castData.cast_count} actors` },
            { status: 'active', text: 'Creating video index', detail: '' },
            { status: 'pending', text: 'Searching for actors in video', detail: '' },
        ]);

        currentProject = await createProject(imdbId, videoSource);
        currentImdbId = imdbId;
        saveState();
        
        updateProcessStatus([
            { status: 'complete', text: 'Fetching cast from IMDb...', detail: `Found ${castData.cast_count} actors` },
            { status: 'complete', text: 'Video indexed', detail: '' },
            { status: 'complete', text: 'Search complete', detail: `${currentProject.actors.filter(a => a.clips?.length > 0).length} actors found` },
        ]);

        displayContent(castData, currentProject);

    } catch (error) {
        console.error(error);
        alert('Error: ' + error.message);
    } finally {
        isProcessing = false;
        findContentBtn.disabled = false;
    }
}

// Display Functions
function displayContent(castData, project) {
    contentTitle.innerHTML = `<div class="title-header"><h2>${castData.title}</h2></div>`;
    const foundActors = project.actors?.filter(a => a.clips && a.clips.length > 0) || [];
    
    actorsGrid.innerHTML = castData.cast.map(actor => {
        const actorData = foundActors.find(a => a.actor_id === actor.name_id);
        const isFound = !!actorData;
        
        let thumbnailsHtml = '';
        if (isFound) {
            const thumbnails = actorData.clips.slice(0, 3).map(clip => 
                `<div class="clip-thumb-wrapper">
                    <img src="/thumbnails/${castData.imdb_title_id}_${clip.start.toFixed(1)}.jpg" class="clip-thumbnail" onerror="this.style.display='none'">
                    <span class="clip-time">${clip.start.toFixed(1)}s - ${clip.end.toFixed(1)}s</span>
                </div>`
            ).join('');
            thumbnailsHtml = `<div class="clip-thumbnails">${thumbnails}</div>`;
        }

        // Multi-source Reference Images
        let referenceImagesHtml = '';
        const headshots = actor.all_headshots || (actor.headshot_url ? [actor.headshot_url] : []);
        if (headshots.length > 0) {
            const images = headshots.map((url, i) => `
                <div class="ref-image-wrapper">
                    <img src="${url}" class="ref-image" title="${i === 0 ? 'IMDb' : 'TMDB'} Source">
                    <span class="ref-source-tag">${i === 0 ? 'IMDb' : 'TMDB'}</span>
                </div>
            `).join('');
            referenceImagesHtml = `<div class="reference-images-strip">${images}</div>`;
        }
        
        return `
        <div class="actor-card fade-in" data-actor-id="${actor.name_id}">
            <img src="${actor.headshot_url || 'https://via.placeholder.com/300x400?text=No+Image'}" onerror="this.src='https://via.placeholder.com/300x400?text=No+Image'}" class="main-headshot">
            <div class="actor-info">
                <h3>${actor.name}</h3>
                <p class="character">${actor.characters?.join(', ') || ''}</p>
                
                <div class="ref-section-label">Reference Sources</div>
                ${referenceImagesHtml}

                <div class="ref-section-label">Discovered Clips</div>
                ${thumbnailsHtml}
                ${isFound ? `
                    <div class="action-area">
                        ${actorData.generated_video ? `
                            <div class="video-generated">
                                <span class="success-badge">✓ Spot Generated</span>
                                <video controls width="100%" style="margin-top: 0.5rem; border-radius: 4px;">
                                    <source src="${getVideoUrl(project.project_id, actor.name_id)}" type="video/mp4">
                                </video>
                            </div>
                        ` : `
                            <button class="generate-btn" onclick="handleGenerateSpot('${actor.name}', '${actor.name_id}')">Generate Spot</button>
                        `}
                        <div class="export-controls">
                            <select id="exportFormat_${actor.name_id}" class="export-select">
                                <option value="EDL">EDL</option>
                                <option value="AAF">AAF</option>
                                <option value="MAM">MAM</option>
                            </select>
                            <button class="export-dl-btn" onclick="handleExport('${actor.name_id}')">Download</button>
                        </div>
                    </div>
                ` : '<p class="not-found">Not found in video</p>'}
            </div>
        </div>`;
    }).join('');

    contentDetails.classList.remove('hidden');
    setTimeout(() => processStatus.classList.add('hidden'), 2000);
}

// Global Handlers
window.handleGenerateSpot = async function(actorName, actorId) {
    if (!currentProject) return;
    const actorCard = document.querySelector(`[data-actor-id="${actorId}"]`);
    const actionArea = actorCard?.querySelector('.action-area');
    if (!actionArea) return;
    
    const originalContent = actionArea.innerHTML;
    actionArea.innerHTML = `<div class="generating-state"><div class="spinner"></div><span>Generating...</span></div>`;

    try {
        await generateSpot(currentProject.project_id, actorName);
        currentProject = await getProject(currentProject.project_id);
        const actorData = currentProject.actors.find(a => a.actor_id === actorId);
        
        actionArea.innerHTML = `
            <div class="video-generated">
                <span class="success-badge">✓ Spot Generated</span>
                <video controls width="100%" style="margin-top: 0.5rem; border-radius: 4px;" autoplay>
                    <source src="${getVideoUrl(currentProject.project_id, actorId)}" type="video/mp4">
                </video>
            </div>
            <div class="export-controls">
                <select id="exportFormat_${actorId}" class="export-select">
                    <option value="EDL">EDL</option>
                    <option value="AAF">AAF</option>
                    <option value="MAM">MAM</option>
                </select>
                <button class="export-dl-btn" onclick="handleExport('${actorId}')">Download</button>
            </div>`;
    } catch (error) {
        console.error(error);
        actionArea.innerHTML = originalContent;
    }
};

window.handleExport = async function(actorId) {
    if (!currentProject) return;
    const format = document.getElementById(`exportFormat_${actorId}`).value;
    const btn = event.target;
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '...';

    try {
        const response = await fetch(`${API_BASE_URL}/api/projects/${currentProject.project_id}/export`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ actor_id: actorId, format: format }),
        });
        const result = await response.json();
        window.open(`${API_BASE_URL}${result.file_url}`, '_blank');
        btn.textContent = '✓';
        setTimeout(() => { 
            btn.textContent = originalText; 
            btn.disabled = false; 
        }, 2000);
    } catch (error) {
        console.error(error);
        btn.textContent = 'Err';
        setTimeout(() => {
            btn.textContent = originalText;
            btn.disabled = false;
        }, 2000);
    }
};

// Initial state restore
if (restoreState()) {
    // Note: We don't auto-trigger search to avoid unexpected API calls on load
    // but the state is ready for the user.
}
