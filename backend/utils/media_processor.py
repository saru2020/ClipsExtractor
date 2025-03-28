import os
import logging
import shutil
import tempfile
import subprocess
import traceback
import json
from pathlib import Path
import yt_dlp
from moviepy.editor import VideoFileClip
import ffmpeg
from openai import OpenAI
from models.job import Job, JobStatus, Clip

# Set up logging
logger = logging.getLogger(__name__)


class MockOpenAIClient:
    """Mock OpenAI client for local development without requiring API key"""
    def __init__(self):
        logger.info("Using MockOpenAIClient for local development")
        # Initialize with the v1.0+ structure
        self.audio = self.MockAudio()
        self.chat = self.MockChat()
        # Add _transcribe method for legacy compatibility
        self._transcribe = self.audio.transcriptions.create
            
    class MockAudio:
        def __init__(self):
            self.transcriptions = self.MockTranscriptions()
            
        class MockTranscriptions:
            def create(self, model=None, file=None):
                logger.info(f"Mock transcription with model {model}")
                # Return a simple mock transcription
                return type('obj', (object,), {
                    'text': "This is a mock transcription for development purposes. "
                            "In a real environment, this would contain the actual transcription of the video content. "
                            "The mock response simulates what OpenAI Whisper would return."
                })
    
    class MockChat:
        def __init__(self):
            self.completions = self.MockCompletions()
            
        class MockCompletions:
            def create(self, model=None, messages=None, response_format=None):
                logger.info(f"Mock completion with model {model}")
                # Return a simple mock completion with fake timestamps
                mock_response = {
                    "clips": [
                        {
                            "start_time": 10.0,
                            "end_time": 20.0,
                            "text": "This is a mock clip segment for development purposes."
                        },
                        {
                            "start_time": 35.0,
                            "end_time": 45.0,
                            "text": "This is another mock clip segment for testing the UI."
                        }
                    ]
                }
                
                return type('obj', (object,), {
                    'choices': [
                        type('obj', (object,), {
                            'message': type('obj', (object,), {
                                'content': json.dumps(mock_response)
                            })
                        })
                    ]
                })


class LegacyOpenAIClientWrapper:
    """Wrapper for legacy OpenAI client API to maintain compatibility with new client interface"""
    def __init__(self, openai_module, api_key, base_url=None):
        self.openai = openai_module
        self.openai.api_key = api_key
        if base_url:
            self.openai.api_base = base_url
        
        # Create proxy audio class
        self.audio = type('AudioProxy', (), {
            'transcriptions': type('TranscriptionsProxy', (), {
                'create': self._transcribe
            })
        })()
        
        # Create proxy chat class
        self.chat = type('ChatProxy', (), {
            'completions': type('CompletionsProxy', (), {
                'create': self._chat_complete
            })
        })()
    
    def _transcribe(self, model, file):
        """Legacy implementation of transcription API"""
        logger.info(f"Using legacy transcription API with model {model}")
        try:
            # Try the new API format first (v1.0+)
            if hasattr(self.openai, 'AudioTranscription'):
                logger.info("Using openai.AudioTranscription.create")
                result = self.openai.AudioTranscription.create(model=model, file=file)
            elif hasattr(self.openai, 'audio') and hasattr(self.openai.audio, 'transcriptions'):
                logger.info("Using openai.audio.transcriptions.create")
                result = self.openai.audio.transcriptions.create(model=model, file=file)
            # Fall back to old API format (v0.x)
            elif hasattr(self.openai, 'Audio'):
                logger.info("Using openai.Audio.transcribe (deprecated)")
                result = self.openai.Audio.transcribe(model, file)
            else:
                # As a last resort, use a mock response
                logger.warning("No compatible transcription API found, using mock response")
                result = type('MockTranscription', (), {
                    'text': "This is a mock transcription used when no compatible API was found."
                })
                
            # Convert to new format if needed
            if not hasattr(result, 'text') and isinstance(result, dict) and 'text' in result:
                return type('TranscriptionResult', (), {'text': result['text']})
            return result
        except Exception as e:
            logger.error(f"Transcription error: {str(e)}")
            # Return mock data as a fallback
            return type('ErrorTranscription', (), {
                'text': "An error occurred during transcription. This is mock text to allow processing to continue."
            })
    
    def _chat_complete(self, model, messages, response_format=None):
        """Legacy implementation of chat completion API"""
        logger.info(f"Using legacy chat completion API with model {model}")
        
        try:
            # Try the new API format first (v1.0+)
            if hasattr(self.openai, 'chat') and hasattr(self.openai.chat, 'completions'):
                logger.info("Using openai.chat.completions.create")
                kwargs = {
                    'model': model,
                    'messages': messages
                }
                
                if response_format:
                    kwargs['response_format'] = response_format
                    
                result = self.openai.chat.completions.create(**kwargs)
                return result
            
            # Fall back to old API format (v0.x)
            elif hasattr(self.openai, 'ChatCompletion'):
                logger.info("Using openai.ChatCompletion.create (deprecated)")
                kwargs = {
                    'model': model,
                    'messages': messages
                }
                
                if response_format:
                    if isinstance(response_format, dict) and 'type' in response_format:
                        if response_format['type'] == 'json_object':
                            kwargs['response_format'] = {'type': 'json_object'}
                
                result = self.openai.ChatCompletion.create(**kwargs)
                
                # Convert to new format if needed
                if not hasattr(result, 'choices') and isinstance(result, dict) and 'choices' in result:
                    # Create a proxy object mimicking the new API
                    proxy_result = type('ChatCompletionResult', (), {
                        'choices': [{
                            'message': type('Message', (), {
                                'content': result['choices'][0]['message']['content']
                            })
                        }]
                    })
                    return proxy_result
                
                return result
            else:
                # Instead of using mock data, raise an exception
                error_msg = "No compatible chat completion API found"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
        except Exception as e:
            # Log and re-raise the exception instead of returning mock data
            logger.error(f"Chat completion error: {str(e)}")
            raise


class MediaProcessor:
    def __init__(self, temp_dir=None):
        logger.info("Initializing MediaProcessor")
        self.temp_dir = temp_dir or os.getenv('MEDIA_TEMP_PATH', '/tmp/clips-extractor-media')
        os.makedirs(self.temp_dir, exist_ok=True)
        logger.info(f"Using temp directory: {self.temp_dir}")
        
        # Clean environment variables that might interfere with OpenAI client
        for env_var in list(os.environ.keys()):
            if 'PROXY' in env_var.upper() or 'HTTP_PROXY' in env_var.upper() or 'HTTPS_PROXY' in env_var.upper():
                logger.warning(f"Unsetting potentially problematic environment variable: {env_var}")
                del os.environ[env_var]
        
        api_key = os.getenv('OPENAI_API_KEY')
        
        try:
            logger.info('Initializing OpenAI client')
            if not api_key:
                error_msg = "No OpenAI API key provided in environment. Must set OPENAI_API_KEY environment variable."
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Create minimal client with only required parameters
            base_url = os.getenv('OPENAI_BASE_URL')
            
            # Initialize with only required parameters
            init_kwargs = {'api_key': api_key}
            if base_url:
                logger.info(f"Using custom base URL: {base_url}")
                init_kwargs['base_url'] = base_url

            print('init_kwargs: ', init_kwargs)
            # Create client with minimal configuration to avoid unexpected parameters
            self.client = OpenAI(**init_kwargs)
            logger.info("OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def download_media(self, job: Job):
        """Download media from the given URL."""
        logger.info(f"Starting media download from URL: {job.url}")
        job.update_status(JobStatus.DOWNLOADING)
        
        # Create a unique directory for this job
        job_dir = os.path.join(self.temp_dir, job.id)
        os.makedirs(job_dir, exist_ok=True)
        logger.info(f"Created job directory: {job_dir}")
        
        try:
            # YouTube or other supported services
            output_path = os.path.join(job_dir, f"input.%(ext)s")
            ydl_opts = {
                'format': 'best[ext=mp4]/best',
                'outtmpl': output_path,
                'quiet': True,
            }
            
            logger.info(f"Downloading with yt-dlp using options: {ydl_opts}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(job.url, download=True)
                downloaded_file = ydl.prepare_filename(info)
                
            logger.info(f"Media downloaded successfully to: {downloaded_file}")
            job.input_media_path = downloaded_file
            return downloaded_file
            
        except Exception as e:
            error_msg = f"Failed to download media: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            job.update_status(JobStatus.FAILED, error_msg)
            raise
    
    def get_transcript(self, media_path):
        """Extract transcript with timestamps from media file using OpenAI Whisper API."""
        logger.info(f"Starting transcription for: {media_path}")
        
        # Extract audio first
        audio_path = media_path.replace(Path(media_path).suffix, '.mp3')
        logger.info(f"Extracting audio to: {audio_path}")
        
        try:
            ffmpeg_cmd = [
                'ffmpeg', '-y', '-i', media_path, 
                '-q:a', '0', '-map', 'a', audio_path
            ]
            logger.info(f"Running FFmpeg command: {' '.join(ffmpeg_cmd)}")
            
            result = subprocess.run(
                ffmpeg_cmd, 
                check=True, 
                capture_output=True,
                text=True
            )
            
            if result.stderr:
                logger.debug(f"FFmpeg stderr: {result.stderr}")
            
            logger.info(f"Audio extraction complete: {audio_path}")
            
            # Verify audio file exists and has content
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"Audio file was not created: {audio_path}")
            
            file_size = os.path.getsize(audio_path)
            logger.info(f"Audio file size: {file_size} bytes")
            
            if file_size == 0:
                raise ValueError(f"Audio file is empty: {audio_path}")
            
            # Transcribe with OpenAI Whisper using the proper v1.0+ API format
            # and request timestamps and word-level timings
            logger.info("Starting OpenAI Whisper transcription with timestamps")
            with open(audio_path, 'rb') as audio_file:
                try:
                    # Request timestamps and word timings in the response
                    transcription = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        response_format="verbose_json",  # This provides timestamps
                        timestamp_granularities=["segment", "word"]  # Get both segment and word-level timestamps
                    )
                    
                    # For verbose_json, the result will be a JSON structure with segments and words
                    logger.info(f"Transcription complete with timestamps")
                    
                    # Return the full transcription data including timestamps
                    return transcription
                    
                except Exception as e:
                    logger.error(f"OpenAI transcription error: {str(e)}")
                    logger.error(traceback.format_exc())
                    raise
            
        except Exception as e:
            logger.error(f"Failed to transcribe media: {str(e)}")
            logger.error(traceback.format_exc())
            raise
        finally:
            # Clean up audio file
            if os.path.exists(audio_path):
                try:
                    # os.remove(audio_path)
                    logger.info(f"Cleaned up audio file: {audio_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up audio file: {str(e)}")
    
    def get_clip_timestamps(self, transcript_data, prompt):
        """Get timestamps for clips relevant to the prompt using OpenAI API and real transcript timestamps."""
        # Extract the plain text for the LLM prompt
        if hasattr(transcript_data, 'text'):
            plain_text = transcript_data.text
        else:
            plain_text = str(transcript_data)
            
        logger.info(f"Getting clip timestamps for prompt: {prompt}")
        logger.info(f"Transcript length: {len(plain_text)} characters")
        
        # Extract segments with timestamps from the transcript data
        segments = []
        if hasattr(transcript_data, 'segments'):
            segments = transcript_data.segments
        elif isinstance(transcript_data, dict) and 'segments' in transcript_data:
            segments = transcript_data['segments']
            
        if not segments:
            logger.warning("No timestamp segments found in transcript data. Using AI estimation instead.")
            
        # Prepare a better prompt that includes segment information
        system_content = """You are a helpful assistant that identifies relevant sections in a video based on its transcript. 
        Use the exact timestamps provided in the transcript segments when possible. Return timestamps as JSON objects with 
        start_time, end_time, and text fields."""
        
        # Create a structured prompt with transcript segments
        segments_text = ""
        if segments:
            for i, segment in enumerate(segments):
                if hasattr(segment, 'start') and hasattr(segment, 'end') and hasattr(segment, 'text'):
                    segments_text += f"[{segment.start:.2f} - {segment.end:.2f}] {segment.text}\n"
                elif isinstance(segment, dict) and 'start' in segment and 'end' in segment and 'text' in segment:
                    segments_text += f"[{segment['start']:.2f} - {segment['end']:.2f}] {segment['text']}\n"
        
        if segments_text:
            user_content = f"""Given the following transcript with timestamps, identify sections that are most relevant to this topic: '{prompt}'.
            
            USE THE EXACT TIMESTAMPS from the transcript segments. DO NOT MAKE UP OR ESTIMATE TIMESTAMPS.
            
            Return each section as a JSON object with start_time and end_time in seconds, and the relevant text.
            Format your entire response as a list of these objects under a 'clips' key.
            
            Timestamped Transcript:
            {segments_text[:3000]}..."""
        else:
            # Fallback to using plain text if no segments are available
            user_content = f"""Given the following transcript, identify sections that are most relevant to this topic: '{prompt}'.
            
            Return each section as a JSON object with start_time and end_time in seconds, and the relevant text.
            Format your entire response as a list of these objects under a 'clips' key.
            
            Transcript:
            {plain_text[:3000]}..."""
            
        logger.info(f"System prompt: {system_content}")
        logger.info(f"User prompt (truncated): {user_content[:100]}...")
        
        # Use the correct v1.0+ client API format for chat completions
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ],
            response_format={"type": "json_object"}
        )
        
        # Get the response content from the completion
        response_content = response.choices[0].message.content
        logger.info(f"Received response from OpenAI: {response_content[:100]}...")
        
        # Parse the response
        clips_data = json.loads(response_content)
        logger.info(f"Successfully parsed JSON response")
        
        if 'clips' not in clips_data:
            error_msg = "Invalid response format: 'clips' key missing in API response"
            logger.error(error_msg)
            logger.error(f"Full response: {response_content}")
            raise ValueError(error_msg)
        
        clips = []
        for clip_data in clips_data.get('clips', []):
            try:
                # Validate clip data
                if 'start_time' not in clip_data or 'end_time' not in clip_data or 'text' not in clip_data:
                    logger.warning(f"Skipping invalid clip data, missing required fields: {clip_data}")
                    continue
                    
                clip = Clip(
                    start_time=float(clip_data['start_time']),
                    end_time=float(clip_data['end_time']),
                    text=clip_data['text']
                )
                clips.append(clip)
                logger.info(f"Added clip: {clip.start_time} - {clip.end_time}")
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"Failed to parse clip data: {str(e)}")
                logger.warning(f"Clip data: {clip_data}")
                # Continue processing other clips
        
        if not clips:
            error_msg = "No valid clips found in API response"
            logger.error(error_msg)
            raise ValueError(error_msg)
            
        logger.info(f"Found {len(clips)} clips")
        return clips
    
    def extract_clips(self, job: Job):
        """Extract clips from the video based on timestamps."""
        logger.info(f"Extracting clips for job: {job.id}")
        job.update_status(JobStatus.EXTRACTING)
        
        try:
            # Create output directory
            job_dir = os.path.dirname(job.input_media_path)
            clips_dir = os.path.join(job_dir, 'clips')
            os.makedirs(clips_dir, exist_ok=True)
            logger.info(f"Created clips directory: {clips_dir}")
            
            # Check if we have clips to extract
            if not job.clips:
                logger.warning("No clips to extract")
                return None
            
            # Extract clips
            clip_paths = []
            for i, clip in enumerate(job.clips):
                clip_path = os.path.join(clips_dir, f"clip_{i}.mp4")
                logger.info(f"Extracting clip {i}: {clip.start_time} - {clip.end_time} to {clip_path}")
                
                try:
                    video = VideoFileClip(job.input_media_path)
                    
                    # Validate clip boundaries
                    video_duration = video.duration
                    logger.info(f"Video duration: {video_duration} seconds")
                    
                    # Adjust clip boundaries if needed
                    start_time = max(0, min(clip.start_time, video_duration))
                    end_time = max(start_time, min(clip.end_time, video_duration))
                    
                    if start_time != clip.start_time or end_time != clip.end_time:
                        logger.warning(f"Adjusted clip boundaries from {clip.start_time}-{clip.end_time} to {start_time}-{end_time}")
                    
                    subclip = video.subclip(start_time, end_time)
                    logger.info(f"Created subclip of duration: {subclip.duration} seconds")
                    
                    # Use verbose=False to prevent log spam, and logger=None to prevent moviepy from using its own logger
                    subclip.write_videofile(clip_path, codec='libx264', audio_codec='aac', verbose=False, logger=None)
                    logger.info(f"Saved clip to: {clip_path}")
                    
                    video.close()
                    clip_paths.append(clip_path)
                    
                except Exception as e:
                    logger.error(f"Failed to extract clip {i}: {str(e)}")
                    logger.error(traceback.format_exc())
                    # Continue with other clips instead of failing completely
                    continue
            
            # Combine clips
            if clip_paths:
                output_path = os.path.join(job_dir, "output.mp4")
                logger.info(f"Combining {len(clip_paths)} clips into {output_path}")
                
                # Combine the clips into a single video
                result = self._combine_clips(clip_paths, output_path)
                
                if result:
                    job.output_media_path = output_path
                    logger.info(f"Clips combined successfully to: {output_path}")
                    
                    # Copy the output to local_storage to make it accessible via HTTP
                    try:
                        # Create the local_storage directory structure
                        local_storage_dir = os.path.join(os.getcwd(), 'local_storage')
                        os.makedirs(local_storage_dir, exist_ok=True)
                        
                        # Create the path for the bucket/outputs/job-id structure
                        bucket_name = os.getenv('S3_BUCKET_NAME', 'clips-extractor-media')
                        local_output_dir = os.path.join(local_storage_dir, bucket_name, 'outputs', job.id)
                        os.makedirs(local_output_dir, exist_ok=True)
                        
                        # Copy the output file
                        local_output_path = os.path.join(local_output_dir, "output.mp4")
                        shutil.copy2(output_path, local_output_path)
                        logger.info(f"Copied output file to local storage: {local_output_path}")
                    except Exception as e:
                        logger.warning(f"Failed to copy output to local storage: {str(e)}")
                    
                    return output_path
                else:
                    logger.error("Failed to combine clips")
            else:
                logger.warning("No clips were extracted successfully")
            
            return None
            
        except Exception as e:
            error_msg = f"Failed to extract clips: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            job.update_status(JobStatus.FAILED, error_msg)
            raise
    
    def _combine_clips(self, clip_paths, output_path):
        """Combine multiple clips into a single video."""
        logger.info(f"Combining clips: {clip_paths}")
        
        if not clip_paths:
            logger.warning("No clips to combine")
            return None
            
        # Create a text file with the list of clips
        list_file = tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False)
        try:
            for clip_path in clip_paths:
                list_file.write(f"file '{clip_path}'\n")
            list_file.close()
            logger.info(f"Created concat list file: {list_file.name}")
            
            # Use ffmpeg to concatenate the clips
            ffmpeg_cmd = [
                'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                '-i', list_file.name, '-c', 'copy', output_path
            ]
            logger.info(f"Running FFmpeg combine command: {' '.join(ffmpeg_cmd)}")
            
            result = subprocess.run(
                ffmpeg_cmd, 
                check=True, 
                capture_output=True,
                text=True
            )
            
            if result.stderr:
                logger.debug(f"FFmpeg stderr during combine: {result.stderr}")
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logger.info(f"Combined video created successfully: {output_path} ({os.path.getsize(output_path)} bytes)")
                return output_path
            else:
                logger.error(f"Output file wasn't created or is empty: {output_path}")
                return None
            
        except Exception as e:
            logger.error(f"Error combining clips: {str(e)}")
            logger.error(traceback.format_exc())
            return None
        finally:
            try:
                os.unlink(list_file.name)
                logger.info(f"Cleaned up concat list file: {list_file.name}")
            except Exception as e:
                logger.warning(f"Failed to clean up concat list file: {str(e)}")
    
    def cleanup(self, job_id):
        """Clean up temporary files for a job."""
        job_dir = os.path.join(self.temp_dir, job_id)
        logger.info(f"Cleaning up job directory: {job_dir}")
        
        if os.path.exists(job_dir):
            try:
                shutil.rmtree(job_dir)
                logger.info(f"Successfully removed job directory: {job_dir}")
            except Exception as e:
                logger.error(f"Failed to clean up job directory: {str(e)}")
                logger.error(traceback.format_exc())
