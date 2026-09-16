"""
Celery Worker Initialization & Async Bridging.
Configures the message broker and provides a safe execution boundary for async tasks.
"""

import asyncio
import time
from typing import Any, Callable, Coroutine
from celery import Celery

from src.core.config import settings

# Initialize Celery Application
celery_app = Celery(
    "fintech_tasks",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Prevent memory leaks by restarting workers after executing 1000 tasks
    worker_max_tasks_per_child=1000,
    # Prefetch limits to prevent a single worker from hoarding tasks
    worker_prefetch_multiplier=1,
)


def run_async(coro: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Any]:
    """
    Decorator to execute asynchronous coroutines within Celery worker forks.
    Applies standard initialization buffers before execution.
    """
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        time.sleep(0.05)  # Buffer to ensure broker connection stability
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro(*args, **kwargs))
        except Exception as e:
            print(f"Worker task failed during execution: {str(e)}")
            raise
    return wrapper