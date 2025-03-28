/**
 * API client for interacting with the Clips Extractor backend
 */

// Get API URL from environment variable, with fallback
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

console.log('Using API URL:', API_BASE_URL);

export interface ExtractRequest {
  url: string;
  prompt: string;
}

export interface Clip {
  start_time: number;
  end_time: number;
  text: string;
}

export interface JobResponse {
  id: string;
  status: string;
  created_at: string;
  updated_at: string;
  clips: Clip[];
  error_message?: string;
  output_url?: string;
}

/**
 * Submit a new clip extraction job
 */
export async function submitExtractJob(data: ExtractRequest): Promise<JobResponse> {
  console.log('Submitting job to:', `${API_BASE_URL}/extract`);
  
  const response = await fetch(`${API_BASE_URL}/extract`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({detail: 'Failed to parse error response'}));
    throw new Error(error.detail || 'Failed to submit extraction job');
  }

  const result = await response.json();
  console.log('Job submitted successfully:', result);
  return result;
}

/**
 * Get the status of a job
 */
export async function getJobStatus(jobId: string): Promise<JobResponse> {
  console.log('Getting job status from:', `${API_BASE_URL}/jobs/${jobId}`);
  
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}`, {
    headers: {
      'Accept': 'application/json',
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({detail: 'Failed to parse error response'}));
    throw new Error(error.detail || 'Failed to get job status');
  }

  const result = await response.json();
  console.log('Job status received:', result);
  return result;
} 