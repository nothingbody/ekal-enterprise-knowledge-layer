"""
权限与角色常量模块。

提供 Backend 与 Server 共用的角色定义、权限常量与映射。
"""
from enum import Enum
from typing import Set, Dict


class Role(str, Enum):
    """用户角色枚举。"""
    SUPER_ADMIN = "super_admin"  # 超级管理员
    ADMIN = "admin"              # 平台管理员
    ORG_ADMIN = "org_admin"      # 组织管理员
    USER = "user"                # 普通用户
    VIEWER = "viewer"            # 只读用户
    GUEST = "guest"              # 访客


class Permission(str, Enum):
    """权限枚举。"""
    # 知识库权限
    KB_READ = "kb:read"
    KB_WRITE = "kb:write"
    KB_DELETE = "kb:delete"
    KB_ADMIN = "kb:admin"

    # 文档权限
    DOC_READ = "doc:read"
    DOC_WRITE = "doc:write"
    DOC_DELETE = "doc:delete"

    # 对话权限
    CHAT_READ = "chat:read"
    CHAT_WRITE = "chat:write"
    CHAT_DELETE = "chat:delete"

    # 模型配置权限
    MODEL_READ = "model:read"
    MODEL_WRITE = "model:write"
    MODEL_DELETE = "model:delete"

    # 用户管理权限
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_DELETE = "user:delete"

    # 组织管理权限
    ORG_READ = "org:read"
    ORG_WRITE = "org:write"
    ORG_DELETE = "org:delete"

    # 系统管理权限
    SYSTEM_READ = "system:read"
    SYSTEM_WRITE = "system:write"
    SYSTEM_ADMIN = "system:admin"

    # 工作空间权限
    WORKSPACE_READ = "workspace:read"
    WORKSPACE_WRITE = "workspace:write"
    WORKSPACE_ADMIN = "workspace:admin"

    # 技能权限
    SKILL_READ = "skill:read"
    SKILL_WRITE = "skill:write"
    SKILL_PUBLISH = "skill:publish"

    # API 密钥权限
    API_KEY_READ = "api_key:read"
    API_KEY_WRITE = "api_key:write"


# 角色层级（数值越大权限越高）
ROLE_HIERARCHY: Dict[Role, int] = {
    Role.SUPER_ADMIN: 100,
    Role.ADMIN: 80,
    Role.ORG_ADMIN: 60,
    Role.USER: 40,
    Role.VIEWER: 20,
    Role.GUEST: 10,
}


# 角色默认权限映射
ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.GUEST: {
        Permission.KB_READ,
        Permission.DOC_READ,
        Permission.CHAT_READ,
    },
    Role.VIEWER: {
        Permission.KB_READ,
        Permission.DOC_READ,
        Permission.CHAT_READ,
        Permission.MODEL_READ,
        Permission.SKILL_READ,
    },
    Role.USER: {
        Permission.KB_READ,
        Permission.KB_WRITE,
        Permission.DOC_READ,
        Permission.DOC_WRITE,
        Permission.CHAT_READ,
        Permission.CHAT_WRITE,
        Permission.MODEL_READ,
        Permission.SKILL_READ,
        Permission.SKILL_WRITE,
        Permission.WORKSPACE_READ,
        Permission.API_KEY_READ,
        Permission.API_KEY_WRITE,
    },
    Role.ORG_ADMIN: {
        Permission.KB_READ,
        Permission.KB_WRITE,
        Permission.KB_DELETE,
        Permission.KB_ADMIN,
        Permission.DOC_READ,
        Permission.DOC_WRITE,
        Permission.DOC_DELETE,
        Permission.CHAT_READ,
        Permission.CHAT_WRITE,
        Permission.CHAT_DELETE,
        Permission.MODEL_READ,
        Permission.MODEL_WRITE,
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.ORG_READ,
        Permission.SKILL_READ,
        Permission.SKILL_WRITE,
        Permission.WORKSPACE_READ,
        Permission.WORKSPACE_WRITE,
        Permission.API_KEY_READ,
        Permission.API_KEY_WRITE,
    },
    Role.ADMIN: {
        Permission.KB_READ,
        Permission.KB_WRITE,
        Permission.KB_DELETE,
        Permission.KB_ADMIN,
        Permission.DOC_READ,
        Permission.DOC_WRITE,
        Permission.DOC_DELETE,
        Permission.CHAT_READ,
        Permission.CHAT_WRITE,
        Permission.CHAT_DELETE,
        Permission.MODEL_READ,
        Permission.MODEL_WRITE,
        Permission.MODEL_DELETE,
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.USER_DELETE,
        Permission.ORG_READ,
        Permission.ORG_WRITE,
        Permission.SYSTEM_READ,
        Permission.SYSTEM_WRITE,
        Permission.SKILL_READ,
        Permission.SKILL_WRITE,
        Permission.SKILL_PUBLISH,
        Permission.WORKSPACE_READ,
        Permission.WORKSPACE_WRITE,
        Permission.WORKSPACE_ADMIN,
        Permission.API_KEY_READ,
        Permission.API_KEY_WRITE,
    },
    Role.SUPER_ADMIN: set(Permission),  # 超级管理员拥有所有权限
}


def has_permission(role: Role, permission: Permission) -> bool:
    """
    检查角色是否拥有指定权限。

    :param role: 用户角色
    :param permission: 要检查的权限
    :return: True 表示拥有权限
    """
    return permission in ROLE_PERMISSIONS.get(role, set())


def has_any_permission(role: Role, permissions: Set[Permission]) -> bool:
    """
    检查角色是否拥有任一指定权限。

    :param role: 用户角色
    :param permissions: 权限集合
    :return: True 表示拥有至少一个权限
    """
    role_perms = ROLE_PERMISSIONS.get(role, set())
    return bool(role_perms & permissions)


def has_all_permissions(role: Role, permissions: Set[Permission]) -> bool:
    """
    检查角色是否拥有所有指定权限。

    :param role: 用户角色
    :param permissions: 权限集合
    :return: True 表示拥有所有权限
    """
    role_perms = ROLE_PERMISSIONS.get(role, set())
    return permissions <= role_perms


def check_role_level(role: Role, min_role: Role) -> bool:
    """
    检查角色层级是否达到最低要求。

    :param role: 用户角色
    :param min_role: 最低要求角色
    :return: True 表示达到要求
    """
    return ROLE_HIERARCHY.get(role, 0) >= ROLE_HIERARCHY.get(min_role, 0)


def get_role_from_string(role_str: str) -> Role:
    """
    从字符串转换为 Role 枚举。

    :param role_str: 角色字符串
    :return: Role 枚举
    :raises ValueError: 无效角色字符串
    """
    try:
        return Role(role_str)
    except ValueError:
        # 尝试大小写不敏感匹配
        for role in Role:
            if role.value.lower() == role_str.lower():
                return role
        raise ValueError(f"无效的角色: {role_str}")
