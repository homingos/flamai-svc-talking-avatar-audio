import base64
import os
import sys
import uuid
import time
import json
from pathlib import Path
import asyncio
import tempfile
import shutil
from typing import Optional, Dict, Any, List
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
from src.utils.resources.gcp_bucket_manager import GCSBucketManager


class TTSServerlessSystem:
    """
    RunPod Serverless TTS System
    Single unified endpoint structure for all TTS operations with GCP storage
    Enhanced with session tracking, local file saving, and improved GCP integration
    """
    
    def __init__(self):
        """Initialize the TTS system for RunPod"""
        self.settings = settings
        
        # Initialize TTS service
        logger.info("🎤 Initializing TTS Service...")
        
        # Get configuration from settings
        service_config_data = self.settings.get("server_manager.services.minimax_tts", {})
        
        logger.info(f"📋 TTS Configuration:")
        logger.info(f"  - Service: Minimax TTS")
        logger.info(f"  - Config: {service_config_data}")
        
        service_config = ServiceConfig(
            name="minimax_tts",
            config=service_config_data.get("config", {})
        )
        
        self.tts_service = MinimaxTtsService(service_config)
        
        # Initialize the service
        asyncio.run(self.tts_service.initialize())
        
        # Initialize GCP Bucket Manager
        self.gcp_manager = None
        self._initialize_gcp_manager()
        
        # Setup temp directories
        self.temp_dir = Path("/tmp/runpod_uploads")
        self.temp_dir.mkdir(exist_ok=True)
        
        # Setup local temp directory for testing if enabled
        self.local_temp_dir = None
        if self.settings.get("app.save_local_tests", False):
            self.local_temp_dir = Path(self.settings.get("app.local_audio_directory", "runtime/temp"))
            self.local_temp_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 Local audio saving enabled: {self.local_temp_dir}")
        
        # Processing metrics
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.start_time = time.time()
        
        logger.info("✅ TTS Serverless System initialized!")

    def _generate_session_id(self) -> str:
        """Generate a unique session ID for tracking requests."""
        return str(uuid.uuid4())
    
    def _initialize_gcp_manager(self):
        """Initialize GCP bucket manager if enabled - delegates all credential handling to GCSBucketManager"""
        try:
            bucket_name = os.getenv('GCP_BUCKET_NAME')
            if bucket_name:
                try:
                    logger.info("Initializing GCP Bucket Manager...")
                    logger.info(f"  - Bucket: {bucket_name}")
                    
                    # Let GCSBucketManager handle all credential detection and authentication
                    self.gcp_manager = GCSBucketManager(
                        bucket_name=bucket_name,
                        credentials_path=os.getenv('GOOGLE_APPLICATION_CREDENTIALS'),  # Let GCSBucketManager handle env vars if this is None
                        create_bucket=os.getenv('GCP_CREATE_BUCKET', 'false').lower() == 'true',
                        location=os.getenv('GCP_BUCKET_LOCATION', 'US'),
                        project_id=os.getenv('GCP_PROJECT_ID')
                    )
                    logger.info(f"✅ GCP Bucket Manager initialized successfully for bucket: {bucket_name}")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to initialize GCP Bucket Manager: {e}")
                    logger.error("This might be due to missing or invalid GCP credentials")
                    logger.info("GCP upload functionality will be disabled")
                    self.gcp_manager = None
            else:
                logger.warning("📦 GCP_BUCKET_NAME not set. GCP upload functionality will be disabled.")
                self.gcp_manager = None
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize GCP Bucket Manager: {e}")
            self.gcp_manager = None

    def _save_local_file(self, audio_bytes: bytes, prefix: str, session_id: str):
        """Saves audio bytes to a local file if enabled in config."""
        if not self.settings.get("app.save_local_tests", False) or not audio_bytes or not self.local_temp_dir:
            return

        try:
            timestamp = int(time.time())
            output_path = self.local_temp_dir / f"{prefix}_{timestamp}.mp3"
            with open(output_path, "wb") as f:
                f.write(audio_bytes)
            logger.info(f"Session {session_id}: Audio file saved locally for testing at: {output_path}")
        except Exception as e:
            logger.error(f"Session {session_id}: Failed to save local file: {e}")

    def _generate_structured_bucket_path(self, project_id: str, filename: str) -> str:
        """
        Generate a structured bucket path using the new format.
        
        Format: <base_path>/<project_id>/<date>/audio/<filename>
        Example: talking-avatar/my-project-123/2024-01-15/audio/file.mp3
        
        Args:
            project_id: Project ID for organization
            filename: Name of the file to upload
            
        Returns:
            str: Complete structured path for the file
        """
        try:
            # Get base path from configuration
            gcp_config = self.settings.get_gcp_config()
            base_path = gcp_config.get('base_path', 'talking-avatar')
            
            # Use the GCP manager's method if available
            if self.gcp_manager:
                return self.gcp_manager.generate_structured_path(base_path, project_id, filename)
            else:
                # Fallback implementation if GCP manager is not available
                from datetime import datetime
                date_str = datetime.now().strftime("%Y-%m-%d")
                structured_path = f"{base_path.strip('/')}/{project_id}/{date_str}/audio/{filename}"
                return structured_path.replace('\\', '/')
                
        except Exception as e:
            logger.error(f"Failed to generate structured path: {e}")
            # Fallback to simple filename
            return filename

    async def _save_to_temp_and_upload(self, audio_bytes: bytes, project_id: str, 
                                     filename_prefix: str = "audio", session_id: str = None) -> Optional[str]:
        """Save audio to temp directory and upload to GCP if configured - uses only GCSBucketManager methods."""
        if not session_id:
            session_id = self._generate_session_id()
            
        gcp_path = None
        
        # Save to local temp directory first
        temp_dir = self.settings.get("server_manager.directories.temp", "runtime/temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        timestamp = int(time.time())
        filename = f"{filename_prefix}_{timestamp}.mp3"
        local_temp_path = os.path.join(temp_dir, filename)
        
        # Save locally
        with open(local_temp_path, 'wb') as f:
            f.write(audio_bytes)
        logger.info(f"Session {session_id}: Audio saved to temp directory: {local_temp_path}")
        
        # Upload to GCP if manager is available
        if self.gcp_manager:
            try:
                # Generate structured bucket path
                full_bucket_path = self._generate_structured_bucket_path(project_id, filename)

                logger.info(f"Session {session_id}: Attempting to upload to GCP bucket path: {full_bucket_path}")
                logger.info(f"Session {session_id}: Upload path generated for project_id='{project_id}'")
                
                # Use GCSBucketManager's upload_file method
                success = self.gcp_manager.upload_file(local_temp_path, full_bucket_path)
                if success:
                    logger.info(f"Session {session_id}: Successfully uploaded audio to GCP: {full_bucket_path}")
                    gcp_path = full_bucket_path
                else:
                    logger.error(f"Session {session_id}: Failed to upload audio to GCP: {full_bucket_path}")
            except Exception as e:
                logger.error(f"Session {session_id}: Error uploading audio to GCP: {e}")
        else:
            logger.warning(f"Session {session_id}: GCP manager not available, skipping upload")
        
        return gcp_path

    async def _upload_audio_to_gcp(self, audio_bytes: bytes, project_id: str, filename_prefix: str = "audio", 
                                 session_id: str = None) -> Optional[str]:
        """Upload audio bytes to GCP bucket and return the bucket path - uses only GCSBucketManager methods."""
        if not session_id:
            session_id = self._generate_session_id()
            
        if not self.gcp_manager:
            logger.warning(f"Session {session_id}: GCP bucket manager not available, skipping upload")
            return None

        try:
            # Generate filename with timestamp
            timestamp = int(time.time())
            filename = f"{filename_prefix}_{timestamp}.mp3"
            
            # Generate structured bucket path
            full_bucket_path = self._generate_structured_bucket_path(project_id, filename)

            logger.info(f"Session {session_id}: Upload path generated for project_id='{project_id}'")

            # Use GCSBucketManager's upload_data method instead of creating temporary files
            success = self.gcp_manager.upload_data(audio_bytes, full_bucket_path)
            if success:
                logger.info(f"Session {session_id}: Successfully uploaded audio to GCP: {full_bucket_path}")
                return full_bucket_path
            else:
                logger.error(f"Session {session_id}: Failed to upload audio to GCP: {full_bucket_path}")
                return None

        except Exception as e:
            logger.error(f"Session {session_id}: Error uploading audio to GCP: {e}")
            return None
    
    async def generate_speech(
        self, 
        text: str, 
        voice_id: str,
        project_id: str,
        upload_to_gcp: bool = True
    ) -> Dict[str, Any]:
        """Generate speech from text using existing voice ID"""
        start_time = time.time()
        session_id = self._generate_session_id()
        
        try:
            logger.info(f"Session {session_id}: Processing speech generation request")
            logger.info(f"Session {session_id}: Text: '{text[:100]}...'")
            logger.info(f"Session {session_id}: Voice ID: {voice_id}")
            logger.info(f"Session {session_id}: Project ID: {project_id}")
            logger.info(f"Session {session_id}: Upload to GCP: {upload_to_gcp}")
            
            # Validate input parameters
            if not text or not text.strip():
                return {
                    "success": False,
                    "session_id": session_id,
                    "error_message": "Text cannot be empty",
                    "processing_time": time.time() - start_time
                }
            
            if not voice_id or not voice_id.strip():
                return {
                    "success": False,
                    "session_id": session_id,
                    "error_message": "Voice ID cannot be empty",
                    "processing_time": time.time() - start_time
                }
            
            if not project_id or not project_id.strip():
                return {
                    "success": False,
                    "session_id": session_id,
                    "error_message": "Project ID cannot be empty",
                    "processing_time": time.time() - start_time
                }
            
            # Check text length (reasonable limit)
            max_text_length = 10000  # 10k characters
            if len(text) > max_text_length:
                return {
                    "success": False,
                    "session_id": session_id,
                    "error_message": f"Text cannot exceed {max_text_length} characters",
                    "processing_time": time.time() - start_time
                }
            
            # Generate speech
            logger.info(f"Session {session_id}: Generating speech...")
            audio_bytes = await self.tts_service.generate_speech_bytes(text, voice_id)
            
            if not audio_bytes:
                return {
                    "success": False,
                    "session_id": session_id,
                    "error_message": "Failed to generate speech from TTS service",
                    "processing_time": time.time() - start_time
                }
            
            # Save local file if enabled
            self._save_local_file(audio_bytes, "generate_speech", session_id)
            
            # Upload to GCP if requested
            gcp_url = None
            gcp_bucket_path = None
            if upload_to_gcp:
                logger.info(f"Session {session_id}: Starting GCP upload process")
                gcp_bucket_path = await self._save_to_temp_and_upload(
                    audio_bytes, 
                    project_id,
                    "generate_speech",
                    session_id
                )
                if gcp_bucket_path and self.gcp_manager:
                    gcp_url = self.gcp_manager.get_public_url(gcp_bucket_path)
                    logger.info(f"Session {session_id}: Generated public URL: {gcp_url}")
                elif gcp_bucket_path:
                    logger.warning(f"Session {session_id}: Uploaded to GCP but couldn't generate public URL")
                else:
                    logger.warning(f"Session {session_id}: Failed to upload audio to GCP")
            else:
                logger.info(f"Session {session_id}: GCP upload not requested, skipping")
            
            processing_time = time.time() - start_time
            
            logger.info(f"Session {session_id}: Speech generation completed successfully in {processing_time:.3f}s")
            
            response = {
                "success": True,
                "session_id": session_id,
                "text": text,
                "voice_id": voice_id,
                "project_id": project_id,
                "audio_size_bytes": len(audio_bytes),
                "processing_time": processing_time,
                "message": "Speech generated successfully"
            }
            
            if gcp_url:
                response["gcp_url"] = gcp_url
                response["message"] += f" and uploaded to GCP: {gcp_url}"
            elif gcp_bucket_path:
                response["gcp_bucket_path"] = gcp_bucket_path
                response["message"] += f" and uploaded to GCP bucket: {gcp_bucket_path}"
            else:
                response["message"] += " (GCP upload skipped or failed)"
            
            return response
                
        except Exception as e:
            logger.error(f"Session {session_id}: Error processing speech generation request: {str(e)}")
            return {
                "success": False,
                "session_id": session_id,
                "error_message": f"Processing error: {str(e)}",
                "processing_time": time.time() - start_time
            }
    
    async def clone_voice(
        self, 
        new_voice_id: str, 
        audio_base64: str,
        project_id: str
    ) -> Dict[str, Any]:
        """Clone a voice from audio data"""
        start_time = time.time()
        session_id = self._generate_session_id()
        
        try:
            logger.info(f"Session {session_id}: Processing voice cloning request")
            logger.info(f"Session {session_id}: New Voice ID: {new_voice_id}")
            logger.info(f"Session {session_id}: Project ID: {project_id}")
            
            # Validate input parameters
            if not new_voice_id or not new_voice_id.strip():
                return {
                    "success": False,
                    "session_id": session_id,
                    "error_message": "New voice ID cannot be empty",
                    "processing_time": time.time() - start_time
                }
            
            if not audio_base64:
                return {
                    "success": False,
                    "session_id": session_id,
                    "error_message": "Audio data cannot be empty",
                    "processing_time": time.time() - start_time
                }
            
            if not project_id or not project_id.strip():
                return {
                    "success": False,
                    "session_id": session_id,
                    "error_message": "Project ID cannot be empty",
                    "processing_time": time.time() - start_time
                }
            
            # Validate voice ID format (basic validation)
            if len(new_voice_id) < 8:
                return {
                    "success": False,
                    "session_id": session_id,
                    "error_message": "Voice ID must be at least 8 characters long",
                    "processing_time": time.time() - start_time
                }
            
            # Decode and save the temporary audio file
            try:
                audio_bytes = base64.b64decode(audio_base64)
                temp_file_path = self.temp_dir / f"clone_{uuid.uuid4()}.mp3"
                with open(temp_file_path, "wb") as f:
                    f.write(audio_bytes)
            except Exception as e:
                logger.error(f"Session {session_id}: Failed to decode or save audio file: {e}")
                return {
                    "success": False,
                    "session_id": session_id,
                    "error_message": f"Failed to decode or save audio file: {e}",
                    "processing_time": time.time() - start_time
                }
            
            # Clone voice
            logger.info(f"Session {session_id}: Cloning voice...")
            cloned_voice_id = await self.tts_service.create_voice_from_file(temp_file_path, new_voice_id)
            
            # Cleanup temporary file
            temp_file_path.unlink()
            
            if not cloned_voice_id:
                return {
                    "success": False,
                    "session_id": session_id,
                    "error_message": "Failed to clone voice from TTS service",
                    "processing_time": time.time() - start_time
                }
            
            processing_time = time.time() - start_time
            
            logger.info(f"Session {session_id}: Voice cloning completed successfully in {processing_time:.3f}s")
            
            return {
                "success": True,
                "session_id": session_id,
                "new_voice_id": new_voice_id,
                "cloned_voice_id": cloned_voice_id,
                "project_id": project_id,
                "processing_time": processing_time,
                "message": "Voice cloned successfully"
            }
                
        except Exception as e:
            logger.error(f"Session {session_id}: Error processing voice cloning request: {str(e)}")
            return {
                "success": False,
                "session_id": session_id,
                "error_message": f"Processing error: {str(e)}",
                "processing_time": time.time() - start_time
            }
    
    async def clone_and_generate_speech(
        self, 
        text: str, 
        new_voice_id: str, 
        audio_base64: str,
        project_id: str,
        upload_to_gcp: bool = True
    ) -> Dict[str, Any]:
        """Clone voice and generate speech in one operation"""
        start_time = time.time()
        session_id = self._generate_session_id()
        
        try:
            logger.info(f"Session {session_id}: Processing clone-and-generate request")
            logger.info(f"Session {session_id}: Text: '{text[:100]}...'")
            logger.info(f"Session {session_id}: New Voice ID: {new_voice_id}")
            logger.info(f"Session {session_id}: Project ID: {project_id}")
            logger.info(f"Session {session_id}: Upload to GCP: {upload_to_gcp}")
            
            # Validate input parameters
            if not all([text, new_voice_id, audio_base64, project_id]):
                return {
                    "success": False,
                    "session_id": session_id,
                    "error_message": "Missing required parameters: text, new_voice_id, audio_base64, or project_id",
                    "processing_time": time.time() - start_time
                }
            
            if not text.strip():
                return {
                    "success": False,
                    "session_id": session_id,
                    "error_message": "Text cannot be empty",
                    "processing_time": time.time() - start_time
                }
            
            if len(new_voice_id) < 8:
                return {
                    "success": False,
                    "session_id": session_id,
                    "error_message": "Voice ID must be at least 8 characters long",
                    "processing_time": time.time() - start_time
                }
            
            # Check text length
            max_text_length = 10000
            if len(text) > max_text_length:
                return {
                    "success": False,
                    "session_id": session_id,
                    "error_message": f"Text cannot exceed {max_text_length} characters",
                    "processing_time": time.time() - start_time
                }
            
            # Decode and save the temporary audio file
            try:
                audio_bytes = base64.b64decode(audio_base64)
                temp_file_path = self.temp_dir / f"clone_gen_{uuid.uuid4()}.mp3"
                with open(temp_file_path, "wb") as f:
                    f.write(audio_bytes)
            except Exception as e:
                logger.error(f"Session {session_id}: Failed to decode or save audio file: {e}")
                return {
                    "success": False,
                    "session_id": session_id,
                    "error_message": f"Failed to decode or save audio file: {e}",
                    "processing_time": time.time() - start_time
                }
            
            # Perform the clone and speech generation
            logger.info(f"Session {session_id}: Performing clone-and-generate workflow...")
            output_audio_bytes = await self.tts_service.clone_and_generate_speech_bytes(
                text=text,
                audio_clone_path=str(temp_file_path),
                new_voice_id=new_voice_id
            )
            
            # Cleanup temporary file
            temp_file_path.unlink()
            
            if not output_audio_bytes:
                return {
                    "success": False,
                    "session_id": session_id,
                    "error_message": "Failed to complete clone-and-generate workflow",
                    "processing_time": time.time() - start_time
                }
            
            # Save local file if enabled
            self._save_local_file(output_audio_bytes, "clone_and_generate", session_id)
            
            # Upload to GCP if requested
            gcp_url = None
            gcp_bucket_path = None
            if upload_to_gcp:
                logger.info(f"Session {session_id}: Starting GCP upload process")
                gcp_bucket_path = await self._save_to_temp_and_upload(
                    output_audio_bytes, 
                    project_id,
                    "clone_and_generate",
                    session_id
                )
                if gcp_bucket_path and self.gcp_manager:
                    gcp_url = self.gcp_manager.get_public_url(gcp_bucket_path)
                    logger.info(f"Session {session_id}: Generated public URL: {gcp_url}")
                elif gcp_bucket_path:
                    logger.warning(f"Session {session_id}: Uploaded to GCP but couldn't generate public URL")
                else:
                    logger.warning(f"Session {session_id}: Failed to upload audio to GCP")
            else:
                logger.info(f"Session {session_id}: GCP upload not requested, skipping")
            
            processing_time = time.time() - start_time
            
            logger.info(f"Session {session_id}: Clone-and-generate completed successfully in {processing_time:.3f}s")
            
            response = {
                "success": True,
                "session_id": session_id,
                "text": text,
                "new_voice_id": new_voice_id,
                "project_id": project_id,
                "audio_size_bytes": len(output_audio_bytes),
                "processing_time": processing_time,
                "message": "Clone-and-generate workflow completed successfully"
            }
            
            if gcp_url:
                response["gcp_url"] = gcp_url
                response["message"] += f" and uploaded to GCP: {gcp_url}"
            elif gcp_bucket_path:
                response["gcp_bucket_path"] = gcp_bucket_path
                response["message"] += f" and uploaded to GCP bucket: {gcp_bucket_path}"
            else:
                response["message"] += " (GCP upload skipped or failed)"
            
            return response
                
        except Exception as e:
            logger.error(f"Session {session_id}: Error processing clone-and-generate request: {str(e)}")
            return {
                "success": False,
                "session_id": session_id,
                "error_message": f"Processing error: {str(e)}",
                "processing_time": time.time() - start_time
            }
    
    async def health_check(self) -> Dict[str, Any]:
        """Enhanced health check with comprehensive system information"""
        session_id = self._generate_session_id()
        
        try:
            logger.info(f"Session {session_id}: Performing system health check...")
            
            # Check TTS service
            service_status = self.tts_service.get_status()
            tts_healthy = service_status.get('initialized', False)
            logger.info(f"Session {session_id}: TTS Service health: {'✅ OK' if tts_healthy else '❌ FAILED'}")
            
            # Check GCP bucket manager
            gcp_status = {"initialized": False, "status": "disabled"}
            if self.gcp_manager:
                try:
                    # Test bucket access by checking if bucket exists
                    bucket_exists = self.gcp_manager.bucket.exists() if self.gcp_manager.bucket else False
                    gcp_status = {
                        "initialized": True,
                        "bucket_name": self.gcp_manager.bucket_name,
                        "bucket_exists": bucket_exists,
                        "status": "healthy" if bucket_exists else "bucket_not_found"
                    }
                    logger.info(f"Session {session_id}: GCP Bucket Manager health: {'✅ OK' if bucket_exists else '⚠️ BUCKET NOT FOUND'}")
                except Exception as e:
                    gcp_status = {
                        "initialized": False,
                        "status": "error",
                        "error": str(e)
                    }
                    logger.error(f"Session {session_id}: GCP Bucket Manager health: ❌ ERROR - {e}")
            else:
                logger.info(f"Session {session_id}: GCP Bucket Manager: ⚪ DISABLED")
            
            # Calculate uptime
            uptime = time.time() - self.start_time
            
            # Get system information
            import sys
            
            system_info = {
                "python_version": sys.version,
                "service_initialized": service_status.get('initialized', False),
                "api_configured": service_status.get('api_configured', False),
                "service_name": service_status.get('name', 'unknown'),
                "temp_directory": str(self.temp_dir),
                "temp_dir_exists": self.temp_dir.exists(),
                "local_temp_enabled": self.local_temp_dir is not None,
                "local_temp_directory": str(self.local_temp_dir) if self.local_temp_dir else None,
                "gcp_enabled": self.gcp_manager is not None
            }
            
            # Calculate processing metrics
            success_rate = (
                self.successful_requests / self.total_requests 
                if self.total_requests > 0 else 0
            )
            
            processing_metrics = {
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "success_rate": success_rate,
                "uptime": uptime
            }
            
            overall_health = tts_healthy
            status = "healthy" if overall_health else "unhealthy"
            
            logger.info(f"Session {session_id}: Overall system health: {'✅ HEALTHY' if overall_health else '❌ UNHEALTHY'}")
            
            return {
                "success": True,
                "session_id": session_id,
                "status": status,
                "timestamp": time.time(),
                "service_name": "TTS Service",
                "version": "1.0.0",
                "uptime": uptime,
                "components": {
                    "tts_service": tts_healthy,
                    "gcp_bucket_manager": gcp_status
                },
                "system_info": system_info,
                "processing_metrics": processing_metrics,
                "service_status": service_status
            }
            
        except Exception as e:
            logger.error(f"Session {session_id}: Health check failed: {str(e)}")
            return {
                "success": False,
                "session_id": session_id,
                "status": "unhealthy",
                "error_message": f"Health check failed: {str(e)}"
            }

    async def debug_gcp(self) -> Dict[str, Any]:
        """Provides detailed debugging information about GCP configuration and status."""
        session_id = self._generate_session_id()
        
        try:
            logger.info(f"Session {session_id}: Getting GCP debug information...")
            
            import os
            
            debug_info = {
                "session_id": session_id,
                "environment_variables": {
                    "GCP_BUCKET_NAME": os.getenv('GCP_BUCKET_NAME'),
                    "GOOGLE_APPLICATION_CREDENTIALS": os.getenv('GOOGLE_APPLICATION_CREDENTIALS'),
                    "RUNPOD_SECRET_GKE_SA_DEV": os.getenv('RUNPOD_SECRET_GKE_SA_DEV'),
                    "GCP_PROJECT_ID": os.getenv('GCP_PROJECT_ID'),
                    "GCP_CREATE_BUCKET": os.getenv('GCP_CREATE_BUCKET'),
                    "GCP_BUCKET_LOCATION": os.getenv('GCP_BUCKET_LOCATION'),
                    "GKE_SA_DEV": os.getenv('GKE_SA_DEV')
                },
                "gcp_manager_status": {
                    "available": self.gcp_manager is not None,
                    "bucket_name": self.gcp_manager.bucket_name if self.gcp_manager else None,
                    "credentials_path": self.gcp_manager.credentials_path if self.gcp_manager else None,
                    "project_id": self.gcp_manager.project_id if self.gcp_manager else None,
                    "client_available": self.gcp_manager.client is not None if self.gcp_manager else False,
                    "bucket_available": self.gcp_manager.bucket is not None if self.gcp_manager else False
                },
                "config_settings": {
                    "gcp_enabled": self.settings.get("gcp.enabled"),
                    "gcp_bucket_name": self.settings.get("gcp.bucket_name"),
                    "gcp_credentials_path": self.settings.get("gcp.credentials_path"),
                    "gcp_default_upload_path": self.settings.get("gcp.default_upload_path")
                }
            }
            
            # Test bucket access if manager is available
            if self.gcp_manager:
                try:
                    # Try to list first few objects to test access
                    blobs = list(self.gcp_manager.bucket.list_blobs(max_results=1))
                    debug_info["bucket_test"] = {
                        "accessible": True,
                        "message": "Bucket is accessible"
                    }
                    logger.info(f"Session {session_id}: GCP bucket access test successful")
                except Exception as e:
                    debug_info["bucket_test"] = {
                        "accessible": False,
                        "error": str(e)
                    }
                    logger.error(f"Session {session_id}: GCP bucket access test failed: {e}")
            else:
                debug_info["bucket_test"] = {
                    "accessible": False,
                    "error": "GCP manager not available"
                }
                logger.warning(f"Session {session_id}: GCP manager not available for testing")
            
            return {
                "success": True,
                "data": debug_info
            }
            
        except Exception as e:
            logger.error(f"Session {session_id}: Error getting GCP debug info: {str(e)}")
            return {
                "success": False,
                "session_id": session_id,
                "error_message": f"Failed to get GCP debug info: {str(e)}"
            }

    async def test_gcp_upload(self) -> Dict[str, Any]:
        """Test GCP upload functionality with a dummy file."""
        session_id = self._generate_session_id()
        
        try:
            logger.info(f"Session {session_id}: Testing GCP upload functionality")
            
            # Create dummy audio data
            dummy_audio = b"dummy audio data for testing"
            
            result = {
                "success": False,
                "session_id": session_id,
                "gcp_manager_available": False,
                "upload_success": False,
                "gcp_url": None,
                "error": None
            }
            
            if not self.gcp_manager:
                result["error"] = "GCP manager not available"
                logger.warning(f"Session {session_id}: GCP manager not available for test")
                return result
            
            result["gcp_manager_available"] = True
            
            # Try to upload dummy data
            gcp_path = await self._save_to_temp_and_upload(
                dummy_audio, 
                "test-project-123",
                "test_upload",
                session_id
            )
            
            if gcp_path:
                result["success"] = True
                result["upload_success"] = True
                result["gcp_url"] = self.gcp_manager.get_public_url(gcp_path)
                logger.info(f"Session {session_id}: Test upload successful: {result['gcp_url']}")
            else:
                result["error"] = "Upload failed - check logs for details"
                logger.error(f"Session {session_id}: Test upload failed")
                
            return result
                
        except Exception as e:
            logger.error(f"Session {session_id}: Test upload error: {e}")
            return {
                "success": False,
                "session_id": session_id,
                "error_message": str(e)
            }
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get detailed system information"""
        session_id = self._generate_session_id()
        
        try:
            logger.info(f"Session {session_id}: Getting system information...")
            
            # Get service information
            service_status = self.tts_service.get_status()
            
            # Get GCP status
            gcp_info = {"enabled": False, "status": "disabled"}
            if self.gcp_manager:
                try:
                    bucket_exists = self.gcp_manager.bucket.exists() if self.gcp_manager.bucket else False
                    gcp_info = {
                        "enabled": True,
                        "bucket_name": self.gcp_manager.bucket_name,
                        "bucket_exists": bucket_exists,
                        "status": "healthy" if bucket_exists else "bucket_not_found"
                    }
                except Exception as e:
                    gcp_info = {
                        "enabled": True,
                        "status": "error",
                        "error": str(e)
                    }
            
            # Get system information
            import sys
            
            system_info = {
                "python_version": sys.version,
                "service_initialized": service_status.get('initialized', False),
                "api_configured": service_status.get('api_configured', False),
                "service_name": service_status.get('name', 'unknown'),
                "temp_directory": str(self.temp_dir),
                "temp_dir_exists": self.temp_dir.exists(),
                "local_temp_enabled": self.local_temp_dir is not None,
                "local_temp_directory": str(self.local_temp_dir) if self.local_temp_dir else None,
                "gcp_enabled": self.gcp_manager is not None,
                "gcp_info": gcp_info
            }
            
            # Get CPU and memory info if available
            try:
                import psutil
                system_info["cpu_count"] = psutil.cpu_count()
                system_info["memory_total"] = psutil.virtual_memory().total / 1024**3
            except ImportError:
                logger.warning(f"Session {session_id}: psutil not available for system info")
            except Exception as e:
                logger.warning(f"Session {session_id}: Could not get system info: {e}")
            
            # Calculate processing metrics
            uptime = time.time() - self.start_time
            success_rate = (
                self.successful_requests / self.total_requests 
                if self.total_requests > 0 else 0
            )
            
            processing_metrics = {
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "success_rate": success_rate,
                "uptime": uptime
            }
            
            logger.info(f"Session {session_id}: System information retrieved successfully")
            
            return {
                "success": True,
                "session_id": session_id,
                "status": "healthy" if service_status.get('initialized', False) else "unhealthy",
                "timestamp": time.time(),
                "service_name": "TTS Service",
                "version": "1.0.0",
                "uptime": uptime,
                "service_status": service_status,
                "system_info": system_info,
                "processing_metrics": processing_metrics
            }
            
        except Exception as e:
            logger.error(f"Session {session_id}: Error getting system info: {str(e)}")
            return {
                "success": False,
                "session_id": session_id,
                "error_message": f"Failed to get system info: {str(e)}"
            }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get processing metrics and statistics"""
        session_id = self._generate_session_id()
        
        try:
            logger.info(f"Session {session_id}: Getting processing metrics...")
            
            uptime = time.time() - self.start_time
            success_rate = (
                self.successful_requests / self.total_requests 
                if self.total_requests > 0 else 0
            )
            
            metrics = {
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "success_rate": success_rate,
                "uptime": uptime,
                "timestamp": time.time()
            }
            
            logger.info(f"Session {session_id}: Processing metrics retrieved successfully")
            
            return {
                "success": True,
                "session_id": session_id,
                "metrics": metrics
            }
            
        except Exception as e:
            logger.error(f"Session {session_id}: Error getting metrics: {str(e)}")
            return {
                "success": False,
                "session_id": session_id,
                "error_message": f"Failed to get metrics: {str(e)}"
            }


# Global system instance
_system_instance: Optional[TTSServerlessSystem] = None

def get_system_instance() -> TTSServerlessSystem:
    """Get or create the system instance"""
    global _system_instance
    if _system_instance is None:
        _system_instance = TTSServerlessSystem()
    return _system_instance

# UNIFIED RUNPOD HANDLER - Single Template Structure
async def handler(job):
    """
    🎯 UNIFIED RUNPOD HANDLER
    Single template structure for ALL endpoints
    Enhanced with session tracking, local file saving, and improved GCP integration
    
    Expected Input Format (ALL endpoints use this same structure):
    {
        "input": {
            "endpoint": "generate_speech" | "clone_voice" | "clone_and_generate" | "health_check" | "system_info" | "metrics" | "debug_gcp" | "test_gcp_upload",
            "data": {
                // Endpoint-specific parameters go here
                // For generate_speech and clone_and_generate:
                //   - project_id: str (required for structured path generation)
                //   - upload_to_gcp: bool (default: true)
            }
        }
    }
    
    Output Format (ALL endpoints return this same structure):
    {
        "success": true/false,
        "data": {
            // Endpoint-specific response data
            // Now includes session_id for request tracking
            // Instead of audio_base64, now includes:
            //   - gcp_url: string (if uploaded to GCP and public URL generated)
            //   - gcp_bucket_path: string (if uploaded to GCP bucket)
            //   - audio_size_bytes: int
        },
        "error_message": "string" | null,
        "processing_time": float,
        "endpoint": "string"
    }
    """
    
    start_time = time.time()
    
    try:
        # Extract input from RunPod job
        input_data = job.get("input", {})
        endpoint = input_data.get("endpoint")
        data = input_data.get("data", {})
        
        if not endpoint:
            return {
                "success": False,
                "data": {},
                "error_message": "Missing required parameter: endpoint",
                "processing_time": time.time() - start_time,
                "endpoint": "unknown"
            }
        
        logger.info(f"🚀 Processing RunPod request - Endpoint: {endpoint}")
        
        # Get system instance
        system = get_system_instance()
        
        # Route to appropriate endpoint handler
        if endpoint == "generate_speech":
            # Generate Speech Endpoint
            text = data.get("text")
            voice_id = data.get("voice_id")
            project_id = data.get("project_id")
            upload_to_gcp = data.get("upload_to_gcp", True)  # Default to True
            
            if not text or not voice_id or not project_id:
                return {
                    "success": False,
                    "data": {},
                    "error_message": "Missing required parameters: text, voice_id, and project_id",
                    "processing_time": time.time() - start_time,
                    "endpoint": endpoint
                }
            
            result = await system.generate_speech(
                text=text,
                voice_id=voice_id,
                project_id=project_id,
                upload_to_gcp=upload_to_gcp
            )
            
            # Update metrics
            system.total_requests += 1
            if result["success"]:
                system.successful_requests += 1
            else:
                system.failed_requests += 1
            
            return {
                "success": result["success"],
                "data": {
                    "session_id": result.get("session_id"),
                    "text": result.get("text"),
                    "voice_id": result.get("voice_id"),
                    "project_id": result.get("project_id"),
                    "gcp_url": result.get("gcp_url"),
                    "gcp_bucket_path": result.get("gcp_bucket_path"),
                    "audio_size_bytes": result.get("audio_size_bytes"),
                    "message": result.get("message")
                },
                "error_message": result.get("error_message"),
                "processing_time": time.time() - start_time,
                "endpoint": endpoint
            }
        
        elif endpoint == "clone_voice":
            # Clone Voice Endpoint
            new_voice_id = data.get("new_voice_id")
            audio_base64 = data.get("audio_base64")
            project_id = data.get("project_id")
            
            if not new_voice_id or not audio_base64 or not project_id:
                return {
                    "success": False,
                    "data": {},
                    "error_message": "Missing required parameters: new_voice_id, audio_base64, and project_id",
                    "processing_time": time.time() - start_time,
                    "endpoint": endpoint
                }
            
            result = await system.clone_voice(
                new_voice_id=new_voice_id,
                audio_base64=audio_base64,
                project_id=project_id
            )
            
            # Update metrics
            system.total_requests += 1
            if result["success"]:
                system.successful_requests += 1
            else:
                system.failed_requests += 1
            
            return {
                "success": result["success"],
                "data": {
                    "session_id": result.get("session_id"),
                    "new_voice_id": result.get("new_voice_id"),
                    "cloned_voice_id": result.get("cloned_voice_id"),
                    "project_id": result.get("project_id"),
                    "message": result.get("message")
                },
                "error_message": result.get("error_message"),
                "processing_time": time.time() - start_time,
                "endpoint": endpoint
            }
        
        elif endpoint == "clone_and_generate":
            # Clone and Generate Speech Endpoint
            text = data.get("text")
            new_voice_id = data.get("new_voice_id")
            audio_base64 = data.get("audio_base64")
            project_id = data.get("project_id")
            upload_to_gcp = data.get("upload_to_gcp", True)  # Default to True
            
            if not all([text, new_voice_id, audio_base64, project_id]):
                return {
                    "success": False,
                    "data": {},
                    "error_message": "Missing required parameters: text, new_voice_id, audio_base64, and project_id",
                    "processing_time": time.time() - start_time,
                    "endpoint": endpoint
                }
            
            result = await system.clone_and_generate_speech(
                text=text,
                new_voice_id=new_voice_id,
                audio_base64=audio_base64,
                project_id=project_id,
                upload_to_gcp=upload_to_gcp
            )
            
            # Update metrics
            system.total_requests += 1
            if result["success"]:
                system.successful_requests += 1
            else:
                system.failed_requests += 1
            
            return {
                "success": result["success"],
                "data": {
                    "session_id": result.get("session_id"),
                    "text": result.get("text"),
                    "new_voice_id": result.get("new_voice_id"),
                    "project_id": result.get("project_id"),
                    "gcp_url": result.get("gcp_url"),
                    "gcp_bucket_path": result.get("gcp_bucket_path"),
                    "audio_size_bytes": result.get("audio_size_bytes"),
                    "message": result.get("message")
                },
                "error_message": result.get("error_message"),
                "processing_time": time.time() - start_time,
                "endpoint": endpoint
            }
        
        elif endpoint == "health_check":
            # Health Check Endpoint
            result = await system.health_check()
            
            return {
                "success": result["success"],
                "data": {
                    "session_id": result.get("session_id"),
                    "status": result.get("status"),
                    "timestamp": result.get("timestamp"),
                    "service_name": result.get("service_name"),
                    "version": result.get("version"),
                    "uptime": result.get("uptime"),
                    "components": result.get("components"),
                    "system_info": result.get("system_info"),
                    "processing_metrics": result.get("processing_metrics"),
                    "service_status": result.get("service_status")
                },
                "error_message": result.get("error_message"),
                "processing_time": time.time() - start_time,
                "endpoint": endpoint
            }
        
        elif endpoint == "system_info":
            # System Info Endpoint
            result = system.get_system_info()
            
            return {
                "success": result["success"],
                "data": {
                    "session_id": result.get("session_id"),
                    "status": result.get("status"),
                    "timestamp": result.get("timestamp"),
                    "service_name": result.get("service_name"),
                    "version": result.get("version"),
                    "uptime": result.get("uptime"),
                    "service_status": result.get("service_status"),
                    "system_info": result.get("system_info"),
                    "processing_metrics": result.get("processing_metrics")
                },
                "error_message": result.get("error_message"),
                "processing_time": time.time() - start_time,
                "endpoint": endpoint
            }
        
        elif endpoint == "metrics":
            # Metrics Endpoint
            result = system.get_metrics()
            
            return {
                "success": result["success"],
                "data": {
                    "session_id": result.get("session_id"),
                    "metrics": result.get("metrics")
                },
                "error_message": result.get("error_message"),
                "processing_time": time.time() - start_time,
                "endpoint": endpoint
            }

        elif endpoint == "debug_gcp":
            # GCP Debug Endpoint
            result = await system.debug_gcp()
            
            return {
                "success": result["success"],
                "data": result.get("data", {}),
                "error_message": result.get("error_message"),
                "processing_time": time.time() - start_time,
                "endpoint": endpoint
            }

        elif endpoint == "test_gcp_upload":
            # Test GCP Upload Endpoint
            result = await system.test_gcp_upload()
            
            return {
                "success": result["success"],
                "data": {
                    "session_id": result.get("session_id"),
                    "gcp_manager_available": result.get("gcp_manager_available"),
                    "upload_success": result.get("upload_success"),
                    "gcp_url": result.get("gcp_url"),
                    "error": result.get("error")
                },
                "error_message": result.get("error_message"),
                "processing_time": time.time() - start_time,
                "endpoint": endpoint
            }
        
        else:
            return {
                "success": False,
                "data": {},
                "error_message": f"Unknown endpoint: {endpoint}. Available: generate_speech, clone_voice, clone_and_generate, health_check, system_info, metrics, debug_gcp, test_gcp_upload",
                "processing_time": time.time() - start_time,
                "endpoint": endpoint
            }
            
    except Exception as e:
        logger.error(f"❌ RunPod handler error: {str(e)}")
        return {
            "success": False,
            "data": {},
            "error_message": f"Handler error: {str(e)}",
            "processing_time": time.time() - start_time,
            "endpoint": input_data.get("endpoint", "unknown")
        }

# RunPod serverless setup
if __name__ == "__main__":
    logger.info("🚀 Starting RunPod TTS System...")
    
    # Initialize the system at startup
    system = get_system_instance()
    logger.info("✅ System initialized successfully!")
    
    logger.info("📋 Available Endpoints:")
    logger.info("  - generate_speech: Generate speech from text using existing voice ID")
    logger.info("  - clone_voice: Clone a voice from audio data")
    logger.info("  - clone_and_generate: Clone voice and generate speech in one operation")
    logger.info("  - health_check: Get system health status")
    logger.info("  - system_info: Get detailed system information")
    logger.info("  - metrics: Get processing metrics and statistics")
    logger.info("  - debug_gcp: Get detailed GCP configuration and status")
    logger.info("  - test_gcp_upload: Test GCP upload functionality with dummy file")
    
    logger.info("📦 GCP Integration:")
    logger.info("  - Audio files are uploaded to GCP bucket by default")
    logger.info("  - Set upload_to_gcp=false in request data to disable GCP upload")
    logger.info("  - project_id parameter is required for structured path generation")
    logger.info("  - Files are organized as: talking-avatar/<project_id>/<date>/audio/<filename>")
    logger.info("  - GCP URLs are generated when possible for direct access")
    
    logger.info("🔍 Enhanced Features:")
    logger.info("  - Session ID tracking for all requests")
    logger.info("  - Local file saving for testing (configurable)")
    logger.info("  - Enhanced error handling and validation")
    logger.info("  - Improved GCP integration with public URL generation")
    logger.info("  - Debug and testing endpoints for troubleshooting")
    
    # Start the RunPod serverless worker
    runpod.serverless.start({"handler": handler})