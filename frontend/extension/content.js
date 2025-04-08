// Listen for messages from the popup
chrome.runtime.onMessage.addListener((request) => {
  if (request.action === 'seekTo') {
    const video = document.querySelector('video');
    if (video) {
      video.currentTime = request.timestamp;
      video.play();
    }
  } else if (request.action === 'extractClips') {
    const videoId = getVideoId();
    if (videoId) {
      extractClips(videoId, request.prompt);
    }
  }
});

// Function to extract video ID from URL
function getVideoId() {
  const urlParams = new URLSearchParams(window.location.search);
  return urlParams.get('v');
}

// Function to get the full YouTube video URL
function getVideoUrl() {
  return window.location.href;
}

// Function to extract clips using the backend API
async function extractClips(videoId, prompt) {
  console.log(`Starting extraction for video ${videoId} with prompt: ${prompt}`);
  try {
    // Call the backend API to start the extraction
    console.log('Calling backend API...');
    const response = await fetch('http://localhost:8000/api/extract', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        url: getVideoUrl(),
        prompt: prompt
      })
    });

    if (!response.ok) {
      throw new Error(`API request failed: ${response.status} - ${response.statusText}`);
    }

    const data = await response.json();
    const jobId = data.id;
    console.log(`Job created with ID: ${jobId}`);

    // Store the job ID and prompt in extension storage
    await chrome.storage.local.set({
      [videoId]: {
        jobId: jobId,
        status: 'pending',
        prompt: prompt
      }
    });
    
    // Also store the prompt using the jobId key for reference
    await chrome.storage.local.set({
      [`job_${jobId}`]: {
        prompt: prompt
      }
    });
    
    // Send a response back to the popup with the jobId
    chrome.runtime.sendMessage({
      action: 'jobStarted',
      videoId: videoId,
      jobId: jobId
    });

    // Poll for job status
    pollJobStatus(jobId, videoId, prompt);
    
    // Return the jobId to the popup
    return { jobId: jobId };
  } catch (error) {
    console.error('Error starting extraction:', error);
    let errorMessage;
    
    // Handle specific network errors
    if (error.name === 'TypeError' || error.message.includes('Failed to fetch')) {
      errorMessage = 'Cannot connect to server. Please check if the server is running at http://localhost:8000';
    } else {
      errorMessage = error.message || 'Failed to connect to the server. Please try again.';
    }
    
    console.log(`Sending error message to popup: ${errorMessage}`);
    
    // Update storage to reflect the error state
    await chrome.storage.local.set({
      [videoId]: {
        status: 'failed',
        prompt: prompt,
        error: errorMessage
      }
    });
    
    // Notify popup about the error
    chrome.runtime.sendMessage({
      action: 'extractionError',
      error: errorMessage,
      videoId: videoId
    });
  }
}

// Keep track of active polling intervals
const activePolls = new Map();

// Function to poll job status
async function pollJobStatus(jobId, videoId, prompt) {
  // Clear any existing polling for this video
  if (activePolls.has(videoId)) {
    clearTimeout(activePolls.get(videoId));
    activePolls.delete(videoId);
  }

  try {
    const response = await fetch(`http://localhost:8000/api/jobs/${jobId}`);
    if (!response.ok) {
      throw new Error(`Failed to get job status: ${response.status} - ${response.statusText}`);
    }

    const data = await response.json();
    console.log("Job status data received:", data); // Log the complete data

    // Check if we should continue polling by checking storage
    const storageData = await chrome.storage.local.get(videoId);
    const videoData = storageData[videoId];
    
    // If status is failed in storage, stop polling
    if (videoData && videoData.status === 'failed') {
      console.log('Stopping poll due to failed status in storage');
      return;
    }

    if (data.status === 'completed') {
      console.log("Job completed, raw clips data:", data.clips);
      
      // Validate and normalize the clips data
      let normalizedClips = [];
      
      if (data.clips) {
        if (typeof data.clips === 'string') {
          try {
            normalizedClips = JSON.parse(data.clips);
          } catch (e) {
            console.error('Error parsing clips string:', e);
          }
        } else if (Array.isArray(data.clips)) {
          normalizedClips = data.clips.map(clip => {
            // Ensure each clip has the required fields
            return {
              start_time: typeof clip.start_time === 'number' ? clip.start_time : 0,
              end_time: typeof clip.end_time === 'number' ? clip.end_time : 0,
              text: typeof clip.text === 'string' ? clip.text : 'No text available'
            };
          });
        }
      }
      
      console.log("Normalized clips:", normalizedClips);
      console.log("Normalized clips length:", normalizedClips.length);
      
      // Store the validated clips in extension storage
      await chrome.storage.local.set({
        [videoId]: {
          jobId: jobId,
          status: 'completed',
          clips: normalizedClips,
          prompt: prompt
        }
      });
      
      // Verify that clips were stored properly
      const updatedData = await chrome.storage.local.get(videoId);
      console.log("Verified clips in storage:", updatedData[videoId].clips);

      // Notify popup about completion with validated clips
      chrome.runtime.sendMessage({
        action: 'extractionComplete',
        videoId: videoId,
        jobId: jobId,
        clips: normalizedClips
      });
    } else if (data.status === 'failed') {
      await chrome.storage.local.set({
        [videoId]: {
          jobId: jobId,
          status: 'failed',
          error: data.error_message || 'Processing failed. Please try again.',
          prompt: prompt
        }
      });

      chrome.runtime.sendMessage({
        action: 'extractionError',
        error: data.error_message || 'Processing failed. Please try again.',
        videoId: videoId,
        jobId: jobId
      });
    } else {
      // Continue polling if job is still processing
      const timeoutId = setTimeout(() => pollJobStatus(jobId, videoId, prompt), 5000);
      activePolls.set(videoId, timeoutId);
    }
  } catch (error) {
    console.error('Error polling job status:', error);
    let errorMessage;
    if (error.message.includes('Failed to fetch')) {
      errorMessage = 'Lost connection to server. Please check if the server is running.';
    } else {
      errorMessage = error.message || 'Lost connection to the server. Please try again.';
    }
    
    // Update storage to reflect the error state
    await chrome.storage.local.set({
      [videoId]: {
        status: 'failed',
        prompt: prompt,
        error: errorMessage
      }
    });
    
    // Notify popup about the error
    chrome.runtime.sendMessage({
      action: 'extractionError',
      error: errorMessage,
      videoId: videoId,
      jobId: jobId
    });
  }
}

// Function to process video transcripts and generate clips
async function processVideo() {
  const videoId = getVideoId();
  if (!videoId) return;

  // Get existing clips from storage
  const data = await chrome.storage.local.get(videoId);
  if (data[videoId]) return; // Clips already exist

  // Get transcript
  const transcriptButton = document.querySelector('button.ytp-subtitles-button');
  if (!transcriptButton || !transcriptButton.getAttribute('aria-pressed') === 'true') {
    console.log('No transcript available');
    return;
  }

  // For demonstration, create some sample clips
  // In a real implementation, you would process the actual transcript
  const sampleClips = [
    {
      timestamp: 30,
      summary: "Introduction to the topic"
    },
    {
      timestamp: 120,
      summary: "Main discussion points"
    },
    {
      timestamp: 300,
      summary: "Key takeaways and conclusion"
    }
  ];

  // Store clips in extension storage
  await chrome.storage.local.set({
    [videoId]: sampleClips
  });
}

// Wait for page load and process video
window.addEventListener('load', () => {
  // Wait for YouTube's dynamic content to load
  setTimeout(processVideo, 2000);
});

// Listen for YouTube navigation (SPA)
let lastUrl = location.href;
new MutationObserver(() => {
  const url = location.href;
  if (url !== lastUrl) {
    lastUrl = url;
    setTimeout(processVideo, 2000);
  }
}).observe(document, { subtree: true, childList: true }); 