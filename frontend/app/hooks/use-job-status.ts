import { useState, useEffect } from 'react';
import { getJobStatus, JobResponse } from '../api/api-client';

interface UseJobStatusOptions {
  pollingInterval?: number; // in milliseconds
  stopPollingOnComplete?: boolean;
}

export function useJobStatus(
  jobId: string | null,
  options: UseJobStatusOptions = {}
) {
  const { 
    pollingInterval = 5000, 
    stopPollingOnComplete = true 
  } = options;
  
  const [data, setData] = useState<JobResponse | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    if (!jobId) return;

    let isActive = true;
    let intervalId: NodeJS.Timeout | null = null;

    async function fetchStatus() {
      if (!isActive || !jobId) return;

      try {
        setLoading(true);
        const result = await getJobStatus(jobId);
        
        if (isActive) {
          setData(result);
          setError(null);
          
          // Stop polling if job is completed or failed and stopPollingOnComplete is true
          if (
            stopPollingOnComplete && 
            (result.status === 'completed' || result.status === 'failed')
          ) {
            if (intervalId) clearInterval(intervalId);
          }
        }
      } catch (err) {
        if (isActive) {
          setError(err instanceof Error ? err : new Error(String(err)));
        }
      } finally {
        if (isActive) {
          setLoading(false);
        }
      }
    }

    // Initial fetch
    fetchStatus();

    // Set up polling interval
    intervalId = setInterval(fetchStatus, pollingInterval);

    return () => {
      isActive = false;
      if (intervalId) clearInterval(intervalId);
    };
  }, [jobId, pollingInterval, stopPollingOnComplete]);

  return { data, error, loading };
} 