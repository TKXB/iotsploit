#!/usr/bin/env python3
"""Execution queue and scheduler for tool execution."""

import time
import threading
import queue
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from concurrent.futures import ThreadPoolExecutor, Future
import uuid

from .execution_backend import ExecutionResult, get_execution_backend_manager

logger = logging.getLogger(__name__)

class TaskPriority(IntEnum):
    """Task priority levels (lower number = higher priority)"""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4

class TaskStatus(Enum):
    """Task execution status"""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"

@dataclass
class ExecutionTask:
    """Represents a tool execution task"""
    task_id: str
    tool_name: str
    tool_path: str
    args: List[str]
    priority: TaskPriority = TaskPriority.NORMAL
    timeout: Optional[int] = None
    working_dir: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    backend: Optional[str] = None
    callback: Optional[Callable] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Status tracking
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[ExecutionResult] = None
    error: Optional[str] = None

@dataclass
class QueueStats:
    """Execution queue statistics"""
    total_tasks: int = 0
    pending_tasks: int = 0
    running_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    cancelled_tasks: int = 0
    average_execution_time: float = 0.0
    queue_size: int = 0

class ExecutionQueue:
    """Priority-based execution queue with scheduling"""
    
    def __init__(self, max_workers: int = 4, max_queue_size: int = 1000):
        self.max_workers = max_workers
        self.max_queue_size = max_queue_size
        
        # Task storage
        self.tasks: Dict[str, ExecutionTask] = {}
        self.task_queue = queue.PriorityQueue(maxsize=max_queue_size)
        
        # Execution management
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.running_tasks: Dict[str, Future] = {}
        
        # Synchronization
        self._lock = threading.RLock()
        self._shutdown = False
        
        # Statistics
        self.stats = QueueStats()
        
        # Backend manager
        self.backend_manager = get_execution_backend_manager()
        
        logger.info(f"Execution queue initialized with {max_workers} workers")
    
    def submit_task(self, tool_name: str, tool_path: str, args: List[str],
                   priority: TaskPriority = TaskPriority.NORMAL,
                   timeout: Optional[int] = None,
                   working_dir: Optional[str] = None,
                   env: Optional[Dict[str, str]] = None,
                   backend: Optional[str] = None,
                   callback: Optional[Callable] = None,
                   metadata: Optional[Dict[str, Any]] = None) -> str:
        """Submit a task for execution"""
        
        if self._shutdown:
            raise RuntimeError("Execution queue is shutdown")
        
        if self.task_queue.qsize() >= self.max_queue_size:
            raise RuntimeError("Execution queue is full")
        
        # Create task
        task_id = str(uuid.uuid4())
        task = ExecutionTask(
            task_id=task_id,
            tool_name=tool_name,
            tool_path=tool_path,
            args=args,
            priority=priority,
            timeout=timeout,
            working_dir=working_dir,
            env=env,
            backend=backend,
            callback=callback,
            metadata=metadata or {}
        )
        
        with self._lock:
            # Store task
            self.tasks[task_id] = task
            task.status = TaskStatus.QUEUED
            
            # Add to priority queue (priority, creation_time, task_id)
            self.task_queue.put((priority.value, task.created_at, task_id))
            
            # Update stats
            self.stats.total_tasks += 1
            self.stats.pending_tasks += 1
            self.stats.queue_size = self.task_queue.qsize()
        
        logger.debug(f"Task {task_id} queued with priority {priority.name}")
        
        
        self._process_queue()
        
        return task_id
    
    def _process_queue(self):
        """Process queued tasks"""
        with self._lock:
            # Check if we can start more tasks
            while (len(self.running_tasks) < self.max_workers and 
                   not self.task_queue.empty() and 
                   not self._shutdown):
                
                try:
                    # Get highest priority task
                    priority, created_at, task_id = self.task_queue.get_nowait()
                    
                    if task_id not in self.tasks:
                        continue  # Task was cancelled
                    
                    task = self.tasks[task_id]
                    
                    # Submit for execution
                    future = self.executor.submit(self._execute_task, task)
                    self.running_tasks[task_id] = future
                    
                    # Update task status
                    task.status = TaskStatus.RUNNING
                    task.started_at = time.time()
                    
                    # Update stats
                    self.stats.pending_tasks -= 1
                    self.stats.running_tasks += 1
                    self.stats.queue_size = self.task_queue.qsize()
                    
                    logger.debug(f"Started execution of task {task_id}")
                    
                except queue.Empty:
                    break
    
    def _execute_task(self, task: ExecutionTask) -> ExecutionResult:
        """Execute a single task"""
        try:
            logger.info(f"Executing task {task.task_id}: {task.tool_name}")
            
            # Execute using backend manager
            result = self.backend_manager.execute(
                tool_path=task.tool_path,
                args=task.args,
                backend=task.backend,
                working_dir=task.working_dir,
                env=task.env,
                timeout=task.timeout
            )
            
            # Update task
            with self._lock:
                task.result = result
                task.completed_at = time.time()
                task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
                
                # Remove from running tasks
                if task.task_id in self.running_tasks:
                    del self.running_tasks[task.task_id]
                
                # Update stats
                self.stats.running_tasks -= 1
                if result.success:
                    self.stats.completed_tasks += 1
                else:
                    self.stats.failed_tasks += 1
                
                # Update average execution time
                self._update_average_execution_time(result.execution_time)
            
            # Call callback if provided
            if task.callback:
                try:
                    task.callback(task, result)
                except Exception as e:
                    logger.error(f"Task callback failed: {e}")
            
            logger.info(f"Task {task.task_id} completed: {result.success}")
            
            # Process more tasks
            self._process_queue()
            
            return result
            
        except Exception as e:
            logger.error(f"Task {task.task_id} execution failed: {e}")
            
            # Update task
            with self._lock:
                task.error = str(e)
                task.completed_at = time.time()
                task.status = TaskStatus.FAILED
                
                # Remove from running tasks
                if task.task_id in self.running_tasks:
                    del self.running_tasks[task.task_id]
                
                # Update stats
                self.stats.running_tasks -= 1
                self.stats.failed_tasks += 1
            
            # Process more tasks
            self._process_queue()
            
            raise
    
    def _update_average_execution_time(self, execution_time: float):
        """Update average execution time"""
        completed = self.stats.completed_tasks
        if completed == 1:
            self.stats.average_execution_time = execution_time
        else:
            # Running average
            current_avg = self.stats.average_execution_time
            self.stats.average_execution_time = (
                (current_avg * (completed - 1) + execution_time) / completed
            )
    
    def get_task(self, task_id: str) -> Optional[ExecutionTask]:
        """Get task by ID"""
        with self._lock:
            return self.tasks.get(task_id)
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task"""
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return False
            
            if task.status == TaskStatus.RUNNING:
                # Try to cancel running task
                future = self.running_tasks.get(task_id)
                if future and future.cancel():
                    task.status = TaskStatus.CANCELLED
                    task.completed_at = time.time()
                    del self.running_tasks[task_id]
                    self.stats.running_tasks -= 1
                    self.stats.cancelled_tasks += 1
                    return True
                return False
            
            elif task.status in [TaskStatus.PENDING, TaskStatus.QUEUED]:
                # Cancel queued task
                task.status = TaskStatus.CANCELLED
                task.completed_at = time.time()
                self.stats.pending_tasks -= 1
                self.stats.cancelled_tasks += 1
                return True
            
            return False
    
    def wait_for_task(self, task_id: str, timeout: Optional[float] = None) -> Optional[ExecutionResult]:
        """Wait for task completion"""
        task = self.get_task(task_id)
        if not task:
            return None
        
        start_time = time.time()
        while task.status in [TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING]:
            if timeout and (time.time() - start_time) > timeout:
                return None
            time.sleep(0.1)
        
        return task.result
    
    def list_tasks(self, status: Optional[TaskStatus] = None) -> List[ExecutionTask]:
        """List tasks, optionally filtered by status"""
        with self._lock:
            tasks = list(self.tasks.values())
            if status:
                tasks = [t for t in tasks if t.status == status]
            return sorted(tasks, key=lambda t: t.created_at)
    
    def get_stats(self) -> QueueStats:
        """Get queue statistics"""
        with self._lock:
            stats = QueueStats(
                total_tasks=self.stats.total_tasks,
                pending_tasks=self.stats.pending_tasks,
                running_tasks=self.stats.running_tasks,
                completed_tasks=self.stats.completed_tasks,
                failed_tasks=self.stats.failed_tasks,
                cancelled_tasks=self.stats.cancelled_tasks,
                average_execution_time=self.stats.average_execution_time,
                queue_size=self.task_queue.qsize()
            )
            return stats
    
    def clear_completed_tasks(self, older_than: Optional[float] = None):
        """Clear completed tasks"""
        with self._lock:
            current_time = time.time()
            to_remove = []
            
            for task_id, task in self.tasks.items():
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    if older_than is None or (task.completed_at and 
                                            (current_time - task.completed_at) > older_than):
                        to_remove.append(task_id)
            
            for task_id in to_remove:
                del self.tasks[task_id]
            
            logger.info(f"Cleared {len(to_remove)} completed tasks")
    
    def shutdown(self, wait: bool = True):
        """Shutdown the execution queue"""
        logger.info("Shutting down execution queue...")
        
        with self._lock:
            self._shutdown = True
        
        if wait:
            # Cancel all pending tasks
            for task_id, task in list(self.tasks.items()):
                if task.status in [TaskStatus.PENDING, TaskStatus.QUEUED]:
                    self.cancel_task(task_id)
        
        # Shutdown executor
        self.executor.shutdown(wait=wait)
        logger.info("Execution queue shutdown complete")

class TaskScheduler:
    """Task scheduler with simple cron-like capabilities"""
    
    def __init__(self, execution_queue: ExecutionQueue):
        self.execution_queue = execution_queue
        self.scheduled_tasks: Dict[str, Dict] = {}
        self._scheduler_thread = None
        self._shutdown = False
        self._lock = threading.Lock()
    
    def schedule_task(self, schedule_id: str, tool_name: str, tool_path: str, 
                     args: List[str], cron_expression: str, **kwargs) -> str:
        """Schedule a recurring task"""
        with self._lock:
            self.scheduled_tasks[schedule_id] = {
                'tool_name': tool_name,
                'tool_path': tool_path,
                'args': args,
                'cron_expression': cron_expression,
                'kwargs': kwargs,
                'last_run': None,
                'next_run': self._calculate_next_run(cron_expression)
            }
        
        if not self._scheduler_thread:
            self._start_scheduler()
        
        return schedule_id
    
    def _calculate_next_run(self, cron_expression: str) -> float:
        """Calculate next run time (simplified)"""
        return time.time() + 60
    
    def _start_scheduler(self):
        """Start the scheduler thread"""
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._scheduler_thread.start()
    
    def _scheduler_loop(self):
        """Main scheduler loop"""
        while not self._shutdown:
            current_time = time.time()
            
            with self._lock:
                for schedule_id, task_info in self.scheduled_tasks.items():
                    if current_time >= task_info['next_run']:
                        self.execution_queue.submit_task(
                            tool_name=task_info['tool_name'],
                            tool_path=task_info['tool_path'],
                            args=task_info['args'],
                            **task_info['kwargs']
                        )
                        
                        # Update next run
                        task_info['last_run'] = current_time
                        task_info['next_run'] = self._calculate_next_run(
                            task_info['cron_expression']
                        )
            
            time.sleep(1)
    
    def shutdown(self):
        """Shutdown the scheduler"""
        self._shutdown = True
        if self._scheduler_thread:
            self._scheduler_thread.join()

_execution_queue = None
_task_scheduler = None

def get_execution_queue() -> ExecutionQueue:
    """Get singleton execution queue"""
    global _execution_queue
    if _execution_queue is None:
        _execution_queue = ExecutionQueue()
    return _execution_queue

def get_task_scheduler() -> TaskScheduler:
    """Get singleton task scheduler"""
    global _task_scheduler
    if _task_scheduler is None:
        _task_scheduler = TaskScheduler(get_execution_queue())
    return _task_scheduler 