# /src/api/routes.py

import time
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse

from src.api.handlers import TtsHandler, get_tts_handler
from src.api.models import ErrorDetail, GenerateSpeechRequest, HealthCheckResponse, VoiceCloneResponse
from src.utils.config.settings import settings
from src.utils.resources.logger import logger

router = APIRouter(prefix="/api/v1", tags=["TTS and Voice Cloning"])

# Create a directory to save test outputs if configured
if settings.get("app.save_local_tests", False):
    OUTPUT_DIR = Path("local_audio_tests")
    OUTPUT_DIR.mkdir(exist_ok=True)
    logger.warning(f"Local audio saving is enabled. Files will be saved to '{OUTPUT_DIR}'.")


def _save_local_file(audio_bytes: bytes, prefix: str):
    """Saves audio bytes to a local file if enabled in config."""
    if not settings.get("app.save_local_tests", False) or not audio_bytes:
        return

    timestamp = int(time.time())
    output_path = OUTPUT_DIR / f"{prefix}_{timestamp}.mp3"
    with open(output_path, "wb") as f:
        f.write(audio_bytes)
    logger.info(f"SUCCESS: Audio file saved locally for testing at: {output_path}")


@router.post(
    "/tts/generate",
    summary="Generate Speech from Text",
    description="Synthesizes audio from the provided text using an existing voice ID.",
    responses={
        200: {"content": {"audio/mpeg": {}}, "description": "Successful audio generation."},
        400: {"model": ErrorDetail, "description": "Invalid input."},
        500: {"model": ErrorDetail, "description": "Internal server error."},
    },
)
async def generate_speech(
    request_data: GenerateSpeechRequest,
    request: Request,
    handler: TtsHandler = Depends(get_tts_handler),
):
    """
    Generates audio and streams it back as an MP3 file.
    """
    audio_bytes = await handler.generate_speech(request_data, request)
    _save_local_file(audio_bytes, "generate_speech")
    return StreamingResponse(BytesIO(audio_bytes), media_type="audio/mpeg")


@router.post(
    "/voice/clone",
    summary="Clone a New Voice",
    description="Uploads an audio file and creates a new voice clone with a specified ID.",
    response_model=VoiceCloneResponse,
)
async def clone_voice(
    request: Request,
    new_voice_id: str = Form(
        ...,
        min_length=8,
        pattern=r"^[a-zA-Z][a-zA-Z0-9]*$",
        description="A unique ID for the new voice. Must be at least 8 characters, alphanumeric, and start with a letter.",
        examples=["MyCustomVoice01"],
    ),
    audio_file: UploadFile = File(..., description="The MP3 or WAV audio file for cloning."),
    handler: TtsHandler = Depends(get_tts_handler),
):
    """
    Handles the two-step process of uploading an audio file and creating a voice clone.
    """
    return await handler.clone_voice(new_voice_id, audio_file, request)


@router.post(
    "/voice/clone-and-generate",
    summary="Clone Voice and Generate Speech (Automated Workflow)",
    description="The primary automated endpoint. Uploads an audio file, clones a new voice, and immediately generates speech with it.",
    responses={
        200: {"content": {"audio/mpeg": {}}, "description": "Successful audio generation."},
        400: {"model": ErrorDetail, "description": "Invalid input."},
        500: {"model": ErrorDetail, "description": "Internal server error."},
    },
)
async def clone_and_generate(
    request: Request,
    text: str = Form(..., description="The text to synthesize."),
    new_voice_id: str = Form(
        ...,
        min_length=8,
        pattern=r"^[a-zA-Z][a-zA-Z0-9]*$",
        description="A unique ID for the new voice.",
        examples=["MyNewCloneAndSpeakVoice"],
    ),
    audio_file: UploadFile = File(..., description="The audio file for cloning."),
    handler: TtsHandler = Depends(get_tts_handler),
):
    """
    Performs the full clone-and-speak workflow in a single API call.
    """
    audio_bytes = await handler.clone_and_generate_speech(text, new_voice_id, audio_file, request)
    _save_local_file(audio_bytes, "clone_and_generate")
    return StreamingResponse(BytesIO(audio_bytes), media_type="audio/mpeg")


@router.get("/health", response_model=HealthCheckResponse, summary="Service Health Check")
async def health_check(request: Request, handler: TtsHandler = Depends(get_tts_handler)):
    """
    Performs a health check on the API and its dependent services.
    """
    return await handler.get_health_status(request)