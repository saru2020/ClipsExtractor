from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid


class JobStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    EXTRACTING = "extracting"
    COMPLETED = "completed"
    FAILED = "failed"


class Clip(BaseModel):
    start_time: float
    end_time: float
    text: str


class Job(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str
    prompt: str
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    error_message: Optional[str] = None
    input_media_path: Optional[str] = None
    output_media_path: Optional[str] = None
    output_media_url: Optional[str] = None
    clips: List[Clip] = []
    
    def update_status(self, status: JobStatus, error_message: Optional[str] = None):
        self.status = status
        self.updated_at = datetime.now()
        if error_message:
            self.error_message = error_message
