from typing import Optional
from fastapi import Request, HTTPException
from .server_manager import ServerManager
from .process_manager import ProcessManager

def get_server_manager(request: Request) -> ServerManager:
    server_manager = getattr(request.app.state, 'server_manager', None)
    if server_manager is None:
        raise HTTPException(status_code=503, detail="Server manager not available")
    return server_manager

def get_process_manager(request: Request) -> ProcessManager:
    process_manager = getattr(request.app.state, 'process_manager', None)
    if process_manager is None:
        raise HTTPException(status_code=503, detail="Process manager not available")
    return process_manager