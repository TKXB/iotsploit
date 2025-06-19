#!/usr/bin/env python

import cmd2
from cmd2 import ansi
import sys
import subprocess
import time
from .base_commands import BaseCommands
from sat_toolkit.tools.xlogger import xlog as logger
import os
import signal


class DjangoCommands(BaseCommands):
    """Django-related commands for the SAT Shell"""

    @cmd2.with_category('Django Commands')
    def do_runserver(self, arg):
        'Start Django development server, Daphne WebSocket server, MCP WebSocket bridge, and Celery worker in the background'
        if self.django_server_process or self.daphne_server_process:
            self.poutput("Servers are already running.")
            return

        try:
            logger.info("Attempting to start Django, Daphne, MCP WebSocket bridge, and Celery servers in background...")
            
            # Prepare the commands
            django_cmd = [sys.executable, 'manage.py', 'runserver', '--noreload', '0.0.0.0:8888']
            daphne_cmd = [
                sys.executable, 
                '-m', 
                'daphne', 
                '-b', 
                '0.0.0.0', 
                '-p', 
                '9999', 
                'sat_django_entry.asgi:application'
            ]
            mcp_bridge_cmd = [
                sys.executable,
                'sat_mcp_server/websocket_bridge_simple.py'
            ]
            celery_cmd = [
                sys.executable,
                '-m',
                'celery',
                '-A',
                'sat_toolkit',
                'worker',
                '--loglevel=info'
            ]
            
            logger.info(f"Running Django command: {' '.join(django_cmd)}")
            logger.info(f"Running Daphne command: {' '.join(daphne_cmd)}")
            logger.info(f"Running MCP WebSocket Bridge command: {' '.join(mcp_bridge_cmd)}")
            logger.info(f"Running Celery command: {' '.join(celery_cmd)}")
            
            # Start the processes with direct output to stdout/stderr
            self.django_server_process = subprocess.Popen(
                django_cmd, 
                stdout=sys.stdout,  # 直接输出到控制台
                stderr=sys.stderr,
                universal_newlines=True
            )
            
            self.daphne_server_process = subprocess.Popen(
                daphne_cmd, 
                stdout=sys.stdout,  # 直接输出到控制台
                stderr=sys.stderr,
                universal_newlines=True
            )
            
            # Start the WebSocket bridge in its own process group so that we can
            # later terminate the entire group (bridge + sat_fastmcp child)
            self.mcp_bridge_process = subprocess.Popen(
                mcp_bridge_cmd,
                stdout=sys.stdout,  # 直接输出到控制台
                stderr=sys.stderr,
                universal_newlines=True,
                start_new_session=True  # create new session = new PGID on POSIX
            )
            
            self.celery_worker_process = subprocess.Popen(
                celery_cmd,
                stdout=sys.stdout,  # 直接输出到控制台
                stderr=sys.stderr,
                universal_newlines=True
            )
            
            logger.info("All servers started successfully in the background.")
            logger.info("Services running on:")
            logger.info("  - Django HTTP API: http://localhost:8888")
            logger.info("  - Daphne WebSocket: ws://localhost:9999")
            logger.info("  - MCP WebSocket Bridge: ws://localhost:9998")
            logger.info("  - Celery Worker: background task processing")
            
            # Wait for HTTP server to be available and initialize devices
            import requests
            max_retries = 30
            retry_interval = 1
            
            logger.info("Waiting for HTTP server to be available...")
            for i in range(max_retries):
                try:
                    # Try to initialize devices using the HTTP endpoint (GET method)
                    response = requests.get('http://127.0.0.1:8888/api/initialize_devices/')
                    if response.status_code == 200:
                        logger.info("Devices initialized successfully via HTTP API")
                        break
                    else:
                        logger.error(f"Failed to initialize devices: {response.text}")
                        break
                except requests.exceptions.ConnectionError:
                    if i < max_retries - 1:
                        time.sleep(retry_interval)
                    else:
                        logger.error("HTTP server did not become available in time")
                    continue
                except Exception as e:
                    logger.error(f"Error initializing devices: {str(e)}")
                    break
            
        except Exception as e:
            logger.error(f"Failed to start servers: {str(e)}")
            logger.debug("Detailed traceback:", exc_info=True)

    @cmd2.with_category('Django Commands')
    def do_stop_server(self, arg):
        'Stop Django development server, Daphne WebSocket server, MCP WebSocket bridge, and Celery worker'
        try:
            # Cleanup devices using HTTP endpoint (GET method)
            import requests
            try:
                response = requests.get('http://127.0.0.1:8888/api/cleanup_devices/')
                if response.status_code == 200:
                    logger.info("Devices cleaned up successfully via HTTP API")
                else:
                    logger.error(f"Failed to cleanup devices: {response.text}")
            except requests.exceptions.ConnectionError:
                logger.warning("Could not reach HTTP server for device cleanup")
            except Exception as e:
                logger.error(f"Error during device cleanup: {str(e)}")
            
            # Stop the servers
            if self.django_server_process:
                self.django_server_process.terminate()
                self.django_server_process = None
            
            if self.daphne_server_process:
                self.daphne_server_process.terminate()
                self.daphne_server_process = None
            
            if hasattr(self, 'mcp_bridge_process') and self.mcp_bridge_process:
                try:
                    # Terminate the entire process group so that child processes
                    # such as sat_fastmcp are also stopped.
                    os.killpg(os.getpgid(self.mcp_bridge_process.pid), signal.SIGTERM)
                except ProcessLookupError:
                    # Process already gone
                    pass
                except Exception as e:
                    logger.error(f"Failed to terminate MCP bridge process group: {e}")
                finally:
                    self.mcp_bridge_process = None
            
            if hasattr(self, 'celery_worker_process') and self.celery_worker_process:
                self.celery_worker_process.terminate()
                self.celery_worker_process = None
            
            if not any([self.django_server_process, self.daphne_server_process, 
                        getattr(self, 'mcp_bridge_process', None),
                        getattr(self, 'celery_worker_process', None)]):
                logger.info("All servers stopped.")
            else:
                logger.error("No servers were running.")
                
        except Exception as e:
            logger.error(f"Error stopping servers: {str(e)}")
            logger.debug("Detailed error:", exc_info=True)
