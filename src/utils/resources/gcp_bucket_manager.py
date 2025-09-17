import os
import json
from typing import Optional, Union, List, BinaryIO
from pathlib import Path
from google.cloud import storage
from google.cloud.exceptions import NotFound, Forbidden, Conflict
from google.oauth2 import service_account
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GCSBucketManager:
    """
    A comprehensive Google Cloud Storage bucket manager that supports both
    authenticated and unauthenticated access to GCS buckets.
    """
    
    def __init__(self, bucket_name: str, credentials_path: Optional[str] = None, 
                 create_bucket: bool = False, location: str = "US", 
                 project_id: Optional[str] = None):
        """
        Initialize the GCS Bucket Manager.
        
        Args:
            bucket_name (str): Name of the GCS bucket
            credentials_path (str, optional): Path to the credentials.json file.
                If None, will check GOOGLE_APPLICATION_CREDENTIALS environment variable,
                then attempt to use default credentials or anonymous access.
            create_bucket (bool): Whether to create the bucket if it doesn't exist.
                Requires authenticated access. Default: False
            location (str): Location for bucket creation (e.g., "US", "EU", "us-central1").
                Default: "US"
            project_id (str, optional): GCP project ID for bucket creation.
                If None, will try to extract from credentials or use default project.
        """
        self.bucket_name = bucket_name
        self.create_bucket = create_bucket
        self.location = location
        self.project_id = project_id
        
        # Priority order: explicit parameter > environment variable > None
        if credentials_path:
            self.credentials_path = credentials_path
        else:
            self.credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        
        self.client = None
        self.bucket = None
        
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the GCS client with appropriate authentication."""
        try:
            if self.credentials_path and os.path.exists(self.credentials_path):
                # Use service account credentials
                logger.info(f"Using service account credentials from {self.credentials_path}")
                credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_path
                )
                self.client = storage.Client(credentials=credentials)
                
                # Extract project_id from credentials if not provided
                if not self.project_id:
                    try:
                        with open(self.credentials_path, 'r') as f:
                            cred_data = json.load(f)
                            self.project_id = cred_data.get('project_id')
                    except Exception as e:
                        logger.warning(f"Could not extract project_id from credentials: {e}")
                        
            elif self.credentials_path:
                # Credentials path was provided but file doesn't exist
                logger.warning(f"Credentials file not found at {self.credentials_path}, falling back to default authentication")
                try:
                    # Try default credentials first (env variables, gcloud auth, etc.)
                    self.client = storage.Client()
                    logger.info("Using default credentials")
                except Exception as e:
                    logger.warning(f"Default credentials failed: {e}")
                    if self.create_bucket:
                        raise ValueError("Cannot create bucket without proper authentication")
                    # Fallback to anonymous client for public buckets
                    self.client = storage.Client.create_anonymous_client()
                    logger.info("Using anonymous client for public bucket access")
            else:
                # No credentials path provided
                logger.info("No credentials path provided, attempting to use default credentials or anonymous access")
                try:
                    # Try default credentials first (env variables, gcloud auth, etc.)
                    self.client = storage.Client()
                    logger.info("Using default credentials")
                except Exception as e:
                    logger.warning(f"Default credentials failed: {e}")
                    if self.create_bucket:
                        raise ValueError("Cannot create bucket without proper authentication")
                    # Fallback to anonymous client for public buckets
                    self.client = storage.Client.create_anonymous_client()
                    logger.info("Using anonymous client for public bucket access")
            
            # Get or create bucket reference
            self.bucket = self._get_or_create_bucket()
            
        except Exception as e:
            logger.error(f"Failed to initialize GCS client: {e}")
            raise
    
    def _get_or_create_bucket(self):
        """Get bucket reference, creating it if necessary and requested."""
        try:
            # Try to get existing bucket
            bucket = self.client.bucket(self.bucket_name)
            bucket.reload()  # This will raise NotFound if bucket doesn't exist
            logger.info(f"Using existing bucket: {self.bucket_name}")
            return bucket
            
        except NotFound:
            if self.create_bucket:
                logger.info(f"Bucket '{self.bucket_name}' not found. Creating new bucket...")
                return self._create_bucket()
            else:
                logger.error(f"Bucket '{self.bucket_name}' not found and create_bucket=False")
                raise
        except Exception as e:
            logger.error(f"Error accessing bucket '{self.bucket_name}': {e}")
            raise
    
    def _create_bucket(self):
        """Create a new GCS bucket."""
        try:
            if not self.project_id:
                # Try to get project from client
                try:
                    self.project_id = self.client.project
                except:
                    pass
                
            if not self.project_id:
                raise ValueError("project_id is required for bucket creation. Please provide it explicitly or ensure it's available in your credentials.")
            
            # Create bucket with specified location
            bucket = self.client.bucket(self.bucket_name)
            bucket = self.client.create_bucket(bucket, project=self.project_id, location=self.location)
            
            logger.info(f"Successfully created bucket '{self.bucket_name}' in location '{self.location}'")
            return bucket
            
        except Conflict:
            # Bucket already exists (race condition or global namespace conflict)
            logger.warning(f"Bucket '{self.bucket_name}' already exists. Using existing bucket.")
            bucket = self.client.bucket(self.bucket_name)
            bucket.reload()
            return bucket
        except Exception as e:
            logger.error(f"Failed to create bucket '{self.bucket_name}': {e}")
            raise
    
    def create_bucket_if_not_exists(self, location: Optional[str] = None, 
                                   project_id: Optional[str] = None) -> bool:
        """
        Explicitly create bucket if it doesn't exist.
        
        Args:
            location (str, optional): Location for bucket creation. Uses instance default if None.
            project_id (str, optional): GCP project ID. Uses instance default if None.
        
        Returns:
            bool: True if bucket was created or already exists, False if creation failed
        """
        try:
            # Use provided parameters or fall back to instance defaults
            create_location = location or self.location
            create_project_id = project_id or self.project_id
            
            # Check if bucket already exists
            try:
                test_bucket = self.client.bucket(self.bucket_name)
                test_bucket.reload()
                logger.info(f"Bucket '{self.bucket_name}' already exists")
                return True
            except NotFound:
                pass  # Bucket doesn't exist, proceed with creation
            
            # Create the bucket
            if not create_project_id:
                try:
                    create_project_id = self.client.project
                except:
                    pass
                    
            if not create_project_id:
                logger.error("project_id is required for bucket creation")
                return False
            
            bucket = self.client.bucket(self.bucket_name)
            bucket = self.client.create_bucket(bucket, project=create_project_id, location=create_location)
            
            # Update instance bucket reference
            self.bucket = bucket
            
            logger.info(f"Successfully created bucket '{self.bucket_name}' in location '{create_location}'")
            return True
            
        except Conflict:
            logger.info(f"Bucket '{self.bucket_name}' already exists (created by another process)")
            return True
        except Exception as e:
            logger.error(f"Failed to create bucket '{self.bucket_name}': {e}")
            return False
    
    def upload_file(self, local_file_path: str, bucket_path: Optional[str] = None) -> bool:
        """
        Upload a file to the bucket with support for directory paths.
        
        Args:
            local_file_path (str): Path to the local file to upload
            bucket_path (str, optional): Directory path in the bucket where the file should be stored.
                Can be a directory path (e.g., "audio/files/") or full blob name (e.g., "audio/files/myfile.mp3").
                If None, uploads to root with original filename.
                If ends with '/', treats as directory and appends filename.
        
        Returns:
            bool: True if upload successful, False otherwise
        """
        try:
            if not os.path.exists(local_file_path):
                logger.error(f"Local file not found: {local_file_path}")
                return False
            
            filename = os.path.basename(local_file_path)
            
            if bucket_path is None:
                # Upload to root with original filename
                blob_name = filename
            elif bucket_path.endswith('/'):
                # Treat as directory path, append filename
                blob_name = f"{bucket_path.rstrip('/')}/{filename}"
            else:
                # Treat as full blob name
                blob_name = bucket_path
            
            # Normalize path separators for consistency
            blob_name = blob_name.replace('\\', '/')
            
            blob = self.bucket.blob(blob_name)
            
            logger.info(f"Uploading {local_file_path} to {blob_name}")
            blob.upload_from_filename(local_file_path)
            logger.info(f"Successfully uploaded {blob_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upload file: {e}")
            return False
    
    def upload_data(self, data: Union[str, bytes], bucket_path: str) -> bool:
        """
        Upload raw data to the bucket with support for directory paths.
        
        Args:
            data (Union[str, bytes]): Data to upload
            bucket_path (str): Full path in the bucket where the data should be stored
                (e.g., "audio/files/data.txt")
        
        Returns:
            bool: True if upload successful, False otherwise
        """
        try:
            # Normalize path separators for consistency
            blob_name = bucket_path.replace('\\', '/')
            
            blob = self.bucket.blob(blob_name)
            
            logger.info(f"Uploading data to {blob_name}")
            if isinstance(data, str):
                blob.upload_from_string(data)
            else:
                blob.upload_from_string(data)
            
            logger.info(f"Successfully uploaded data to {blob_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upload data: {e}")
            return False
    
    def download_file(self, bucket_path: str, local_file_path: str) -> bool:
        """
        Download a file from the bucket with support for directory paths.
        
        Args:
            bucket_path (str): Path of the blob in the bucket (e.g., "audio/files/myfile.mp3")
            local_file_path (str): Local path where the file should be saved
        
        Returns:
            bool: True if download successful, False otherwise
        """
        try:
            if not bucket_path or not local_file_path:
                logger.error("Both bucket_path and local_file_path must be provided")
                return False
            
            # Normalize path separators for consistency
            blob_name = bucket_path.replace('\\', '/')
            
            blob = self.bucket.blob(blob_name)
            
            # Create directory if it doesn't exist and local_file_path has a directory component
            local_dir = os.path.dirname(local_file_path)
            if local_dir:  # Only create directory if there is a directory component
                os.makedirs(local_dir, exist_ok=True)
            
            logger.info(f"Downloading {blob_name} to {local_file_path}")
            blob.download_to_filename(local_file_path)
            logger.info(f"Successfully downloaded {blob_name}")
            return True
            
        except NotFound:
            logger.error(f"Blob '{blob_name}' not found in bucket")
            return False
        except Exception as e:
            logger.error(f"Failed to download file: {e}")
            return False
    
    def download_as_bytes(self, bucket_path: str) -> Optional[bytes]:
        """
        Download a blob as bytes with support for directory paths.
        
        Args:
            bucket_path (str): Path of the blob in the bucket (e.g., "audio/files/myfile.mp3")
        
        Returns:
            Optional[bytes]: Blob content as bytes, None if failed
        """
        try:
            # Normalize path separators for consistency
            blob_name = bucket_path.replace('\\', '/')
            
            blob = self.bucket.blob(blob_name)
            logger.info(f"Downloading {blob_name} as bytes")
            return blob.download_as_bytes()
            
        except NotFound:
            logger.error(f"Blob '{blob_name}' not found in bucket")
            return None
        except Exception as e:
            logger.error(f"Failed to download blob as bytes: {e}")
            return None
    
    def download_as_text(self, bucket_path: str, encoding: str = 'utf-8') -> Optional[str]:
        """
        Download a blob as text with support for directory paths.
        
        Args:
            bucket_path (str): Path of the blob in the bucket (e.g., "audio/files/myfile.txt")
            encoding (str): Text encoding (default: utf-8)
        
        Returns:
            Optional[str]: Blob content as string, None if failed
        """
        try:
            # Normalize path separators for consistency
            blob_name = bucket_path.replace('\\', '/')
            
            blob = self.bucket.blob(blob_name)
            logger.info(f"Downloading {blob_name} as text")
            return blob.download_as_text(encoding=encoding)
            
        except NotFound:
            logger.error(f"Blob '{blob_name}' not found in bucket")
            return None
        except Exception as e:
            logger.error(f"Failed to download blob as text: {e}")
            return None
    
    def list_blobs(self, prefix: Optional[str] = None) -> List[str]:
        """
        List all blobs in the bucket.
        
        Args:
            prefix (str, optional): Filter blobs with this prefix
        
        Returns:
            List[str]: List of blob names
        """
        try:
            blobs = self.client.list_blobs(self.bucket, prefix=prefix)
            blob_names = [blob.name for blob in blobs]
            logger.info(f"Found {len(blob_names)} blobs")
            return blob_names
            
        except Exception as e:
            logger.error(f"Failed to list blobs: {e}")
            return []
    
    def delete_blob(self, bucket_path: str) -> bool:
        """
        Delete a blob from the bucket with support for directory paths.
        
        Args:
            bucket_path (str): Path of the blob to delete (e.g., "audio/files/myfile.mp3")
        
        Returns:
            bool: True if deletion successful, False otherwise
        """
        try:
            # Normalize path separators for consistency
            blob_name = bucket_path.replace('\\', '/')
            
            blob = self.bucket.blob(blob_name)
            blob.delete()
            logger.info(f"Successfully deleted {blob_name}")
            return True
            
        except NotFound:
            logger.error(f"Blob '{blob_name}' not found in bucket")
            return False
        except Exception as e:
            logger.error(f"Failed to delete blob: {e}")
            return False
    
    def blob_exists(self, bucket_path: str) -> bool:
        """
        Check if a blob exists in the bucket with support for directory paths.
        
        Args:
            bucket_path (str): Path of the blob to check (e.g., "audio/files/myfile.mp3")
        
        Returns:
            bool: True if blob exists, False otherwise
        """
        try:
            # Normalize path separators for consistency
            blob_name = bucket_path.replace('\\', '/')
            
            blob = self.bucket.blob(blob_name)
            return blob.exists()
        except Exception as e:
            logger.error(f"Failed to check blob existence: {e}")
            return False
    
    def get_blob_info(self, bucket_path: str) -> Optional[dict]:
        """
        Get information about a blob with support for directory paths.
        
        Args:
            bucket_path (str): Path of the blob (e.g., "audio/files/myfile.mp3")
        
        Returns:
            Optional[dict]: Blob information, None if failed
        """
        try:
            # Normalize path separators for consistency
            blob_name = bucket_path.replace('\\', '/')
            
            blob = self.bucket.blob(blob_name)
            blob.reload()
            
            return {
                'name': blob.name,
                'size': blob.size,
                'created': blob.time_created,
                'updated': blob.updated,
                'content_type': blob.content_type,
                'md5_hash': blob.md5_hash,
                'crc32c': blob.crc32c
            }
            
        except NotFound:
            logger.error(f"Blob '{blob_name}' not found in bucket")
            return None
        except Exception as e:
            logger.error(f"Failed to get blob info: {e}")
            return None
    
    def copy_blob(self, source_bucket_path: str, destination_bucket_path: str) -> bool:
        """
        Copy a blob within the same bucket with support for directory paths.
        
        Args:
            source_bucket_path (str): Path of the source blob (e.g., "audio/files/source.mp3")
            destination_bucket_path (str): Path of the destination blob (e.g., "backup/audio/source.mp3")
        
        Returns:
            bool: True if copy successful, False otherwise
        """
        try:
            # Normalize path separators for consistency
            source_blob_name = source_bucket_path.replace('\\', '/')
            destination_blob_name = destination_bucket_path.replace('\\', '/')
            
            source_blob = self.bucket.blob(source_blob_name)
            destination_blob = self.bucket.blob(destination_blob_name)
            
            # Copy the blob
            destination_blob.rewrite(source_blob)
            logger.info(f"Successfully copied {source_blob_name} to {destination_blob_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to copy blob: {e}")
            return False

    def upload_directory(self, local_dir_path: str, bucket_dir_path: str = "") -> bool:
        """
        Upload an entire directory to the bucket.
        
        Args:
            local_dir_path (str): Path to the local directory to upload
            bucket_dir_path (str): Directory path in the bucket (e.g., "audio/files/")
                If empty, uploads to bucket root.
        
        Returns:
            bool: True if all files uploaded successfully, False otherwise
        """
        try:
            if not os.path.exists(local_dir_path) or not os.path.isdir(local_dir_path):
                logger.error(f"Local directory not found or not a directory: {local_dir_path}")
                return False
            
            success_count = 0
            total_count = 0
            
            # Walk through all files in the directory
            for root, dirs, files in os.walk(local_dir_path):
                for file in files:
                    local_file = os.path.join(root, file)
                    
                    # Calculate relative path from the base directory
                    rel_path = os.path.relpath(local_file, local_dir_path)
                    
                    # Create bucket path
                    if bucket_dir_path:
                        bucket_path = f"{bucket_dir_path.rstrip('/')}/{rel_path}"
                    else:
                        bucket_path = rel_path
                    
                    # Normalize path separators
                    bucket_path = bucket_path.replace('\\', '/')
                    
                    total_count += 1
                    if self.upload_file(local_file, bucket_path):
                        success_count += 1
            
            logger.info(f"Directory upload completed: {success_count}/{total_count} files uploaded successfully")
            return success_count == total_count
            
        except Exception as e:
            logger.error(f"Failed to upload directory: {e}")
            return False
    
    def download_directory(self, bucket_dir_path: str, local_dir_path: str) -> bool:
        """
        Download all files from a bucket directory to a local directory.
        
        Args:
            bucket_dir_path (str): Directory path in the bucket (e.g., "audio/files/")
            local_dir_path (str): Local directory path where files should be downloaded
        
        Returns:
            bool: True if all files downloaded successfully, False otherwise
        """
        try:
            # Normalize bucket directory path
            bucket_prefix = bucket_dir_path.replace('\\', '/').rstrip('/') + '/' if bucket_dir_path else ""
            
            # List all blobs with the prefix
            blobs = self.list_blobs(prefix=bucket_prefix)
            
            if not blobs:
                logger.warning(f"No files found in bucket directory: {bucket_dir_path}")
                return True
            
            success_count = 0
            total_count = len(blobs)
            
            for blob_name in blobs:
                # Calculate local file path
                if bucket_prefix:
                    rel_path = blob_name[len(bucket_prefix):]
                else:
                    rel_path = blob_name
                
                local_file_path = os.path.join(local_dir_path, rel_path)
                
                if self.download_file(blob_name, local_file_path):
                    success_count += 1
            
            logger.info(f"Directory download completed: {success_count}/{total_count} files downloaded successfully")
            return success_count == total_count
            
        except Exception as e:
            logger.error(f"Failed to download directory: {e}")
            return False
