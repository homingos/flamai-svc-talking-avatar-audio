# /src/api/models.py

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

# --- Response Schemas ---

class VoiceCloneResponse(BaseModel):
    success: bool
    message: str
    voice_id: Optional[str] = None

class HealthCheckResponse(BaseModel):
    status: HealthStatus
    service_name: str
    version: str
    services: Dict[str, Any]

class ErrorDetail(BaseModel):
    detail: str