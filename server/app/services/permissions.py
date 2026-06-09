"""Reusable resource-level permission checks."""
from fastapi import HTTPException
from app.models.user import User, UserRole
from app.core.security import check_role_level


def require_owner_or_admin(resource_owner_id: int, current_user: User, action: str = "操作") -> None:
    if resource_owner_id == current_user.id:
        return
    if check_role_level(current_user, UserRole.ADMIN):
        return
    raise HTTPException(403, f"无权{action}此资源")
