# /src/api/routes.py

import time
from io import BytesIO
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse

from src.api.handlers import TtsHandler, get_tts_handler
from src.api.models import (
    ErrorDetail, 
    GenerateSpeechRequest, 
    GenerateSpeechResponse,
    CloneAndGenerateResponse,
    HealthCheckResponse, 
    VoiceCloneResponse
)
from src.utils.config.settings import settings
from src.utils.resources.logger import logger

router = APIRouter(prefix="/api/v1", tags=["TTS and Voice Cloning"])

# Create a directory to save test outputs if configured
if settings.get("app.save_local_tests", False):
    OUTPUT_DIR = Path(settings.get("app.local_audio_directory", "runtime/temp"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.warning(f"Local audio saving is enabled. Files will be saved to '{OUTPUT_DIR}'.")


def _save_local_file(audio_bytes: bytes, prefix: str):
    """Saves audio bytes to a local file if enabled in config."""
    if not settings.get("app.save_local_tests", False) or not audio_bytes:
        return

    output_dir = Path(settings.get("app.local_audio_directory", "runtime/temp"))
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = int(time.time())
    output_path = output_dir / f"{prefix}_{timestamp}.mp3"
    with open(output_path, "wb") as f:
        f.write(audio_bytes)
    logger.info(f"SUCCESS: Audio file saved locally for testing at: {output_path}")


@router.post(
    "/tts/generate",
    summary="Generate Speech from Text",
    description="Synthesizes audio from the provided text using an existing voice ID. Optionally uploads to GCP bucket.",
    response_model=GenerateSpeechResponse,
    responses={
        200: {"model": GenerateSpeechResponse, "description": "Successful audio generation."},
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
    Generates audio and returns response with optional GCP URL.
    If upload_to_gcp is True, also saves to temp directory and uploads to GCP bucket.
    """
    audio_bytes, gcp_url, session_id = await handler.generate_speech(request_data, request)
    _save_local_file(audio_bytes, "generate_speech")
    
    return GenerateSpeechResponse(
        session_id=session_id,
        status="success",
        message="Audio generated successfully",
        gcp_url=gcp_url
    )


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
    description="The primary automated endpoint. Uploads an audio file, clones a new voice, and immediately generates speech with it. Optionally uploads to GCP bucket.",
    response_model=CloneAndGenerateResponse,
    responses={
        200: {"model": CloneAndGenerateResponse, "description": "Successful audio generation."},
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
    project_id: str = Form(
        ...,
        min_length=1,
        description="The project ID for tracking and organization.",
        examples=["my-project-123"]
    ),
    upload_to_gcp: bool = Form(
        default=False,
        description="Whether to upload the generated audio to GCP bucket"
    ),
    filename: Optional[str] = Form(
        default=None,
        description="Optional custom filename for the uploaded file (e.g., 'my_audio.mp3'). If not provided, a timestamp-based filename will be generated.",
        examples=["custom_speech.mp3"]
    ),
    handler: TtsHandler = Depends(get_tts_handler),
):
    """
    Performs the full clone-and-speak workflow in a single API call.
    If upload_to_gcp is True, also saves to temp directory and uploads to GCP bucket.
    """
    audio_bytes, gcp_url, session_id = await handler.clone_and_generate_speech(
        text, new_voice_id, audio_file, request, project_id, upload_to_gcp, filename
    )
    _save_local_file(audio_bytes, "clone_and_generate")
    
    return CloneAndGenerateResponse(
        session_id=session_id,
        status="success",
        message="Audio generated successfully",
        gcp_url=gcp_url,
    )


@router.get("/health", response_model=HealthCheckResponse, summary="Service Health Check")
async def health_check(request: Request, handler: TtsHandler = Depends(get_tts_handler)):
    """
    Performs a health check on the API and its dependent services.
    """
    return await handler.get_health_status(request)


@router.get("/debug/gcp", summary="GCP Debug Information")
async def debug_gcp(request: Request, handler: TtsHandler = Depends(get_tts_handler)):
    """
    Provides detailed debugging information about GCP configuration and status.
    """
    import os
    
    # Get GCP manager
    gcp_manager = handler._get_gcp_manager(request)
    
    debug_info = {
        "environment_variables": {
            "GCP_BUCKET_NAME": os.getenv('GCP_BUCKET_NAME'),
            "GOOGLE_APPLICATION_CREDENTIALS": os.getenv('GOOGLE_APPLICATION_CREDENTIALS'),
            "GKE_SA_DEV": os.getenv('GKE_SA_DEV'),
            "GCP_PROJECT_ID": os.getenv('GCP_PROJECT_ID'),
            "GCP_CREATE_BUCKET": os.getenv('GCP_CREATE_BUCKET'),
            "GCP_BUCKET_LOCATION": os.getenv('GCP_BUCKET_LOCATION'),
            "BUCKET_PATH": os.getenv('BUCKET_PATH')
        },
        "gcp_manager_status": {
            "available": gcp_manager is not None,
            "bucket_name": gcp_manager.bucket_name if gcp_manager else None,
            "credentials_path": gcp_manager.credentials_path if gcp_manager else None,
            "project_id": gcp_manager.project_id if gcp_manager else None,
            "client_available": gcp_manager.client is not None if gcp_manager else False,
            "bucket_available": gcp_manager.bucket is not None if gcp_manager else False
        },
        "config_settings": {
            "gcp_enabled": settings.get("gcp.enabled"),
            "gcp_bucket_name": settings.get("gcp.bucket_name"),
            "gcp_credentials_path": settings.get("gcp.credentials_path"),
            "gcp_default_upload_path": settings.get("gcp.default_upload_path")
        }
    }
    
    # Test bucket access if manager is available
    if gcp_manager:
        try:
            # Try to list first few objects to test access
            blobs = list(gcp_manager.bucket.list_blobs(max_results=1))
            debug_info["bucket_test"] = {
                "accessible": True,
                "message": "Bucket is accessible"
            }
        except Exception as e:
            debug_info["bucket_test"] = {
                "accessible": False,
                "error": str(e)
            }
    else:
        debug_info["bucket_test"] = {
            "accessible": False,
            "error": "GCP manager not available"
        }
    
    return debug_info