import base64
import os
import sys
import uuid
from pathlib import Path
import asyncio
import runpod
from dotenv import load_dotenv

# Ensure the app can find the 'src' directory modules
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
# Load .env file for local testing of the RunPod handler
load_dotenv()

from src.services.tts_service import MinimaxTtsService
from src.core.server_manager import ServiceConfig
from src.utils.config.settings import settings
from src.utils.resources.logger import logger

# Globals
tts_service: MinimaxTtsService = None
TEMP_DIR = Path("/tmp/runpod_uploads")
TEMP_DIR.mkdir(exist_ok=True)


def _initialize_service():
    """Initializes the TTS service on cold start."""
    global tts_service
    if tts_service is None:
        logger.info("Cold start: Initializing Minimax TTS Service for RunPod...")
        
        # Configuration is dynamically loaded with env var substitution
        service_config_data = settings.get("server_manager.services.minimax_tts", {})
        
        service_config = ServiceConfig(
            name="minimax_tts",
            config=service_config_data.get("config", {})
        )
        tts_service = MinimaxTtsService(service_config)
        
        # Manually initialize since we're not using the full server manager lifespan
        asyncio.run(tts_service.initialize())
        logger.info("Minimax TTS Service initialized.")
    return tts_service


async def handle_generate_speech(job_input: dict):
    """Handler for generating speech from text and an existing voice_id."""
    text = job_input.get('text')
    voice_id = job_input.get('voice_id')

    if not text or not voice_id:
        return {"error": "Missing 'text' or 'voice_id' in job input."}

    audio_bytes = await tts_service.generate_speech_bytes(text, voice_id)
    if audio_bytes:
        return {"audio_base64": base64.b64encode(audio_bytes).decode('utf-8')}
    else:
        return {"error": "Failed to generate speech."}


async def handle_clone_and_generate(job_input: dict):
    """Handler for the full clone-and-generate workflow."""
    text = job_input.get('text')
    new_voice_id = job_input.get('new_voice_id')
    audio_base64 = job_input.get('audio_base64')

    if not all([text, new_voice_id, audio_base64]):
        return {"error": "Missing 'text', 'new_voice_id', or 'audio_base64' in job input."}

    # Decode and save the temporary audio file
    try:
        audio_bytes = base64.b64decode(audio_base64)
        temp_file_path = TEMP_DIR / f"{uuid.uuid4()}.mp3"
        with open(temp_file_path, "wb") as f:
            f.write(audio_bytes)
    except Exception as e:
        logger.error(f"Failed to decode or save audio file: {e}")
        return {"error": f"Failed to decode or save audio file: {e}"}

    # Perform the clone and speech generation
    output_audio_bytes = await tts_service.clone_and_generate_speech_bytes(
        text=text,
        audio_clone_path=str(temp_file_path),
        new_voice_id=new_voice_id
    )
    
    # Cleanup temporary file
    os.remove(temp_file_path)

    if output_audio_bytes:
        return {"audio_base64": base64.b64encode(output_audio_bytes).decode('utf-8')}
    else:
        return {"error": "Failed to clone voice and generate speech."}


async def handler(job):
    """
    The main handler for RunPod serverless requests.
    Routes job to the appropriate function based on the 'endpoint' key.
    """
    _initialize_service()
    
    job_input = job.get('input', {})
    endpoint = job_input.get('endpoint')

    if endpoint == 'generate_speech':
        return await handle_generate_speech(job_input)
    elif endpoint == 'clone_and_generate':
        return await handle_clone_and_generate(job_input)
    else:
        return {"error": f"Unknown endpoint '{endpoint}'. Available: 'generate_speech', 'clone_and_generate'."}

# Start Serverless Worker
if __name__ == "__main__":
    logger.info("Starting RunPod Serverless Worker for TTS Service.")
    runpod.serverless.start({"handler": handler})