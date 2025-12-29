import os
import uuid
import json
import logging
from datetime import datetime
from django.http import JsonResponse, FileResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from ..tools.file_obfuscator_service import FileManager

logger = logging.getLogger(__name__)

# Base directory for uploaded files
UPLOAD_DIR = os.path.join(settings.BASE_DIR, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Initialize the file manager
file_manager = FileManager(UPLOAD_DIR)

def get_file_info(file_path):
    """Get file information including size, date modified, etc."""
    try:
        stats = os.stat(file_path)
        file_size = stats.st_size
        modified_time = datetime.fromtimestamp(stats.st_mtime)
        
        # Format file size
        if file_size < 1024:
            size_str = f"{file_size} B"
        elif file_size < 1024*1024:
            size_str = f"{file_size/1024:.1f} KB"
        else:
            size_str = f"{file_size/(1024*1024):.1f} MB"
            
        return {
            'name': os.path.basename(file_path),
            'size': size_str,
            'size_bytes': file_size,
            'modified': modified_time.strftime('%Y-%m-%d %H:%M:%S'),
            'path': os.path.relpath(file_path, UPLOAD_DIR)
        }
    except Exception as e:
        logger.error(f"Error getting file info for {file_path}: {str(e)}")
        return None

@csrf_exempt
def upload_file(request):
    """
    API endpoint to upload files to the server
    
    POST with multipart/form-data:
    - file: The file to upload
    - category (optional): Category/subfolder to store the file in
    
    Returns:
    - JSON response with upload status and file information
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'}, status=405)
    
    try:
        if 'file' not in request.FILES:
            return JsonResponse({'status': 'error', 'message': 'No file was provided'}, status=400)
            
        uploaded_file = request.FILES['file']
        
        # Get optional category (subfolder)
        category = request.POST.get('category', '')
        
        # Read file data
        file_data = uploaded_file.read()
        
        # Save the file using FileManager
        result = file_manager.save_file(
            file_data=file_data,
            category=category,
            original_filename=uploaded_file.name
        )
        
        if not result['success']:
            return JsonResponse({
                'status': 'error',
                'message': f"Error saving file: {result.get('error', 'Unknown error')}"
            }, status=500)
        
        # Get file info
        file_info = file_manager.get_file_info(result['path'])
        
        if not file_info:
            return JsonResponse({
                'status': 'error',
                'message': 'File saved but could not retrieve file information'
            }, status=500)
        
        # Add original filename to response
        file_info['original_name'] = uploaded_file.name
        
        logger.info(f"File uploaded successfully: {uploaded_file.name} -> {result['full_path']}")
        
        return JsonResponse({
            'status': 'success',
            'message': 'File uploaded successfully',
            'file': file_info,
            'download_url': f"/api/download_file/{result['path']}"
        })
        
    except Exception as e:
        logger.error(f"Error in upload_file: {str(e)}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'Server error: {str(e)}'}, status=500)

def list_files(request):
    """
    API endpoint to list all uploaded files
    
    GET parameters:
    - category (optional): Filter files by category/subfolder
    
    Returns:
    - JSON response with list of files
    """
    try:
        # Get optional category parameter
        category = request.GET.get('category', '')
        
        # Use FileManager to list files
        result = file_manager.list_files(category)
        
        files = result.get('files', [])
        categories = result.get('categories', [])
        error = result.get('error')
        
        if error:
            logger.warning(f"Error listing files: {error}")
        
        response_data = {
            'status': 'success',
            'message': f'Found {len(files)} files' + (f' and {len(categories)} categories' if categories else ''),
            'files': files
        }
        
        # Add categories if available
        if categories:
            response_data['categories'] = categories
        
        # Add current category if specified
        if category:
            response_data['current_category'] = category
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Error in list_files: {str(e)}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'Server error: {str(e)}'}, status=500)

@csrf_exempt
def download_file(request, file_path=''):
    """
    API endpoint to download a previously uploaded file
    
    Parameters:
        file_path (str): The path of the file to download relative to the upload directory
    
    Returns:
        File response for download or error message
    """
    try:
        if not file_path:
            return JsonResponse({
                'status': 'error',
                'message': 'No file path specified'
            }, status=400)
        
        # Get file info using FileManager
        file_info = file_manager.get_file_info(file_path)
        
        if not file_info:
            return JsonResponse({
                'status': 'error',
                'message': f'File not found: {file_path}'
            }, status=404)
        
        # Open the file and create a FileResponse
        file = open(file_info['full_path'], 'rb')
        response = FileResponse(file)
        
        # Get file extension
        file_extension = os.path.splitext(file_info['name'])[1].lower()
        
        # Set content type based on file extension
        if file_extension == '.pdf':
            response['Content-Type'] = 'application/pdf'
        elif file_extension == '.zip':
            response['Content-Type'] = 'application/zip'
        elif file_extension == '.jpg' or file_extension == '.jpeg':
            response['Content-Type'] = 'image/jpeg'
        elif file_extension == '.png':
            response['Content-Type'] = 'image/png'
        elif file_extension == '.gif':
            response['Content-Type'] = 'image/gif'
        elif file_extension == '.txt':
            response['Content-Type'] = 'text/plain'
        elif file_extension == '.csv':
            response['Content-Type'] = 'text/csv'
        elif file_extension == '.json':
            response['Content-Type'] = 'application/json'
        else:
            response['Content-Type'] = 'application/octet-stream'
        
        # Set Content-Disposition to attachment to force download
        response['Content-Disposition'] = f'attachment; filename="{file_info["name"]}"'
        
        logger.info(f"Serving download for file: {file_path}")
        return response
        
    except Exception as e:
        logger.error(f"Error in download_file: {str(e)}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': f'Error downloading file: {str(e)}'
        }, status=500)

@csrf_exempt
def delete_file(request, file_path=''):
    """
    API endpoint to delete a previously uploaded file
    
    DELETE request
    
    Parameters:
        file_path (str): The path of the file to delete relative to the upload directory
    
    Returns:
        JSON response indicating success or failure
    """
    if request.method != 'DELETE':
        return JsonResponse({'status': 'error', 'message': 'Only DELETE method is allowed'}, status=405)
    
    try:
        if not file_path:
            return JsonResponse({
                'status': 'error',
                'message': 'No file path specified'
            }, status=400)
        
        # Use FileManager to delete the file
        success = file_manager.delete_file(file_path)
        
        if success:
            return JsonResponse({
                'status': 'success',
                'message': f'File deleted: {os.path.basename(file_path)}'
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to delete file: {file_path}'
            }, status=404)
        
    except Exception as e:
        logger.error(f"Error in delete_file: {str(e)}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': f'Error deleting file: {str(e)}'
        }, status=500) 