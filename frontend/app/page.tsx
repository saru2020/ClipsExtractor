'use client';

import { useState } from 'react';
import ExtractForm from './components/ExtractForm';
import JobStatus from './components/JobStatus';

export default function Home() {
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleJobSubmit = (jobId: string) => {
    setCurrentJobId(jobId);
    setError(null);
  };

  const handleSubmitError = (error: Error) => {
    setError(error.message);
  };

  const handleReset = () => {
    setCurrentJobId(null);
    setError(null);
  };

  return (
    <main className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="container mx-auto">
        <header className="text-center mb-8">
          <h1 className="text-3xl font-bold mb-2">Clips Extractor</h1>
          <p className="text-gray-600 max-w-2xl mx-auto">
            Extract relevant clips from YouTube videos or other media sources based on your topic of interest.
          </p>
        </header>

        {error && (
          <div className="w-full max-w-2xl mx-auto bg-red-100 text-red-800 p-4 rounded-md mb-6">
            {error}
          </div>
        )}

        {!currentJobId ? (
          <ExtractForm 
            onSubmitSuccess={handleJobSubmit} 
            onSubmitError={handleSubmitError} 
          />
        ) : (
          <JobStatus 
            jobId={currentJobId} 
            onReset={handleReset} 
          />
        )}

        <footer className="mt-12 text-center text-sm text-gray-500">
          <p>Powered by OpenAI</p>
        </footer>
      </div>
    </main>
  );
}
