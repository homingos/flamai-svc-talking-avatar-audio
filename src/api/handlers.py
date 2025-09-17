# /src/api/handlers.py

import os
import time
from fastapi import Request, HTTPException, UploadFile
from pathlib import Path
import tempfile
import shutil
from typing import Optional

from src.services.tts_service import MinimaxTtsService
from src.core.managers import get_server_manager
from src.api.models import GenerateSpeechRequest, HealthStatus
from src.utils.resources.logger import logger
from src.utils.config.settings import settings
from src.utils.resources.gcp_bucket_manager import GCSBucketManager

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

    def _get_gcp_manager(self, request: Request) -> Optional[GCSBucketManager]:
        """Retrieves the GCP bucket manager instance from the application state."""
        try:
            return getattr(request.app.state, 'gcp_bucket_manager', None)
        except Exception as e:
            logger.error(f"Failed to retrieve GCP bucket manager: {e}")
            return None

    async def _upload_audio_to_gcp(self, audio_bytes: bytes, request: Request, 
                                 custom_path: Optional[str] = None, 
                                 filename_prefix: str = "audio") -> Optional[str]:
        """Upload audio bytes to GCP bucket and return the bucket path."""
        gcp_manager = self._get_gcp_manager(request)
        if not gcp_manager:
            logger.warning("GCP bucket manager not available, skipping upload")
            return None

        try:
            # Generate filename with timestamp
            timestamp = int(time.time())
            filename = f"{filename_prefix}_{timestamp}.mp3"
            
            # Determine bucket path
            bucket_path = os.getenv('BUCKET_PATH', custom_path or '')
            if bucket_path:
                full_bucket_path = f"{bucket_path.rstrip('/')}/{filename}"
            else:
                full_bucket_path = filename

            # Create temporary file to upload
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
                tmp_file.write(audio_bytes)
                tmp_file_path = tmp_file.name

            try:
                # Upload to GCP
                success = gcp_manager.upload_file(tmp_file_path, full_bucket_path)
                if success:
                    logger.info(f"Successfully uploaded audio to GCP: {full_bucket_path}")
                    return full_bucket_path
                else:
                    logger.error(f"Failed to upload audio to GCP: {full_bucket_path}")
                    return None
            finally:
                # Clean up temporary file
                os.unlink(tmp_file_path)

        except Exception as e:
            logger.error(f"Error uploading audio to GCP: {e}")
            return None

    async def _save_to_temp_and_upload(self, audio_bytes: bytes, request: Request, 
                                     custom_path: Optional[str] = None, 
                                     filename_prefix: str = "audio") -> Optional[str]:
        """Save audio to temp directory and upload to GCP if configured."""
        gcp_path = None
        
        # Save to local temp directory first
        temp_dir = settings.get("server_manager.directories.temp", "runtime/temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        timestamp = int(time.time())
        filename = f"{filename_prefix}_{timestamp}.mp3"
        local_temp_path = os.path.join(temp_dir, filename)
        
        # Save locally
        with open(local_temp_path, 'wb') as f:
            f.write(audio_bytes)
        logger.info(f"Audio saved to temp directory: {local_temp_path}")
        
        # Upload to GCP if manager is available
        gcp_manager = self._get_gcp_manager(request)
        if gcp_manager:
            try:
                # Determine bucket path
                bucket_path = os.getenv('BUCKET_PATH', custom_path or '')
                if bucket_path:
                    full_bucket_path = f"{bucket_path.rstrip('/')}/{filename}"
                else:
                    full_bucket_path = filename

                # Upload from temp file
                success = gcp_manager.upload_file(local_temp_path, full_bucket_path)
                if success:
                    logger.info(f"Successfully uploaded audio to GCP: {full_bucket_path}")
                    gcp_path = full_bucket_path
                else:
                    logger.error(f"Failed to upload audio to GCP: {full_bucket_path}")
            except Exception as e:
                logger.error(f"Error uploading audio to GCP: {e}")
        
        return gcp_path

    async def generate_speech(self, request_data: GenerateSpeechRequest, request: Request) -> bytes:
        """Handles the logic for the speech generation endpoint."""
        tts_service = self._get_tts_service(request)
        audio_bytes = await tts_service.generate_speech_bytes(request_data.text, request_data.voice_id)
        if not audio_bytes:
            raise HTTPException(status_code=500, detail="Failed to generate audio from the backend API.")
        
        # Upload to GCP if requested
        if request_data.upload_to_gcp:
            gcp_path = await self._save_to_temp_and_upload(
                audio_bytes, 
                request, 
                request_data.gcp_path, 
                "generate_speech"
            )
            if gcp_path:
                logger.info(f"Audio uploaded to GCP: {gcp_path}")
            else:
                logger.warning("Failed to upload audio to GCP")
        
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

    async def clone_and_generate_speech(self, text: str, new_voice_id: str, audio_file: UploadFile, 
                                      request: Request, upload_to_gcp: bool = False, 
                                      gcp_path: Optional[str] = None) -> bytes:
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
        
        # Upload to GCP if requested
        if upload_to_gcp:
            gcp_path_result = await self._save_to_temp_and_upload(
                audio_bytes, 
                request, 
                gcp_path, 
                "clone_and_generate"
            )
            if gcp_path_result:
                logger.info(f"Audio uploaded to GCP: {gcp_path_result}")
            else:
                logger.warning("Failed to upload audio to GCP")
        
        return audio_bytes

    async def get_health_status(self, request: Request) -> dict:
        """Provides a detailed health check of the service."""
        server_manager = get_server_manager(request)
        service_statuses = {name: service.get_status() for name, service in server_manager.services.items()}
        
        # Add GCP bucket manager status
        try:
            gcp_manager = self._get_gcp_manager(request)
            if gcp_manager:
                service_statuses["gcp_bucket_manager"] = {
                    "initialized": True,
                    "bucket_name": gcp_manager.bucket_name,
                    "status": "healthy"
                }
            else:
                service_statuses["gcp_bucket_manager"] = {
                    "initialized": False,
                    "status": "disabled"
                }
        except Exception as e:
            service_statuses["gcp_bucket_manager"] = {
                "initialized": False,
                "status": "error",
                "error": str(e)
            }
        
        overall_status = HealthStatus.HEALTHY
        # Only consider services that are not disabled when checking health
        active_services = [s for s in service_statuses.values() if s.get("status") != "disabled"]
        if not all(s.get("initialized", False) for s in active_services):
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