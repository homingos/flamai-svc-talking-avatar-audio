# /app.py

import os
import uvicorn
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

# Load environment variables from .env file at the earliest moment.
load_dotenv()

from src.api.routes import router as api_router
from src.core.process_manager import ProcessManager, create_process_manager
from src.core.server_manager import AIService, ServerManager, ServiceConfig, create_server_manager
from src.services.tts_service import MinimaxTtsService
from src.utils.config.settings import settings
from src.utils.resources.logger import logger

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

        await register_services(server_manager)
        
        server_manager.setup_signal_handlers()
        if not await server_manager.initialize():
            raise RuntimeError("Server manager initialization failed.")
        
        logger.info(f"{settings.get('app.name')} started successfully. All services are ready.")

    except Exception as e:
        logger.error(f"Error during application startup: {e}", exc_info=True)
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
    return RedirectResponse(url="/docs")

@app.get("/status", tags=["Health"])
async def get_status():
    return {"status": "ok", "service": settings.get("app.name")}

if __name__ == "__main__":
    server_config = settings.get_server_config()
    uvicorn.run(
        "app:app",
        host=server_config.get("host", "0.0.0.0"),
        port=server_config.get("port", 8000),
        reload=server_config.get("reload", False),
        workers=server_config.get("workers", 1),
    )