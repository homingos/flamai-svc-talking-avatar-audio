import asyncio
import signal
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import os  # Make sure to import os

from src.utils.resources.logger import logger
from src.utils.config.settings import settings
from .process_manager import ProcessManager, create_process_manager

class ServiceConfig:
    def __init__(self, name: str, enabled: bool = True, initialization_timeout: float = 30.0, config: dict = None):
        self.name = name
        self.enabled = enabled
        self.initialization_timeout = initialization_timeout
        self.config = config or {}

class AIService(ABC):
    def __init__(self, config: ServiceConfig):
        self.config = config
        self.is_initialized = False

    @abstractmethod
    async def initialize(self) -> bool:
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        pass
    
    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        pass

class ServerManager:
    def __init__(self):
        self.services: Dict[str, AIService] = {}
        self.process_manager = create_process_manager()

    def register_service(self, service: AIService):
        self.services[service.config.name] = service

    def get_service(self, name: str) -> Optional[AIService]:
        return self.services.get(name)

    async def initialize(self):
        logger.info("Initializing all registered services...")
        for name, service in self.services.items():
            if service.config.enabled:
                logger.info(f"Initializing service: {name}...")
                success = await service.initialize()
                if not success:
                    logger.error(f"Failed to initialize service: {name}")
                    return False
        return True

    async def shutdown(self):
        logger.info("Shutting down all registered services...")
        for name, service in reversed(list(self.services.items())):
            if service.is_initialized:
                logger.info(f"Shutting down service: {name}...")
                await service.shutdown()

    def setup_signal_handlers(self):
        # Only set signal handlers if not running inside pytest
        if "PYTEST_CURRENT_TEST" in os.environ:
            logger.info("Skipping signal handler setup in test environment.")
            return

        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.handle_shutdown_signal(s)))
        except (NotImplementedError, ValueError):
            logger.warning("Signal handlers are not supported on this platform.")

    async def handle_shutdown_signal(self, sig):
        logger.warning(f"Received shutdown signal: {sig.name}. Shutting down gracefully.")
        await self.shutdown()
        
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        [task.cancel() for task in tasks]
        
        logger.info(f"Cancelling {len(tasks)} outstanding tasks")
        await asyncio.gather(*tasks, return_exceptions=True)
        asyncio.get_running_loop().stop()

def create_server_manager() -> ServerManager:
    return ServerManager()