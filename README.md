# Talking Avatar TTS & Voice Clone Service

![Python](https://img.shields.io/badge/python-v3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-Modern-blue.svg)
![TTS](https://img.shields.io/badge/TTS-MiniMax-purple.svg)
![GCP](https://img.shields.io/badge/GCP-Storage-orange.svg)
![RunPod](https://img.shields.io/badge/RunPod-Serverless-purple.svg)
![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)

A high-performance, production-ready REST API for Text-to-Speech (TTS) and Voice Cloning using MiniMax AI services. Built with FastAPI for asynchronous processing, featuring automated GCP storage integration, comprehensive session tracking, and optimized for both standalone deployment and serverless environments like RunPod.

## ✨ Features

- 🎤 **Advanced Text-to-Speech**: High-quality speech synthesis using MiniMax TTS models
- 🎭 **Voice Cloning**: Create custom voice models from audio samples with intelligent cloning
- ⚡ **Automated Workflows**: Single-endpoint clone-and-generate for streamlined operations
- 🌐 **GCP Storage Integration**: Automatic upload to Google Cloud Storage with structured path organization
- 🚀 **Multiple Deployment Options**: FastAPI server, RunPod serverless, and Docker containers
- 📊 **Session Tracking**: Comprehensive request tracking with unique session IDs
- 🎯 **Production Ready**: Robust error handling, logging, and graceful shutdown mechanisms
- 🔧 **Configurable Architecture**: YAML-based configuration with environment variable overrides
- 🌍 **Serverless Optimized**: RunPod integration for auto-scaling deployment
- 📁 **Intelligent File Management**: Structured bucket paths and automatic cleanup
- 🔍 **Debug & Monitoring**: Built-in health checks, metrics, and GCP debugging endpoints

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/homingos/flamai-svc-talking-avatar-audio.git
cd flamai-svc-talking-avatar-audio

# Install dependencies using uv (recommended)
uv sync --all-groups

# Or using pip
pip install -e ".[dev]"
```

### 2. Environment Configuration

Create a `.env` file with your configuration:

```bash
# MiniMax API Configuration (Required)
MINIMAX_API_KEY="your_minimax_api_key_here"
MINIMAX_GROUP_ID="your_minimax_group_id_here"

# GCP Storage Configuration (Required for cloud uploads)
GCP_BUCKET_NAME="your-bucket-name"
GKE_SA_DEV='{"type": "service_account", "project_id": "your-project", ...}'
GCP_PROJECT_ID="your-gcp-project-id"
BUCKET_PATH="talking-avatar"  # Base path for organized storage
PROJECT_ID="your-project-identifier"  # For request organization

# Optional Configuration
GCP_CREATE_BUCKET=false
GCP_BUCKET_LOCATION="US"
```

### 3. Run the Application

#### Option A: FastAPI Server
```bash
# Start the FastAPI server
python app.py

# The server will start on http://localhost:8000
# Visit http://localhost:8000/docs for interactive API documentation
```

#### Option B: RunPod Serverless
```bash
# Deploy to RunPod using the runpod_app.py handler
# Configure environment variables in RunPod template
# Use the unified handler endpoint structure
```

#### Option C: Docker Deployment
```bash
# Build the Docker image
docker build -t talking-avatar-audio .

# Run the container with environment variables
docker run -p 8000:8000 --env-file .env talking-avatar-audio
```

## 📁 Project Structure

```
flamai-svc-talking-avatar-audio/
├── app.py                     # FastAPI server entry point
├── runpod_app.py             # RunPod serverless handler with unified endpoints
├── pyproject.toml            # Project dependencies and configuration
├── uv.lock                   # Dependency lock file
├── test_input.json           # Sample test data
├── src/
│   ├── api/                  # API layer
│   │   ├── routes.py         # REST API endpoints
│   │   ├── handlers.py       # Request handlers with GCP integration
│   │   ├── models.py         # Pydantic data models
│   │   └── __init__.py
│   ├── core/                 # Core system components
│   │   ├── server_manager.py # Server lifecycle management
│   │   ├── process_manager.py # Process and file management
│   │   ├── managers.py       # Manager utilities
│   │   └── __init__.py
│   ├── services/             # Business logic services
│   │   ├── tts_service.py    # MiniMax TTS service integration
│   │   └── __init__.py
│   └── utils/                # Utilities and configuration
│       ├── config/           # Configuration management
│       │   ├── config.yaml   # Default configuration
│       │   ├── settings.py   # Settings loader with env support
│       │   └── __init__.py
│       ├── resources/        # Resource utilities
│       │   ├── logger.py     # Structured logging
│       │   ├── gcp_bucket_manager.py # GCP storage manager
│       │   ├── file_cleanup.py # Automated file cleanup
│       │   └── __init__.py
│       └── __init__.py
├── runtime/                  # Runtime directories
│   ├── temp/                # Temporary audio files
│   ├── logs/                # Application logs
│   └── outputs/             # Generated outputs
└── tests/                   # Test suite
    ├── test_api.py          # API endpoint tests
    ├── conftest.py          # Test configuration
    └── __init__.py
```

## ⚙️ Configuration

### Main Configuration

The application uses a comprehensive YAML configuration system with environment variable overrides:

```yaml
# src/utils/config/config.yaml
app:
  name: "MiniMax TTS and Voice Cloning API"
  version: "1.0.0"
  description: "Production-ready API for Text-to-Speech and Voice Cloning"
  debug: false
  environment: "production"
  save_local_tests: true  # Save generated audio locally for testing
  local_audio_directory: "runtime/temp"

server:
  host: "0.0.0.0"
  port: 8000
  reload: false
  workers: 1

# GCP Configuration
gcp:
  enabled: true
  bucket_name: "${GCP_BUCKET_NAME}"
  credentials_path: "${GKE_SA_DEV}"
  create_bucket: false
  location: "US"
  project_id: "${GCP_PROJECT_ID}"
  base_path: "talking-avatar"  # Structured path: /<bucket>/<base_path>/<project_id>/<date>/audio/<filename>

# Service Configuration
server_manager:
  services:
    minimax_tts:
      enabled: true
      initialization_timeout: 60.0
      config:
        api_key: "${MINIMAX_API_KEY}"
        group_id: "${MINIMAX_GROUP_ID}"
```

### GCP Storage Structure

Files are automatically organized in a structured hierarchy:

```
bucket-name/
└── talking-avatar/              # Base path (configurable)
    └── project-123/             # Project ID
        └── 2025-09-22/          # Date (YYYY-MM-DD)
            └── audio/           # Content type
                ├── custom_filename.mp3      # Custom filename
                └── generate_speech_1234.mp3 # Auto-generated filename
```

## 🔌 API Endpoints

### Core Endpoints

#### Health Check
```bash
GET /api/v1/health
# Returns: Service health status and component information

# Response:
{
  "session_id": "uuid",
  "status": "healthy",
  "service_name": "MiniMax TTS and Voice Cloning API",
  "version": "1.0.0",
  "services": {
    "minimax_tts": {
      "initialized": true,
      "api_configured": true
    }
  }
}
```

#### Generate Speech
```bash
POST /api/v1/tts/generate
Content-Type: application/json

{
  "text": "Hello world, this is a test of the API.",
  "voice_id": "male-english-2",
  "project_id": "my-project-123",
  "upload_to_gcp": true,
  "filename": "custom_speech.mp3"  // Optional
}

# Response:
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "success",
  "message": "Audio generated successfully",
  "gcp_url": "https://storage.googleapis.com/bucket/talking-avatar/my-project-123/2025-09-22/audio/custom_speech.mp3"
}
```

#### Clone Voice
```bash
POST /api/v1/voice/clone
Content-Type: multipart/form-data

new_voice_id=MyCustomVoice01
audio_file=@/path/to/voice_sample.mp3

# Response:
{
  "session_id": "uuid",
  "success": true,
  "message": "Voice cloned successfully",
  "voice_id": "MyCustomVoice01"
}
```

#### Clone and Generate (Automated Workflow)
```bash
POST /api/v1/voice/clone-and-generate
Content-Type: multipart/form-data

text=This is a new voice, cloned and generated in one step.
new_voice_id=MyWebAppVoice001
project_id=my-project-123
upload_to_gcp=true
filename=cloned_speech.mp3
audio_file=@/path/to/voice_sample.mp3

# Response:
{
  "session_id": "uuid",
  "status": "success",
  "message": "Audio generated successfully",
  "gcp_url": "https://storage.googleapis.com/bucket/talking-avatar/my-project-123/2025-09-22/audio/cloned_speech.mp3"
}
```

#### Debug and Monitoring
```bash
GET /api/v1/debug/gcp
# Returns: Detailed GCP configuration and connection status

# Response includes:
{
  "environment_variables": { ... },
  "gcp_manager_status": { ... },
  "config_settings": { ... },
  "bucket_test": {
    "accessible": true,
    "message": "Bucket is accessible"
  }
}
```

### RunPod Serverless Endpoints

The RunPod handler provides a unified endpoint structure:

```bash
# Unified RunPod Request Format
{
  "input": {
    "endpoint": "generate_speech" | "clone_voice" | "clone_and_generate" | "health_check",
    "data": {
      // Endpoint-specific parameters
      "text": "Hello world",
      "voice_id": "male-english-2",
      "project_id": "my-project-123",
      "upload_to_gcp": true,
      "filename": "custom.mp3"  // Optional
    }
  }
}

# Unified RunPod Response Format
{
  "success": true,
  "data": {
    "session_id": "uuid",
    "gcp_url": "https://storage.googleapis.com/...",
    "audio_size_bytes": 1234567,
    "processing_time": 2.34,
    "message": "Audio generated successfully"
  },
  "error_message": null,
  "processing_time": 2.34,
  "endpoint": "generate_speech"
}
```

Available RunPod endpoints:
- `generate_speech` - Generate speech from text
- `clone_voice` - Clone voice from audio data
- `clone_and_generate` - Complete workflow in one call
- `health_check` - System health status
- `system_info` - Detailed system information
- `metrics` - Processing metrics
- `debug_gcp` - GCP debugging information
- `test_gcp_upload` - Test GCP upload functionality

## 🛠️ Advanced Usage

### Custom Filename Support

The system supports both automatic and custom filename generation:

```python
# Auto-generated filename (timestamp-based)
{
  "text": "Hello world",
  "voice_id": "male-english-2",
  "project_id": "my-project-123",
  "upload_to_gcp": true
  # filename not specified - generates: generate_speech_1234567890.mp3
}

# Custom filename
{
  "text": "Hello world",
  "voice_id": "male-english-2", 
  "project_id": "my-project-123",
  "upload_to_gcp": true,
  "filename": "welcome_message.mp3"  # Custom filename
}
```

### Session Tracking

Every request receives a unique session ID for tracking:

```python
# All responses include session tracking
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "success",
  // ... other response data
}

# Use session IDs for:
# - Request correlation in logs
# - Debugging specific requests  
# - Performance monitoring
# - Error tracking
```

### GCP Integration Features

```python
# Structured path generation
# Format: <base_path>/<project_id>/<date>/audio/<filename>
# Example: talking-avatar/my-project-123/2025-09-22/audio/speech.mp3

# Public URL generation
gcp_url = "https://storage.googleapis.com/bucket/talking-avatar/my-project-123/2025-09-22/audio/speech.mp3"

# Automatic cleanup after successful upload
# Local temp files are cleaned up after GCP upload
```

### Batch Processing with RunPod

```python
import requests

# Process multiple requests
requests_batch = [
    {
        "input": {
            "endpoint": "generate_speech",
            "data": {
                "text": "First message",
                "voice_id": "voice-1",
                "project_id": "project-1",
                "filename": "message_1.mp3"
            }
        }
    },
    {
        "input": {
            "endpoint": "clone_and_generate", 
            "data": {
                "text": "Second message",
                "new_voice_id": "CustomVoice001",
                "audio_base64": "base64_encoded_audio_data",
                "project_id": "project-1",
                "filename": "message_2.mp3"
            }
        }
    }
]

# Process each request
for request_data in requests_batch:
    response = requests.post(runpod_endpoint, json=request_data)
    result = response.json()
    print(f"Session: {result['data']['session_id']}, URL: {result['data']['gcp_url']}")
```

### Performance Optimization

```python
# Configuration for optimal performance
performance_config = {
    "save_local_tests": False,      # Disable local saving in production
    "upload_to_gcp": True,          # Enable cloud storage
    "workers": 4,                   # Increase workers for FastAPI
    "timeout": 120,                 # Adjust timeout for large files
}

# RunPod optimization
runpod_config = {
    "container_disk_in_gb": 20,     # Sufficient storage for temp files
    "memory_in_gb": 8,              # Memory for audio processing
    "cpu_count": 4,                 # CPU cores for parallel processing
}
```

## 📊 Monitoring & Metrics

### Built-in Health Checks

```bash
# Basic health check (optimized for speed)
curl http://localhost:8000/api/v1/health

# GCP configuration debugging
curl http://localhost:8000/api/v1/debug/gcp

# For RunPod environments
{
  "input": {
    "endpoint": "health_check",
    "data": {}
  }
}
```

### Session Tracking and Logging

The system provides comprehensive logging with session correlation:

```python
# Log format includes session IDs
# 2025-09-22 10:30:15 - Session abc123: Processing speech generation request
# 2025-09-22 10:30:16 - Session abc123: Audio saved to temp directory
# 2025-09-22 10:30:17 - Session abc123: Successfully uploaded to GCP
# 2025-09-22 10:30:18 - Session abc123: Speech generation completed in 3.2s
```

### Performance Metrics

```python
# Available metrics through RunPod endpoints
{
  "input": {
    "endpoint": "metrics",
    "data": {}
  }
}

# Response includes:
{
  "total_requests": 1234,
  "successful_requests": 1200,
  "failed_requests": 34,
  "success_rate": 0.972,
  "uptime": 86400,
  "average_processing_time": 2.3
}
```

## 🌍 Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `MINIMAX_API_KEY` | MiniMax API authentication key | - | **Yes** |
| `MINIMAX_GROUP_ID` | MiniMax group/organization ID | - | **Yes** |
| `GCP_BUCKET_NAME` | Google Cloud Storage bucket name | - | **Yes** (for GCP) |
| `GKE_SA_DEV` | GCP service account JSON (as string) | - | **Yes** (for GCP) |
| `GCP_PROJECT_ID` | Google Cloud Project ID | - | **Yes** (for GCP) |
| `PROJECT_ID` | Application project identifier | - | **Yes** |
| `BUCKET_PATH` | Base path for GCP storage organization | "talking-avatar" | No |
| `GCP_CREATE_BUCKET` | Auto-create bucket if missing | false | No |
| `GCP_BUCKET_LOCATION` | GCP bucket location/region | "US" | No |
| `APP_DEBUG` | Enable debug logging | false | No |
| `SERVER_HOST` | Server host address | 0.0.0.0 | No |
| `SERVER_PORT` | Server port | 8000 | No |

### GCP Service Account Setup

The `GKE_SA_DEV` environment variable should contain a complete GCP service account JSON:

```json
{
  "type": "service_account",
  "project_id": "your-project-id",
  "private_key_id": "key-id",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "service-account@your-project.iam.gserviceaccount.com",
  "client_id": "client-id",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/service-account%40your-project.iam.gserviceaccount.com"
}
```

## 🚀 Production Deployment

### Performance Considerations

1. **Hardware Requirements**:
   - **CPU**: 2+ cores for concurrent request handling
   - **RAM**: 4GB+ for audio processing and caching
   - **Storage**: SSD recommended for temporary file operations
   - **Network**: Stable internet for MiniMax API and GCP uploads

2. **Scaling Options**:
   - **FastAPI**: Use multiple workers with `uvicorn --workers 4`
   - **RunPod**: Auto-scaling serverless deployment
   - **Docker**: Container orchestration with Kubernetes
   - **Load Balancing**: Multiple instances behind load balancer

3. **GCP Optimization**:
   - Use regional buckets for better performance
   - Configure bucket lifecycle policies for cost optimization
   - Enable CDN for frequently accessed audio files
   - Use structured paths for efficient organization

### Security Considerations

```bash
# Production environment variables
export APP_DEBUG=false
export LOG_LEVEL=WARNING
export CORS_ALLOW_ORIGINS='["https://yourdomain.com"]'

# Secure credential handling
# Use secret management systems for sensitive data
# Rotate API keys regularly
# Implement proper IAM roles for GCP access
```

### Monitoring Setup

```bash
# Health check monitoring
curl -f http://localhost:8000/api/v1/health || exit 1

# Log monitoring for session tracking
tail -f runtime/logs/app.log | grep "Session"

# GCP upload monitoring
curl http://localhost:8000/api/v1/debug/gcp | jq '.bucket_test.accessible'
```

## 🐛 Troubleshooting

### Common Issues

1. **MiniMax API Issues**:
   ```bash
   # Check API credentials
   echo $MINIMAX_API_KEY
   echo $MINIMAX_GROUP_ID
   
   # Test API connectivity
   curl -H "Authorization: Bearer $MINIMAX_API_KEY" \
        "https://api.minimax.io/v1/files?GroupId=$MINIMAX_GROUP_ID"
   ```

2. **GCP Storage Issues**:
   ```bash
   # Debug GCP configuration
   curl http://localhost:8000/api/v1/debug/gcp
   
   # Check service account JSON
   echo $GKE_SA_DEV | jq .
   
   # Verify bucket access
   gsutil ls gs://$GCP_BUCKET_NAME
   ```

3. **Audio Processing Issues**:
   ```bash
   # Check local file generation
   ls -la runtime/temp/
   
   # Monitor session logs
   grep "Session.*Processing" runtime/logs/app.log
   
   # Verify file cleanup
   grep "cleanup" runtime/logs/app.log
   ```

4. **RunPod Deployment Issues**:
   ```bash
   # Check environment variables in RunPod
   {
     "input": {
       "endpoint": "debug_gcp",
       "data": {}
     }
   }
   
   # Test upload functionality
   {
     "input": {
       "endpoint": "test_gcp_upload", 
       "data": {}
     }
   }
   ```

### Debug Mode

```bash
# Enable detailed logging
export APP_DEBUG=true
export LOG_LEVEL=DEBUG

# Run with verbose output
python app.py

# Monitor all requests
tail -f runtime/logs/app.log | grep -E "(Session|ERROR|WARNING)"
```

### Performance Debugging

```bash
# Monitor processing times
grep "processing_time" runtime/logs/app.log

# Check GCP upload performance  
grep "GCP upload" runtime/logs/app.log

# Monitor memory usage
ps aux | grep python
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes following the existing patterns
4. Add tests for new functionality
5. Ensure all tests pass: `python -m pytest tests/`
6. Update documentation as needed
7. Commit your changes (`git commit -m 'Add amazing feature'`)
8. Push to the branch (`git push origin feature/amazing-feature`)
9. Open a Pull Request

### Development Setup

```bash
# Install development dependencies
uv sync --all-groups

# Run tests
python -m pytest tests/ -v

# Format code
black src/
isort src/

# Type checking
mypy src/

# Run local server with hot reload
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### Testing

```bash
# Run all tests
python -m pytest tests/

# Test specific functionality
python -m pytest tests/test_api.py::test_generate_speech

# Test with coverage
python -m pytest --cov=src tests/

# Integration testing with actual APIs (requires valid credentials)
python -m pytest tests/ --integration
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/) for high-performance async web APIs
- Powered by [MiniMax AI](https://www.minimax.io/platform_overview) for advanced TTS and voice cloning
- Google Cloud Storage integration for reliable file storage and delivery
- [RunPod](https://runpod.io/) serverless platform for scalable deployment
- [Pydantic](https://pydantic.dev/) for robust data validation and settings management
- [Uvicorn](https://www.uvicorn.org/) ASGI server for production deployment

---

**Ready to get started?** Follow the [Quick Start](#-quick-start) guide and have your TTS service running in minutes! 🚀
