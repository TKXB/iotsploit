#!/usr/bin/env python

import cmd2
from cmd2 import ansi
import sys
import subprocess
import time
from .base_commands import BaseCommands
from iotsploit_core.utils import iots_logger
import os
import socket
from typing import Tuple

from django.conf import settings
from iotsploit_core.utils.helpers import log_dir, process_group_kwargs, terminate_process_group

from .resource_commands import add_service_start_arguments, service_start_kwargs

logger = iots_logger.get_logger(__name__)


runserver_parser = cmd2.Cmd2ArgumentParser(description="Start the backend service suite")
add_service_start_arguments(runserver_parser)


class DjangoCommands(BaseCommands):
    """Django-related commands for the SAT Shell"""

    def _services_log_to_console(self) -> bool:
        override = os.getenv("IOTSPLOIT_SERVICE_LOG_TO_CONSOLE", "").strip().lower()
        if override:
            return override in ("1", "true", "yes", "y", "on")
        return os.getenv("IOTSPLOIT_LOG_FORMAT", "standard").strip().lower() == "standard"

    def _open_service_log(self, service_name: str):
        if not hasattr(self, "_service_log_files"):
            self._service_log_files = []

        service_log_dir = log_dir()
        service_log_dir.mkdir(parents=True, exist_ok=True)
        log_path = service_log_dir / f"{service_name}.log"
        log_file = open(log_path, "a", buffering=1, encoding="utf-8")
        self._service_log_files.append(log_file)
        return log_file, log_path

    def _service_stdio(self, service_name: str):
        if self._services_log_to_console():
            return sys.stdout, sys.stderr, None

        log_file, log_path = self._open_service_log(service_name)
        return log_file, subprocess.STDOUT, log_path

    def _close_service_log_files(self):
        for log_file in getattr(self, "_service_log_files", []):
            try:
                log_file.close()
            except Exception:
                pass
        self._service_log_files = []

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

        try:
            import redis

            redis.Redis(host=redis_host, port=redis_port, db=redis_db).ping()
        except Exception as e:  # pragma: no cover
            return False, (
                f"Connected to {redis_host}:{redis_port} but Redis ping failed: {e}\n"
                "Install the iotsploit-django distributed extra and ensure Redis is healthy."
            )

        return True, "Redis is available"

    @cmd2.with_category('Django Commands')
    @cmd2.with_argparser(runserver_parser)
    def do_runserver(self, args):
        'Start the local or distributed backend runtime in the background'
        return self._start_services(**service_start_kwargs(args))

    def _start_services(self, *, host, api_port, ws_port, mcp_host, mcp_port):
        ports = (api_port, ws_port, mcp_port)
        if len(set(ports)) != len(ports):
            self.perror("--api-port, --ws-port, and --mcp-port must use distinct ports")
            return False

        if self.django_server_process or self.daphne_server_process:
            self.poutput("Servers are already running.")
            return

        try:
            distributed = settings.IOTSPLOIT_RUNTIME == "distributed"
            logger.info("Starting the %s backend runtime", settings.IOTSPLOIT_RUNTIME)

            api_client_host = "127.0.0.1" if host == "0.0.0.0" else host
            mcp_client_host = "127.0.0.1" if mcp_host == "0.0.0.0" else mcp_host
            api_base_url = f"http://{api_client_host}:{api_port}"
            ws_base_url = f"ws://{api_client_host}:{ws_port}"
            mcp_url = f"http://{mcp_client_host}:{mcp_port}/mcp"

            if distributed:
                redis_ok, redis_msg = self._check_redis_available()
                if not redis_ok:
                    self.poutput(ansi.style("\n[ERROR] Redis is unavailable.", fg=ansi.Fg.RED, bold=True))
                    self.poutput(redis_msg)
                    return False

            django_cmd = [sys.executable, '-m', 'django', 'runserver', '--noreload', f'{host}:{api_port}']
            if distributed:
                daphne_cmd = [
                    sys.executable, '-m', 'daphne', '-b', host, '-p', str(ws_port),
                    'iotsploit_django.asgi:application',
                ]
            else:
                daphne_cmd = [
                    sys.executable, '-m', 'daphne',
                    '-e', f'tcp:{api_port}:interface={host}',
                    '-e', f'tcp:{ws_port}:interface={host}',
                    'iotsploit_django.asgi:application',
                ]
            mcp_bridge_cmd = [
                sys.executable,
                '-m',
                'iotsploit_mcp.cli',
                'http',
                '--host',
                mcp_host,
                '--port',
                str(mcp_port),
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
            # Interactive runs are routed to their own queue (see
            # CELERY_TASK_ROUTES) and need a worker that consumes it. Without
            # this process the GUI would queue an interactive plugin and wait
            # forever with nothing to run it. Concurrency 1 keeps a single
            # question open at a time, and the separate process means a run
            # parked on a prompt never occupies a general worker slot.
            interactive_celery_cmd = [
                sys.executable,
                '-m',
                'celery',
                '-A',
                'iotsploit_django.tasks.celery_app:app',
                'worker',
                '--loglevel=info',
                '-Q',
                'interactive',
                '-c',
                '1',
                '-n',
                'interactive@%h',
            ]
            streaming_celery_cmd = [
                sys.executable,
                '-m',
                'celery',
                '-A',
                'iotsploit_django.tasks.celery_app:app',
                'worker',
                '--loglevel=info',
                '-Q',
                'streaming',
                '-n',
                'streaming@%h',
            ]
            os.environ["IOTSPLOIT_DJANGO_API_BASE_URL"] = api_base_url
            os.environ["IOTSPLOIT_DJANGO_WS_BASE_URL"] = ws_base_url
            os.environ["IOTSPLOIT_MCP_URL"] = mcp_url
            self._service_api_base_url = api_base_url
            service_env = os.environ.copy()
            
            if distributed:
                logger.info(f"Running Django command: {' '.join(django_cmd)}")
            logger.info(f"Running Daphne command: {' '.join(daphne_cmd)}")
            logger.info(f"Running MCP HTTP server command: {' '.join(mcp_bridge_cmd)}")
            if distributed:
                logger.info(f"Running Celery command: {' '.join(celery_cmd)}")
                logger.info(f"Running interactive Celery command: {' '.join(interactive_celery_cmd)}")
                logger.info(f"Running streaming Celery command: {' '.join(streaming_celery_cmd)}")
            if not self._services_log_to_console():
                logger.info("Service logs are redirected to %s", log_dir())
            
            # Start the processes with direct output to stdout/stderr
            if distributed:
                django_stdout, django_stderr, _ = self._service_stdio("django")
                self.django_server_process = subprocess.Popen(
                    django_cmd,
                    stdout=django_stdout,
                    stderr=django_stderr,
                    universal_newlines=True,
                    env=service_env,
                )
            
            daphne_stdout, daphne_stderr, _ = self._service_stdio("daphne")
            self.daphne_server_process = subprocess.Popen(
                daphne_cmd, 
                stdout=daphne_stdout,
                stderr=daphne_stderr,
                universal_newlines=True,
                env=service_env,
            )
            
            # Start the MCP HTTP server in its own process group so that we can
            # later terminate the entire group
            # Set up environment variables for MCP bridge (Django API URL)
            mcp_env = service_env.copy()
            
            mcp_stdout, mcp_stderr, _ = self._service_stdio("mcp")
            self.mcp_bridge_process = subprocess.Popen(
                mcp_bridge_cmd,
                stdout=mcp_stdout,
                stderr=mcp_stderr,
                universal_newlines=True,
                env=mcp_env,
                **process_group_kwargs(),
            )
            
            if distributed:
                celery_stdout, celery_stderr, _ = self._service_stdio("celery")
                self.celery_worker_process = subprocess.Popen(
                    celery_cmd, stdout=celery_stdout, stderr=celery_stderr,
                    universal_newlines=True, env=service_env,
                )
                interactive_stdout, interactive_stderr, _ = self._service_stdio("celery-interactive")
                self.interactive_worker_process = subprocess.Popen(
                    interactive_celery_cmd, stdout=interactive_stdout, stderr=interactive_stderr,
                    universal_newlines=True, env=service_env,
                )
                streaming_stdout, streaming_stderr, _ = self._service_stdio("celery-streaming")
                self.streaming_worker_process = subprocess.Popen(
                    streaming_celery_cmd, stdout=streaming_stdout, stderr=streaming_stderr,
                    universal_newlines=True, env=service_env,
                )
            
            logger.info("All servers started successfully in the background.")
            logger.info("Services running on:")
            logger.info("  - Django HTTP API listens on: http://%s:%s", host, api_port)
            logger.info("  - Daphne WebSocket listens on: ws://%s:%s", host, ws_port)
            logger.info("  - MCP HTTP listens on: http://%s:%s/mcp", mcp_host, mcp_port)
            if mcp_host != "127.0.0.1":
                logger.warning("MCP is exposed beyond loopback and does not authenticate incoming requests")
            if distributed:
                logger.info("  - Celery workers: standard, interactive, and streaming queues")
            else:
                logger.info("  - Background work: in-process thread pools")
            
            # Wait for HTTP server to be available and initialize devices
            import requests
            max_retries = 30
            retry_interval = 1
            
            logger.info("Waiting for HTTP server to be available...")
            for i in range(max_retries):
                try:
                    response = requests.post(
                        f'{api_base_url}/api/initialize_devices/')
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
        'Stop Django development server, Daphne WebSocket server, MCP HTTP server, and Celery worker'
        try:
            # Cleanup devices using the HTTP endpoint.
            # Only attempt HTTP cleanup if the Django server process is still alive
            api_process = self.django_server_process or self.daphne_server_process
            if api_process and api_process.poll() is None:
                import requests
                try:
                    api_base_url = getattr(self, "_service_api_base_url", "http://127.0.0.1:8888")
                    response = requests.post(f'{api_base_url}/api/cleanup_devices/')
                    if response.status_code == 200:
                        logger.info("Devices cleaned up successfully via HTTP API")
                    else:
                        logger.error(f"Failed to cleanup devices: {response.text}")
                except requests.exceptions.ConnectionError:
                    logger.warning("Could not reach HTTP server for device cleanup")
                except Exception as e:
                    logger.error(f"Error during device cleanup: {str(e)}")
            else:
                logger.debug("Django server not running, skipping HTTP device cleanup")
            
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
                    terminate_process_group(self.mcp_bridge_process)
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

            if getattr(self, 'interactive_worker_process', None):
                self.interactive_worker_process.terminate()
                self.interactive_worker_process = None

            if getattr(self, 'streaming_worker_process', None):
                self.streaming_worker_process.terminate()
                self.streaming_worker_process = None

            self._close_service_log_files()
            
            if not any([self.django_server_process, self.daphne_server_process, 
                        getattr(self, 'mcp_bridge_process', None),
                        getattr(self, 'celery_worker_process', None),
                        getattr(self, 'interactive_worker_process', None),
                        getattr(self, 'streaming_worker_process', None)]):
                logger.info("All servers stopped.")
            else:
                logger.error("No servers were running.")
                
        except Exception as e:
            logger.error(f"Error stopping servers: {str(e)}")
            logger.debug("Detailed error:", exc_info=True)
