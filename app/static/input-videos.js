// Input Videos UI Logic
const API_BASE = '/api/input-videos';

// State
let currentDate = null;
let currentAngle = 'FR';
let scannedVideos = {};
let jobs = [];
let ws = null;

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    await loadSystemStats();
    await loadJobs();
    setupEventListeners();
    connectWebSocket();

    // Update current time display
    const videoPlayer = document.getElementById('video-player');
    videoPlayer.addEventListener('timeupdate', () => {
        const currentTime = formatTime(videoPlayer.currentTime);
        document.getElementById('current-time').textContent = currentTime;
    });
});

function setupEventListeners() {
    document.getElementById('scan-btn').addEventListener('click', scanVideos);
    document.getElementById('mark-start-btn').addEventListener('click', markStartTime);
    document.getElementById('mark-end-btn').addEventListener('click', markEndTime);
    document.getElementById('add-game-btn').addEventListener('click', addGame);
    document.getElementById('process-all-btn').addEventListener('click', processAllGames);
}

async function loadSystemStats() {
    try {
        const response = await fetch('/health');
        const data = await response.json();

        const statsHtml = `
            <div class="stat-chip">
                🖥️ CPU Cores: ${navigator.hardwareConcurrency || 'N/A'}
            </div>
            <div class="stat-chip">
                ${data.gpu_available ? '🎮 GPU: Available' : '⚙️ GPU: Not Available (CPU Mode)'}
            </div>
            <div class="stat-chip">
                💾 Disk Space: ${data.disk_space_gb.toFixed(1)} GB
            </div>
            <div class="stat-chip">
                ⚡ Max Concurrent: ${data.max_concurrent_ffmpeg} FFmpeg processes
            </div>
        `;

        document.getElementById('system-stats').innerHTML = statsHtml;
    } catch (error) {
        console.error('Error loading system stats:', error);
    }
}

async function scanVideos() {
    const btn = document.getElementById('scan-btn');
    btn.disabled = true;
    btn.textContent = 'Scanning...';

    try {
        const response = await fetch(`${API_BASE}/scan`);
        const data = await response.json();

        scannedVideos = data.dates;

        let resultsHtml = '';

        if (data.total_videos === 0) {
            resultsHtml = '<p style="color: #dc3545;">No videos found in /input directory</p>';
        } else {
            for (const [date, dateInfo] of Object.entries(data.dates)) {
                const validation = dateInfo.validation;
                const videos = dateInfo.videos;

                resultsHtml += `
                    <div class="info-card" style="margin-bottom: 15px;">
                        <div class="info-label">Date: ${date}</div>
                        <div class="info-value">${videos.length} videos found</div>
                        ${validation.complete
                            ? `<p style="color: #28a745; margin-top: 10px;">✓ All 4 angles present</p>`
                            : `<div class="validation-warning" style="margin-top: 10px;">
                                ⚠️ Only ${validation.count} angle(s) available: ${validation.present_angles.join(', ')}
                                <br>Will process with available angles only
                               </div>`
                        }
                        <button class="btn btn-primary" onclick="loadDateVideos('${date}')" style="margin-top: 10px;">
                            Load Preview (${validation.count} angle${validation.count > 1 ? 's' : ''})
                        </button>
                        <div style="margin-top: 10px; font-size: 12px; color: #666;">
                            ${videos.map(v => `
                                <div>${v.angle_short}: ${v.filename} (${v.resolution}, ${Math.round(v.duration)}s)</div>
                            `).join('')}
                        </div>
                    </div>
                `;
            }
        }

        document.getElementById('scan-results').innerHTML = resultsHtml;

    } catch (error) {
        console.error('Error scanning videos:', error);
        alert('Error scanning videos: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Scan /input Directory';
    }
}

function loadDateVideos(date) {
    currentDate = date;
    const dateVideos = scannedVideos[date].videos;

    // Show preview and game marking sections
    document.getElementById('preview-section').style.display = 'block';
    document.getElementById('game-marking-section').style.display = 'block';

    // Set date in game marking form
    document.getElementById('game-date').value = date;

    // Get available angles
    const availableAngles = dateVideos.map(v => v.angle_short);
    const firstAvailableAngle = availableAngles[0] || 'FR';

    // Create angle selector buttons
    const angleSelectorHtml = ['FR', 'FL', 'NL', 'NR'].map(angle => {
        const hasVideo = availableAngles.includes(angle);
        const isFirst = angle === firstAvailableAngle;
        return `
            <button
                class="angle-btn ${isFirst ? 'active' : ''}"
                data-angle="${angle}"
                ${!hasVideo ? 'disabled' : ''}
                onclick="switchAngle('${angle}')">
                ${angle} ${!hasVideo ? '(Missing)' : ''}
            </button>
        `;
    }).join('');

    document.getElementById('angle-selector').innerHTML = angleSelectorHtml;

    // Load first available video
    switchAngle(firstAvailableAngle);
}

function switchAngle(angle) {
    currentAngle = angle;

    // Update active button
    document.querySelectorAll('.angle-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.angle === angle);
    });

    const player = document.getElementById('video-player');
    const video = scannedVideos[currentDate].videos.find(v => v.angle_short === angle);

    if (!video) {
        alert('Video not found for angle: ' + angle);
        return;
    }

    // Update video player via HTTP stream
    player.src = `/api/input-videos/stream/${currentDate}/${angle}`;
    player.load();

    // Update video info
    const infoHtml = `
        <div class="info-card">
            <div class="info-label">Source</div>
            <div class="info-value">HTTP Range Stream</div>
            <p style="color: #28a745; margin-top: 5px;">✓ Smooth seeking enabled</p>
            <p style="font-size: 11px; color: #666; margin-top: 3px;">Using byte-range requests</p>
        </div>
        <div class="info-card">
            <div class="info-label">Resolution</div>
            <div class="info-value">${video.resolution}</div>
            ${video.is_4k ? '<p style="color: #ffc107; margin-top: 5px;">⚠️ Will compress to 1080p</p>' : ''}
        </div>
        <div class="info-card">
            <div class="info-label">Duration</div>
            <div class="info-value">${formatTime(video.duration)}</div>
        </div>
        <div class="info-card">
            <div class="info-label">File Size</div>
            <div class="info-value">${formatBytes(video.size)}</div>
        </div>
        <div class="info-card">
            <div class="info-label">Angle</div>
            <div class="info-value">${video.angle_full}</div>
        </div>
    `;

    document.getElementById('video-info').innerHTML = infoHtml;
}

function markStartTime() {
    const player = document.getElementById('video-player');
    const time = formatTime(player.currentTime);
    document.getElementById('start-time').value = time;
}

function markEndTime() {
    const player = document.getElementById('video-player');
    const time = formatTime(player.currentTime);
    document.getElementById('end-time').value = time;
}

async function addGame() {
    const date = document.getElementById('game-date').value;
    const gameNumber = parseInt(document.getElementById('game-number').value);
    const timeStart = document.getElementById('start-time').value;
    const timeEnd = document.getElementById('end-time').value;

    // Validation
    if (!date || !gameNumber || !timeStart || !timeEnd) {
        alert('Please fill all fields');
        return;
    }

    if (!validateTimeFormat(timeStart) || !validateTimeFormat(timeEnd)) {
        alert('Invalid time format. Use HH:MM:SS');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/jobs`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                date,
                game_number: gameNumber,
                time_start: timeStart,
                time_end: timeEnd
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail);
        }

        const data = await response.json();
        console.log('Game added:', data);

        // Increment game number for next game
        document.getElementById('game-number').value = gameNumber + 1;

        // Clear times
        document.getElementById('start-time').value = '';
        document.getElementById('end-time').value = '';

        // Reload jobs
        await loadJobs();

        alert(`Game ${data.job.game_id} added successfully!`);

    } catch (error) {
        console.error('Error adding game:', error);
        alert('Error adding game: ' + error.message);
    }
}

async function loadJobs() {
    try {
        const response = await fetch(`${API_BASE}/jobs`);
        const data = await response.json();

        jobs = data.jobs;

        if (jobs.length === 0) {
            document.getElementById('games-list').innerHTML = '<p style="color: #666;">No games defined yet</p>';
            document.getElementById('process-all-btn').disabled = true;
            return;
        }

        // Enable process button if there are pending jobs
        const hasPending = jobs.some(j => j.status === 'pending');
        document.getElementById('process-all-btn').disabled = !hasPending;

        // Render jobs table
        let tableHtml = `
            <table class="jobs-table">
                <thead>
                    <tr>
                        <th>Game ID</th>
                        <th>Date</th>
                        <th>Time Range</th>
                        <th>Status</th>
                        <th>Angles</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
        `;

        for (const job of jobs) {
            const statusClass = `status-${job.status}`;

            // Count angle statuses
            const angleStatuses = Object.entries(job.angle_status).map(([angle, status]) => {
                const icon = status === 'completed' ? '✓' : status === 'error' ? '✗' : status === 'processing' ? '⏳' : '○';
                return `${angle}: ${icon}`;
            }).join(' | ');

            tableHtml += `
                <tr>
                    <td><strong>${job.game_id}</strong></td>
                    <td>${job.date}</td>
                    <td>${job.time_start} - ${job.time_end}</td>
                    <td><span class="status-badge ${statusClass}">${job.status}</span></td>
                    <td style="font-size: 12px;">${angleStatuses}</td>
                    <td>
                        ${job.status === 'pending'
                            ? `<button class="btn btn-danger btn-sm" onclick="deleteJob('${job.game_id}')">Delete</button>`
                            : ''
                        }
                    </td>
                </tr>
            `;
        }

        tableHtml += '</tbody></table>';

        document.getElementById('games-list').innerHTML = tableHtml;

    } catch (error) {
        console.error('Error loading jobs:', error);
    }
}

async function deleteJob(gameId) {
    if (!confirm(`Delete game ${gameId}?`)) return;

    try {
        const response = await fetch(`${API_BASE}/jobs/${gameId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail);
        }

        await loadJobs();

    } catch (error) {
        console.error('Error deleting job:', error);
        alert('Error deleting job: ' + error.message);
    }
}

async function processAllGames() {
    if (!confirm('Start processing all pending games in parallel?')) return;

    try {
        const response = await fetch(`${API_BASE}/process`, {
            method: 'POST'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail);
        }

        const data = await response.json();

        console.log('Processing started:', data);

        document.getElementById('processing-section').style.display = 'block';
        document.getElementById('process-all-btn').disabled = true;

        alert(`Processing ${data.jobs_count} games with max ${data.max_concurrent} concurrent FFmpeg processes`);

    } catch (error) {
        console.error('Error starting processing:', error);
        alert('Error starting processing: ' + error.message);
    }
}

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/progress`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('WebSocket connected');
    };

    ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        handleProgressUpdate(message);
    };

    ws.onclose = () => {
        console.log('WebSocket disconnected, reconnecting...');
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

function handleProgressUpdate(message) {
    console.log('Progress update:', message);

    // Update jobs list
    loadJobs();

    // Display processing status
    if (message.game_id) {
        let statusHtml = `
            <div class="info-card">
                <div class="info-label">Current Game</div>
                <div class="info-value">${message.game_id}</div>
                <p>Stage: ${message.stage}</p>
                ${message.angle ? `<p>Angle: ${message.angle}</p>` : ''}
            </div>
        `;

        if (message.progress) {
            const progress = message.progress;
            const percent = ((progress.completed / progress.total) * 100).toFixed(0);

            statusHtml += `
                <div class="info-card">
                    <div class="info-label">Overall Progress</div>
                    <div class="info-value">${progress.completed} / ${progress.total}</div>
                    <div class="progress-bar-container">
                        <div class="progress-bar" style="width: ${percent}%"></div>
                    </div>
                    <p style="margin-top: 10px;">
                        Completed: ${progress.completed} | Failed: ${progress.failed}
                    </p>
                </div>
            `;
        }

        if (message.angle_status) {
            statusHtml += '<div class="angle-progress">';
            for (const [angle, status] of Object.entries(message.angle_status)) {
                const statusClass = `status-${status}`;
                statusHtml += `
                    <div class="angle-progress-item">
                        <strong>${angle}</strong><br>
                        <span class="status-badge ${statusClass}">${status}</span>
                    </div>
                `;
            }
            statusHtml += '</div>';
        }

        document.getElementById('processing-status').innerHTML = statusHtml;
    }

    // Re-enable process button when done
    if (message.processing_active === false) {
        document.getElementById('process-all-btn').disabled = false;
        alert('Processing completed!');
    }
}

// Utility functions
function formatTime(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return (bytes / Math.pow(k, i)).toFixed(1) + ' ' + sizes[i];
}

function validateTimeFormat(time) {
    const regex = /^([0-9]{2}):([0-9]{2}):([0-9]{2})$/;
    return regex.test(time);
}
