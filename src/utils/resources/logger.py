# /src/utils/resources/logger.py

import logging
import sys
from pathlib import Path
from typing import Optional
from src.utils.config.settings import settings  # <--- FIXED

class Logger:
    _logger: Optional[logging.Logger] = None

    @staticmethod
    def get_logger() -> logging.Logger:
        if Logger._logger is None:
            log_config = settings.get_logging_config()
            app_name = settings.get("app.name", "app")
            
            logger = logging.getLogger(app_name)
            logger.setLevel(log_config.get("level", "INFO").upper())
            logger.handlers.clear()

            formatter = logging.Formatter(log_config.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

            Logger._logger = logger
        return Logger._logger

logger = Logger.get_logger()