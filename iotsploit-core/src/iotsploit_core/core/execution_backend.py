#!/usr/bin/env python3
"""
Execution Backend Abstraction for IoTSploit Tool Manager
========================================================

Provides multiple execution backends for tool execution:
- Subprocess Backend (default)
- Invoke Backend (task automation)
- sh Backend (pythonic shell)
- Sarge Backend (subprocess wrapper)

This allows plugins to choose the best execution method for their needs.
"""

import os
import sys
import time
import logging
import subprocess
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

@dataclass
class ExecutionResult:
    """Standardized execution result across all backends"""
    success: bool
    return_code: int
    stdout: str
    stderr: str
    execution_time: float
    command: str
    tool_path: str
    backend: str
    metadata: Dict[str, Any] = None

class ExecutionBackend(ABC):
    """Abstract base class for execution backends"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"execution.{name}")
    
    @abstractmethod
    def execute(self, tool_path: str, args: List[str], 
                working_dir: Optional[str] = None,
                env: Optional[Dict[str, str]] = None,
                timeout: Optional[int] = None) -> ExecutionResult:
        """Execute a tool with given arguments"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available"""
        pass
    
    def _prepare_environment(self, env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Prepare execution environment"""
        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)
        return exec_env

class SubprocessBackend(ExecutionBackend):
    """Default subprocess-based execution backend"""
    
    def __init__(self):
        super().__init__("subprocess")
    
    def execute(self, tool_path: str, args: List[str], 
                working_dir: Optional[str] = None,
                env: Optional[Dict[str, str]] = None,
                timeout: Optional[int] = None) -> ExecutionResult:
        """Execute using subprocess module"""
        
        command = [tool_path] + args
        command_str = ' '.join(command)
        exec_env = self._prepare_environment(env)
        
        self.logger.debug(f"Executing: {command_str}")
        start_time = time.time()
        
        try:
            result = subprocess.run(
                command,
                cwd=working_dir,
                env=exec_env,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            execution_time = time.time() - start_time
            
            return ExecutionResult(
                success=result.returncode == 0,
                return_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time=execution_time,
                command=command_str,
                tool_path=tool_path,
                backend=self.name
            )
            
        except subprocess.TimeoutExpired as e:
            execution_time = time.time() - start_time
            return ExecutionResult(
                success=False,
                return_code=-1,
                stdout=e.stdout.decode() if e.stdout else "",
                stderr=f"Command timed out after {timeout} seconds",
                execution_time=execution_time,
                command=command_str,
                tool_path=tool_path,
                backend=self.name
            )
        except Exception as e:
            execution_time = time.time() - start_time
            return ExecutionResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr=str(e),
                execution_time=execution_time,
                command=command_str,
                tool_path=tool_path,
                backend=self.name
            )
    
    def is_available(self) -> bool:
        """Subprocess is always available"""
        return True

class InvokeBackend(ExecutionBackend):
    """Invoke-based execution backend for task automation"""
    
    def __init__(self):
        super().__init__("invoke")
        self._invoke_available = self._check_invoke()
    
    def _check_invoke(self) -> bool:
        """Check if invoke is available"""
        try:
            import invoke
            return True
        except ImportError:
            return False
    
    def execute(self, tool_path: str, args: List[str], 
                working_dir: Optional[str] = None,
                env: Optional[Dict[str, str]] = None,
                timeout: Optional[int] = None) -> ExecutionResult:
        """Execute using invoke"""
        
        if not self._invoke_available:
            raise RuntimeError("Invoke backend not available")
        
        import invoke
        from invoke.exceptions import CommandTimedOut, UnexpectedExit
        
        command_str = f"{tool_path} {' '.join(args)}"
        exec_env = self._prepare_environment(env)
        
        self.logger.debug(f"Executing with invoke: {command_str}")
        start_time = time.time()
        
        try:
            # Create context with environment
            ctx = invoke.Context()
            if working_dir:
                ctx.cd(working_dir)
            
            # Execute command
            result = ctx.run(
                command_str,
                env=exec_env,
                hide=True,
                warn=True,
                timeout=timeout
            )
            
            execution_time = time.time() - start_time
            
            return ExecutionResult(
                success=result.ok,
                return_code=result.return_code,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time=execution_time,
                command=command_str,
                tool_path=tool_path,
                backend=self.name,
                metadata={'invoke_result': result}
            )
            
        except CommandTimedOut as e:
            execution_time = time.time() - start_time
            return ExecutionResult(
                success=False,
                return_code=-1,
                stdout=e.result.stdout if e.result else "",
                stderr=f"Command timed out after {timeout} seconds",
                execution_time=execution_time,
                command=command_str,
                tool_path=tool_path,
                backend=self.name
            )
        except Exception as e:
            execution_time = time.time() - start_time
            return ExecutionResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr=str(e),
                execution_time=execution_time,
                command=command_str,
                tool_path=tool_path,
                backend=self.name
            )
    
    def is_available(self) -> bool:
        """Check if invoke is available"""
        return self._invoke_available

class ShBackend(ExecutionBackend):
    """sh-based execution backend for pythonic shell operations"""
    
    def __init__(self):
        super().__init__("sh")
        self._sh_available = self._check_sh()
    
    def _check_sh(self) -> bool:
        """Check if sh is available"""
        try:
            import sh
            return True
        except ImportError:
            return False
    
    def execute(self, tool_path: str, args: List[str], 
                working_dir: Optional[str] = None,
                env: Optional[Dict[str, str]] = None,
                timeout: Optional[int] = None) -> ExecutionResult:
        """Execute using sh"""
        
        if not self._sh_available:
            raise RuntimeError("sh backend not available")
        
        import sh
        from sh import CommandNotFound, TimeoutException
        
        command_str = f"{tool_path} {' '.join(args)}"
        exec_env = self._prepare_environment(env)
        
        self.logger.debug(f"Executing with sh: {command_str}")
        start_time = time.time()
        
        try:
            # Get the command
            tool_name = os.path.basename(tool_path)
            if hasattr(sh, tool_name):
                cmd = getattr(sh, tool_name)
            else:
                cmd = sh.Command(tool_path)
            
            # Execute with sh
            result = cmd(
                *args,
                _cwd=working_dir,
                _env=exec_env,
                _timeout=timeout,
                _return_cmd=True
            )
            
            execution_time = time.time() - start_time
            
            return ExecutionResult(
                success=result.exit_code == 0,
                return_code=result.exit_code,
                stdout=str(result.stdout),
                stderr=str(result.stderr),
                execution_time=execution_time,
                command=command_str,
                tool_path=tool_path,
                backend=self.name,
                metadata={'sh_result': result}
            )
            
        except TimeoutException as e:
            execution_time = time.time() - start_time
            return ExecutionResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds",
                execution_time=execution_time,
                command=command_str,
                tool_path=tool_path,
                backend=self.name
            )
        except Exception as e:
            execution_time = time.time() - start_time
            return ExecutionResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr=str(e),
                execution_time=execution_time,
                command=command_str,
                tool_path=tool_path,
                backend=self.name
            )
    
    def is_available(self) -> bool:
        """Check if sh is available"""
        return self._sh_available

class SargeBackend(ExecutionBackend):
    """Sarge-based execution backend for advanced subprocess operations"""
    
    def __init__(self):
        super().__init__("sarge")
        self._sarge_available = self._check_sarge()
    
    def _check_sarge(self) -> bool:
        """Check if sarge is available"""
        try:
            import sarge
            return True
        except ImportError:
            return False
    
    def execute(self, tool_path: str, args: List[str], 
                working_dir: Optional[str] = None,
                env: Optional[Dict[str, str]] = None,
                timeout: Optional[int] = None) -> ExecutionResult:
        """Execute using sarge"""
        
        if not self._sarge_available:
            raise RuntimeError("Sarge backend not available")
        
        import sarge
        
        command_str = f"{tool_path} {' '.join(args)}"
        exec_env = self._prepare_environment(env)
        
        self.logger.debug(f"Executing with sarge: {command_str}")
        start_time = time.time()
        
        try:
            # Execute with sarge
            process = sarge.run(
                command_str,
                cwd=working_dir,
                env=exec_env,
                stdout=sarge.Capture(),
                stderr=sarge.Capture(),
                async_=False
            )
            
            # Wait for completion with timeout
            if timeout:
                process.wait(timeout=timeout)
            else:
                process.wait()
            
            execution_time = time.time() - start_time
            
            return ExecutionResult(
                success=process.returncode == 0,
                return_code=process.returncode,
                stdout=process.stdout.text if process.stdout else "",
                stderr=process.stderr.text if process.stderr else "",
                execution_time=execution_time,
                command=command_str,
                tool_path=tool_path,
                backend=self.name,
                metadata={'sarge_process': process}
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            return ExecutionResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr=str(e),
                execution_time=execution_time,
                command=command_str,
                tool_path=tool_path,
                backend=self.name
            )
    
    def is_available(self) -> bool:
        """Check if sarge is available"""
        return self._sarge_available

class ExecutionBackendManager:
    """Manages multiple execution backends"""
    
    def __init__(self):
        self.backends: Dict[str, ExecutionBackend] = {}
        self.default_backend = "subprocess"
        self._initialize_backends()
    
    def _initialize_backends(self):
        """Initialize all available backends"""
        backends = [
            SubprocessBackend(),
            InvokeBackend(),
            ShBackend(),
            SargeBackend()
        ]
        
        for backend in backends:
            if backend.is_available():
                self.backends[backend.name] = backend
                logger.debug(f"Registered execution backend: {backend.name}")
            else:
                logger.debug(f"Backend not available: {backend.name}")
    
    def get_backend(self, name: Optional[str] = None) -> ExecutionBackend:
        """Get execution backend by name"""
        backend_name = name or self.default_backend
        
        if backend_name not in self.backends:
            if backend_name == self.default_backend:
                raise RuntimeError(f"Default backend '{backend_name}' not available")
            else:
                logger.warning(f"Backend '{backend_name}' not available, falling back to default")
                backend_name = self.default_backend
        
        return self.backends[backend_name]
    
    def list_available_backends(self) -> List[str]:
        """List all available backends"""
        return list(self.backends.keys())

    def get_status(self) -> Dict[str, Any]:
        """Get status of all execution backends"""
        return {
            'default_backend': self.default_backend,
            'available_backends': self.list_available_backends(),
            'total_backends': len(self.backends),
        }

    def set_default_backend(self, name: str):
        """Set default execution backend"""
        if name not in self.backends:
            raise ValueError(f"Backend '{name}' not available")
        self.default_backend = name
        logger.info(f"Default execution backend set to: {name}")
    
    def execute(self, tool_path: str, args: List[str], 
                backend: Optional[str] = None, **kwargs) -> ExecutionResult:
        """Execute using specified or default backend"""
        execution_backend = self.get_backend(backend)
        return execution_backend.execute(tool_path, args, **kwargs)

# Singleton instance
_backend_manager = None

def get_execution_backend_manager() -> ExecutionBackendManager:
    """Get singleton execution backend manager"""
    global _backend_manager
    if _backend_manager is None:
        _backend_manager = ExecutionBackendManager()
    return _backend_manager 