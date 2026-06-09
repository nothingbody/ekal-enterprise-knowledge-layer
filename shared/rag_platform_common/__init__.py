"""
知枢 RAG 平台共享库。

提供 Backend 与 Server 共用的安全、密码、JWT、Token 黑名单、加密等基础能力。
"""
from .password import hash_password, verify_password
from .jwt_utils import create_access_token, create_refresh_token
from .token_blacklist import (
    revoke_token as revoke_token_async,
    is_token_revoked as is_token_revoked_async,
    get_async_redis,
    cleanup_memory_blacklist,
    reset_state as reset_blacklist_state,
)
from .encryption import (
    encrypt_value,
    decrypt_value,
    is_encrypted,
    migrate_to_fernet,
    DecryptionError,
)
from .pagination import (
    PaginatedResult,
    paginate,
    calculate_offset,
    validate_pagination,
)
from .permissions import (
    Role,
    Permission,
    ROLE_HIERARCHY,
    ROLE_PERMISSIONS,
    has_permission,
    has_any_permission,
    has_all_permissions,
    check_role_level,
    get_role_from_string,
)

__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "revoke_token_async",
    "is_token_revoked_async",
    "get_async_redis",
    "cleanup_memory_blacklist",
    "reset_blacklist_state",
    "encrypt_value",
    "decrypt_value",
    "is_encrypted",
    "migrate_to_fernet",
    "DecryptionError",
    "PaginatedResult",
    "paginate",
    "calculate_offset",
    "validate_pagination",
    "Role",
    "Permission",
    "ROLE_HIERARCHY",
    "ROLE_PERMISSIONS",
    "has_permission",
    "has_any_permission",
    "has_all_permissions",
    "check_role_level",
    "get_role_from_string",
]
