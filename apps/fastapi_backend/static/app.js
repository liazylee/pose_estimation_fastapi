// Global variables
let currentTaskId = null;
let statusInterval = null;

// Initialize dashboard
document.addEventListener('DOMContentLoaded', function() {
    console.log('Dashboard loaded');
    checkHealth();
    refreshSystemInfo();
    refreshActiveStreams();
    refreshFileList();
    refreshTaskList();
});

// File selection handler
function onFileSelected() {
    const fileInput = document.getElementById('videoFile');
    const uploadBtn = document.getElementById('uploadBtn');
    
    if (fileInput.files.length > 0) {
        uploadBtn.disabled = false;
        updateStatus(`Selected: ${fileInput.files[0].name} (${formatFileSize(fileInput.files[0].size)})`);
    } else {
        uploadBtn.disabled = true;
        updateStatus('Ready to upload video...');
    }
}

// Upload file function
async function uploadFile() {
    const fileInput = document.getElementById('videoFile');
    const file = fileInput.files[0];
    
    if (!file) {
        showError('Please select a file first');
        return;
    }
    
    const uploadBtn = document.getElementById('uploadBtn');
    const progressDiv = document.getElementById('uploadProgress');
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');
    
    // Disable button and show progress
    uploadBtn.disabled = true;
    progressDiv.classList.remove('hidden');
    updateStatus('Uploading and processing...');
    
    // Create form data
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        // Upload with progress tracking
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error(`Upload failed: ${response.statusText}`);
        }
        
        const result = await response.json();
        
        // Update UI with result
        currentTaskId = result.task_id;
        document.getElementById('currentTaskId').textContent = currentTaskId;
        document.getElementById('streamUrl').textContent = result.stream_url;
        
        // Enable stream controls
        document.getElementById('copyStreamBtn').disabled = false;
        document.getElementById('loadStreamBtn').disabled = false;
        document.getElementById('stopStreamBtn').disabled = false;
        
        updateStatus(`✅ Upload successful! Task ID: ${currentTaskId}`);
        
        // Start status polling
        startStatusPolling();
        
        // Refresh active streams
        refreshActiveStreams();
        
        // Hide progress bar
        setTimeout(() => {
            progressDiv.classList.add('hidden');
            uploadBtn.disabled = false;
        }, 1000);
        
    } catch (error) {
        console.error('Upload error:', error);
        showError(`Upload failed: ${error.message}`);
        progressDiv.classList.add('hidden');
        uploadBtn.disabled = false;
    }
}

// Status polling functions
function startStatusPolling() {
    if (statusInterval) {
        clearInterval(statusInterval);
    }
    
    statusInterval = setInterval(async () => {
        if (currentTaskId) {
            await refreshStatus();
            await refreshStreamStatus();
        }
    }, 3000); // Poll every 3 seconds
}

function stopStatusPolling() {
    if (statusInterval) {
        clearInterval(statusInterval);
        statusInterval = null;
    }
}

// Refresh task status
async function refreshStatus() {
    if (!currentTaskId) {
        showError('No active task');
        return;
    }
    
    try {
        const response = await fetch(`/status/${currentTaskId}`);
        
        if (!response.ok) {
            throw new Error('Status check failed');
        }
        
        const status = await response.json();
        
        // Update status display
        document.getElementById('currentStatus').textContent = status.status;
        document.getElementById('currentProgress').textContent = `${status.progress}%`;
        
        // Update progress bar if visible
        const progressBar = document.getElementById('progressBar');
        const progressText = document.getElementById('progressText');
        
        if (!document.getElementById('uploadProgress').classList.contains('hidden')) {
            progressBar.style.width = `${status.progress}%`;
            progressText.textContent = `${status.progress}%`;
        }
        
        // If task is completed, stop polling
        if (status.status === 'completed' || status.status === 'failed') {
            stopStatusPolling();
        }
        
    } catch (error) {
        console.error('Status refresh failed:', error);
    }
}

// Refresh stream status
async function refreshStreamStatus() {
    if (!currentTaskId) return;
    
    try {
        const response = await fetch(`/streams/${currentTaskId}/status`);
        
        if (response.ok) {
            const status = await response.json();
            document.getElementById('streamStatus').textContent = status.status;
            
            // Update stream controls based on status
            const isActive = status.is_active;
            document.getElementById('stopStreamBtn').disabled = !isActive;
        }
    } catch (error) {
        console.error('Stream status refresh failed:', error);
    }
}

// Copy stream URL to clipboard
async function copyStreamUrl() {
    const streamUrl = document.getElementById('streamUrl').textContent;
    
    if (streamUrl && streamUrl !== 'None') {
        try {
            await navigator.clipboard.writeText(streamUrl);
            showSuccess('Stream URL copied to clipboard!');
        } catch (error) {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = streamUrl;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            showSuccess('Stream URL copied to clipboard!');
        }
    } else {
        showError('No stream URL available');
    }
}

// Load stream in video player
function loadStream() {
    const streamUrl = document.getElementById('streamUrl').textContent;
    const videoElement = document.getElementById('streamVideo');
    
    if (streamUrl && streamUrl !== 'None') {
        // Note: Most browsers don't support RTSP directly
        // This is a placeholder - in production you'd need a streaming solution
        showInfo('RTSP streams require VLC or specialized player. URL copied to clipboard.');
        copyStreamUrl();
        
        // TODO: Implement HLS or WebRTC conversion for browser playback
        // For now, just show the RTSP URL
    } else {
        showError('No stream URL available');
    }
}

// Stop stream
async function stopStream() {
    if (!currentTaskId) {
        showError('No active task');
        return;
    }
    
    try {
        const response = await fetch(`/streams/${currentTaskId}/stop`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            throw new Error('Failed to stop stream');
        }
        
        const result = await response.json();
        showSuccess(result.message);
        
        // Update UI
        document.getElementById('streamStatus').textContent = 'Stopped';
        document.getElementById('stopStreamBtn').disabled = true;
        
        // Refresh active streams
        refreshActiveStreams();
        
    } catch (error) {
        showError(`Failed to stop stream: ${error.message}`);
    }
}

// Refresh active streams
async function refreshActiveStreams() {
    try {
        const response = await fetch('/streams');
        
        if (!response.ok) {
            throw new Error('Failed to get active streams');
        }
        
        const data = await response.json();
        
        // Update active streams count
        document.getElementById('activeStreamCount').textContent = data.count;
        
        // Update active streams list
        const streamsList = document.getElementById('activeStreamsList');
        if (data.active_streams.length > 0) {
            streamsList.innerHTML = data.active_streams.map(taskId => 
                `<div class="stream-item">
                    <span>${taskId.substring(0, 8)}...</span>
                    <button onclick="selectTask('${taskId}')" class="btn-small">Select</button>
                    <button onclick="stopStreamById('${taskId}')" class="btn-small btn-danger">Stop</button>
                </div>`
            ).join('');
        } else {
            streamsList.innerHTML = '<div class="no-streams">No active streams</div>';
        }
        
    } catch (error) {
        console.error('Failed to refresh active streams:', error);
        document.getElementById('activeStreamCount').textContent = 'Error';
    }
}

// Stop stream by ID
async function stopStreamById(taskId) {
    try {
        const response = await fetch(`/streams/${taskId}/stop`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            throw new Error('Failed to stop stream');
        }
        
        showSuccess(`Stream ${taskId.substring(0, 8)}... stopped`);
        refreshActiveStreams();
        
    } catch (error) {
        showError(`Failed to stop stream: ${error.message}`);
    }
}

// Stop all streams
async function stopAllStreams() {
    if (!confirm('Are you sure you want to stop all active streams?')) {
        return;
    }
    
    try {
        const response = await fetch('/streams');
        const data = await response.json();
        
        const stopPromises = data.active_streams.map(taskId => 
            fetch(`/streams/${taskId}/stop`, { method: 'POST' })
        );
        
        await Promise.all(stopPromises);
        
        showSuccess('All streams stopped successfully');
        refreshActiveStreams();
        
    } catch (error) {
        showError(`Failed to stop all streams: ${error.message}`);
    }
}

// Select a task
function selectTask(taskId) {
    currentTaskId = taskId;
    document.getElementById('currentTaskId').textContent = taskId;
    document.getElementById('streamUrl').textContent = `rtsp://localhost:8554/${taskId}`;
    
    // Enable controls
    document.getElementById('copyStreamBtn').disabled = false;
    document.getElementById('loadStreamBtn').disabled = false;
    
    // Start status polling
    startStatusPolling();
    
    showSuccess(`Selected task: ${taskId.substring(0, 8)}...`);
}

// Check health
async function checkHealth() {
    try {
        const response = await fetch('/health');
        const data = await response.json();
        
        document.getElementById('backendStatus').textContent = 'Healthy';
        document.getElementById('backendStatus').classList.add('text-success');
        
        showSuccess('Backend is healthy');
        
    } catch (error) {
        console.error('Health check error:', error);
        document.getElementById('backendStatus').textContent = 'Error';
        document.getElementById('backendStatus').classList.add('text-error');
        showError('Backend health check failed');
    }
}

// Refresh system info
async function refreshSystemInfo() {
    try {
        // Check server status
        const healthResponse = await fetch('/health');
        const healthData = await healthResponse.json();
        
        document.getElementById('serverStatus').textContent = healthData.status === 'healthy' ? 'Online' : 'Error';
        document.getElementById('kafkaStatus').textContent = healthData.kafka ? 'Connected' : 'Disconnected';
        
        // Get task count
        const tasksResponse = await fetch('/api/tasks');
        if (tasksResponse.ok) {
            const tasksData = await tasksResponse.json();
            document.getElementById('activeTasks').textContent = tasksData.tasks ? tasksData.tasks.length : 0;
        }
        
    } catch (error) {
        console.error('Failed to refresh system info:', error);
        document.getElementById('serverStatus').textContent = 'Error';
    }
}

// View API docs
function viewApiDocs() {
    window.open('/docs', '_blank');
}

// Test API endpoints
async function testApi(endpoint) {
    const responseElement = document.getElementById('apiResponse');
    responseElement.textContent = 'Loading...';
    
    try {
        const response = await fetch(endpoint);
        const data = await response.json();
        
        responseElement.textContent = JSON.stringify(data, null, 2);
        
    } catch (error) {
        responseElement.textContent = `Error: ${error.message}`;
    }
}

// Utility functions
function updateStatus(message) {
    document.getElementById('status').textContent = message;
}

function showSuccess(message) {
    console.log('Success:', message);
    // Could add toast notifications here
}

function showError(message) {
    console.error('Error:', message);
    // Could add toast notifications here
}

function showInfo(message) {
    console.info('Info:', message);
    // Could add toast notifications here
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatDate(dateString) {
    return new Date(dateString).toLocaleString();
}

// Modal functions
function showModal(title, content) {
    document.getElementById('modalContent').innerHTML = `<h4>${title}</h4>${content}`;
    document.getElementById('resultModal').classList.remove('hidden');
}

function closeModal() {
    document.getElementById('resultModal').classList.add('hidden');
}

// Close modal when clicking outside
window.onclick = function(event) {
    const modal = document.getElementById('resultModal');
    if (event.target === modal) {
        closeModal();
    }
}

// Auto-refresh every 30 seconds
setInterval(() => {
    if (!statusInterval) { // Only refresh if not actively polling a task
        refreshSystemInfo();
    }
}, 30000); 