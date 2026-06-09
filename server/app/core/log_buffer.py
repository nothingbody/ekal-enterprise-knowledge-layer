"""In-memory ring buffer for recent application log entries."""
import logging
from collections import deque
from datetime import datetime, timezone

_MAX_ENTRIES = 500
_buffer: deque = deque(maxlen=_MAX_ENTRIES)


class BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": self.format(record),
        }
        if record.exc_info and record.exc_info[1]:
            entry["exception"] = logging.Formatter().formatException(record.exc_info)
        _buffer.append(entry)


def get_recent_logs(limit: int = 100, level: str | None = None) -> list[dict]:
    entries = list(_buffer)
    if level:
        entries = [e for e in entries if e["level"] == level.upper()]
    return entries[-limit:]


def setup_log_buffer():
    handler = BufferHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    for name in ("central_server", "uvicorn", "uvicorn.access", "uvicorn.error", "audit", "app"):
        logging.getLogger(name).addHandler(handler)
