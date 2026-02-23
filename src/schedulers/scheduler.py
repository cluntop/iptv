import asyncio
import threading
from typing import Dict, Any, Callable, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

from ..utils import get_logger

logger = get_logger("scheduler")


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    name: str
    func: Callable
    schedule: str
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None


class TaskScheduler:
    def __init__(self, db_manager=None):
        self.db = db_manager
        self.tasks: Dict[str, Task] = {}
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def add_task(
        self,
        name: str,
        func: Callable,
        schedule: str,
        args: tuple = (),
        kwargs: Dict[str, Any] = None,
        enabled: bool = True,
    ) -> Task:
        task = Task(
            name=name,
            func=func,
            schedule=schedule,
            args=args,
            kwargs=kwargs or {},
            enabled=enabled,
        )

        task.next_run = self._parse_schedule(schedule, datetime.now())

        with self._lock:
            self.tasks[name] = task

        logger.info(f"Added task: {name} with schedule: {schedule}")
        return task

    def remove_task(self, name: str) -> bool:
        with self._lock:
            if name in self.tasks:
                del self.tasks[name]
                logger.info(f"Removed task: {name}")
                return True
        return False

    def enable_task(self, name: str) -> bool:
        with self._lock:
            if name in self.tasks:
                self.tasks[name].enabled = True
                logger.info(f"Enabled task: {name}")
                return True
        return False

    def disable_task(self, name: str) -> bool:
        with self._lock:
            if name in self.tasks:
                self.tasks[name].enabled = False
                logger.info(f"Disabled task: {name}")
                return True
        return False

    def get_task(self, name: str) -> Optional[Task]:
        with self._lock:
            return self.tasks.get(name)

    def get_all_tasks(self) -> List[Task]:
        with self._lock:
            return list(self.tasks.values())

    def _parse_schedule(self, schedule: str, now: datetime) -> datetime:
        if schedule.startswith("daily@"):
            hour = int(schedule.split("@")[1])
            next_run = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run

        elif schedule.startswith("hourly"):
            next_run = now + timedelta(hours=1)
            next_run = next_run.replace(minute=0, second=0, microsecond=0)
            return next_run

        elif schedule.startswith("interval@"):
            minutes = int(schedule.split("@")[1])
            return now + timedelta(minutes=minutes)

        elif schedule.startswith("weekly@"):
            weekday = int(schedule.split("@")[1])
            hour = int(schedule.split("@")[2])
            days_ahead = (weekday - now.weekday() + 7) % 7
            if days_ahead == 0 and now.hour >= hour:
                days_ahead = 7
            next_run = now + timedelta(days=days_ahead)
            next_run = next_run.replace(hour=hour, minute=0, second=0, microsecond=0)
            return next_run

        return now + timedelta(minutes=30)

    def _execute_task(self, task: Task):
        task.status = TaskStatus.RUNNING
        task.last_run = datetime.now()
        logger.info(f"Executing task: {task.name}")

        try:
            if asyncio.iscoroutinefunction(task.func):
                result = asyncio.run(task.func(*task.args, **task.kwargs))
            else:
                result = task.func(*task.args, **task.kwargs)

            task.status = TaskStatus.COMPLETED
            task.result = str(result)
            task.error = None
            logger.info(f"Task {task.name} completed successfully")

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            logger.error(f"Task {task.name} failed: {e}")

        task.next_run = self._parse_schedule(task.schedule, datetime.now())

    def _run_loop(self):
        logger.info("Scheduler loop started")

        while not self._stop_event.is_set():
            now = datetime.now()

            with self._lock:
                for task in self.tasks.values():
                    if not task.enabled:
                        continue

                    if task.next_run and task.next_run <= now:
                        if task.status != TaskStatus.RUNNING:
                            threading.Thread(
                                target=self._execute_task, args=(task,), daemon=True
                            ).start()

            self._stop_event.wait(60)

        logger.info("Scheduler loop stopped")

    def start(self):
        if self.running:
            logger.warning("Scheduler is already running")
            return

        self.running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Scheduler started")

    def stop(self):
        if not self.running:
            return

        self.running = False
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=5)

        logger.info("Scheduler stopped")

    def run_task_now(self, name: str) -> bool:
        with self._lock:
            if name in self.tasks:
                task = self.tasks[name]
                if task.status != TaskStatus.RUNNING:
                    threading.Thread(
                        target=self._execute_task, args=(task,), daemon=True
                    ).start()
                    return True
        return False

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "running": self.running,
                "total_tasks": len(self.tasks),
                "enabled_tasks": sum(1 for t in self.tasks.values() if t.enabled),
                "tasks": [
                    {
                        "name": t.name,
                        "status": t.status.value,
                        "enabled": t.enabled,
                        "last_run": t.last_run.isoformat() if t.last_run else None,
                        "next_run": t.next_run.isoformat() if t.next_run else None,
                        "result": t.result,
                        "error": t.error,
                    }
                    for t in self.tasks.values()
                ],
                "timestamp": datetime.now().isoformat(),
            }


_scheduler: Optional[TaskScheduler] = None


def get_scheduler(db_manager=None) -> TaskScheduler:
    global _scheduler

    if _scheduler is None:
        _scheduler = TaskScheduler(db_manager)

    return _scheduler


def init_scheduler(db_manager=None) -> TaskScheduler:
    global _scheduler

    if _scheduler is not None:
        _scheduler.stop()

    _scheduler = TaskScheduler(db_manager)
    return _scheduler
