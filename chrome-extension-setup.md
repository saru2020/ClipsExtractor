# Chrome Extension Setup

This guide explains how to set up and run the Clips Extractor Chrome extension locally.

## Features

- Extract relevant clips directly while browsing YouTube videos
- Tap on extracted content with its timestamp to play the video from that point
- Works only with YouTube videos

## Prerequisites

- Google Chrome browser

## Installation & Local Setup

1. **Clone the repository (if not already done):**
   ```bash
   git clone https://github.com/saru2020/ClipsExtractor.git
   cd ClipsExtractor
   ```

2. **Navigate to the Chrome extension directory:**
   ```bash
   cd frontend/extension
   ```

3. **Load the extension in Chrome:**
   - Open Chrome and go to `chrome://extensions/`
   - Enable **Developer mode** (toggle in the top right)
   - Click **Load unpacked**
   - Select the `frontend/extension` folder

## Usage

- Navigate to any YouTube video page.
- Use the extension popup or sidebar to extract relevant clips based on your topic of interest.
- The extension will display extracted content with timestamps.
- **Tap on any extracted timestamp** to play the YouTube video from that point.

## Notes

- The extension works only with YouTube videos.
- Ensure the backend server is running and accessible at `http://localhost:8000` if the extension requires API calls.
- For API configuration, update the backend URL in the extension code if your backend is running elsewhere.

For further troubleshooting or questions, refer to the main [README](./README.md) or open an issue in the repository. 