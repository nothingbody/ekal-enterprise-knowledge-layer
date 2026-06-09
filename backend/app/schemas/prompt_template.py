from typing import Optional
from pydantic import BaseModel, Field


class PromptTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    content: str = Field(min_length=1)
    category: str = Field(default="custom", max_length=50)


class PromptTemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    content: Optional[str] = Field(default=None, min_length=1)
    category: Optional[str] = Field(default=None, max_length=50)


class PromptTemplateResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    content: str
    category: str = "custom"
    is_builtin: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}
