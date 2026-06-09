from datetime import datetime, date
import re
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Auth ──

def _validate_password_strength(v: str) -> str:
    """Enforce password policy: min 8 chars, at least one letter and one digit."""
    if len(v) < 8:
        raise ValueError("密码长度不能少于 8 位")
    if not re.search(r"[A-Za-z]", v):
        raise ValueError("密码必须包含至少一个字母")
    if not re.search(r"\d", v):
        raise ValueError("密码必须包含至少一个数字")
    return v


class UserRegister(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    email: EmailStr = Field(max_length=100)
    password: str = Field(min_length=8, max_length=100)
    invite_code: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


class UserLogin(BaseModel):
    username: str
    password: str
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    os_info: Optional[str] = None
    app_version: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# ── User ──

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    org_id: Optional[int] = None
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    last_login_ip: Optional[str] = None
    last_login_at: Optional[datetime] = None
    plan: str = "trial"
    trial_total: int = 50
    trial_used: int = 0
    token_credit: int = 0
    token_used: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    org_id: Optional[int] = None
    password: Optional[str] = Field(None, min_length=8)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_password_strength(v)
        return v


# ── Organization ──

class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    max_members: int = 50


class OrgResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    owner_id: Optional[int] = None
    max_members: int
    is_active: bool
    member_count: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class OrgUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    max_members: Optional[int] = None
    is_active: Optional[bool] = None


class OrgMemberAdd(BaseModel):
    user_id: int
    role: str = "member"


class OrgMemberResponse(BaseModel):
    id: int
    user_id: int
    username: str
    email: str
    role: str
    joined_at: Optional[datetime] = None
    plan: Optional[str] = None
    token_used: Optional[int] = 0
    token_credit: Optional[int] = 0
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Device ──

class DeviceRegister(BaseModel):
    device_id: str
    device_name: Optional[str] = None
    os_info: Optional[str] = None
    app_version: Optional[str] = None
    mac_address: Optional[str] = None


class DeviceHeartbeat(BaseModel):
    device_id: str
    app_version: Optional[str] = None
    extra: Optional[dict] = None


class DeviceResponse(BaseModel):
    id: int
    device_id: str
    device_name: Optional[str] = None
    os_info: Optional[str] = None
    app_version: Optional[str] = None
    mac_address: Optional[str] = None
    is_active: bool
    last_heartbeat: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Usage ──

class UsageReportCreate(BaseModel):
    device_id: Optional[str] = None
    report_date: date
    token_count: int = 0
    conversation_count: int = 0
    message_count: int = 0
    kb_count: int = 0
    doc_count: int = 0


# ── Skills ──

class SkillPublish(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    category: Optional[str] = None
    skill_type: str = "prompt"
    version: str = "1.0.0"
    config: Optional[str] = None
    icon_url: Optional[str] = None


class SkillResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    category: Optional[str] = None
    skill_type: str
    version: str
    author_id: Optional[int] = None
    author_name: Optional[str] = None
    status: str
    download_count: int
    is_featured: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SkillReviewAction(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected|unlisted)$", description="approved、rejected 或 unlisted")
    comment: Optional[str] = None


# ── Synced User Data ──

class SyncMemoryItem(BaseModel):
    user_id: Optional[int] = None
    content: str
    category: str = "general"
    source: Optional[str] = None
    importance: float = 1.0
    memory_type: str = "persistent"
    created_at: Optional[str] = None


class SyncMemoriesRequest(BaseModel):
    device_id: str
    memories: List[SyncMemoryItem]


class SyncProfileRequest(BaseModel):
    device_id: str
    profile: dict


class SyncAgentItem(BaseModel):
    user_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    kb_ids: Optional[str] = None
    is_active: Optional[bool] = True
    created_at: Optional[str] = None


class SyncAgentsRequest(BaseModel):
    device_id: str
    agents: List[SyncAgentItem]


class SyncOperationLogItem(BaseModel):
    local_id: Optional[int] = None
    user_id: Optional[int] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[int] = None
    detail: Optional[str] = None
    ip_address: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0
    created_at: Optional[str] = None


class SyncOperationLogsRequest(BaseModel):
    device_id: str
    logs: List[SyncOperationLogItem] = Field(max_length=500)


# ── Admin Dashboard ──

class DashboardStats(BaseModel):
    total_users: int
    active_users_today: int
    total_organizations: int
    total_devices: int
    online_devices: int
    total_skills: int
    pending_skills: int
    total_tokens_today: int
    total_tokens_total: int


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int


# ── Workspace ──

class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    org_id: Optional[int] = None


class WorkspaceResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    org_id: Optional[int] = None
    owner_id: int
    is_active: bool
    member_count: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class WorkspaceMemberAdd(BaseModel):
    user_id: Optional[int] = None
    username: Optional[str] = None
    role: str = "viewer"


# ── Knowledge Base ──

class KBCreate(BaseModel):
    workspace_id: Optional[int] = None
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    embedding_model: Optional[str] = None
    chunk_strategy: str = "fixed"
    chunk_size: int = 500
    chunk_overlap: int = 50
    search_mode: str = "hybrid"


class KBResponse(BaseModel):
    id: int
    workspace_id: int
    owner_id: int
    name: str
    description: Optional[str] = None
    embedding_model: Optional[str] = None
    doc_count: int = 0
    chunk_count: int = 0
    search_mode: str = "hybrid"
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class KBUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    search_mode: Optional[str] = None


# ── Document ──

class DocumentResponse(BaseModel):
    id: int
    kb_id: int
    filename: str
    file_size: Optional[int] = None
    file_type: str
    chunk_count: int = 0
    status: str
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Chat ──

class ConversationCreate(BaseModel):
    workspace_id: Optional[int] = None
    kb_id: Optional[int] = None
    title: Optional[str] = None
    llm_model: Optional[str] = None


class ConversationResponse(BaseModel):
    id: int
    user_id: int
    workspace_id: Optional[int] = None
    kb_id: Optional[int] = None
    title: Optional[str] = None
    llm_model: Optional[str] = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ConversationUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)


class MessageFeedback(BaseModel):
    feedback: Optional[str] = Field(None, max_length=20)


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)


class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    references: Optional[str] = None
    token_count: int = 0
    latency_ms: Optional[float] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Model Config ──

class ModelConfigCreate(BaseModel):
    model_type: str
    provider: str
    api_base: str
    api_key: Optional[str] = None
    model_name: str
    display_name: str
    params: Optional[str] = None
    is_default: bool = False
    is_shared: bool = False
    max_tokens_per_day: Optional[int] = None


class ModelConfigResponse(BaseModel):
    id: int
    org_id: Optional[int] = None
    model_type: str
    provider: str
    api_base: str
    model_name: str
    display_name: str
    is_default: bool
    is_shared: bool
    api_key_set: bool = False
    max_tokens_per_day: Optional[int] = None
    tokens_used_today: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ModelConfigUpdate(BaseModel):
    provider: Optional[str] = None
    display_name: Optional[str] = None
    model_name: Optional[str] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    params: Optional[str] = None
    is_default: Optional[bool] = None
    is_shared: Optional[bool] = None
    max_tokens_per_day: Optional[int] = None
