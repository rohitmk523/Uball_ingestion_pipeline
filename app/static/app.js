// Basketball Video Processing Pipeline Frontend

class PipelineApp {
    constructor() {
        this.config = null;
        this.cameras = [];
        this.files = [];
        this.games = [];
        this.websocket = null;
        this.processingStatus = {};

        this.init();
    }

    async init() {
        console.log('Initializing Basketball Pipeline App');

        // Load initial configuration
        await this.loadConfig();

        // Setup event listeners
        this.setupEventListeners();

        // Connect WebSocket
        this.connectWebSocket();

        // Initial data load
        await this.refreshCameras();

        this.log('Pipeline initialized', 'info');
    }

    setupEventListeners() {
        // Side selection
        document.getElementById('set-side-btn').addEventListener('click', () => this.setSide());

        // AWS configuration
        document.getElementById('save-aws-btn').addEventListener('click', () => this.saveAwsConfig());

        // Camera management
        document.getElementById('refresh-cameras-btn').addEventListener('click', () => this.refreshCameras());
        document.getElementById('load-files-btn').addEventListener('click', () => this.loadFiles());

        // Game management
        document.getElementById('add-game-btn').addEventListener('click', () => this.addGame());
        document.getElementById('start-processing-btn').addEventListener('click', () => this.startProcessing());
        document.getElementById('clear-games-btn').addEventListener('click', () => this.clearGames());

        // Log management
        document.getElementById('clear-log-btn').addEventListener('click', () => this.clearLog());

        // Auto-refresh games list
        setInterval(() => this.loadGames(), 5000);
    }

    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            this.config = await response.json();

            // Update UI with current config
            if (this.config.side) {
                document.getElementById('side-select').value = this.config.side;
                document.getElementById('system-status').textContent = `Ready (${this.config.side})`;
            } else {
                document.getElementById('system-status').textContent = 'Side not configured';
            }

            // Don't populate AWS credentials for security
            document.getElementById('s3-bucket').value = this.config.s3_bucket;
            document.getElementById('s3-region').value = this.config.s3_region;

        } catch (error) {
            console.error('Error loading config:', error);
            this.showToast('Error loading configuration', 'error');
        }
    }

    async setSide() {
        const side = document.getElementById('side-select').value;
        if (!side) {
            this.showToast('Please select a side', 'error');
            return;
        }

        try {
            const response = await fetch('/api/config/side', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ side })
            });

            if (response.ok) {
                this.config.side = side;
                document.getElementById('system-status').textContent = `Ready (${side})`;
                this.showToast(`Side set to ${side}`, 'success');
                this.log(`Side configured: ${side}`, 'info');
            } else {
                throw new Error('Failed to set side');
            }
        } catch (error) {
            console.error('Error setting side:', error);
            this.showToast('Error setting side', 'error');
        }
    }

    async saveAwsConfig() {
        const awsConfig = {
            aws_access_key: document.getElementById('aws-access-key').value,
            aws_secret_key: document.getElementById('aws-secret-key').value,
            s3_bucket: document.getElementById('s3-bucket').value,
            s3_region: document.getElementById('s3-region').value
        };

        if (!awsConfig.aws_access_key || !awsConfig.aws_secret_key) {
            this.showToast('Please provide AWS credentials', 'error');
            return;
        }

        try {
            const response = await fetch('/api/config/aws', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(awsConfig)
            });

            if (response.ok) {
                this.showToast('AWS configuration saved and validated', 'success');
                this.log('AWS configuration updated', 'success');

                // Clear form for security
                document.getElementById('aws-access-key').value = '';
                document.getElementById('aws-secret-key').value = '';
            } else {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to save AWS config');
            }
        } catch (error) {
            console.error('Error saving AWS config:', error);
            this.showToast(`Error: ${error.message}`, 'error');
        }
    }

    async refreshCameras() {
        try {
            const response = await fetch('/api/cameras');
            const data = await response.json();
            this.cameras = data.cameras;

            this.updateCameraList();
            this.log(`Found ${this.cameras.length} cameras`, 'info');
        } catch (error) {
            console.error('Error refreshing cameras:', error);
            this.showToast('Error refreshing cameras', 'error');
        }
    }

    updateCameraList() {
        const container = document.getElementById('camera-list');

        if (this.cameras.length === 0) {
            container.innerHTML = '<p class="text-warning">No GoPro cameras detected. Please connect cameras via USB.</p>';
            return;
        }

        container.innerHTML = this.cameras.map((camera, index) => `
            <div class="camera-item connected">
                <div>
                    <strong>Camera ${index + 1}</strong>
                    <div class="file-meta">${camera}</div>
                </div>
                <span class="status-badge status-complete">Connected</span>
            </div>
        `).join('');
    }

    async loadFiles() {
        try {
            document.getElementById('load-files-btn').textContent = 'Loading...';
            document.getElementById('load-files-btn').disabled = true;

            const response = await fetch('/api/files');
            const data = await response.json();
            this.files = data.files;

            this.updateFilesList();
            this.log(`Loaded ${this.files.length} video files`, 'info');

        } catch (error) {
            console.error('Error loading files:', error);
            this.showToast('Error loading video files', 'error');
        } finally {
            document.getElementById('load-files-btn').textContent = 'Load Video Files';
            document.getElementById('load-files-btn').disabled = false;
        }
    }

    updateFilesList() {
        const container = document.getElementById('video-files-list');

        if (this.files.length === 0) {
            container.innerHTML = '<p>No video files found. Please load files from connected cameras.</p>';
            return;
        }

        container.innerHTML = this.files.map(file => `
            <div class="file-item">
                <div class="file-info">
                    <strong>${file.filename}</strong>
                    <div class="file-meta">
                        ${file.resolution} • ${this.formatDuration(file.duration)} • ${this.formatFileSize(file.size)}
                    </div>
                    <div class="file-meta">
                        ${new Date(file.timestamp).toLocaleString()}
                    </div>
                </div>
            </div>
        `).join('');
    }

    async addGame() {
        const startTime = document.getElementById('start-time').value;
        const endTime = document.getElementById('end-time').value;

        if (!startTime || !endTime) {
            this.showToast('Please provide start and end times', 'error');
            return;
        }

        // Validate time format
        const timeRegex = /^([0-1]?[0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$/;
        if (!timeRegex.test(startTime) || !timeRegex.test(endTime)) {
            this.showToast('Invalid time format. Use HH:MM:SS', 'error');
            return;
        }

        try {
            const response = await fetch('/api/games', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    time_range: {
                        start: startTime,
                        end: endTime
                    }
                })
            });

            if (response.ok) {
                const game = await response.json();
                this.showToast(`Game ${game.uuid} created`, 'success');
                this.log(`Added game: ${game.uuid} (${startTime} - ${endTime})`, 'success');

                // Clear form
                document.getElementById('start-time').value = '';
                document.getElementById('end-time').value = '';

                // Refresh games list
                await this.loadGames();
            } else {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to create game');
            }
        } catch (error) {
            console.error('Error adding game:', error);
            this.showToast(`Error: ${error.message}`, 'error');
        }
    }

    async loadGames() {
        try {
            const response = await fetch('/api/games');
            const data = await response.json();
            this.games = data.games;

            this.updateGamesList();
        } catch (error) {
            console.error('Error loading games:', error);
        }
    }

    updateGamesList() {
        const tbody = document.getElementById('games-table-body');

        if (this.games.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center">No games defined</td></tr>';
            return;
        }

        tbody.innerHTML = this.games.map(game => `
            <tr>
                <td>${game.uuid}</td>
                <td>${game.time_range.start}</td>
                <td>${game.time_range.end}</td>
                <td>${this.calculateDuration(game.time_range.start, game.time_range.end)}</td>
                <td><span class="status-badge status-${game.status}">${game.status}</span></td>
                <td>
                    ${game.status === 'pending' ?
                        `<button onclick="app.deleteGame('${game.uuid}')" class="danger-btn">Delete</button>` :
                        ''
                    }
                </td>
            </tr>
        `).join('');
    }

    async deleteGame(uuid) {
        if (!confirm('Are you sure you want to delete this game?')) {
            return;
        }

        try {
            const response = await fetch(`/api/games/${uuid}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                this.showToast('Game deleted', 'success');
                this.log(`Deleted game: ${uuid}`, 'info');
                await this.loadGames();
            } else {
                throw new Error('Failed to delete game');
            }
        } catch (error) {
            console.error('Error deleting game:', error);
            this.showToast('Error deleting game', 'error');
        }
    }

    async startProcessing() {
        if (!this.config.side) {
            this.showToast('Please configure side first', 'error');
            return;
        }

        const pendingGames = this.games.filter(g => g.status === 'pending');
        if (pendingGames.length === 0) {
            this.showToast('No pending games to process', 'error');
            return;
        }

        if (!confirm(`Start processing ${pendingGames.length} games? This will take time.`)) {
            return;
        }

        try {
            const response = await fetch('/api/process/start', {
                method: 'POST'
            });

            if (response.ok) {
                this.showToast('Processing started', 'success');
                this.log(`Started processing ${pendingGames.length} games`, 'info');

                // Show progress section
                document.getElementById('progress-section').style.display = 'block';

                // Disable start button
                document.getElementById('start-processing-btn').disabled = true;
                document.getElementById('start-processing-btn').textContent = 'Processing...';

            } else {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to start processing');
            }
        } catch (error) {
            console.error('Error starting processing:', error);
            this.showToast(`Error: ${error.message}`, 'error');
        }
    }

    async clearGames() {
        if (!confirm('Are you sure you want to clear all games? This cannot be undone.')) {
            return;
        }

        try {
            // Delete each game individually
            for (const game of this.games) {
                if (game.status === 'pending') {
                    await fetch(`/api/games/${game.uuid}`, { method: 'DELETE' });
                }
            }

            this.showToast('All pending games cleared', 'success');
            this.log('Cleared all games', 'info');
            await this.loadGames();

        } catch (error) {
            console.error('Error clearing games:', error);
            this.showToast('Error clearing games', 'error');
        }
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/progress`;

        this.websocket = new WebSocket(wsUrl);

        this.websocket.onopen = () => {
            console.log('WebSocket connected');
            this.log('Real-time updates connected', 'info');
        };

        this.websocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleProgressUpdate(data);
        };

        this.websocket.onclose = () => {
            console.log('WebSocket disconnected, reconnecting...');
            setTimeout(() => this.connectWebSocket(), 3000);
        };

        this.websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }

    handleProgressUpdate(data) {
        console.log('Progress update:', data);

        if (data.message) {
            this.log(data.message, 'info');
        }

        if (data.game_uuid && data.angle) {
            this.updateAngleProgress(data);
        }

        if (data.processing_active === false) {
            // Processing completed
            document.getElementById('start-processing-btn').disabled = false;
            document.getElementById('start-processing-btn').textContent = 'Start Processing All Games';
            this.log('Processing completed', 'success');
            this.loadGames(); // Refresh games list
        }
    }

    updateAngleProgress(data) {
        const progressSection = document.getElementById('detailed-progress');
        const progressId = `progress-${data.game_uuid}-${data.angle}`;

        let progressItem = document.getElementById(progressId);
        if (!progressItem) {
            progressItem = document.createElement('div');
            progressItem.id = progressId;
            progressItem.className = 'progress-item';
            progressSection.appendChild(progressItem);
        }

        const percentage = Math.round(data.progress * 100);
        const stageText = data.stage.replace(/_/g, ' ').toUpperCase();

        progressItem.innerHTML = `
            <h4>${data.game_uuid} - ${data.angle}</h4>
            <div class="progress-details">
                <span>Stage: ${stageText}</span>
                <span>${percentage}%</span>
            </div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: ${percentage}%"></div>
            </div>
            ${data.message ? `<p>${data.message}</p>` : ''}
            ${data.error_message ? `<p class="error">Error: ${data.error_message}</p>` : ''}
        `;

        if (data.stage === 'complete') {
            setTimeout(() => {
                progressItem.style.opacity = '0.5';
            }, 2000);
        }
    }

    // Utility functions
    formatDuration(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }

    formatFileSize(bytes) {
        const units = ['B', 'KB', 'MB', 'GB'];
        let size = bytes;
        let unitIndex = 0;

        while (size >= 1024 && unitIndex < units.length - 1) {
            size /= 1024;
            unitIndex++;
        }

        return `${size.toFixed(1)} ${units[unitIndex]}`;
    }

    calculateDuration(start, end) {
        const startTime = new Date(`1970-01-01T${start}Z`);
        const endTime = new Date(`1970-01-01T${end}Z`);
        const diff = (endTime - startTime) / 1000;
        return this.formatDuration(diff);
    }

    log(message, type = 'info') {
        const logContainer = document.getElementById('activity-log');
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = document.createElement('p');
        logEntry.className = `log-entry ${type}`;
        logEntry.textContent = `[${timestamp}] ${message}`;

        logContainer.appendChild(logEntry);
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    clearLog() {
        document.getElementById('activity-log').innerHTML = '';
        this.log('Log cleared', 'info');
    }

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 5000);
    }
}

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.app = new PipelineApp();
});