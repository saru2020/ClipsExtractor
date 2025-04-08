import os
import logging
import asyncio
import traceback
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl
from typing import Optional, Dict
import json

from models.job import Job, JobStatus
from utils.media_processor import MediaProcessor
from utils.s3_manager import S3Manager

# Set up logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# In-memory job storage (replace with a database in production)
jobs: Dict[str, Job] = {}

# Request and response models
class ExtractClipRequest(BaseModel):
    url: str
    prompt: str

class JobResponse(BaseModel):
    id: str
    status: str
    created_at: str
    updated_at: str
    clips: list = []
    error_message: Optional[str] = None
    output_url: Optional[str] = None

# Dependencies
def get_media_processor():
    try:
        return MediaProcessor()
    except Exception as e:
        logger.error(f"Failed to initialize MediaProcessor: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def get_s3_manager():
    try:
        return S3Manager()
    except Exception as e:
        logger.error(f"Failed to initialize S3Manager: {str(e)}")
        logger.error(traceback.format_exc())
        raise

# Background task to process the job
async def process_job(
    job_id: str, 
    media_processor: MediaProcessor,
    s3_manager: S3Manager
):
    job = jobs[job_id]
    
    try:
        logger.info(f"Starting processing for job {job_id}")
        
        # Download media
        logger.info(f"Job {job_id}: Downloading media from URL: {job.url}")
        media_path = media_processor.download_media(job)
        logger.info(f"Job {job_id}: Media downloaded to {media_path}")
        
        # Process and get transcript
        job.update_status(JobStatus.PROCESSING)
        logger.info(f"Job {job_id}: Transcribing media")
        transcript_data = media_processor.get_transcript(media_path)
        
        # Log transcript information
        if hasattr(transcript_data, 'text'):
            transcript_text = transcript_data.text
        elif isinstance(transcript_data, dict) and 'text' in transcript_data:
            transcript_text = transcript_data['text']
        else:
            transcript_text = str(transcript_data)
            
        # Count segments if available
        segments_count = 0
        if hasattr(transcript_data, 'segments'):
            segments_count = len(transcript_data.segments)
        elif isinstance(transcript_data, dict) and 'segments' in transcript_data:
            segments_count = len(transcript_data['segments'])
            
        logger.info(f"Job {job_id}: Transcription completed, text length: {len(transcript_text)} chars, segments: {segments_count}")
        
        logger.info(f"Job {job_id}: Transcript data: {transcript_text}")
        
        # Get clip timestamps
        logger.info(f"Job {job_id}: Getting clip timestamps for prompt: {job.prompt}")
        job.clips = media_processor.get_clip_timestamps(transcript_data, job.prompt)
        logger.info(f"Job {job_id}: Found {len(job.clips)} clips")
        
        # For local development, we can skip clip extraction and S3 upload if needed
        # Just return the clips as timestamps for the frontend to handle
        if len(job.clips) == 0:
            # If no clips were found, set an error
            error_msg = "No clips could be found for the given prompt"
            logger.warning(f"Job {job_id}: {error_msg}")
            job.update_status(JobStatus.FAILED, error_msg)
            return
        
        # Extract clips - this is optional for local development
        try:
            logger.info(f"Job {job_id}: Extracting clips")
            output_path = media_processor.extract_clips(job)
            logger.info(f"Job {job_id}: Clips extracted to {output_path}")
            
            # Upload to S3 - only if both output_path and S3 manager are available
            if output_path and hasattr(s3_manager, 'mock_storage_dir') and s3_manager.mock_storage_dir:
                logger.info(f"Job {job_id}: Uploading to mock S3")
                try:
                    s3_key = f"outputs/{job.id}/output.mp4"
                    s3_uri = s3_manager.upload_file(output_path, s3_key)
                    logger.info(f"Job {job_id}: File uploaded to {s3_uri}")
                    
                    presigned_url = s3_manager.generate_presigned_url(s3_key, 24 * 3600)  # 24 hours
                    job.output_media_url = presigned_url
                    logger.info(f"Job {job_id}: Generated presigned URL: {presigned_url[:100]}...")
                except Exception as e:
                    # If upload fails, log it but don't fail the job - we still have the clips
                    logger.warning(f"Job {job_id}: S3 upload failed: {str(e)}. Continuing without upload.")
            else:
                logger.info(f"Job {job_id}: Skipping S3 upload for local development")
        except Exception as e:
            # If clip extraction fails, log the error but continue with timestamps only
            logger.warning(f"Job {job_id}: Clip extraction failed: {str(e)}. Continuing with timestamps only.")
        
        job.update_status(JobStatus.COMPLETED)
        logger.info(f"Job {job_id}: Processing completed successfully")
        
    except Exception as e:
        error_msg = f"Job processing failed: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        job.update_status(JobStatus.FAILED, error_msg)
    
    finally:
        # Clean up after some time
        # In a production environment, schedule this cleanup with a proper task queue
        await asyncio.sleep(3600)  # 1 hour
        try:
            logger.info(f"Job {job_id}: Cleaning up temporary files")
            media_processor.cleanup(job.id)
        except Exception as e:
            logger.error(f"Job {job_id}: Cleanup failed: {str(e)}")

# API endpoints
@router.post("/extract", response_model=JobResponse)
async def extract_clip(
    request: Request,
    extract_request: ExtractClipRequest,
    background_tasks: BackgroundTasks,
    media_processor: MediaProcessor = Depends(get_media_processor),
    s3_manager: S3Manager = Depends(get_s3_manager)
):
    """Submit a new clip extraction job."""
    try:
        # Log request info
        client_host = request.client.host if request.client else "unknown"
        logger.info(f"Received extraction request from {client_host}")
        logger.info(f"Request data: URL={extract_request.url}, Prompt={extract_request.prompt}")
        
        # Create job
        job = Job(url=extract_request.url, prompt=extract_request.prompt)
        jobs[job.id] = job
        logger.info(f"Created job with ID: {job.id}")
        
        # Start processing in the background
        background_tasks.add_task(process_job, job.id, media_processor, s3_manager)
        logger.info(f"Added job {job.id} to background tasks")
        
        return JobResponse(
            id=job.id,
            status=job.status,
            created_at=job.created_at.isoformat(),
            updated_at=job.updated_at.isoformat()
        )
    except Exception as e:
        error_msg = f"Failed to submit extraction job: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_msg)

# @router.options("/extract")
# async def options_extract():
#     """Handle OPTIONS preflight request for extract endpoint."""
#     return JSONResponse(content={})

@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str):
    """Get the status of a job."""
    logger.info(f"Received status request for job: {job_id}")
    
    if job_id not in jobs:
        logger.warning(f"Job not found: {job_id}")
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    logger.info(f"Job {job_id} status: {job.status}")
    
    return JobResponse(
        id=job.id,
        status=job.status,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        clips=[{
            "start_time": clip.start_time,
            "end_time": clip.end_time,
            "text": clip.text
        } for clip in job.clips],
        error_message=job.error_message,
        output_url=job.output_media_url
    )
