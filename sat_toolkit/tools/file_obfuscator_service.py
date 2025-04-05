#!/usr/bin/env python3
"""
File Handling Utilities

This module provides file handling utilities for the Django application.
It replaces the previous Flask-based file obfuscation service.
"""

import os
import uuid
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

class FileManager:
    """A class to handle file operations."""
    
    def __init__(self, base_dir):
        """Initialize the FileManager with a base directory for file storage."""
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
    
    def save_file(self, file_data, category=None, original_filename=None):
        """
        Save a file to the storage directory.
        
        Args:
            file_data: The file data (bytes)
            category: Optional subfolder/category to store the file in
            original_filename: Optional original filename to preserve
            
        Returns:
            dict: Information about the saved file including path and unique filename
        """
        try:
            # Create a clean category name if provided
            if category:
                category = category.replace('..', '').replace('/', '_').replace('\\', '_')
                target_dir = os.path.join(self.base_dir, category)
                os.makedirs(target_dir, exist_ok=True)
            else:
                target_dir = self.base_dir
            
            # Generate a unique filename
            if original_filename:
                file_ext = os.path.splitext(original_filename)[1]
            else:
                file_ext = '.bin'  # Default extension
                
            unique_filename = f"{uuid.uuid4().hex}{file_ext}"
            file_path = os.path.join(target_dir, unique_filename)
            
            # Save the file
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            # Return file info
            rel_path = os.path.relpath(file_path, self.base_dir)
            
            return {
                'success': True,
                'path': rel_path,
                'full_path': file_path,
                'filename': unique_filename,
                'original_filename': original_filename,
                'category': category
            }
            
        except Exception as e:
            logger.error(f"Error saving file: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def delete_file(self, file_path):
        """
        Delete a file from the storage directory.
        
        Args:
            file_path: Path to the file relative to the base directory
            
        Returns:
            bool: True if file was deleted successfully, False otherwise
        """
        try:
            # Clean the path to prevent directory traversal
            file_path = file_path.replace('..', '').replace('\\', '/').lstrip('/')
            full_path = os.path.normpath(os.path.join(self.base_dir, file_path))
            
            # Security check
            if not full_path.startswith(os.path.normpath(self.base_dir)):
                logger.warning(f"Security violation: Attempted path traversal: {file_path}")
                return False
            
            # Check if file exists
            if not os.path.exists(full_path) or not os.path.isfile(full_path):
                logger.error(f"File not found: {full_path}")
                return False
            
            # Delete the file
            os.remove(full_path)
            logger.info(f"File deleted: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting file: {str(e)}")
            return False
    
    def get_file_info(self, file_path):
        """
        Get information about a file.
        
        Args:
            file_path: Path to the file relative to the base directory
            
        Returns:
            dict: File information or None if file does not exist
        """
        try:
            # Clean the path to prevent directory traversal
            file_path = file_path.replace('..', '').replace('\\', '/').lstrip('/')
            full_path = os.path.normpath(os.path.join(self.base_dir, file_path))
            
            # Security check
            if not full_path.startswith(os.path.normpath(self.base_dir)):
                logger.warning(f"Security violation: Attempted path traversal: {file_path}")
                return None
            
            # Check if file exists
            if not os.path.exists(full_path) or not os.path.isfile(full_path):
                logger.error(f"File not found: {full_path}")
                return None
            
            # Get file stats
            stats = os.stat(full_path)
            size_bytes = stats.st_size
            
            # Format file size
            if size_bytes < 1024:
                size_str = f"{size_bytes} B"
            elif size_bytes < 1024*1024:
                size_str = f"{size_bytes/1024:.1f} KB"
            else:
                size_str = f"{size_bytes/(1024*1024):.1f} MB"
            
            return {
                'name': os.path.basename(full_path),
                'path': file_path,
                'full_path': full_path,
                'size': size_str,
                'size_bytes': size_bytes,
                'created': stats.st_ctime,
                'modified': stats.st_mtime
            }
            
        except Exception as e:
            logger.error(f"Error getting file info: {str(e)}")
            return None
    
    def list_files(self, category=None):
        """
        List files in the storage directory.
        
        Args:
            category: Optional subfolder/category to list files from
            
        Returns:
            dict: List of files and categories
        """
        try:
            # Clean the category path if provided
            if category:
                category = category.replace('..', '').replace('/', '_').replace('\\', '_')
                search_dir = os.path.join(self.base_dir, category)
                if not os.path.exists(search_dir) or not os.path.isdir(search_dir):
                    return {
                        'files': [],
                        'categories': [],
                        'current_category': category
                    }
            else:
                search_dir = self.base_dir
            
            files = []
            categories = []
            
            # Scan the directory
            for item in os.listdir(search_dir):
                item_path = os.path.join(search_dir, item)
                
                if os.path.isfile(item_path):
                    # Get file info
                    stats = os.stat(item_path)
                    size_bytes = stats.st_size
                    
                    # Format file size
                    if size_bytes < 1024:
                        size_str = f"{size_bytes} B"
                    elif size_bytes < 1024*1024:
                        size_str = f"{size_bytes/1024:.1f} KB"
                    else:
                        size_str = f"{size_bytes/(1024*1024):.1f} MB"
                    
                    rel_path = os.path.relpath(item_path, self.base_dir)
                    
                    files.append({
                        'name': item,
                        'path': rel_path,
                        'size': size_str,
                        'size_bytes': size_bytes,
                        'modified': stats.st_mtime
                    })
                
                elif os.path.isdir(item_path):
                    # Count files in this category
                    file_count = len([f for f in os.listdir(item_path) if os.path.isfile(os.path.join(item_path, f))])
                    
                    if category:
                        # If we're in a subfolder, build the path accordingly
                        cat_path = f"{category}/{item}"
                    else:
                        cat_path = item
                    
                    categories.append({
                        'name': item,
                        'path': cat_path,
                        'file_count': file_count
                    })
            
            return {
                'files': files,
                'categories': categories,
                'current_category': category
            }
            
        except Exception as e:
            logger.error(f"Error listing files: {str(e)}")
            return {
                'files': [],
                'categories': [],
                'error': str(e)
            } 