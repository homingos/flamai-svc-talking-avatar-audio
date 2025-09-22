# /src/api/handlers.py

import os
import time
import uuid
from fastapi import Request, HTTPException, UploadFile
from pathlib import Path
import tempfile
import shutil
from typing import Optional

from src.services.tts_service import MinimaxTtsService
from src.core.managers import get_server_manager
from src.api.models import GenerateSpeechRequest, HealthStatus, GenerateSpeechResponse, VoiceCloneResponse, CloneAndGenerateResponse
from src.utils.resources.logger import logger
from src.utils.config.settings import settings
from src.utils.resources.gcp_bucket_manager import GCSBucketManager
from src.utils.resources.file_cleanup import cleanup_after_gcp_upload

class TtsHandler:
    def _generate_session_id(self) -> str:
        """Generate a unique session ID for tracking requests."""
        return str(uuid.uuid4())

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
            gcp_manager = getattr(request.app.state, 'gcp_bucket_manager', None)
            if gcp_manager:
                logger.info("GCP bucket manager is available")
            else:
                logger.warning("GCP bucket manager is not available")
            return gcp_manager
        except Exception as e:
            logger.error(f"Failed to retrieve GCP bucket manager: {e}")
            return None

    async def _upload_audio_to_gcp(self, audio_bytes: bytes, request: Request, 
                                 project_id: str, filename_prefix: str = "audio") -> Optional[str]:
        """Upload audio bytes to GCP bucket and return the bucket path."""
        gcp_manager = self._get_gcp_manager(request)
        if not gcp_manager:
            logger.warning("GCP bucket manager not available, skipping upload")
            return None

        try:
            # Generate filename with timestamp
            timestamp = int(time.time())
            filename = f"{filename_prefix}_{timestamp}.mp3"
            
            # Get base path from configuration
            gcp_config = settings.get_gcp_config()
            base_path = gcp_config.get('base_path', 'talking-avatar')
            
            # Generate structured path using the new method
            full_bucket_path = gcp_manager.generate_structured_path(base_path, project_id, filename)

            # Create temporary file to upload
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
                tmp_file.write(audio_bytes)
                tmp_file_path = tmp_file.name

            try:
                # Upload to GCP
                success = gcp_manager.upload_file(tmp_file_path, full_bucket_path)
                if success:
                    logger.info(f"Successfully uploaded audio to GCP: {full_bucket_path}")
                    # Schedule cleanup of temporary file after successful upload
                    cleanup_after_gcp_upload(tmp_file_path, delay_seconds=1.0)
                    return full_bucket_path
                else:
                    logger.error(f"Failed to upload audio to GCP: {full_bucket_path}")
                    # Clean up temp file immediately on failure
                    os.unlink(tmp_file_path)
                    return None
            except Exception as e:
                logger.error(f"Error during GCP upload: {e}")
                # Clean up temp file on exception
                try:
                    os.unlink(tmp_file_path)
                except:
                    pass
                return None

        except Exception as e:
            logger.error(f"Error uploading audio to GCP: {e}")
            return None

    async def _save_to_temp_and_upload(self, audio_bytes: bytes, request: Request, 
                                     project_id: str, filename_prefix: str = "audio") -> Optional[str]:
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
                # Get base path from configuration
                gcp_config = settings.get_gcp_config()
                base_path = gcp_config.get('base_path', 'talking-avatar')
                
                # Generate structured path using the new method
                full_bucket_path = gcp_manager.generate_structured_path(base_path, project_id, filename)

                logger.info(f"Attempting to upload to GCP bucket path: {full_bucket_path}")
                
                # Upload from temp file
                success = gcp_manager.upload_file(local_temp_path, full_bucket_path)
                if success:
                    logger.info(f"Successfully uploaded audio to GCP: {full_bucket_path}")
                    gcp_path = full_bucket_path
                    # Schedule cleanup of local temp file after successful GCP upload
                    cleanup_after_gcp_upload(local_temp_path, delay_seconds=2.0)
                else:
                    logger.error(f"Failed to upload audio to GCP: {full_bucket_path}")
            except Exception as e:
                logger.error(f"Error uploading audio to GCP: {e}")
        else:
            logger.warning("GCP manager not available, skipping upload")
        
        return gcp_path

    async def generate_speech(self, request_data: GenerateSpeechRequest, request: Request) -> tuple[bytes, Optional[str], str]:
        """Handles the logic for the speech generation endpoint."""
        session_id = self._generate_session_id()
        logger.info(f"Session {session_id}: Generating speech for project {request_data.project_id}")
        logger.info(f"Session {session_id}: Upload to GCP requested: {request_data.upload_to_gcp}")
        
        tts_service = self._get_tts_service(request)
        audio_bytes = await tts_service.generate_speech_bytes(request_data.text, request_data.voice_id)
        if not audio_bytes:
            logger.error(f"Session {session_id}: Failed to generate audio from the backend API")
            raise HTTPException(status_code=500, detail="Failed to generate audio from the backend API.")
        
        gcp_url = None
        
        # Upload to GCP if requested
        if request_data.upload_to_gcp:
            logger.info(f"Session {session_id}: Starting GCP upload process")
            gcp_path = await self._save_to_temp_and_upload(
                audio_bytes, 
                request, 
                request_data.project_id, 
                "generate_speech"
            )
            if gcp_path:
                logger.info(f"Session {session_id}: Audio uploaded to GCP: {gcp_path}")
                # Generate public URL
                gcp_manager = self._get_gcp_manager(request)
                if gcp_manager:
                    gcp_url = gcp_manager.get_public_url(gcp_path)
                    logger.info(f"Session {session_id}: Generated public URL: {gcp_url}")
                else:
                    logger.error(f"Session {session_id}: GCP manager not available for URL generation")
            else:
                logger.warning(f"Session {session_id}: Failed to upload audio to GCP")
        else:
            logger.info(f"Session {session_id}: GCP upload not requested, skipping")
        
        logger.info(f"Session {session_id}: Speech generation completed successfully. GCP URL: {gcp_url}")
        return audio_bytes, gcp_url, session_id

    async def clone_voice(self, new_voice_id: str, audio_file: UploadFile, request: Request) -> VoiceCloneResponse:
        """Handles the logic for uploading a file and cloning a voice."""
        session_id = self._generate_session_id()
        logger.info(f"Session {session_id}: Cloning voice with ID: {new_voice_id}")
        
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
            logger.info(f"Session {session_id}: Voice cloned successfully with ID: {cloned_voice_id}")
            return VoiceCloneResponse(
                session_id=session_id,
                success=True,
                message="Voice cloned successfully.",
                voice_id=cloned_voice_id
            )
        else:
            logger.error(f"Session {session_id}: Failed to clone voice from the backend API")
            raise HTTPException(status_code=500, detail="Failed to clone voice from the backend API.")

    async def clone_and_generate_speech(self, text: str, new_voice_id: str, audio_file: UploadFile, 
                                      request: Request, project_id: str, upload_to_gcp: bool = False) -> tuple[bytes, Optional[str], str]:
        """Handles the combined clone-and-generate workflow."""
        session_id = self._generate_session_id()
        logger.info(f"Session {session_id}: Starting clone-and-generate workflow")
        logger.info(f"Session {session_id}: Upload to GCP requested: {upload_to_gcp}")
        
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
            logger.error(f"Session {session_id}: Failed to complete clone-and-generate workflow")
            raise HTTPException(status_code=500, detail="Failed to complete clone-and-generate workflow.")
        
        gcp_url = None
        
        # Upload to GCP if requested
        if upload_to_gcp:
            logger.info(f"Session {session_id}: Starting GCP upload process")
            gcp_path_result = await self._save_to_temp_and_upload(
                audio_bytes, 
                request, 
                project_id, 
                "clone_and_generate"
            )
            if gcp_path_result:
                logger.info(f"Session {session_id}: Audio uploaded to GCP: {gcp_path_result}")
                # Generate public URL
                gcp_manager = self._get_gcp_manager(request)
                if gcp_manager:
                    gcp_url = gcp_manager.get_public_url(gcp_path_result)
                    logger.info(f"Session {session_id}: Generated public URL: {gcp_url}")
                else:
                    logger.error(f"Session {session_id}: GCP manager not available for URL generation")
            else:
                logger.warning(f"Session {session_id}: Failed to upload audio to GCP")
        else:
            logger.info(f"Session {session_id}: GCP upload not requested, skipping")
        
        logger.info(f"Session {session_id}: Clone-and-generate workflow completed successfully. GCP URL: {gcp_url}")
        return audio_bytes, gcp_url, session_id

    async def get_health_status(self, request: Request) -> dict:
        """Provides a detailed health check of the service."""
        session_id = self._generate_session_id()
        logger.info(f"Session {session_id}: Health check requested")
        
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
            "session_id": session_id,
            "status": overall_status,
            "service_name": settings.get("app.name"),
            "version": settings.get("app.version"),
            "services": service_statuses
        }

    async def test_gcp_upload(self, request: Request) -> dict:
        """Test GCP upload functionality with a dummy file."""
        session_id = self._generate_session_id()
        logger.info(f"Session {session_id}: Testing GCP upload functionality")
        
        # Create dummy audio data
        dummy_audio = b"dummy audio data for testing"
        
        result = {
            "session_id": session_id,
            "gcp_manager_available": False,
            "upload_success": False,
            "gcp_url": None,
            "error": None
        }
        
        try:
            gcp_manager = self._get_gcp_manager(request)
            if not gcp_manager:
                result["error"] = "GCP manager not available"
                return result
            
            result["gcp_manager_available"] = True
            
            # Try to upload dummy data
            gcp_path = await self._save_to_temp_and_upload(
                dummy_audio, 
                request, 
                "test-project-123", 
                "test_upload"
            )
            
            if gcp_path:
                result["upload_success"] = True
                result["gcp_url"] = gcp_manager.get_public_url(gcp_path)
                logger.info(f"Session {session_id}: Test upload successful: {result['gcp_url']}")
            else:
                result["error"] = "Upload failed - check logs for details"
                logger.error(f"Session {session_id}: Test upload failed")
                
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Session {session_id}: Test upload error: {e}")
        
        return result

# Dependency Injection factory
def get_tts_handler() -> TtsHandler:
    return TtsHandler()
