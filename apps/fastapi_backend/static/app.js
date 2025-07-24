// Global variables
let currentTaskId = null;
let statusPollInterval = null;
let pollingActive = false;

// Initialize dashboard when page loads
document.addEventListener('DOMContentLoaded', function () {
    console.log('Dashboard loaded');
    // Initial data load
    refreshSystemInfo();
});

// File selection handler
function onFileSelected() {
    const fileInput = document.getElementById('videoFile');
    const uploadBtn = document.getElementById('uploadBtn');

    if (fileInput.files.length > 0) {
        uploadBtn.disabled = false;
        updateStatus(`File selected: ${fileInput.files[0].name}`);
    } else {
        uploadBtn.disabled = true;
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

        // Show current task info section
        document.getElementById('currentTaskInfo').style.display = 'block';

        // Refresh stream status using only /streams/{task_id}/status
        await refreshStreamStatus();

        updateStatus(`✅ Upload successful! Task ID: ${currentTaskId}`);

        // Start status polling
        startStatusPolling();

        // Hide progress bar
        setTimeout(() => {
            progressDiv.classList.add('hidden');
            uploadBtn.disabled = false;
        }, 1000);

    } catch (error) {
        showError(`Upload failed: ${error.message}`);
        progressDiv.classList.add('hidden');
        uploadBtn.disabled = false;
    }
}

// Status polling functions
function startStatusPolling() {
    if (!currentTaskId || pollingActive) return;

    pollingActive = true;
    statusPollInterval = setInterval(async () => {
        await refreshStreamStatus();
    }, 5000); // Poll every 5 seconds
}

function stopStatusPolling() {
    if (statusPollInterval) {
        clearInterval(statusPollInterval);
        statusPollInterval = null;
        pollingActive = false;
    }
}

// Main function: refresh stream status using only /streams/{task_id}/status
async function refreshStreamStatus() {
    if (!currentTaskId) return;

    try {
        const response = await fetch(`/streams/${currentTaskId}/status`);
        if (response.ok) {
            const data = await response.json();

            // Update stream status
            document.getElementById('streamStatus').textContent = data.active ? 'Active' : 'Inactive';

            // Update stream URLs
            const origUrl = data.rtsp_url || 'None';
            const procUrl = data.annotations_rtsp_url || 'None';
            document.getElementById('originalStreamUrl').textContent = origUrl;
            document.getElementById('processedStreamUrl').textContent = procUrl;

            // Update video elements
            const origVideo = document.getElementById('originalVideo');
            const procVideo = document.getElementById('processedVideo');

            if (origUrl !== 'None') {
                origVideo.src = origUrl;
                // Enable original stream controls
                document.getElementById('copyOriginalStreamBtn').disabled = false;
                document.getElementById('loadOriginalStreamBtn').disabled = false;
                document.getElementById('stopOriginalStreamBtn').disabled = false;
            }

            if (procUrl !== 'None') {
                const streamName = procUrl.split('/').pop();  // 从 rtsp://localhost:8554/mystream 获取 "mystream"
                const webrtcUrl = `https://localhost:8889/stream/webrtc/${streamName}`;

                document.getElementById('processedVideoWebRTC').src = webrtcUrl;
            }

            // Update processing status
            document.getElementById('processingStatus').textContent = data.active ? 'Processing' : 'Completed';

        } else {
            document.getElementById('streamStatus').textContent = 'Inactive';
            document.getElementById('processingStatus').textContent = 'Error';
        }
    } catch (error) {
        console.error('Failed to refresh stream status:', error);
        document.getElementById('streamStatus').textContent = 'Error';
        document.getElementById('processingStatus').textContent = 'Error';
    }
}

// Copy stream URLs
async function copyOriginalStreamUrl() {
    const streamUrl = document.getElementById('originalStreamUrl').textContent;
    if (streamUrl && streamUrl !== 'None') {
        try {
            await navigator.clipboard.writeText(streamUrl);
            showSuccess('Original stream URL copied to clipboard');
        } catch (error) {
            console.error('Failed to copy URL:', error);
            showError('Failed to copy URL');
        }
    } else {
        showError('No original stream URL available');
    }
}

async function copyProcessedStreamUrl() {
    const streamUrl = document.getElementById('processedStreamUrl').textContent;
    if (streamUrl && streamUrl !== 'None') {
        try {
            await navigator.clipboard.writeText(streamUrl);
            showSuccess('Processed stream URL copied to clipboard');
        } catch (error) {
            console.error('Failed to copy URL:', error);
            showError('Failed to copy URL');
        }
    } else {
        showError('No processed stream URL available');
    }
}

// Load stream functions
function loadOriginalStream() {
    const videoElement = document.getElementById('originalVideo');
    if (videoElement.src) {
        videoElement.play().catch(e => console.warn('Playback error:', e));
        showInfo('Loading original RTSP stream...');
    } else {
        showError('No original stream URL available');
    }
}

function loadProcessedStream() {
    const videoElement = document.getElementById('processedVideo');
    if (videoElement.src) {
        videoElement.play().catch(e => console.warn('Playback error:', e));
        showInfo('Loading processed video stream...');
    } else {
        showError('No processed stream URL available');
    }
}

// Refresh processed stream info
async function refreshProcessedStream() {
    await refreshStreamStatus();
    showInfo('Processed stream info refreshed');
}

// Stop stream functions
async function stopOriginalStream() {
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
        document.getElementById('stopOriginalStreamBtn').disabled = true;

        // Refresh stream status
        await refreshStreamStatus();

    } catch (error) {
        showError(`Failed to stop stream: ${error.message}`);
    }
}

// Stop all streams
async function stopAllStreams() {
    try {
        const response = await fetch('/streams/stop-all', {
            method: 'POST'
        });

        if (!response.ok) {
            throw new Error('Failed to stop all streams');
        }

        const result = await response.json();
        showSuccess('All streams stopped');

        // Update UI
        document.getElementById('streamStatus').textContent = 'Stopped';
        document.getElementById('activeStreamCount').textContent = '0';

        // Refresh stream status if there's an active task
        if (currentTaskId) {
            await refreshStreamStatus();
        }

    } catch (error) {
        showError(`Failed to stop all streams: ${error.message}`);
    }
}

// Health check
async function checkHealth() {
    try {
        const response = await fetch('/health');
        if (response.ok) {
            const data = await response.json();
            showSuccess(`Health check passed: ${data.status}`);
        } else {
            showError('Health check failed');
        }
    } catch (error) {
        showError(`Health check error: ${error.message}`);
    }
}

// Refresh system info
async function refreshSystemInfo() {
    try {
        // Check server status
        const healthResponse = await fetch('/health');
        if (healthResponse.ok) {
            document.getElementById('serverStatus').textContent = 'Healthy';
        } else {
            document.getElementById('serverStatus').textContent = 'Unhealthy';
        }

        // Get active streams count
        try {
            const streamsResponse = await fetch('/streams/active');
            if (streamsResponse.ok) {
                const streamsData = await streamsResponse.json();
                document.getElementById('activeStreamCount').textContent = streamsData.active_streams?.length || 0;
            }
        } catch (e) {
            document.getElementById('activeStreamCount').textContent = 'Unknown';
        }

    } catch (error) {
        console.error('Failed to refresh system info:', error);
        document.getElementById('serverStatus').textContent = 'Error';
    }
}

// Utility functions
function updateStatus(message) {
    document.getElementById('status').textContent = message;
}

function showSuccess(message) {
    updateStatus(`✅ ${message}`);
    console.log('Success:', message);
}

function showError(message) {
    updateStatus(`❌ ${message}`);
    console.error('Error:', message);
}

function showInfo(message) {
    updateStatus(`ℹ️ ${message}`);
    console.log('Info:', message);
}

function showModal(title, content) {
    document.getElementById('modalContent').innerHTML = content;
    document.getElementById('resultModal').classList.remove('hidden');
}

function closeModal() {
    document.getElementById('resultModal').classList.add('hidden');
}