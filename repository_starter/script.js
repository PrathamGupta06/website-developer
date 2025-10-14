// Main application JavaScript
document.addEventListener('DOMContentLoaded', function() {
    console.log('Application initialized');
    
    // Initialize application
    initializeApp();
});

/**
 * Initialize the main application
 */
function initializeApp() {
    // Get URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const url = urlParams.get('url');
    
    // Update loading content
    setTimeout(() => {
        const loadingElement = document.querySelector('.loading');
        if (loadingElement) {
            loadingElement.innerHTML = '<p>Application ready!</p>';
        }
    }, 1000);
    
    // Handle URL parameter if present
    if (url) {
        console.log('URL parameter detected:', url);
        handleUrlParameter(url);
    } else {
        console.log('No URL parameter found, using default behavior');
        handleDefaultBehavior();
    }
    
    // Check for attachments
    checkForAttachments();
    
    // Setup event listeners
    setupEventListeners();
}

/**
 * Handle URL parameter processing
 * @param {string} url - The URL to process
 */
function handleUrlParameter(url) {
    const urlDisplay = document.getElementById('url-display');
    const currentUrlElement = document.getElementById('current-url');
    
    if (urlDisplay && currentUrlElement) {
        currentUrlElement.textContent = url;
        urlDisplay.classList.remove('hidden');
    }
    
    // Process the URL based on its type
    if (isImageUrl(url)) {
        processImageUrl(url);
    } else {
        processGenericUrl(url);
    }
}

/**
 * Handle default application behavior
 */
function handleDefaultBehavior() {
    const appContent = document.getElementById('app-content');
    if (appContent) {
        appContent.innerHTML = `
            <div class="text-center">
                <h2>Welcome to the Generated Web Application</h2>
                <p class="mb-2">This application is ready to process requests.</p>
                <p>Try accessing with a URL parameter: <code>?url=your-image-url</code></p>
            </div>
        `;
    }
}

/**
 * Check if a URL points to an image
 * @param {string} url - URL to check
 * @returns {boolean} - True if URL appears to be an image
 */
function isImageUrl(url) {
    const imageExtensions = /\.(jpg|jpeg|png|gif|bmp|svg|webp)$/i;
    return imageExtensions.test(url) || url.includes('image');
}

/**
 * Process an image URL
 * @param {string} url - Image URL to process
 */
function processImageUrl(url) {
    const appContent = document.getElementById('app-content');
    if (appContent) {
        appContent.innerHTML = `
            <div class="text-center">
                <h2>Processing Image</h2>
                <div class="mb-3">
                    <img src="${escapeHtml(url)}" alt="Processing image" style="max-width: 100%; max-height: 400px; border-radius: 8px;" 
                         onerror="handleImageError(this)" onload="handleImageLoad(this)">
                </div>
                <div id="image-result">
                    <p>Analyzing image...</p>
                </div>
            </div>
        `;
    }
}

/**
 * Process a generic URL
 * @param {string} url - URL to process
 */
function processGenericUrl(url) {
    const appContent = document.getElementById('app-content');
    if (appContent) {
        appContent.innerHTML = `
            <div class="text-center">
                <h2>Processing URL</h2>
                <p class="mb-2">Processing: <code>${escapeHtml(url)}</code></p>
                <div id="url-result">
                    <p>Analyzing URL content...</p>
                </div>
            </div>
        `;
    }
    
    // Simulate processing
    setTimeout(() => {
        const resultElement = document.getElementById('url-result');
        if (resultElement) {
            resultElement.innerHTML = '<p>URL processing completed!</p>';
        }
    }, 2000);
}

/**
 * Handle image load success
 * @param {HTMLImageElement} img - The image element
 */
function handleImageLoad(img) {
    console.log('Image loaded successfully:', img.src);
    const resultElement = document.getElementById('image-result');
    if (resultElement) {
        // Simulate image analysis
        setTimeout(() => {
            resultElement.innerHTML = `
                <div class="mb-2">
                    <strong>Image Analysis Complete</strong>
                </div>
                <p>Image dimensions: ${img.naturalWidth} x ${img.naturalHeight}</p>
                <p>Status: Successfully processed</p>
            `;
        }, 1500);
    }
}

/**
 * Handle image load error
 * @param {HTMLImageElement} img - The image element
 */
function handleImageError(img) {
    console.error('Failed to load image:', img.src);
    const resultElement = document.getElementById('image-result');
    if (resultElement) {
        resultElement.innerHTML = `
            <div style="color: #e74c3c;">
                <strong>Error Loading Image</strong>
                <p>Could not load the specified image URL</p>
            </div>
        `;
    }
}

/**
 * Check for and display attachments
 */
function checkForAttachments() {
    // This would typically be populated by the server-side code
    // For now, it's a placeholder for attachment handling
    const attachments = getAttachmentsFromPage();
    
    if (attachments && attachments.length > 0) {
        displayAttachments(attachments);
    }
}

/**
 * Get attachments data from page (placeholder)
 * @returns {Array} - Array of attachment objects
 */
function getAttachmentsFromPage() {
    // This would be populated by server-side rendering or API call
    // Return empty array for now
    return [];
}

/**
 * Display attachments in the UI
 * @param {Array} attachments - Array of attachment objects
 */
function displayAttachments(attachments) {
    const attachmentsContainer = document.getElementById('attachments');
    const attachmentsList = document.getElementById('attachments-list');
    
    if (attachmentsContainer && attachmentsList) {
        attachmentsList.innerHTML = '';
        
        attachments.forEach(attachment => {
            const attachmentElement = createAttachmentElement(attachment);
            attachmentsList.appendChild(attachmentElement);
        });
        
        attachmentsContainer.classList.remove('hidden');
    }
}

/**
 * Create an attachment display element
 * @param {Object} attachment - Attachment object
 * @returns {HTMLElement} - Attachment display element
 */
function createAttachmentElement(attachment) {
    const div = document.createElement('div');
    div.className = 'attachment-item';
    
    if (attachment.type && attachment.type.startsWith('image/')) {
        div.innerHTML = `
            <img src="${escapeHtml(attachment.url)}" alt="${escapeHtml(attachment.name)}">
            <div class="attachment-name">${escapeHtml(attachment.name)}</div>
        `;
    } else {
        div.innerHTML = `
            <div class="attachment-name">${escapeHtml(attachment.name)}</div>
            <div style="color: #666; font-size: 0.8rem;">${attachment.type || 'Unknown type'}</div>
        `;
    }
    
    return div;
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    // Add any global event listeners here
    document.addEventListener('keydown', function(e) {
        // Add keyboard shortcuts if needed
        if (e.ctrlKey && e.key === 'r') {
            e.preventDefault();
            location.reload();
        }
    });
}

/**
 * Utility function to escape HTML
 * @param {string} text - Text to escape
 * @returns {string} - Escaped text
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Utility function to log messages with timestamp
 * @param {string} message - Message to log
 */
function logMessage(message) {
    const timestamp = new Date().toISOString();
    console.log(`[${timestamp}] ${message}`);
}

// Export functions for potential use by other scripts
window.AppFunctions = {
    handleUrlParameter,
    handleDefaultBehavior,
    processImageUrl,
    processGenericUrl,
    displayAttachments,
    logMessage
};