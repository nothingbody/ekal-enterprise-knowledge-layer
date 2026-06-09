"""
Workspace 数据隔离单元测试。

验证 access_service 中的权限控制逻辑：
1. 角色权限层级正确（OWNER/ADMIN/MEMBER/VIEWER）
2. _build_access_payload 正确计算权限
"""
import pytest
from unittest.mock import MagicMock

from app.models.workspace import WorkspaceRole
from app.services.access_service import (
    WRITE_ROLES,
    MANAGE_ROLES,
    _build_access_payload,
)


class TestRoleConstants:
    """角色常量测试。"""

    def test_write_roles_includes_owner_admin_member(self):
        """写权限角色包含 OWNER、ADMIN、MEMBER。"""
        assert WorkspaceRole.OWNER in WRITE_ROLES
        assert WorkspaceRole.ADMIN in WRITE_ROLES
        assert WorkspaceRole.MEMBER in WRITE_ROLES
        assert WorkspaceRole.VIEWER not in WRITE_ROLES

    def test_manage_roles_includes_owner_admin_only(self):
        """管理权限角色仅包含 OWNER、ADMIN。"""
        assert WorkspaceRole.OWNER in MANAGE_ROLES
        assert WorkspaceRole.ADMIN in MANAGE_ROLES
        assert WorkspaceRole.MEMBER not in MANAGE_ROLES
        assert WorkspaceRole.VIEWER not in MANAGE_ROLES


class TestBuildAccessPayload:
    """_build_access_payload 测试。"""

    def _mock_kb(self, user_id: int):
        """创建模拟知识库对象。"""
        kb = MagicMock()
        kb.user_id = user_id
        return kb

    def test_creator_has_full_access(self):
        """知识库创建者拥有完整权限。"""
        kb = self._mock_kb(user_id=1)
        payload = _build_access_payload(
            kb=kb,
            workspace_id=None,
            workspace_name=None,
            member_role=None,
            user_id=1,  # 创建者
        )
        assert payload["can_read"] is True
        assert payload["can_write"] is True
        assert payload["can_manage"] is True
        assert payload["access_role"] == "owner"

    def test_non_creator_without_workspace_has_no_access(self):
        """非创建者且无 Workspace 成员资格时无权限。"""
        kb = self._mock_kb(user_id=1)
        payload = _build_access_payload(
            kb=kb,
            workspace_id=None,
            workspace_name=None,
            member_role=None,
            user_id=2,  # 非创建者
        )
        assert payload["can_read"] is False
        assert payload["can_write"] is False
        assert payload["can_manage"] is False

    def test_workspace_owner_has_full_access(self):
        """Workspace OWNER 拥有完整权限。"""
        kb = self._mock_kb(user_id=1)
        payload = _build_access_payload(
            kb=kb,
            workspace_id=10,
            workspace_name="Test Workspace",
            member_role=WorkspaceRole.OWNER,
            user_id=2,  # 非创建者但是 OWNER
        )
        assert payload["can_read"] is True
        assert payload["can_write"] is True
        assert payload["can_manage"] is True
        assert payload["access_role"] == "owner"

    def test_workspace_admin_has_full_access(self):
        """Workspace ADMIN 拥有完整权限。"""
        kb = self._mock_kb(user_id=1)
        payload = _build_access_payload(
            kb=kb,
            workspace_id=10,
            workspace_name="Test Workspace",
            member_role=WorkspaceRole.ADMIN,
            user_id=2,
        )
        assert payload["can_read"] is True
        assert payload["can_write"] is True
        assert payload["can_manage"] is True
        assert payload["access_role"] == "admin"

    def test_workspace_member_can_read_and_write(self):
        """Workspace MEMBER 有读写权限但无管理权限。"""
        kb = self._mock_kb(user_id=1)
        payload = _build_access_payload(
            kb=kb,
            workspace_id=10,
            workspace_name="Test Workspace",
            member_role=WorkspaceRole.MEMBER,
            user_id=2,
        )
        assert payload["can_read"] is True
        assert payload["can_write"] is True
        assert payload["can_manage"] is False
        assert payload["access_role"] == "member"

    def test_workspace_viewer_has_readonly_access(self):
        """Workspace VIEWER 仅有只读权限。"""
        kb = self._mock_kb(user_id=1)
        payload = _build_access_payload(
            kb=kb,
            workspace_id=10,
            workspace_name="Test Workspace",
            member_role=WorkspaceRole.VIEWER,
            user_id=2,
        )
        assert payload["can_read"] is True
        assert payload["can_write"] is False
        assert payload["can_manage"] is False
        assert payload["access_role"] == "viewer"

    def test_payload_includes_workspace_info(self):
        """Payload 包含 Workspace 信息。"""
        kb = self._mock_kb(user_id=1)
        payload = _build_access_payload(
            kb=kb,
            workspace_id=10,
            workspace_name="My Workspace",
            member_role=WorkspaceRole.MEMBER,
            user_id=2,
        )
        assert payload["workspace_id"] == 10
        assert payload["workspace_name"] == "My Workspace"
        assert payload["kb"] is kb


class TestWorkspaceIsolationLogic:
    """Workspace 隔离逻辑测试。"""

    def test_different_workspace_no_access(self):
        """不同 Workspace 的用户无法访问。"""
        kb = MagicMock()
        kb.user_id = 1
        
        # 用户 3 不是任何 Workspace 的成员（member_role=None）
        payload = _build_access_payload(
            kb=kb,
            workspace_id=10,
            workspace_name="Other Workspace",
            member_role=None,  # 不是成员
            user_id=3,
        )
        assert payload["can_read"] is False
        assert payload["can_write"] is False
        assert payload["can_manage"] is False

    def test_creator_always_has_access_even_without_membership(self):
        """创建者即使不是 Workspace 成员也有权限。"""
        kb = MagicMock()
        kb.user_id = 1
        
        # 用户 1 是创建者，即使不是 Workspace 成员
        payload = _build_access_payload(
            kb=kb,
            workspace_id=10,
            workspace_name="Some Workspace",
            member_role=None,  # 不是成员
            user_id=1,  # 但是创建者
        )
        assert payload["can_read"] is True
        assert payload["can_write"] is True
        assert payload["can_manage"] is True
