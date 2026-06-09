"""
权限模块单元测试。
"""
import pytest
from rag_platform_common.permissions import (
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


class TestRoleEnum:
    """测试角色枚举。"""

    def test_role_values(self):
        """验证角色枚举值。"""
        assert Role.SUPER_ADMIN.value == "super_admin"
        assert Role.ADMIN.value == "admin"
        assert Role.ORG_ADMIN.value == "org_admin"
        assert Role.USER.value == "user"
        assert Role.VIEWER.value == "viewer"
        assert Role.GUEST.value == "guest"

    def test_role_is_string_enum(self):
        """角色枚举可直接作为字符串使用。"""
        assert Role.USER == "user"
        assert Role.ADMIN.value == "admin"


class TestPermissionEnum:
    """测试权限枚举。"""

    def test_permission_format(self):
        """验证权限格式为 resource:action。"""
        assert Permission.KB_READ.value == "kb:read"
        assert Permission.DOC_WRITE.value == "doc:write"
        assert Permission.SYSTEM_ADMIN.value == "system:admin"

    def test_all_permissions_have_colon(self):
        """所有权限都应该包含冒号分隔符。"""
        for perm in Permission:
            assert ":" in perm.value, f"{perm} 缺少冒号分隔符"


class TestRoleHierarchy:
    """测试角色层级。"""

    def test_super_admin_highest(self):
        """超级管理员层级最高。"""
        for role in Role:
            if role != Role.SUPER_ADMIN:
                assert ROLE_HIERARCHY[Role.SUPER_ADMIN] > ROLE_HIERARCHY[role]

    def test_guest_lowest(self):
        """访客层级最低。"""
        for role in Role:
            if role != Role.GUEST:
                assert ROLE_HIERARCHY[Role.GUEST] < ROLE_HIERARCHY[role]

    def test_hierarchy_order(self):
        """验证层级顺序。"""
        assert ROLE_HIERARCHY[Role.SUPER_ADMIN] > ROLE_HIERARCHY[Role.ADMIN]
        assert ROLE_HIERARCHY[Role.ADMIN] > ROLE_HIERARCHY[Role.ORG_ADMIN]
        assert ROLE_HIERARCHY[Role.ORG_ADMIN] > ROLE_HIERARCHY[Role.USER]
        assert ROLE_HIERARCHY[Role.USER] > ROLE_HIERARCHY[Role.VIEWER]
        assert ROLE_HIERARCHY[Role.VIEWER] > ROLE_HIERARCHY[Role.GUEST]


class TestRolePermissions:
    """测试角色权限映射。"""

    def test_super_admin_has_all_permissions(self):
        """超级管理员拥有所有权限。"""
        assert ROLE_PERMISSIONS[Role.SUPER_ADMIN] == set(Permission)

    def test_guest_minimal_permissions(self):
        """访客只有最小权限。"""
        guest_perms = ROLE_PERMISSIONS[Role.GUEST]
        assert Permission.KB_READ in guest_perms
        assert Permission.KB_WRITE not in guest_perms
        assert Permission.SYSTEM_ADMIN not in guest_perms

    def test_user_has_basic_write_permissions(self):
        """普通用户有基本写权限。"""
        user_perms = ROLE_PERMISSIONS[Role.USER]
        assert Permission.KB_WRITE in user_perms
        assert Permission.DOC_WRITE in user_perms
        assert Permission.CHAT_WRITE in user_perms

    def test_admin_has_system_permissions(self):
        """管理员有系统权限。"""
        admin_perms = ROLE_PERMISSIONS[Role.ADMIN]
        assert Permission.SYSTEM_READ in admin_perms
        assert Permission.SYSTEM_WRITE in admin_perms
        assert Permission.USER_DELETE in admin_perms


class TestHasPermission:
    """测试 has_permission 函数。"""

    def test_super_admin_has_any_permission(self):
        """超级管理员拥有任何权限。"""
        for perm in Permission:
            assert has_permission(Role.SUPER_ADMIN, perm)

    def test_guest_read_only(self):
        """访客只有读权限。"""
        assert has_permission(Role.GUEST, Permission.KB_READ)
        assert not has_permission(Role.GUEST, Permission.KB_WRITE)

    def test_user_cannot_delete_users(self):
        """普通用户不能删除用户。"""
        assert not has_permission(Role.USER, Permission.USER_DELETE)

    def test_admin_can_delete_users(self):
        """管理员可以删除用户。"""
        assert has_permission(Role.ADMIN, Permission.USER_DELETE)


class TestHasAnyPermission:
    """测试 has_any_permission 函数。"""

    def test_returns_true_if_any_match(self):
        """任一权限匹配则返回 True。"""
        perms = {Permission.KB_WRITE, Permission.SYSTEM_ADMIN}
        assert has_any_permission(Role.USER, perms)  # 有 KB_WRITE

    def test_returns_false_if_none_match(self):
        """无权限匹配则返回 False。"""
        perms = {Permission.SYSTEM_ADMIN, Permission.USER_DELETE}
        assert not has_any_permission(Role.GUEST, perms)

    def test_empty_set_returns_false(self):
        """空集合返回 False。"""
        assert not has_any_permission(Role.SUPER_ADMIN, set())


class TestHasAllPermissions:
    """测试 has_all_permissions 函数。"""

    def test_returns_true_if_all_match(self):
        """所有权限匹配则返回 True。"""
        perms = {Permission.KB_READ, Permission.DOC_READ}
        assert has_all_permissions(Role.USER, perms)

    def test_returns_false_if_any_missing(self):
        """任一权限缺失则返回 False。"""
        perms = {Permission.KB_READ, Permission.SYSTEM_ADMIN}
        assert not has_all_permissions(Role.USER, perms)

    def test_empty_set_returns_true(self):
        """空集合返回 True（无要求）。"""
        assert has_all_permissions(Role.GUEST, set())


class TestCheckRoleLevel:
    """测试 check_role_level 函数。"""

    def test_same_role_passes(self):
        """相同角色通过检查。"""
        assert check_role_level(Role.USER, Role.USER)

    def test_higher_role_passes(self):
        """更高角色通过检查。"""
        assert check_role_level(Role.ADMIN, Role.USER)
        assert check_role_level(Role.SUPER_ADMIN, Role.ADMIN)

    def test_lower_role_fails(self):
        """更低角色不通过检查。"""
        assert not check_role_level(Role.USER, Role.ADMIN)
        assert not check_role_level(Role.GUEST, Role.USER)


class TestGetRoleFromString:
    """测试 get_role_from_string 函数。"""

    def test_exact_match(self):
        """精确匹配。"""
        assert get_role_from_string("user") == Role.USER
        assert get_role_from_string("admin") == Role.ADMIN

    def test_case_insensitive(self):
        """大小写不敏感。"""
        assert get_role_from_string("USER") == Role.USER
        assert get_role_from_string("Admin") == Role.ADMIN
        assert get_role_from_string("SUPER_ADMIN") == Role.SUPER_ADMIN

    def test_invalid_role_raises(self):
        """无效角色抛出异常。"""
        with pytest.raises(ValueError, match="无效的角色"):
            get_role_from_string("invalid_role")

        with pytest.raises(ValueError):
            get_role_from_string("")
