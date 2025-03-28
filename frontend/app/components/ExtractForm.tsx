'use client';

import { useState } from 'react';
import { submitExtractJob } from '../api/api-client';

interface ExtractFormProps {
  onSubmitSuccess: (jobId: string) => void;
  onSubmitError: (error: Error) => void;
}

export default function ExtractForm({ onSubmitSuccess, onSubmitError }: ExtractFormProps) {
  const [url, setUrl] = useState('');
  const [prompt, setPrompt] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [urlError, setUrlError] = useState('');
  const [promptError, setPromptError] = useState('');

  const validateForm = (): boolean => {
    let isValid = true;
    
    // Clear errors
    setUrlError('');
    setPromptError('');
    
    // Validate URL
    if (!url.trim()) {
      setUrlError('Please enter a URL');
      isValid = false;
    } else if (!isValidUrl(url)) {
      setUrlError('Please enter a valid URL');
      isValid = false;
    }
    
    // Validate prompt
    if (!prompt.trim()) {
      setPromptError('Please enter a prompt');
      isValid = false;
    }
    
    return isValid;
  };
  
  const isValidUrl = (url: string): boolean => {
    try {
      new URL(url);
      return true;
    } catch {
      return false;
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    
    if (!validateForm()) {
      return;
    }
    
    setIsLoading(true);
    
    try {
      const response = await submitExtractJob({ url, prompt });
      onSubmitSuccess(response.id);
    } catch (error) {
      if (error instanceof Error) {
        onSubmitError(error);
      } else {
        onSubmitError(new Error('Failed to submit job'));
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full max-w-2xl mx-auto bg-white rounded-lg shadow p-6">
      <h2 className="text-xl font-bold mb-6">Extract Clips</h2>
      
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="url" className="block text-sm font-medium text-gray-700 mb-1">
            Media URL
          </label>
          <input
            id="url"
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.youtube.com/watch?v=..."
            className={`w-full p-2 border rounded-md ${urlError ? 'border-red-500' : 'border-gray-300'}`}
            disabled={isLoading}
          />
          {urlError && <p className="mt-1 text-sm text-red-600">{urlError}</p>}
        </div>
        
        <div>
          <label htmlFor="prompt" className="block text-sm font-medium text-gray-700 mb-1">
            Topic Prompt
          </label>
          <textarea
            id="prompt"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Describe the topic you want to extract clips about..."
            className={`w-full p-2 border rounded-md ${promptError ? 'border-red-500' : 'border-gray-300'} min-h-[120px]`}
            disabled={isLoading}
          />
          {promptError && <p className="mt-1 text-sm text-red-600">{promptError}</p>}
        </div>
        
        <div className="pt-2">
          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-md transition duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? 'Submitting...' : 'Extract Clips'}
          </button>
        </div>
      </form>
    </div>
  );
} 