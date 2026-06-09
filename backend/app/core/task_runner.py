"""
Task runner that dispatches to Celery when Redis is available,
or falls back to in-process background execution otherwise.

Desktop mode uses a serial queue (single worker thread) to avoid
SQLite / ChromaDB concurrency conflicts that arise when multiple
tasks write to those stores simultaneously from separate threads.
"""
import logging
import queue
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_celery_available: bool | None = None  # cached probe result
_celery_probe_time: float = 0  # monotonic timestamp of last probe
_CELERY_PROBE_TTL = 60  # re-probe every 60 seconds

# Serial task queue for non-Celery (desktop) mode.
_task_queue: queue.Queue | None = None
_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()


def _ensure_worker() -> queue.Queue:
    """Lazily start the single background worker thread and return the queue."""
    global _task_queue, _worker_thread

    if _task_queue is not None and _worker_thread is not None and _worker_thread.is_alive():
        return _task_queue

    with _worker_lock:
        if _task_queue is not None and _worker_thread is not None and _worker_thread.is_alive():
            return _task_queue

        _task_queue = queue.Queue()
        q = _task_queue

        _TASK_TIMEOUT = 600  # 10 minutes max per task
        _MAX_RETRIES = 2

        def _worker():
            while True:
                item = q.get()
                if item is None:
                    break
                func, args = item
                for attempt in range(_MAX_RETRIES + 1):
                    try:
                        # Run task with timeout using a sub-thread
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                            future = pool.submit(func, *args)
                            future.result(timeout=_TASK_TIMEOUT)
                        break  # Success
                    except concurrent.futures.TimeoutError:
                        logger.error(
                            "后台任务超时 (%ds): %s(%s)", _TASK_TIMEOUT, func.__name__, args
                        )
                        break  # Don't retry timeouts
                    except Exception:
                        if attempt < _MAX_RETRIES:
                            delay = 5 * (2 ** attempt)
                            logger.warning(
                                "后台任务失败 (attempt %d/%d): %s(%s)，%ds 后重试",
                                attempt + 1, _MAX_RETRIES + 1, func.__name__, args, delay,
                            )
                            time.sleep(delay)
                        else:
                            logger.exception(
                                "后台任务最终失败: %s(%s)", func.__name__, args
                            )
                q.task_done()

        _worker_thread = threading.Thread(target=_worker, daemon=True, name="task-runner-worker")
        _worker_thread.start()
        logger.info("后台串行任务工作线程已启动")
        return q


def _probe_celery() -> bool:
    """Check if the Celery broker (Redis) is reachable and a worker is active."""
    global _celery_available, _celery_probe_time

    from app.config import settings
    if settings.DESKTOP_MODE:
        _celery_available = False
        return False

    # Use cached result if within TTL
    if _celery_available is not None and (time.monotonic() - _celery_probe_time) < _CELERY_PROBE_TTL:
        return _celery_available

    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=0.5)
        r.ping()
        r.close()
        if not _celery_available:
            logger.info("Redis 已恢复，后台任务切换为 Celery 执行")
        _celery_available = True
    except Exception:
        if _celery_available is not False:
            logger.warning("Redis 不可用，后台任务将使用进程内线程执行（非 Celery）")
        _celery_available = False
    _celery_probe_time = time.monotonic()
    return _celery_available


def dispatch(celery_task, *args: Any) -> None:
    """Dispatch a task: Celery if available, otherwise serial background queue.

    The celery_task must be a Celery task object (decorated with @celery.task).
    The underlying function is called directly for the fallback path.
    """
    if _probe_celery():
        celery_task.delay(*args)
    else:
        q = _ensure_worker()
        q.put((celery_task.run, args))
