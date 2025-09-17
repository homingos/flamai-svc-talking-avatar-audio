# /src/services/tts_service.py

import httpx
from pathlib import Path
from typing import Optional

from src.core.server_manager import AIService, ServiceConfig
from src.utils.resources.logger import logger


class MinimaxTtsService(AIService):
    """
    An asynchronous, production-ready service for MiniMax TTS and Voice Cloning.
    This service handles all communication with the MiniMax API.
    """
    BASE_URL = "https://api.minimax.io/v1"

    def __init__(self, config: ServiceConfig):
        """Initializes the service with its configuration."""
        super().__init__(config)
        self.api_key: Optional[str] = None
        self.group_id: Optional[str] = None
        self.client: httpx.AsyncClient = httpx.AsyncClient(timeout=120.0)

    async def initialize(self) -> bool:
        """
        Initializes the service by loading credentials from the configuration.
        This method is called once at application startup.
        """
        logger.info("Initializing Minimax TTS Service...")
        self.api_key = self.config.config.get("api_key")
        self.group_id = self.config.config.get("group_id")

        if not self.api_key or not self.group_id:
            logger.error("FATAL: MINIMAX_API_KEY or MINIMAX_GROUP_ID not configured. Check config.yaml and your environment variables.")
            self.is_initialized = False
            return False
        
        self.is_initialized = True
        logger.info("Minimax TTS Service initialized successfully.")
        return True

    async def shutdown(self) -> None:
        """Closes the HTTP client during application shutdown."""
        logger.info("Shutting down Minimax TTS Service client.")
        await self.client.aclose()

    def get_status(self) -> dict:
        """Returns the current status of the service for health checks."""
        return {
            "name": self.config.name,
            "initialized": self.is_initialized,
            "api_configured": bool(self.api_key and self.group_id),
        }

    async def _upload_audio(self, audio_path: Path) -> Optional[str]:
        """(Internal) Uploads an audio file and returns its file_id."""
        logger.info(f"Uploading audio file: {audio_path.name}")
        url = f'{self.BASE_URL}/files/upload?GroupId={self.group_id}'
        headers = {'Authorization': f'Bearer {self.api_key}'}
        
        try:
            with open(audio_path, 'rb') as audio_file:
                files = {'file': (audio_path.name, audio_file, 'audio/mpeg')}
                response = await self.client.post(
                    url, 
                    headers=headers, 
                    data={'purpose': 'voice_clone'}, 
                    files=files, 
                    timeout=60
                )
                response.raise_for_status()
            
            result = response.json()
            if result.get('base_resp', {}).get('status_code') == 0:
                file_id = result.get("file", {}).get("file_id")
                logger.info(f"Upload successful. File ID: {file_id}")
                return file_id
            else:
                logger.error(f"API Error during upload: {result.get('base_resp', {}).get('status_msg')}")
                return None
        except Exception as e:
            logger.error(f"An error occurred during upload: {e}", exc_info=True)
            return None

    async def _create_voice_clone(self, file_id: str, new_voice_id: str) -> Optional[str]:
        """(Internal) Creates a voice clone from a file_id."""
        logger.info(f"Creating voice clone '{new_voice_id}'...")
        url = f'{self.BASE_URL}/voice_clone?GroupId={self.group_id}'
        headers = {'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'}
        payload = {"file_id": file_id, "voice_id": new_voice_id}

        try:
            response = await self.client.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            
            if result.get('base_resp', {}).get('status_code') == 0:
                logger.info(f"Voice clone created successfully: {new_voice_id}")
                return new_voice_id
            else:
                logger.error(f"API Error during cloning: {result.get('base_resp', {}).get('status_msg')}")
                return None
        except Exception as e:
            logger.error(f"An error occurred during voice cloning: {e}", exc_info=True)
            return None

    async def generate_speech_bytes(self, text: str, voice_id: str) -> Optional[bytes]:
        """Generates TTS audio and returns it as bytes."""
        logger.info(f"Generating speech with voice '{voice_id}'...")
        url = f"{self.BASE_URL}/t2a_v2?GroupId={self.group_id}"
        headers = {'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'}
        payload = {
            "model": "speech-2.5-hd-preview",
            "text": text,
            "stream": False,
            "voice_setting": {"voice_id": voice_id},
            "audio_setting": {"format": "mp3"}
        }
        try:
            response = await self.client.post(url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            result = response.json()

            if result.get('base_resp', {}).get('status_code') != 0:
                logger.error(f"API Error during TTS: {result.get('base_resp', {}).get('status_msg')}")
                return None

            audio_hex = result.get('data', {}).get('audio')
            if not audio_hex:
                logger.error("TTS response contained no audio data.")
                return None
            
            # The audio data from the API is a hexadecimal string.
            audio_bytes = bytes.fromhex(audio_hex)
            
            logger.info(f"Successfully generated {len(audio_bytes)} bytes of audio.")
            return audio_bytes
        except Exception as e:
            logger.error(f"An error occurred during TTS generation: {e}", exc_info=True)
            return None
            
    async def create_voice_from_file(self, audio_clone_path: Path, new_voice_id: str) -> Optional[str]:
        """Full workflow to create a voice from a local audio file."""
        file_id = await self._upload_audio(audio_clone_path)
        if file_id:
            return await self._create_voice_clone(file_id, new_voice_id)
        return None

    async def clone_and_generate_speech_bytes(self, text: str, audio_clone_path: str, new_voice_id: str) -> Optional[bytes]:
        """High-level method for the full clone-and-speak workflow."""
        cloned_voice_id = await self.create_voice_from_file(Path(audio_clone_path), new_voice_id)
        if cloned_voice_id:
            return await self.generate_speech_bytes(text, cloned_voice_id)
        return None