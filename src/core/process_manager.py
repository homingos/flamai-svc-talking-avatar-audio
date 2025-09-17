# /src/core/process_manager.py

import os
import shutil
import uuid
import time
from pathlib import Path
from typing import Optional, Dict

from src.utils.resources.logger import logger    
from src.utils.config.settings import settings    

class ProcessManager:
    def __init__(self):
        self.config = settings.get("process_manager", {})
        self.temp_dir = Path(settings.get("server_manager.directories.temp", "runtime/temp"))
        self.processes: Dict[str, Dict] = {}
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def create_process(self, process_type: str, metadata: dict) -> str:
        process_id = str(uuid.uuid4())
        self.processes[process_id] = { "id": process_id, "type": process_type, "metadata": metadata, "created_at": time.time(), "files": [] }
        logger.info(f"Created process {process_id} of type {process_type}")
        return process_id

    def add_file_to_process(self, process_id: str, file_path: Path) -> None:
        if process_id in self.processes:
            self.processes[process_id]['files'].append(str(file_path))

    def cleanup_process(self, process_id: str) -> None:
        if process_id in self.processes:
            process = self.processes.pop(process_id)
            for file_path_str in process.get("files", []):
                file_path = Path(file_path_str)
                if file_path.exists():
                    try:
                        file_path.unlink()
                        logger.info(f"Cleaned up temporary file: {file_path}")
                    except OSError as e:
                        logger.error(f"Error removing file {file_path}: {e}")
            logger.info(f"Cleaned up process {process_id}")

def create_process_manager() -> ProcessManager:
    return ProcessManager()