```
# MiniMax TTS and Voice Cloning API

This project provides a production-ready, asynchronous REST API for interacting with the MiniMax Text-to-Speech (TTS) and Voice Cloning services. It is built with FastAPI for high performance and is designed for easy deployment, either as a standard server or as a serverless function on platforms like RunPod. The architecture is modular and extensible, allowing for the easy addition of new AI services in the future.

## Features

- High-Performance: Built with FastAPI and Uvicorn for asynchronous request handling.
- Centralized Configuration: All settings, including API keys, are managed in a single config.yaml file with environment variable support, making it secure and easy to manage different environments (dev, staging, prod).
- Dynamic Service Loading: The application automatically discovers and registers AI services defined in the configuration, making it highly extensible.
- Voice Cloning: Clone voices from an uploaded audio file.
- Text-to-Speech: Generate speech using pre-existing or newly cloned voices.
- Automated Workflow: A single endpoint is provided to clone a voice and generate speech in one API call, simplifying the client-side logic.
- RunPod Ready: Includes a runpod_app.py handler for easy deployment on RunPod Serverless.
- Containerized: Comes with a multi-stage Dockerfile for building lightweight and secure production images.

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- uv (recommended) or pip for package management.
- Docker (for containerized deployment).

### Step 1: Clone the Repository

git clone <your-repo-url>
cd <your-repo-name>

### Step 2: Install Dependencies

It is highly recommended to use a virtual environment.

Using uv (Recommended & Fastest):

# Create a virtual environment
uv venv

# Activate it (Linux/macOS)
source .venv/bin/activate

# Activate it (Windows PowerShell)
# .venv\Scripts\Activate.ps1

# Install all dependencies from the lock file
uv sync

Using pip:

# Create a virtual environment
python -m venv .venv

# Activate it (Linux/macOS)
source .venv/bin/activate

# Activate it (Windows PowerShell)
# .venv\Scripts\Activate.ps1

# Install dependencies
# Note: You must first generate a requirements.txt from pyproject.toml
# You can do this with: pip install "uv" && uv pip compile pyproject.toml -o requirements.txt
pip install -r requirements.txt

### Step 3: Configure Environment Variables

The API requires credentials for the MiniMax service. Create a .env file in the project root by copying the example template:

cp .env.example .env

Now, open the .env file and add your actual MiniMax credentials:

# .env
MINIMAX_API_KEY="your_minimax_api_key_here"
MINIMAX_GROUP_ID="your_minimax_group_id_here"

The application will automatically load these variables and substitute them into the config.yaml at runtime.

### Step 4: Run the Local Development Server

With the virtual environment activated and the .env file configured, you can start the API:

uvicorn app:app --host 0.0.0.0 --port 8000 --reload

--reload: Enables hot-reloading for development, automatically restarting the server when code changes are detected.

The API will now be running at http://localhost:8000.

### Step 5: Access the Interactive API Docs

Once the server is running, open your browser and navigate to the interactive Swagger UI documentation:

http://localhost:8000/docs

Here, you can explore all available endpoints, view their schemas, and test them directly from your browser.

## 📖 API Usage Examples

All API endpoints are prefixed with /api/v1.

### Health Check

Check if the service is running and all its internal components are initialized correctly.

Endpoint: GET /api/v1/health

curl Example:

curl -X GET "http://localhost:8000/api/v1/health"

### Generate Speech (Using an existing voice)

Endpoint: POST /api/v1/tts/generate

Description: Generates speech from text using a pre-existing voice_id.

curl Example:

This command will send a request to generate speech and save the resulting audio as speech.mp3.

curl -X POST "http://localhost:8000/api/v1/tts/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello world, this is a test of the API.",
    "voice_id": "male-english-2"
  }' \
  --output speech.mp3

### Clone a Voice

Endpoint: POST /api/v1/voice/clone

Description: Uploads an audio file to create a new voice clone.

curl Example:

This command clones a voice from my_voice.mp3 and assigns it the ID MyClonedVoice01.

curl -X POST "http://localhost:8000/api/v1/voice/clone" \
  -F "new_voice_id=MyClonedVoice01" \
  -F "audio_file=@/path/to/your/my_voice.mp3"

A successful response will include the new voice_id.

### Clone and Generate Speech (Automated Workflow)

Endpoint: POST /api/v1/voice/clone-and-generate

Description: The primary automated endpoint. It clones a new voice from an audio file and immediately generates speech with it in a single call.

curl Example:

This command clones a voice from my_voice.mp3, names it MyNewVoice123, generates speech from the provided text, and saves the output to output.mp3.

curl -X POST "http://localhost:8000/api/v1/voice/clone-and-generate" \
  -F "text=This is a test of the automated workflow." \
  -F "new_voice_id=MyNewVoice123" \
  -F "audio_file=@/path/to/your/my_voice.mp3" \
  --output output.mp3

## 🐳 Docker Deployment

A multi-stage Dockerfile is provided for building a small, efficient production image.

### 1. Build the Docker Image

From the project's root directory, run:

docker build -t minimax-tts-api .

### 2. Run the Docker Container

You must provide the environment variables to the container. The easiest way is using the --env-file flag with your .env file.

docker run -d --rm \
  -p 8000:8000 \
  --env-file .env \
  --name tts-api-container \
  minimax-tts-api

The containerized API is now running and accessible at http://localhost:8000.

Flags explained:
- -d: Run in detached mode.
- --rm: Automatically remove the container when it stops.
- -p 8000:8000: Map port 8000 on your host to port 8000 in the container.
- --env-file .env: Load environment variables from the .env file.
- --name tts-api-container: Assign a memorable name to the container.

## ☁️ RunPod Deployment

This repository is compatible with RunPod Serverless. The runpod_app.py file serves as the entry point.

1. Create a New Template on RunPod.
2. Set the Container Image: Use the provided Dockerfile or point to a pre-built image in your container registry.
3. Define Secrets: Add your MINIMAX_API_KEY and MINIMAX_GROUP_ID as secure environment variables in the RunPod template settings.
4. Deploy your endpoint.

The runpod_app.py handler will automatically load the secrets and initialize the service.
```