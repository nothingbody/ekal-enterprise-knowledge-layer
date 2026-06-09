"""Audit logging utilities for tracking admin operations."""
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

logger = logging.getLogger("audit")

AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


async def record_audit(
    db: AsyncSession,
    *,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    detail: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    status_code: Optional[int] = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        username=username,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        ip_address=ip_address,
        user_agent=user_agent,
        status_code=status_code,
    )
    db.add(entry)
    await db.commit()
    logger.info(
        "AUDIT %s user=%s resource=%s/%s",
        action, username or user_id, resource_type, resource_id,
    )
    return entry


def parse_action_from_request(method: str, path: str) -> tuple[str, Optional[str], Optional[str]]:
    """Derive action, resource_type, resource_id from request method + path."""
    parts = [p for p in path.split("/") if p and p not in ("api", "v1")]

    action_map = {"POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}
    action_verb = action_map.get(method, method.lower())

    resource_type = parts[0] if parts else None
    resource_id = parts[1] if len(parts) > 1 else None

    if len(parts) >= 3:
        action = f"{action_verb}_{parts[-1]}"
    else:
        action = action_verb

    return action, resource_type, resource_id
