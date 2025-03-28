'use client';

import { useJobStatus } from '../hooks/use-job-status';
import { Clip } from '../api/api-client';
import { useEffect, useState, useRef } from 'react';

// Extend HTMLVideoElement type to include our custom property
interface ExtendedHTMLVideoElement extends HTMLVideoElement {
  _clipEndHandler?: EventListener;
  _canPlayHandler?: EventListener;
}

interface JobStatusProps {
  jobId: string;
  onReset: () => void;
}

export default function JobStatus({ jobId, onReset }: JobStatusProps) {
  const { data, error, loading } = useJobStatus(jobId, {
    pollingInterval: 3000,
    stopPollingOnComplete: true,
  });
  
  // State to track video loading and playback
  const [videoLoaded, setVideoLoaded] = useState<boolean>(false);
  const [videoError, setVideoError] = useState<boolean>(false);
  const [selectedClipIndex, setSelectedClipIndex] = useState<number | null>(null);
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const videoRef = useRef<ExtendedHTMLVideoElement>(null);

  // Log job data to debug
  useEffect(() => {
    if (data) {
      console.log('Job data:', data);
      if (data.output_url) {
        console.log('Output URL:', data.output_url);
      }
    }
  }, [data]);

  // Set up timeupdate listener for current time display
  useEffect(() => {
    const videoElement = videoRef.current;
    if (!videoElement) return;

    const handleTimeUpdate = () => {
      setCurrentTime(videoElement.currentTime);
    };

    const handlePlay = () => {
      setIsPlaying(true);
    };

    const handlePause = () => {
      setIsPlaying(false);
    };

    videoElement.addEventListener('timeupdate', handleTimeUpdate);
    videoElement.addEventListener('play', handlePlay);
    videoElement.addEventListener('pause', handlePause);

    return () => {
      // Only remove listeners if the element still exists
      if (videoElement) {
        videoElement.removeEventListener('timeupdate', handleTimeUpdate);
        videoElement.removeEventListener('play', handlePlay);
        videoElement.removeEventListener('pause', handlePause);
      }
    };
  }, [videoLoaded]); // Only re-run when the video is loaded

  // Clean up event listeners when component unmounts
  useEffect(() => {
    return () => {
      // Clean up all event listeners when component unmounts
      if (videoRef.current) {
        const videoElement = videoRef.current;
        
        // Remove clip end handler
        if (videoElement._clipEndHandler) {
          videoElement.removeEventListener('timeupdate', videoElement._clipEndHandler);
        }
        
        // Remove canplay handler
        if (videoElement._canPlayHandler) {
          videoElement.removeEventListener('canplay', videoElement._canPlayHandler);
        }
        
        // Also remove any other listeners
        videoElement.removeEventListener('loadedmetadata', () => {});
        videoElement.removeEventListener('canplay', () => {});
        videoElement.removeEventListener('timeupdate', () => {});
        videoElement.removeEventListener('play', () => {});
        videoElement.removeEventListener('pause', () => {});
      }
    };
  }, []);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-green-100 text-green-800';
      case 'failed':
        return 'bg-red-100 text-red-800';
      case 'downloading':
      case 'processing':
      case 'extracting':
        return 'bg-blue-100 text-blue-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'downloading':
        return 'Downloading media...';
      case 'processing':
        return 'Processing and transcribing media...';
      case 'extracting':
        return 'Extracting relevant clips...';
      case 'completed':
        return 'Clips extracted successfully!';
      case 'failed':
        return 'Failed to extract clips.';
      default:
        return 'Waiting to start...';
    }
  };

  // Handle video loading events
  const handleVideoLoaded = () => {
    console.log('Video loaded successfully');
    setVideoLoaded(true);
    setVideoError(false);
  };

  const handleVideoError = (e: React.SyntheticEvent<HTMLVideoElement, Event>) => {
    console.error('Video loading error:', e);
    setVideoError(true);
    setVideoLoaded(false);
  };

  // Function to play a specific clip
  const playClip = (index: number) => {
    if (!videoRef.current || !data?.clips?.[index]) return;
    
    // Calculate all clip durations and their positions in the output video
    const clipPositions = calculateClipPositionsInOutput(data.clips);
    const outputStartTime = clipPositions[index].start;
    const outputEndTime = clipPositions[index].end;
    
    // Get the original clip for logging and reference
    const clip = data.clips[index];
    
    console.log(`Playing clip ${index+1}: Original positions ${formatTime(clip.start_time)} - ${formatTime(clip.end_time)}`);
    console.log(`In output video, this is position ${formatTime(outputStartTime)} - ${formatTime(outputEndTime)}`);
    
    setSelectedClipIndex(index);
    
    // Clear any existing clip-specific timeupdate handlers
    if (videoRef.current._clipEndHandler) {
      videoRef.current.removeEventListener('timeupdate', videoRef.current._clipEndHandler);
      delete videoRef.current._clipEndHandler;
    }
    
    // Create a handler to check if we reached the end of the clip
    const handleClipEnd = function() {
      const video = videoRef.current;
      if (!video) return;
      
      // If we've reached or passed the end time, pause the video
      if (video.currentTime >= outputEndTime) {
        console.log(`Clip ${index+1} reached end time (${formatTime(outputEndTime)}), pausing`);
        video.pause();
      }
    };
    
    // Store the handler on the video element so we can remove it later
    videoRef.current._clipEndHandler = handleClipEnd;
    
    // Add the handler to the video element
    videoRef.current.addEventListener('timeupdate', handleClipEnd);
    console.log('Added timeupdate listener to stop at clip end');

    // This is a more reliable way to seek videos in Chrome
    // First, pause the video and save the controls state
    const videoElement = videoRef.current;
    videoElement.pause();
    
    // Remove existing event listeners to avoid multiple calls
    videoElement.removeEventListener('canplay', videoElement._canPlayHandler as EventListener);
    
    // Function to handle canplay event - will be called when seeking is complete
    const handleCanPlay = () => {
      console.log(`Can play event triggered. Current time: ${formatTime(videoElement.currentTime)}`);
      
      // Check if we successfully seeked to the right position
      if (Math.abs(videoElement.currentTime - outputStartTime) < 0.5) {
        console.log(`Successfully seeked to ${formatTime(videoElement.currentTime)}`);
        videoElement.play()
          .then(() => console.log('Started playing after successful seek'))
          .catch(err => console.error('Error playing after seek:', err));
      } else {
        console.warn(`Seek position incorrect. Expected: ${formatTime(outputStartTime)}, Got: ${formatTime(videoElement.currentTime)}`);
        // Try to force it one more time and play anyway
        videoElement.currentTime = outputStartTime;
        videoElement.play()
          .then(() => console.log(`Started playing from ${formatTime(videoElement.currentTime)} after correction`))
          .catch(err => console.error('Error playing after correction:', err));
      }
      
      // Remove this handler after it runs
      videoElement.removeEventListener('canplay', handleCanPlay);
    };
    
    // Store the handler for later cleanup
    videoElement._canPlayHandler = handleCanPlay;
    videoElement.addEventListener('canplay', handleCanPlay);
    
    // Force reload and seek - this works more reliably in Chrome
    const currentSrc = videoElement.src;
    videoElement.load();
    
    // Listen for metadata loaded to set time
    videoElement.addEventListener('loadedmetadata', function onMetadataLoaded() {
      console.log('Metadata loaded, setting currentTime');
      videoElement.currentTime = outputStartTime;
      console.log(`Set current time to ${formatTime(outputStartTime)}`);
      
      // Remove this listener after it runs once
      videoElement.removeEventListener('loadedmetadata', onMetadataLoaded);
    }, { once: true });
    
    // Set the source back to trigger load
    videoElement.src = currentSrc;
  };

  // Play the full video
  const playFullVideo = () => {
    if (!videoRef.current) return;
    
    console.log('Playing full video');
    
    // Clear the selected clip state
    setSelectedClipIndex(null);
    
    // Remove clip-specific timeupdate handler if it exists
    if (videoRef.current._clipEndHandler) {
      videoRef.current.removeEventListener('timeupdate', videoRef.current._clipEndHandler);
      delete videoRef.current._clipEndHandler;
      console.log('Removed clip end handler');
    }
    
    // This is a more reliable way to seek videos in Chrome
    // First, pause the video
    const videoElement = videoRef.current;
    videoElement.pause();
    
    // Remove existing event listeners to avoid multiple calls
    videoElement.removeEventListener('canplay', videoElement._canPlayHandler as EventListener);
    
    // Function to handle canplay event - will be called when seeking is complete
    const handleCanPlay = () => {
      console.log(`Can play event triggered. Current time: ${formatTime(videoElement.currentTime)}`);
      
      // Check if we successfully seeked to the beginning
      if (videoElement.currentTime < 0.5) {
        console.log('Successfully seeked to beginning');
        videoElement.play()
          .then(() => console.log('Started playing full video after successful seek'))
          .catch(err => console.error('Error playing full video after seek:', err));
      } else {
        console.warn(`Seek position incorrect. Expected: 0:00, Got: ${formatTime(videoElement.currentTime)}`);
        // Try to force it one more time and play anyway
        videoElement.currentTime = 0;
        videoElement.play()
          .then(() => console.log(`Started playing full video from ${formatTime(videoElement.currentTime)} after correction`))
          .catch(err => console.error('Error playing full video after correction:', err));
      }
      
      // Remove this handler after it runs
      videoElement.removeEventListener('canplay', handleCanPlay);
    };
    
    // Store the handler for later cleanup
    videoElement._canPlayHandler = handleCanPlay;
    videoElement.addEventListener('canplay', handleCanPlay);
    
    // Force reload and seek - this works more reliably in Chrome
    const currentSrc = videoElement.src;
    videoElement.load();
    
    // Listen for metadata loaded to set time
    videoElement.addEventListener('loadedmetadata', function onMetadataLoaded() {
      console.log('Metadata loaded, setting currentTime to beginning');
      videoElement.currentTime = 0;
      console.log('Set current time to beginning');
      
      // Remove this listener after it runs once
      videoElement.removeEventListener('loadedmetadata', onMetadataLoaded);
    }, { once: true });
    
    // Set the source back to trigger load
    videoElement.src = currentSrc;
  };

  // Calculate clip progress percentage
  const getClipProgressPercentage = (clip: Clip, index: number) => {
    if (!isPlaying || selectedClipIndex === null || selectedClipIndex !== index) return 0;
    
    // Use the clip position calculator
    const clipPositions = calculateClipPositionsInOutput(data?.clips || []);
    
    if (!clipPositions[index]) return 0;
    
    const clipStartInOutput = clipPositions[index].start;
    const clipEndInOutput = clipPositions[index].end;
    
    // Calculate progress based on output video position
    const progress = (currentTime - clipStartInOutput) / (clipEndInOutput - clipStartInOutput);
    return Math.max(0, Math.min(100, progress * 100));
  };
  
  // Helper function to calculate clip positions in the output video
  const calculateClipPositionsInOutput = (clips: Clip[]) => {
    // Create an array to store the start and end times of each clip in the output video
    const positions: { start: number; end: number; duration: number }[] = [];
    let currentPosition = 0;
    
    // Calculate the position of each clip in the output video
    clips.forEach(clip => {
      const duration = clip.end_time - clip.start_time;
      positions.push({
        start: currentPosition,
        end: currentPosition + duration,
        duration
      });
      currentPosition += duration;
    });
    
    return positions;
  };

  return (
    <div className="w-full max-w-2xl mx-auto bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold">Job Status</h2>
        <button
          onClick={onReset}
          className="text-sm text-blue-600 hover:text-blue-800"
        >
          Start Over
        </button>
      </div>

      <div className="mb-6">
        <div className="text-sm text-gray-500 mb-1">Job ID</div>
        <div className="font-mono text-sm bg-gray-100 p-2 rounded">{jobId}</div>
      </div>

      {loading && !data ? (
        <div className="py-6 flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      ) : error ? (
        <div className="bg-red-100 p-4 rounded-md text-red-800 mb-4">
          {error.message}
        </div>
      ) : data ? (
        <div>
          <div className="mb-4">
            <div className="text-sm text-gray-500 mb-1">Status</div>
            <div className={`inline-block px-3 py-1 rounded-full text-sm font-medium ${getStatusColor(data.status)}`}>
              {getStatusText(data.status)}
            </div>
          </div>

          {data.error_message && (
            <div className="bg-red-100 p-4 rounded-md text-red-800 mb-4">
              {data.error_message}
            </div>
          )}

          {data.status === 'completed' && data.output_url && (
            <div className="mb-6">
              <div className="flex justify-between items-center mb-2">
                <h3 className="text-lg font-medium">
                  {selectedClipIndex !== null 
                    ? `Playing Clip ${selectedClipIndex + 1}` 
                    : 'Full Extracted Video'}
                </h3>
                <div className="flex items-center space-x-2">
                  <div className="text-sm text-gray-600">
                    {selectedClipIndex !== null && data.clips[selectedClipIndex] ? (
                      // For clips, show time relative to clip start
                      <>
                        {(() => {
                          // Calculate clip positions in output video
                          const clipPositions = calculateClipPositionsInOutput(data.clips);
                          const clipPosition = clipPositions[selectedClipIndex];
                          
                          // Get relative time within clip
                          const clipDuration = data.clips[selectedClipIndex].end_time - data.clips[selectedClipIndex].start_time;
                          const relativeTime = Math.max(0, currentTime - clipPosition.start);
                          
                          return `${formatTime(relativeTime)} / ${formatTime(clipDuration)}`;
                        })()}
                      </>
                    ) : (
                      // For full video, show absolute time
                      formatTime(currentTime)
                    )}
                  </div>
                  <button
                    onClick={playFullVideo}
                    className={`text-sm px-3 py-1 rounded ${
                      selectedClipIndex === null 
                        ? 'bg-blue-600 text-white' 
                        : 'bg-gray-200 text-gray-700 hover:bg-blue-100'
                    }`}
                  >
                    Play Full Video
                  </button>
                </div>
              </div>
              <div className="aspect-video bg-black rounded-md overflow-hidden">
                <video
                  ref={videoRef}
                  className={`w-full h-full ${videoLoaded ? 'opacity-100' : 'opacity-80'}`}
                  controls
                  src={data.output_url}
                  onLoadedData={handleVideoLoaded}
                  onError={handleVideoError}
                >
                  Your browser does not support the video tag.
                </video>
              </div>
              
              {videoError && (
                <div className="mt-2 bg-yellow-100 p-4 rounded-md text-yellow-800">
                  <p><strong>Warning:</strong> Unable to load the video. It may still be processing or the server may not be able to serve it.</p>
                </div>
              )}
            </div>
          )}

          {data.clips && data.clips.length > 0 && (
            <div>
              <h3 className="text-lg font-medium mb-2">Individual Clips</h3>
              <div className="space-y-3">
                {data.clips.map((clip: Clip, index: number) => {
                  const isSelected = selectedClipIndex === index;
                  const progressPercent = isSelected ? getClipProgressPercentage(clip, index) : 0;
                  
                  return (
                    <div 
                      key={index} 
                      className={`border rounded-md p-3 transition-colors relative overflow-hidden ${
                        isSelected ? 'border-blue-500 bg-blue-50' : 'hover:bg-gray-50'
                      }`}
                    >
                      {/* Progress bar for the currently playing clip */}
                      {isSelected && isPlaying && (
                        <div 
                          className="absolute bottom-0 left-0 h-1 bg-blue-500 transition-all duration-300"
                          style={{ width: `${progressPercent}%` }}
                        />
                      )}
                      
                      <div className="flex justify-between items-center mb-1">
                        <div className="text-sm font-medium">
                          <span>Clip {index + 1}</span>
                          <span className="ml-2 text-xs text-gray-500">
                            (original timestamps: {formatTime(clip.start_time)} - {formatTime(clip.end_time)})
                          </span>
                          {isSelected && isPlaying && (
                            <span className="ml-2 text-xs text-blue-700">
                              • Playing
                            </span>
                          )}
                        </div>
                        <button 
                          onClick={() => playClip(index)}
                          className={`text-xs px-2 py-1 rounded ${
                            isSelected 
                              ? 'bg-blue-500 text-white' 
                              : 'bg-blue-100 text-blue-700 hover:bg-blue-200'
                          }`}
                        >
                          {isSelected && isPlaying ? 'Playing...' : 'Play Clip'}
                        </button>
                      </div>
                      <div className="text-sm text-gray-700">{clip.text}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
} 