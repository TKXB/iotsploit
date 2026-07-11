from iotsploit_django.tools.sat_utils import *

from django.views.decorators.csrf import csrf_exempt

from django.http import JsonResponse
from iotsploit_django.composition_root.wiring import (
    ensure_stream_backend_configured,
)
ensure_stream_backend_configured()

from iotsploit_django.tools.xlogger import xlog

logger = xlog.get_logger('views')










@csrf_exempt
def file_download(request, file_path=''):
    """
    API endpoint to download files from the firmware directory
    
    Parameters:
        file_path (str): The path of the file to download relative to the firmware directory
    
    Returns:
        File response for download or error message
    """
    try:
        import os
        from django.http import FileResponse
        from django.utils.encoding import smart_str
        
        # Base directory for firmware files
        firmware_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'firmware')
        
        # Handle empty path - list available files
        if not file_path:
            try:
                file_list = []
                for root, dirs, files in os.walk(firmware_dir):
                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, firmware_dir)
                        file_size = os.path.getsize(full_path)
                        # Format file size
                        if file_size < 1024:
                            size_str = f"{file_size} B"
                        elif file_size < 1024*1024:
                            size_str = f"{file_size/1024:.1f} KB"
                        else:
                            size_str = f"{file_size/(1024*1024):.1f} MB"
                        
                        file_list.append({
                            'name': file,
                            'path': rel_path,
                            'size': size_str,
                            'download_url': f"/api/download_firmware/{rel_path}"
                        })
                
                return JsonResponse({
                    'status': 'success',
                    'message': f'Found {len(file_list)} files',
                    'files': file_list
                })
            except Exception as e:
                logger.error(f"Error listing firmware files: {str(e)}")
                return JsonResponse({
                    'status': 'error',
                    'message': f'Failed to list firmware files: {str(e)}'
                }, status=500)
        
        # Construct the full file path, ensuring we don't allow directory traversal
        file_path = file_path.replace('..', '').replace('\\', '/').lstrip('/')
        full_path = os.path.normpath(os.path.join(firmware_dir, file_path))
        
        # Security check: ensure the requested file is within the firmware directory
        if not full_path.startswith(os.path.normpath(firmware_dir)):
            logger.warning(f"Security violation: Attempted path traversal: {file_path}")
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid file path. Access denied.'
            }, status=403)
        
        # Check if file exists
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            logger.error(f"File not found: {full_path}")
            return JsonResponse({
                'status': 'error',
                'message': f'File not found: {file_path}'
            }, status=404)
        
        # Get file name and extension
        file_name = os.path.basename(full_path)
        file_extension = os.path.splitext(file_name)[1].lower()
        
        # Open the file and create a FileResponse
        file = open(full_path, 'rb')
        response = FileResponse(file)
        
        # Set content type based on file extension
        if file_extension == '.pdf':
            response['Content-Type'] = 'application/pdf'
        elif file_extension == '.zip':
            response['Content-Type'] = 'application/zip'
        elif file_extension == '.bin':
            response['Content-Type'] = 'application/octet-stream'
        elif file_extension == '.hex':
            response['Content-Type'] = 'text/plain'
        elif file_extension == '.json':
            response['Content-Type'] = 'application/json'
        else:
            response['Content-Type'] = 'application/octet-stream'
        
        # Set Content-Disposition to attachment to force download
        response['Content-Disposition'] = f'attachment; filename={smart_str(file_name)}'
        
        logger.info(f"Serving download for file: {file_path}")
        return response
        
    except Exception as e:
        logger.error(f"Error in file_download: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Error downloading file: {str(e)}'
        }, status=500)

