import os
import time
from pathlib import Path
from typing import Optional
from src.utils.resources.logger import logger


def cleanup_file_immediate(file_path: str) -> bool:
    """
    Immediately clean up a file.
    
    Args:
        file_path: Path to the file to delete
        
    Returns:
        bool: True if cleanup was successful
    """
    try:
        if not os.path.exists(file_path):
            logger.info(f"File already deleted or does not exist: {file_path}")
            return True
        
        # Delete the file
        os.unlink(file_path)
        logger.info(f"Successfully deleted file: {file_path}")
        return True
        
    except PermissionError:
        logger.warning(f"Permission denied deleting file: {file_path}")
        return False
    except FileNotFoundError:
        logger.info(f"File not found during cleanup: {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete file {file_path}: {e}")
        return False


def cleanup_after_gcp_upload(file_path: str, delay_seconds: float = 2.0) -> bool:
    """
    Clean up file after GCP upload with a simple delay approach suitable for serverless environments.
    
    Args:
        file_path: Path to the file to delete
        delay_seconds: Delay before deletion (default: 2.0 seconds)
        
    Returns:
        bool: True if cleanup was scheduled successfully
    """
    try:
        # Validate file path
        if not file_path or not isinstance(file_path, str):
            logger.warning(f"Invalid file path for cleanup: {file_path}")
            return False
        
        # Check if file exists
        if not os.path.exists(file_path):
            logger.warning(f"File does not exist for cleanup: {file_path}")
            return False
        
        # For serverless environments, use a simple delayed cleanup
        # We'll use asyncio.sleep if available, otherwise just immediate cleanup
        try:
            import asyncio
            
            async def delayed_cleanup():
                await asyncio.sleep(delay_seconds)
                cleanup_file_immediate(file_path)
            
            # Schedule the cleanup task
            asyncio.create_task(delayed_cleanup())
            logger.info(f"Scheduled async cleanup for file: {file_path} (delay: {delay_seconds}s)")
            return True
            
        except ImportError:
            # Fallback to immediate cleanup if asyncio is not available
            logger.info(f"Asyncio not available, performing immediate cleanup for: {file_path}")
            return cleanup_file_immediate(file_path)
            
    except Exception as e:
        logger.error(f"Failed to schedule cleanup for {file_path}: {e}")
        return False


def cleanup_temp_directory(temp_dir: str, pattern: str = "*.mp3", 
                         max_age_hours: float = 24.0) -> int:
    """
    Clean up old files from a temporary directory.
    
    Args:
        temp_dir: Directory to clean up
        pattern: File pattern to match (default: "*.mp3")
        max_age_hours: Maximum age of files in hours (default: 24.0)
        
    Returns:
        int: Number of files deleted
    """
    try:
        if not os.path.exists(temp_dir):
            logger.info(f"Temp directory does not exist: {temp_dir}")
            return 0
        
        deleted_count = 0
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        # Find files matching the pattern
        temp_path = Path(temp_dir)
        for file_path in temp_path.glob(pattern):
            try:
                # Check file age
                file_age = current_time - file_path.stat().st_mtime
                
                if file_age > max_age_seconds:
                    file_path.unlink()
                    deleted_count += 1
                    logger.info(f"Cleaned up old file: {file_path} (age: {file_age/3600:.1f}h)")
                    
            except Exception as e:
                logger.error(f"Failed to clean up file {file_path}: {e}")
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old files from {temp_dir}")
        
        return deleted_count
        
    except Exception as e:
        logger.error(f"Failed to clean up temp directory {temp_dir}: {e}")
        return 0
