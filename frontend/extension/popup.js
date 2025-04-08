document.addEventListener('DOMContentLoaded', async () => {
  const clipsContainer = document.getElementById('clips-container');
  const promptInput = document.getElementById('prompt');
  const extractButton = document.getElementById('extract');

  // Query the active tab to check if we're on YouTube
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  
  if (!tab.url || !tab.url.includes('youtube.com/watch')) {
    clipsContainer.innerHTML = '<div class="status">Please navigate to a YouTube video to see clips.</div>';
    promptInput.disabled = true;
    extractButton.disabled = true;
    return;
  }

  // Get video ID from URL
  const videoId = new URLSearchParams(new URL(tab.url).search).get('v');
  if (!videoId) {
    clipsContainer.innerHTML = '<div class="status">Could not find video ID.</div>';
    promptInput.disabled = true;
    extractButton.disabled = true;
    return;
  }

  // Check if we already have clips for this video
  try {
    const data = await chrome.storage.local.get([videoId, `prompt_${videoId}`]);
    const videoData = data[videoId];
    const savedPrompt = data[`prompt_${videoId}`];
    
    console.log('Initial data from storage:', { videoData, savedPrompt });
    
    // Debug stored clips data
    if (videoData && videoData.clips) {
      console.log('Found clips in storage:', videoData.clips);
      console.log('Clips type:', typeof videoData.clips);
      console.log('Is array:', Array.isArray(videoData.clips));
      console.log('Clips length:', videoData.clips.length);
      
      // Parse clips if they're stored as a string
      if (typeof videoData.clips === 'string') {
        try {
          videoData.clips = JSON.parse(videoData.clips);
          console.log('Parsed clips from string:', videoData.clips);
        } catch (e) {
          console.error('Failed to parse clips string:', e);
        }
      }
    }

    // Restore the prompt from chrome.storage.local if available
    if (savedPrompt) {
      console.log('Restoring prompt from chrome storage:', savedPrompt);
      promptInput.value = savedPrompt;
    } else if (videoData && videoData.prompt) {
      console.log('Restoring prompt from video data:', videoData.prompt);
      promptInput.value = videoData.prompt;
    }

    // Check for any in-progress jobs in storage
    const jobData = await new Promise((resolve) => {
      chrome.storage.local.get(null, (items) => {
        // First look for jobs related to the current video
        if (videoData && videoData.jobId) {
          const jobKey = `job_${videoData.jobId}`;
          if (items[jobKey]) {
            resolve(items[jobKey]);
            return;
          }
        }
        
        // If no video-specific job, check for any job
        const jobIds = Object.keys(items).filter(key => key.startsWith('job_'));
        if (jobIds.length > 0) {
          const jobId = jobIds[0];
          resolve(items[jobId]);
        } else {
          resolve(null);
        }
      });
    });

    // Handle job data for in-progress extractions
    if (jobData && jobData.prompt) {
      console.log(`Found active job with prompt: ${jobData.prompt}`);
      // Only override if video data has no prompt
      if (!promptInput.value) {
        promptInput.value = jobData.prompt;
      }
      promptInput.disabled = true;
      extractButton.disabled = true;
      showLoadingState();
    }

    if (videoData) {
      if (videoData.status === 'completed') {
        console.log('Video has completed status');
        
        // If we have clips in storage, display them
        if (videoData.clips && Array.isArray(videoData.clips) && videoData.clips.length > 0) {
          console.log('Video has clips in storage, count:', videoData.clips.length);
          displayClips(videoData.clips);
          promptInput.disabled = true;
          extractButton.disabled = true;
          addStartOverButton();
        } else {
          console.error('Completed status but no valid clips array in storage');
          showError('No valid clips found in storage. Please try again.');
        }
      } else if (videoData.status === 'pending') {
        console.log('Video is pending, showing loading state');
        showLoadingState();
        promptInput.disabled = true;
        extractButton.disabled = true;
      } else if (videoData.status === 'failed') {
        console.log('Video extraction failed, showing error');
        showError(videoData.error);
        promptInput.disabled = false;
        extractButton.disabled = false;
        addStartOverButton();
      }
    }

    // Add click handler for extract button
    extractButton.addEventListener('click', async () => {
      const prompt = promptInput.value.trim();
      if (!prompt) {
        showError('Please enter what content you want to extract.');
        return;
      }

      // Store prompt directly in chrome.storage.local for persistence
      // This ensures it's preserved even if the popup is closed and reopened
      console.log('Storing prompt in chrome storage:', prompt);
      await chrome.storage.local.set({
        [`prompt_${videoId}`]: prompt,
        [videoId]: {
          status: 'pending',
          prompt: prompt,
          lastUpdated: Date.now()
        }
      });

      showLoadingState();
      promptInput.disabled = true;
      extractButton.disabled = true;

      // Add a timeout to check if we haven't received ANY response
      const initialTimeoutId = setTimeout(async () => {
        console.log("Initial timeout triggered - checking server response");
        
        // Check if we've received any updates since starting
        const data = await chrome.storage.local.get(videoId);
        const videoData = data[videoId];
        const timeSinceLastUpdate = Date.now() - (videoData?.lastUpdated || 0);
        
        // Only show error if we haven't received any updates in the last 15 seconds
        if (videoData && videoData.status === 'pending' && timeSinceLastUpdate > 15000) {
          showError('Server is not responding. Please check if the server is running.');
          promptInput.value = prompt; // Ensure prompt is preserved
          promptInput.disabled = false;
          extractButton.disabled = false;
          addStartOverButton();
          
          // Update storage with error state
          await chrome.storage.local.set({
            [videoId]: {
              status: 'failed',
              prompt: prompt,
              error: 'Server is not responding. Please check if the server is running.'
            }
          });
        }
      }, 15000);

      // Store the timeout ID in chrome.storage.local instead of session storage
      await chrome.storage.local.set({
        [`timeout_${videoId}`]: initialTimeoutId.toString()
      });

      // Send message to content script to start extraction
      chrome.tabs.sendMessage(tab.id, {
        action: 'extractClips',
        prompt: prompt
      });
    });

  } catch (error) {
    console.error('Error:', error);
    showError('Error loading clips.');
  }
});

// Listen for messages from content script
chrome.runtime.onMessage.addListener((message) => {
  console.log("Received message from content script:", message);
  
  if (!message.videoId) {
    console.error("Received message without videoId:", message);
    return;
  }

  // Update the lastUpdated timestamp whenever we receive any message
  chrome.storage.local.get(message.videoId, (data) => {
    const videoData = data[message.videoId];
    console.log('Updating lastUpdated timestamp for videoData: ', videoData);
    if (videoData) {
      chrome.storage.local.set({
        [message.videoId]: {
          ...videoData,
          lastUpdated: Date.now()
        }
      });
    }
  });

  // Handle timeout cancellation for initial timeout
  chrome.storage.local.get(`timeout_${message.videoId}`, (data) => {
    const timeoutIdStr = data[`timeout_${message.videoId}`];
    if (timeoutIdStr) {
      const timeoutId = parseInt(timeoutIdStr);
      console.log("Clearing timeout:", timeoutId);
      clearTimeout(timeoutId);
      chrome.storage.local.remove(`timeout_${message.videoId}`);
    }
  });

  if (message.action === 'extractionComplete') {
    console.log("Extraction complete, message clips:", message.clips);
    console.log("Message clips type:", typeof message.clips);
    console.log("Message clips is array:", Array.isArray(message.clips));
    console.log("Message clips length:", message.clips ? message.clips.length : 0);
    
    // FIRST get the current data from storage to ensure we have the clips
    chrome.storage.local.get(message.videoId, async (currentData) => {
      const videoData = currentData[message.videoId];
      console.log("Current video data in storage:", videoData);
      
      // Use clips from storage if available, otherwise use from message
      let clips = [];
      if (videoData && videoData.clips && Array.isArray(videoData.clips) && videoData.clips.length > 0) {
        console.log("Using clips from storage:", videoData.clips);
        clips = videoData.clips;
      } else if (Array.isArray(message.clips) && message.clips.length > 0) {
        console.log("Using clips from message:", message.clips);
        clips = message.clips;
      } else {
        console.log("No clips found in storage or message");
      }
      
      // Get the stored prompt
      const promptData = await chrome.storage.local.get(`prompt_${message.videoId}`);
      const storedPrompt = promptData[`prompt_${message.videoId}`];
      
      if (!storedPrompt) {
        console.error("No stored prompt found for video:", message.videoId);
      }

      // Important: Only update storage if we have clips
      if (clips.length > 0) {
        console.log("Updating storage with clips, count:", clips.length);
        
        // Update storage with completed status, clips, and prompt
        chrome.storage.local.set({
          [message.videoId]: {
            status: 'completed',
            prompt: storedPrompt,
            clips: clips,
            lastUpdated: Date.now(),
            jobId: message.jobId || videoData?.jobId
          }
        }, () => {
          // After storage is updated, immediately display clips
          console.log("Storage updated, retrieving updated data to verify");
          chrome.storage.local.get(message.videoId, (updatedData) => {
            console.log("Verified data in storage:", updatedData[message.videoId]);
            
            // After storage is updated, immediately display clips
            console.log("Displaying clips");
            const promptInput = document.getElementById('prompt');
            if (promptInput && storedPrompt) {
              promptInput.value = storedPrompt;
              promptInput.disabled = true;
            }
            
            // Display clips from storage
            if (clips && clips.length > 0) {
              console.log("Displaying clips, count:", clips.length);
              displayClips(clips);
            } else {
              console.error("No clips found or clips array is empty");
              showError('No clips found for the given prompt.');
            }
            
            addStartOverButton();
          });
        });
      } else {
        console.error("No clips available to update storage");
        showError('No clips found for the given prompt.');
      }
    });
  } else if (message.action === 'extractionError') {
    console.log("Extraction error received:", message.error);

    // Get the stored prompt
    chrome.storage.local.get(`prompt_${message.videoId}`, (data) => {
      const storedPrompt = data[`prompt_${message.videoId}`];
      
      if (!storedPrompt) {
        console.error("No stored prompt found for video:", message.videoId);
      }
      
      // Update storage with error status and prompt
      chrome.storage.local.set({
        [message.videoId]: {
          status: 'failed',
          prompt: storedPrompt,
          error: message.error,
          lastUpdated: Date.now()
        }
      }, () => {
        // Immediately update the UI to show the error
        const promptInput = document.getElementById('prompt');
        if (promptInput && storedPrompt) {
          promptInput.value = storedPrompt;
          promptInput.disabled = false;
        }
        
        const extractButton = document.getElementById('extract');
        if (extractButton) {
          extractButton.disabled = false;
        }
        
        showError(message.error);
        addStartOverButton();
      });
    });
  }
});

function displayClips(clips) {
  const clipsContainer = document.getElementById('clips-container');
  const extractButton = document.getElementById('extract');
  
  console.log("displayClips called with:", clips);
  console.log("clips type:", typeof clips);
  console.log("clips is array:", Array.isArray(clips));
  console.log("clips length:", clips ? clips.length : 0);
  
  if (!clips || !Array.isArray(clips) || clips.length === 0) {
    console.error("displayClips received invalid or empty clips array");
    clipsContainer.innerHTML = '<div class="status">No clips found for the given prompt.</div>';
    return;
  }

  try {
    // Create the HTML content first
    const clipsHTML = clips
      .map((clip, index) => {
        console.log(`Processing clip ${index}:`, clip);
        if (!clip || typeof clip !== 'object') {
          console.error(`Invalid clip at index ${index}:`, clip);
          return '';
        }
        
        const startTime = clip.start_time || 0;
        const text = clip.text || 'No text available';
        
        return `
          <div class="clip-item" data-timestamp="${startTime}">
            <div class="timestamp">${formatTimestamp(startTime)}</div>
            <div class="summary">${text}</div>
          </div>
        `;
      })
      .filter(html => html !== '') // Remove any empty entries
      .join('');

    console.log("Generated HTML:", clipsHTML);
    
    if (!clipsHTML) {
      console.error("No valid clips found to display");
      clipsContainer.innerHTML = '<div class="status">No valid clips found for the given prompt.</div>';
      return;
    }

    // Update the DOM in a single operation
    clipsContainer.innerHTML = clipsHTML;

    // Add click handlers for timestamps
    document.querySelectorAll('.clip-item').forEach(item => {
      item.addEventListener('click', () => {
        const timestamp = item.dataset.timestamp;
        // Send message to content script to seek video
        chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
          if (tab) {
            chrome.tabs.sendMessage(tab.id, {
              action: 'seekTo',
              timestamp: parseInt(timestamp)
            });
          }
        });
      });
    });

    // Only disable the extract button
    extractButton.disabled = true;
  } catch (error) {
    console.error("Error displaying clips:", error);
    clipsContainer.innerHTML = '<div class="status error">Error displaying clips: ' + error.message + '</div>';
  }
}

function showLoadingState() {
  const clipsContainer = document.getElementById('clips-container');
  clipsContainer.innerHTML = '<div class="status loading">Processing video...</div>';
}

function showError(message) {
  const clipsContainer = document.getElementById('clips-container');
  clipsContainer.innerHTML = `<div class="status error">${message}</div>`;
}

function addStartOverButton() {
  const promptInput = document.getElementById('prompt');
  const extractButton = document.getElementById('extract');
  const clipsContainer = document.getElementById('clips-container');
  
  // Remove existing start over button if any
  const existingButton = document.querySelector('.start-over');
  if (existingButton) {
    existingButton.remove();
  }

  const startOverButton = document.createElement('button');
  startOverButton.textContent = 'Start Over';
  startOverButton.className = 'start-over';
  
  // Add button to the input container
  const inputContainer = document.querySelector('.input-container');
  inputContainer.appendChild(startOverButton);

  // Add click handler
  startOverButton.addEventListener('click', async () => {
    // Get current video ID
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const videoId = new URLSearchParams(new URL(tab.url).search).get('v');
    
    // Clear chrome storage
    await chrome.storage.local.remove([
      videoId, 
      `prompt_${videoId}`,
      `timeout_${videoId}`
    ]);
    
    // Reset UI
    promptInput.value = '';
    promptInput.disabled = false;
    extractButton.disabled = false;
    clipsContainer.innerHTML = '<div class="status">Enter a prompt to extract clips.</div>';
    startOverButton.remove();
  });
}

function formatTimestamp(seconds) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainingSeconds = seconds % 60;

  if (hours > 0) {
    return `${hours}:${padZero(minutes)}:${padZero(remainingSeconds)}`;
  }
  return `${minutes}:${padZero(remainingSeconds)}`;
}

function padZero(num) {
  return num.toString().padStart(2, '0');
} 