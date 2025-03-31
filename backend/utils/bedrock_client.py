import os
import logging
import json
import base64
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, ConnectionClosedError
from typing import Dict, List, Optional
import time
import requests

logger = logging.getLogger(__name__)

class BedrockClient:
    """Client for interacting with Amazon Bedrock services."""
    
    def __init__(self):
        logger.info("Initializing BedrockClient")
        self.region = os.getenv('AWS_REGION', 'us-east-2')
        
        # Configure Bedrock client with increased timeouts
        config = Config(
            region_name=self.region,
            retries={'max_attempts': 3},
            connect_timeout=60,  # 60 seconds
            read_timeout=300,    # 5 minutes
            max_pool_connections=50
        )
        
        self.client = boto3.client('bedrock-runtime', config=config)
        self.transcribe_client = boto3.client("transcribe")
        self.s3_client = boto3.client("s3")
        self.bucket_name = os.getenv("S3_BUCKET_NAME", "clips-extractor-media")
        logger.info("Bedrock client initialized successfully")
    
    def transcribe_audio(self, audio_file_path: str) -> str:
        """Transcribe audio using Amazon Transcribe"""
        try:
            # Upload audio file to S3
            file_name = os.path.basename(audio_file_path)
            s3_uri = f"s3://{self.bucket_name}/{file_name}"
            self.s3_client.upload_file(audio_file_path, self.bucket_name, file_name)

            # Start transcription job
            job_name = f"transcribe_{file_name}_{int(time.time())}"
            response = self.transcribe_client.start_transcription_job(
                TranscriptionJobName=job_name,
                Media={"MediaFileUri": s3_uri},
                MediaFormat="mp3",
                LanguageCode="en-US",
                Settings={
                    "ShowSpeakerLabels": True,
                    "MaxSpeakerLabels": 2
                }
            )

            # Wait for job completion
            while True:
                status = self.transcribe_client.get_transcription_job(
                    TranscriptionJobName=job_name
                )
                if status["TranscriptionJob"]["TranscriptionJobStatus"] in ["COMPLETED", "FAILED"]:
                    break
                time.sleep(5)

            if status["TranscriptionJob"]["TranscriptionJobStatus"] == "FAILED":
                raise Exception("Transcription job failed")

            # Get transcription results
            transcript_uri = status["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
            transcript_response = requests.get(transcript_uri)
            transcript_data = transcript_response.json()
            logger.info(f"Transcript data: {transcript_data}")

            # Extract text from transcript
            transcript = ""
            for item in transcript_data["results"]["items"]:
                if item["type"] == "transcript":
                    transcript += item["alternatives"][0]["content"] + " "

            return transcript.strip()

        except Exception as e:
            logger.error(f"Error in transcription: {str(e)}")
            raise
    
    def extract_clips(self, transcript_data, prompt):
        """Extract relevant clips using Claude 3."""
        logger.info(f"Getting clip timestamps for prompt: {prompt}")
        
        # Extract segments with timestamps
        segments = []
        if hasattr(transcript_data, 'segments'):
            segments = transcript_data.segments
        elif isinstance(transcript_data, dict) and 'segments' in transcript_data:
            segments = transcript_data['segments']
        
        # Prepare segments text
        segments_text = ""
        if segments:
            for segment in segments:
                if hasattr(segment, 'start') and hasattr(segment, 'end') and hasattr(segment, 'text'):
                    segments_text += f"[{segment.start:.2f} - {segment.end:.2f}] {segment.text}\n"
                elif isinstance(segment, dict) and 'start' in segment and 'end' in segment and 'text' in segment:
                    segments_text += f"[{segment['start']:.2f} - {segment['end']:.2f}] {segment['text']}\n"
        
        # Prepare system and user prompts
        system_prompt = """You are a helpful assistant that identifies relevant sections in a video based on its transcript. 
        Your task is to find sections that best match the user's topic or interest.
        
        Guidelines:
        1. Use ONLY the exact timestamps from the transcript segments
        2. Select sections that are most relevant to the topic
        3. Include enough context around the topic
        4. Avoid overlapping clips
        5. Keep clips concise but meaningful
        
        Return each section as a JSON object with start_time, end_time, and text fields."""
        
        user_prompt = f"""Given the following transcript with timestamps, identify sections that are most relevant to this topic: '{prompt}'.
        
        IMPORTANT:
        - Use ONLY the exact timestamps from the transcript segments
        - Select sections that best match the topic
        - Include enough context around the topic
        - Avoid overlapping clips
        - Keep clips concise but meaningful
        
        Return each section as a JSON object with start_time and end_time in seconds, and the relevant text.
        Format your entire response as a list of these objects under a 'clips' key.
        
        Timestamped Transcript:
        {segments_text[:3000]}..."""
        
        try:
            # Call Claude 3
            response = self.client.invoke_model(
                modelId='anthropic.claude-3-sonnet-20240229-v1:0',
                body=json.dumps({
                    'anthropic_version': 'bedrock-2023-05-31',
                    'max_tokens': 1000,
                    'messages': [
                        {
                            'role': 'user',
                            'content': [
                                {
                                    'type': 'text',
                                    'text': f"{system_prompt}\n\n{user_prompt}"
                                }
                            ]
                        }
                    ],
                    'temperature': 0.7
                })
            )
            
            # Parse response
            response_body = json.loads(response['body'].read())
            content = response_body.get('content', [])
            if not content:
                raise Exception("No content in Claude's response")
            
            # Extract the JSON array from Claude's response
            response_text = content[0].get('text', '')
            try:
                # Find the JSON array in the response
                start_idx = response_text.find('[')
                end_idx = response_text.rfind(']') + 1
                if start_idx == -1 or end_idx == 0:
                    raise ValueError("No JSON array found in response")
                
                json_str = response_text[start_idx:end_idx]
                clips_data = json.loads(json_str)
                
                logger.info(f"Successfully extracted clips from transcript")
                return clips_data
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Claude's response as JSON: {e}")
                logger.error(f"Raw response: {response_text}")
                raise ValueError("Failed to parse clips from Claude's response")
            
        except Exception as e:
            logger.error(f"Failed to extract clips: {str(e)}")
            raise

    def get_clip_timestamps(self, transcript: str, prompt: str) -> List[Dict[str, float]]:
        """Get clip timestamps using Claude"""
        try:
            # Prepare the prompt for Claude
            system_prompt = """You are a video clip extraction assistant. Your task is to analyze a video transcript and identify specific segments that match the user's requirements.
            For each relevant segment, provide the start and end timestamps in seconds.
            Format your response as a JSON array of objects with 'start' and 'end' timestamps.
            Example: [{"start": 10.5, "end": 25.3}, {"start": 45.0, "end": 60.0}]"""

            user_prompt = f"""Transcript: {transcript}
            User Request: {prompt}
            Please identify the relevant segments and provide timestamps in seconds."""

            # Call Claude through Bedrock
            response = self.client.invoke_model(
                modelId="anthropic.claude-3-sonnet-20240229-v1:0",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"{system_prompt}\n\n{user_prompt}"
                                }
                            ]
                        }
                    ],
                    "temperature": 0.7
                })
            )

            # Parse Claude's response
            response_body = json.loads(response.get("body").read())
            content = response_body.get("content", [])
            if not content:
                raise Exception("No content in Claude's response")

            # Extract the JSON array from Claude's response
            response_text = content[0].get("text", "")
            try:
                # Find the JSON array in the response
                start_idx = response_text.find("[")
                end_idx = response_text.rfind("]") + 1
                if start_idx == -1 or end_idx == 0:
                    raise ValueError("No JSON array found in response")
                
                json_str = response_text[start_idx:end_idx]
                timestamps = json.loads(json_str)
                
                # Validate timestamps
                if not isinstance(timestamps, list):
                    raise ValueError("Response is not a list of timestamps")
                
                for ts in timestamps:
                    if not isinstance(ts, dict) or "start" not in ts or "end" not in ts:
                        raise ValueError("Invalid timestamp format")
                    if not isinstance(ts["start"], (int, float)) or not isinstance(ts["end"], (int, float)):
                        raise ValueError("Timestamps must be numbers")
                    if ts["start"] < 0 or ts["end"] <= ts["start"]:
                        raise ValueError("Invalid timestamp values")
                
                return timestamps
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Claude's response as JSON: {e}")
                logger.error(f"Raw response: {response_text}")
                raise ValueError("Failed to parse timestamps from Claude's response")

        except Exception as e:
            logger.error(f"Error getting clip timestamps: {str(e)}")
            raise 