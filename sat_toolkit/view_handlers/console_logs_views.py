import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import logging
from datetime import datetime, timedelta
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from sat_toolkit.consumers import console_log_buffer, log_buffer_lock

# Set up logging
logger = logging.getLogger(__name__)

# Back‑compatibility stubs
reading_console_output = False
console_reader_thread = None

def start_console_reader():
    """No longer needed – logs are captured via logging handlers."""
    logger.debug("start_console_reader() called – no action required.")
    return False

def stop_console_reader():
    """No longer needed – logs are captured via logging handlers."""
    logger.debug("stop_console_reader() called – no action required.")
    return False

@csrf_exempt
def get_console_logs(request):
    """Get console logs from the buffer
    
    Query parameters:
    - lines: Number of log lines to retrieve (default: 100)
    - level: Filter by log level (default: all)
    - since: Get logs since timestamp (default: all)
    """
    try:
        # Get query parameters
        lines = int(request.GET.get('lines', 100))
        level = request.GET.get('level', None)
        since_str = request.GET.get('since', None)
        
        # Get logs from buffer
        with log_buffer_lock:
            logs = list(console_log_buffer)
        
        # Filter by level if specified
        if level:
            logs = [log for log in logs if f' | {level} | ' in log]
        
        # Filter by timestamp if specified
        if since_str:
            try:
                since = datetime.fromisoformat(since_str.replace('Z', '+00:00'))
                logs = [
                    log for log in logs 
                    if datetime.strptime(log.split(' | ')[0], '%Y-%m-%d %H:%M:%S') > since
                ]
            except Exception as e:
                logger.error(f"Error parsing timestamp: {e}")
        
        # Limit the number of logs returned
        limited_logs = logs[-lines:] if lines > 0 else logs
        
        return JsonResponse({
            'status': 'success',
            'logs': limited_logs,
            'total': len(logs),
            'returned': len(limited_logs),
        })
    except Exception as e:
        logger.error(f"Error getting console logs: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        })

@csrf_exempt
def clear_console_logs(request):
    """Clear all logs from the buffer"""
    if request.method == 'POST':
        try:
            with log_buffer_lock:
                console_log_buffer.clear()
                # Add a "logs cleared" entry
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                console_log_buffer.append(f"{timestamp} | INFO | console | Logs cleared by user")
            
            return JsonResponse({
                'status': 'success',
                'message': 'Console logs cleared successfully'
            })
        except Exception as e:
            logger.error(f"Error clearing console logs: {e}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            })
    
    return JsonResponse({
        'status': 'error',
        'message': 'This endpoint only accepts POST requests'
    })

@csrf_exempt
def control_console_reader(request):
    """Start or stop the console reader thread"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            action = data.get('action')
            
            if action == 'start':
                result = start_console_reader()
                return JsonResponse({
                    'status': 'success' if result else 'info',
                    'message': 'Console reader started' if result else 'Console reader already running'
                })
            elif action == 'stop':
                result = stop_console_reader()
                return JsonResponse({
                    'status': 'success' if result else 'info',
                    'message': 'Console reader stopped' if result else 'Console reader not running'
                })
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Unknown action: {action}'
                })
        except Exception as e:
            logger.error(f"Error controlling console reader: {e}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            })
    
    return JsonResponse({
        'status': 'error',
        'message': 'This endpoint only accepts POST requests'
    })