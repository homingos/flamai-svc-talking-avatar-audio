# /src/api/models.py

import uuid
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum

class HealthStatus(str, Enum):
    """Enum for health check status."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"

# --- Request Schemas ---

class GenerateSpeechRequest(BaseModel):
    text: str = Field(
        ..., 
        min_length=1, 
        description="The text to synthesize.", 
        json_schema_extra={'example': "Hello, this is a test of the API."}
    )
    voice_id: str = Field(
        ..., 
        min_length=1, 
        description="The ID of the voice to use.", 
        json_schema_extra={'example': "male-english-2"}
    )
    project_id: str = Field(
        ...,
        min_length=1,
        description="The project ID for tracking and organization.",
        json_schema_extra={'example': "my-project-123"}
    )
    upload_to_gcp: bool = Field(
        default=False,
        description="Whether to upload the generated audio to GCP bucket",
        json_schema_extra={'example': False}
    )
    filename: Optional[str] = Field(
        default=None,
        description="Optional custom filename for the uploaded file (e.g., 'my_audio.mp3'). If not provided, a timestamp-based filename will be generated.",
        json_schema_extra={'example': "custom_speech.mp3"}
    )

# --- Response Schemas ---

class BaseResponse(BaseModel):
    """Base response model with common fields."""
    session_id: str = Field(
        ...,
        description="Unique session ID for tracking this request",
        json_schema_extra={'example': "550e8400-e29b-41d4-a716-446655440000"}
    )

class GenerateSpeechResponse(BaseResponse):
    status: str = Field(..., description="Status of the operation")
    message: str = Field(..., description="Human-readable message about the operation")
    gcp_url: Optional[str] = Field(
        default=None,
        description="Public URL of the uploaded audio file in GCP bucket",
        json_schema_extra={'example': "https://storage.googleapis.com/my-bucket/audio/generate_speech_1234567890.mp3"}
    )

class VoiceCloneResponse(BaseResponse):
    success: bool
    message: str
    voice_id: Optional[str] = None
    gcp_url: Optional[str] = None

class CloneAndGenerateResponse(BaseResponse):
    status: str = Field(..., description="Status of the operation")
    message: str = Field(..., description="Human-readable message about the operation")
    gcp_url: Optional[str] = Field(
        default=None,
        description="Public URL of the uploaded audio file in GCP bucket",
        json_schema_extra={'example': "https://storage.googleapis.com/my-bucket/audio/clone_and_generate_1234567890.mp3"}
    )

class HealthCheckResponse(BaseResponse):
    status: HealthStatus
    service_name: str
    version: str
    services: Dict[str, Any]

class ErrorDetail(BaseModel):
    detail: str
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID if available"
    )