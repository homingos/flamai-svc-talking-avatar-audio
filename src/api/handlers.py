# /src/api/handlers.py

from fastapi import Request, HTTPException, UploadFile
from pathlib import Path
import tempfile
import shutil

from src.services.tts_service import MinimaxTtsService
from src.core.managers import get_server_manager
# --- FIX: Corrected import path ---
from src.api.models import GenerateSpeechRequest, HealthStatus
from src.utils.resources.logger import logger
from src.utils.config.settings import settings

class TtsHandler:
    def _get_tts_service(self, request: Request) -> MinimaxTtsService:
        """Retrieves the TTS service instance from the application state."""
        try:
            server_manager = get_server_manager(request)
            service = server_manager.get_service("minimax_tts")
            if not service or not isinstance(service, MinimaxTtsService):
                raise HTTPException(status_code=503, detail="TTS service is not available.")
            if not service.is_initialized:
                raise HTTPException(status_code=503, detail="TTS service is not initialized.")
            return service
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to retrieve TTS service: {e}")
            raise HTTPException(status_code=500, detail="Could not access the TTS service.")

    async def generate_speech(self, request_data: GenerateSpeechRequest, request: Request) -> bytes:
        """Handles the logic for the speech generation endpoint."""
        tts_service = self._get_tts_service(request)
        audio_bytes = await tts_service.generate_speech_bytes(request_data.text, request_data.voice_id)
        if not audio_bytes:
            raise HTTPException(status_code=500, detail="Failed to generate audio from the backend API.")
        return audio_bytes

    async def clone_voice(self, new_voice_id: str, audio_file: UploadFile, request: Request) -> dict:
        """Handles the logic for uploading a file and cloning a voice."""
        tts_service = self._get_tts_service(request)
        
        # Save uploaded file to a temporary location
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(audio_file.filename).suffix) as tmp:
                shutil.copyfileobj(audio_file.file, tmp)
                tmp_path = Path(tmp.name)
        finally:
            audio_file.file.close()

        cloned_voice_id = await tts_service.create_voice_from_file(tmp_path, new_voice_id)
        
        # Clean up the temporary file
        tmp_path.unlink()

        if cloned_voice_id:
            return {"success": True, "message": "Voice cloned successfully.", "voice_id": cloned_voice_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to clone voice from the backend API.")

    async def clone_and_generate_speech(self, text: str, new_voice_id: str, audio_file: UploadFile, request: Request) -> bytes:
        """Handles the combined clone-and-generate workflow."""
        tts_service = self._get_tts_service(request)

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(audio_file.filename).suffix) as tmp:
                shutil.copyfileobj(audio_file.file, tmp)
                tmp_path = Path(tmp.name)
        finally:
            audio_file.file.close()

        audio_bytes = await tts_service.clone_and_generate_speech_bytes(
            text=text,
            audio_clone_path=str(tmp_path),
            new_voice_id=new_voice_id,
        )
        
        tmp_path.unlink()

        if not audio_bytes:
            raise HTTPException(status_code=500, detail="Failed to complete clone-and-generate workflow.")
        return audio_bytes

    async def get_health_status(self, request: Request) -> dict:
        """Provides a detailed health check of the service."""
        server_manager = get_server_manager(request)
        service_statuses = {name: service.get_status() for name, service in server_manager.services.items()}
        
        overall_status = HealthStatus.HEALTHY
        if not all(s.get("initialized", False) for s in service_statuses.values()):
            overall_status = HealthStatus.UNHEALTHY

        return {
            "status": overall_status,
            "service_name": settings.get("app.name"),
            "version": settings.get("app.version"),
            "services": service_statuses
        }

# Dependency Injection factory
def get_tts_handler() -> TtsHandler:
    return TtsHandler()