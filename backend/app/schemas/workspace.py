from pydantic import BaseModel, Field
from typing import Optional


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None


class WorkspaceMemberAdd(BaseModel):
    username: str = Field(min_length=1)
    role: str = Field(pattern="^(admin|member|viewer)$", default="member")


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None


class MemberRoleUpdate(BaseModel):
    role: str = Field(pattern="^(admin|member|viewer)$")


class WorkspaceModelShare(BaseModel):
    model_config_id: int


class InvitationCreate(BaseModel):
    role: str = Field(pattern="^(admin|member|viewer)$", default="member")
    expires_hours: Optional[int] = Field(default=168, ge=1, le=8760)  # default 7 days, max 1 year
    max_uses: Optional[int] = Field(default=None, ge=1, le=10000)
