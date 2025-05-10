# Extracting Smart Video Clips with LLMs: Inside the Clips Extractor App

## Introduction

In the age of information overload, finding the most relevant moments in lengthy videos can be a daunting task. **Clips Extractor** is an innovative application designed to solve this problem by leveraging state-of-the-art Large Language Models (LLMs) and AI-powered transcription. This blog post explores the app's goals, technical architecture, and how it uses LLMs to deliver precise, topic-based video clips.

## What is Clips Extractor?

Clips Extractor enables users to extract meaningful clips from YouTube videos based on a topic of interest. Whether you're a researcher, content creator, or casual viewer, you can quickly surface the most relevant segments without manually scrubbing through hours of footage.

## Key Features

- Extract clips from YouTube video
- Search for segments based on user-provided topics
- Get precise timestamps and transcripts for each clip
- Combine selected clips into a single video
- Chrome Extension for direct YouTube integration

## Technical Architecture

The application is built with a modern, scalable stack:

- **Frontend:** Next.js (React, TypeScript, Tailwind CSS)
- **Backend:** Python FastAPI
- **Media Processing:** FFmpeg, OpenAI Whisper, GPT-4o
- **Storage:** AWS S3
- **Chrome Extension:** For seamless YouTube interaction

### Workflow Overview

1. **Media Input:** Users provide a YouTube link (it is auto extracted in the extension)
2. **Audio Extraction:** The backend uses FFmpeg to extract audio from the video.
3. **Transcription:** The audio is transcribed using OpenAI's Whisper model, producing a detailed transcript with timestamps.
4. **Clip Identification:** The transcript and user's topic prompt are sent to an LLM (GPT-4o-mini), which identifies the most relevant segments and returns their timestamps and text.
5. **Clip Extraction:** The backend slices the original video into clips based on the LLM's output and can combine them if needed.
6. **Delivery:** Users receive downloadable clips and transcripts, or can play them directly via the Chrome Extension.

## LLMs in Action: Whisper & GPT-4o

### 1. Transcription with Whisper

- **Model Used:** `whisper-1` (OpenAI)
- **Purpose:** Converts spoken content in videos to text, including segment and word-level timestamps.
- **How it works:**
  - The backend sends the extracted audio to the Whisper API.
  - The response includes a detailed transcript with precise timing for each segment and word.

### 2. Clip Extraction with GPT-4o

- **Model Used:** `gpt-4o-mini` (OpenAI)
- **Purpose:** Finds the most relevant transcript segments based on a user's topic prompt.
- **How it works:**
  - The app constructs a prompt containing the transcript (with timestamps) and the user's topic.
  - GPT-4o analyzes the transcript, selects the best-matching segments, and returns a structured JSON with start/end times and text for each clip.
  - The backend validates and uses this output to extract the corresponding video clips.

### Local LLM Support

For advanced users, the backend can be configured to use a local LLM endpoint by setting the `OPENAI_BASE_URL` environment variable, enabling private or offline processing.

## Example Use Case

1. **User Input:** "Find all parts where the speaker discusses climate change."
2. **Processing:**
   - The app transcribes the video.
   - GPT-4o receives the transcript and prompt, then returns timestamps for relevant sections.
3. **Output:**
   - The user receives a set of clips, each starting and ending at the exact moments where climate change is discussed.

## Conclusion

Clips Extractor demonstrates the power of combining LLMs with traditional media processing to automate the extraction of meaningful video content. By using OpenAI's Whisper for transcription and GPT-4o for intelligent segment selection, the app delivers a seamless experience for anyone looking to quickly find and share the most important moments in any video.

Ready to try it? Check out the [README](./README.md) for setup instructions, or install the Chrome Extension for instant YouTube integration. 