#!/usr/bin/env python

import cmd2
from cmd2 import ansi
import sys
import subprocess
import time
from .base_commands import BaseCommands
from iotsploit_django.tools.xlogger import xlog as logger
import os
import signal
import socket
from typing import Tuple
try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None

from django.conf import settings


class DjangoCommands(BaseCommands):
    """Django-related commands for the SAT Shell"""

    def _check_redis_available(self) -> Tuple[bool, str]:
        """
        Preflight check for Redis reachability using Django settings.

        Returns (ok, message). If ok is False, message contains human-friendly guidance.
        """
        redis_host = getattr(settings, 'REDIS_HOST', '127.0.0.1')
        redis_port = int(getattr(settings, 'REDIS_PORT', 6379))
        redis_db = int(getattr(settings, 'REDIS_DB', 0))

        # Quick TCP reachability check first to avoid long client timeouts
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            try:
                sock.connect((redis_host, redis_port))
            except Exception:
                guide = (
                    f"Redis is not reachable at {redis_host}:{redis_port}.\n"
                    "Celery and WebSocket features require Redis.\n\n"
                    "How to start Redis:\n"
                    "  - If you use Docker: docker run --name redis -p 6379:6379 -d redis:latest\n"
                    "  - On Ubuntu/Debian: sudo apt install redis-server && sudo systemctl start redis-server\n"
                    "  - Or inside project (docker-compose): enable the redis service\n\n"
                    "Please start Redis and try again."
                )
                return False, guide

        # If redis-py is available, ping for certainty
        if redis is not None:
            try:
                client = redis.Redis(host=redis_host, port=redis_port, db=redis_db)
                client.ping()
            except Exception as e:  # pragma: no cover
                return False, (
                    f"Connected to {redis_host}:{redis_port} but Redis ping failed: {e}\n"
                    "Please ensure Redis is healthy and try again."
                )

        return True, "Redis is available"

    @cmd2.with_category('Django Commands')
    def do_runserver(self, arg):
        'Start Django development server, Daphne WebSocket server, MCP WebSocket bridge, and Celery worker in the background'
        if self.django_server_process or self.daphne_server_process:
            self.poutput("Servers are already running.")
            return

        try:
            logger.info("Attempting to start Django, Daphne, MCP WebSocket bridge, and Celery servers in background...")
            
            # Preflight: check Redis and fail fast if unavailable
            redis_ok, redis_msg = self._check_redis_available()
            if not redis_ok:
                self.poutput(ansi.style("\n[ERROR] Redis is unavailable. Cannot start services that depend on it.", fg=ansi.Fg.RED, bold=True))
                self.poutput(redis_msg)
                return False
            
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
                'iotsploit_django.asgi:application'
            ]
            mcp_bridge_cmd = [
                sys.executable,
                '-m',
                'iotsploit_mcp.cli',
                'ws',
                '--host',
                '0.0.0.0',
                '--port',
                '9998',
            ]
            celery_cmd = [
                sys.executable,
                '-m',
                'celery',
                '-A',
                'iotsploit_django.tasks.celery_app:app',
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
            # Set up environment variables for MCP bridge (plugin directories + Django API URL)
            mcp_env = os.environ.copy()
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            mcp_env.setdefault('IOTSPLOIT_DEVICE_PLUGINS_DIR', os.path.join(project_root, 'plugins', 'devices'))
            mcp_env.setdefault('IOTSPLOIT_EXPLOIT_PLUGINS_DIR', os.path.join(project_root, 'plugins', 'exploits'))
            mcp_env.setdefault('IOTSPLOIT_DJANGO_API_BASE_URL', 'http://127.0.0.1:8888')
            
            self.mcp_bridge_process = subprocess.Popen(
                mcp_bridge_cmd,
                stdout=sys.stdout,  # 直接输出到控制台
                stderr=sys.stderr,
                universal_newlines=True,
                start_new_session=True,  # create new session = new PGID on POSIX
                env=mcp_env
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
            
            return None
        
        except Exception as e:
            logger.error(f"Failed to start servers: {str(e)}")
            logger.debug("Detailed traceback:", exc_info=True)
            return False

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
            
            if self.mcp_bridge_process:
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
            
            if self.celery_worker_process:
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
