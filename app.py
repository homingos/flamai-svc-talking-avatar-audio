# /app.py

import os
import json
import uvicorn
from typing import Optional
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

# Load environment variables from .env file at the earliest moment.
load_dotenv()

from src.api.routes import router as api_router, get_dynamic_endpoints
from src.core.process_manager import ProcessManager, create_process_manager
from src.core.server_manager import AIService, ServerManager, ServiceConfig, create_server_manager
from src.services.tts_service import MinimaxTtsService
from src.utils.config.settings import settings
from src.utils.resources.logger import logger
from src.utils.resources.gcp_bucket_manager import GCSBucketManager

# --- Service Class Mapping ---
# Maps service names from config.yaml to their Python class implementations.
# This makes the service registration process dynamic and extensible.
SERVICE_CLASSES: dict[str, type[AIService]] = {
    "minimax_tts": MinimaxTtsService,
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the application's lifespan events for startup and shutdown.
    """
    logger.info(f"Starting {settings.get('app.name', 'TTS API Service')}")
    try:
        # Initialize managers and attach to app state
        process_manager = create_process_manager()
        server_manager = create_server_manager()
        app.state.process_manager = process_manager
        app.state.server_manager = server_manager

        # Initialize GCP Bucket Manager with enhanced credential handling
        bucket_name = os.getenv('GCP_BUCKET_NAME')
        if bucket_name:
            try:
                # Get credentials using the GCSBucketManager static method
                credentials_path, project_id = GCSBucketManager.get_gcp_credentials()
                
                logger.info("Initializing GCP Bucket Manager...")
                logger.info(f"  - Bucket: {bucket_name}")
                logger.info(f"  - Credentials: {'Environment JSON' if not credentials_path else credentials_path}")
                logger.info(f"  - Project ID: {project_id}")
                
                gcp_bucket_manager = GCSBucketManager(
                    bucket_name=bucket_name,
                    credentials_path=credentials_path,  # Will be None if using env JSON
                    create_bucket=os.getenv('GCP_CREATE_BUCKET', 'false').lower() == 'true',
                    location=os.getenv('GCP_BUCKET_LOCATION', 'US'),
                    project_id=project_id
                )
                app.state.gcp_bucket_manager = gcp_bucket_manager
                logger.info(f"✅ GCP Bucket Manager initialized successfully for bucket: {bucket_name}")
                
            except Exception as e:
                logger.error(f"❌ Failed to initialize GCP Bucket Manager: {e}")
                logger.error("This might be due to missing or invalid GCP credentials")
                logger.info("GCP upload functionality will be disabled")
                app.state.gcp_bucket_manager = None
        else:
            logger.warning("📦 GCP_BUCKET_NAME not set. GCP upload functionality will be disabled.")
            app.state.gcp_bucket_manager = None

        await register_services(server_manager)
        
        server_manager.setup_signal_handlers()
        if not await server_manager.initialize():
            raise RuntimeError("Server manager initialization failed.")
        
        logger.info(f"✅ {settings.get('app.name')} started successfully. All services are ready.")

    except Exception as e:
        logger.error(f"❌ Error during application startup: {e}", exc_info=True)
        raise

    yield

    logger.info(f"Shutting down {settings.get('app.name')}")
    try:
        if app.state.server_manager:
            await app.state.server_manager.shutdown()
            logger.info("Server manager shutdown complete.")
    except Exception as e:
        logger.error(f"Error during application shutdown: {e}", exc_info=True)


async def register_services(manager: ServerManager):
    """
    Dynamically registers all services defined in the configuration file.
    """
    services_to_register = settings.get("server_manager.services", {})
    
    for name, service_data in services_to_register.items():
        if not service_data.get("enabled", False):
            logger.warning(f"Service '{name}' is disabled in the configuration. Skipping.")
            continue

        if name not in SERVICE_CLASSES:
            logger.error(f"Service '{name}' has no corresponding class in SERVICE_CLASSES mapping. Skipping.")
            continue

        try:
            service_class = SERVICE_CLASSES[name]
            
            # The settings manager now handles environment variable substitution
            service_config_obj = ServiceConfig(
                name=name,
                config=service_data.get("config", {})
            )
            
            service_instance = service_class(service_config_obj)
            manager.register_service(service_instance)
            logger.info(f"Service '{name}' registered successfully.")

        except Exception as e:
            logger.error(f"Failed to register service '{name}': {e}", exc_info=True)
            raise


app = FastAPI(
    title=settings.get("app.name", "TTS API Service"),
    description=settings.get("app.description"),
    version=settings.get("app.version", "1.0.0"),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
if settings.get("cors.enabled", False):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get("cors.allow_origins", ["*"]),
        allow_credentials=settings.get("cors.allow_credentials", True),
        allow_methods=settings.get("cors.allow_methods", ["*"]),
        allow_headers=settings.get("cors.allow_headers", ["*"]),
    )

app.include_router(api_router)

@app.get("/", include_in_schema=False)
async def root():
    api_prefix = settings.get_api_prefix()
    return {
        "service": settings.get("app.name", "TTS API Service"),
        "version": settings.get("app.version", "1.0.0"),
        "description": settings.get("app.description", "FastAPI service for TTS and Voice Cloning"),
        "docs": "/docs",
        "health": f"{api_prefix}/health",
        "status": "/status",
        "endpoints": get_dynamic_endpoints()
    }

@app.get("/status", tags=["Health"])
async def get_status():
    return {"status": "ok", "service": settings.get("app.name")}

def main():
    """
    Creates and configures a uvicorn server instance.
    Returns the configured server instance.
    """
    server_config = settings.get_server_config()
    
    config = uvicorn.Config(
        "app:app",
        host=server_config.get("host", "0.0.0.0"),
        port=server_config.get("port", 8000),
        reload=server_config.get("reload", False),
        workers=server_config.get("workers", 1),
        log_level=server_config.get("log_level", "info"),
    )

    server = uvicorn.Server(config)
    server.run()

if __name__ == "__main__":
    main()