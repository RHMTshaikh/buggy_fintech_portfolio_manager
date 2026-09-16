"""
Celery Worker Initialization & Async Bridging.
Configures the message broker and provides a safe execution boundary for async tasks.
"""

import asyncio
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
    Decorator to safely execute asynchronous coroutines within synchronous Celery tasks.
    It provisions a new event loop per task execution to prevent fork-related loop corruption.
    """
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            # Python 3.7+ safe async execution
            return asyncio.run(coro(*args, **kwargs))
        except Exception as e:
            # In a real system, integrate with Sentry/Datadog here
            print(f"CRITICAL: Async task execution failed: {str(e)}")
            raise
    return wrapper