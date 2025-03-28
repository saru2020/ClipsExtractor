import os
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from mangum import Mangum
from dotenv import load_dotenv
import shutil
import tempfile

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Debug OpenAI environment variables
for env_var in os.environ:
    if 'OPENAI' in env_var.upper() or 'PROXY' in env_var.upper():
        logger.info(f"Environment variable: {env_var}={os.environ[env_var]}")

app = FastAPI(
    title="Clips Extractor API",
    description="API for extracting clips from media based on user prompts",
    version="1.0.0"
)

# Configure CORS with more permissive settings for development
origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create a directory for local storage that will be served by the static files handler
local_storage_dir = os.path.join(os.getcwd(), 'local_storage')
os.makedirs(local_storage_dir, exist_ok=True)
logger.info(f"Using local storage directory: {local_storage_dir}")

# Mount the local storage directory as a static files location
app.mount("/mock-s3", StaticFiles(directory=local_storage_dir), name="mock-s3")

# Import routes after CORS setup
from app.api import router as api_router
app.include_router(api_router, prefix="/api")

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Mock S3 endpoint for serving files (fallback if static files route doesn't work)
@app.get("/mock-s3/{bucket}/{key:path}")
async def mock_s3(bucket: str, key: str):
    """Mock S3 endpoint to serve media files locally."""
    logging.info(f"Serving mock S3 file: {bucket}/{key}")
    
    # Full path to the file in our local storage
    file_path = os.path.join(local_storage_dir, bucket, key)
    
    if os.path.exists(file_path):
        logging.info(f"Serving file from: {file_path}")
        # Determine content type based on file extension
        content_type = "video/mp4" if file_path.endswith('.mp4') else "application/octet-stream"
        return FileResponse(file_path, media_type=content_type)
    
    # If file doesn't exist in local storage, try to find it in the temp directory
    outputs_dir = os.getenv('MEDIA_TEMP_PATH', '/tmp/clips-extractor-media')
    
    # Extract job ID from the key
    parts = key.split('/')
    if len(parts) >= 2 and parts[0] == 'outputs':
        job_id = parts[1]
        job_dir = os.path.join(outputs_dir, job_id)
        
        if os.path.exists(job_dir):
            # Look for the output file
            if "output.mp4" in parts:
                output_file = os.path.join(job_dir, "output.mp4")
                if os.path.exists(output_file):
                    logging.info(f"Serving output file from temp directory: {output_file}")
                    # Also copy it to local storage for future use
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    shutil.copy2(output_file, file_path)
                    return FileResponse(output_file, media_type="video/mp4")
    
    logging.warning(f"File not found: {file_path}")
    raise HTTPException(status_code=404, detail="File not found")

# Simple CORS test endpoint
@app.options("/{rest_of_path:path}")
async def options_route(rest_of_path: str):
    return {}

# Handler for AWS Lambda
handler = Mangum(app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")
