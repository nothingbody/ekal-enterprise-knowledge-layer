from pydantic import BaseModel, Field
from typing import Optional


class PublishedAppCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    kb_id: int
    llm_model_id: int
    welcome_message: Optional[str] = None
    suggested_questions: Optional[str] = None
    prompt_template: Optional[str] = None
    default_chat_mode: str = Field(default="auto", pattern="^(auto|rag|sql|hybrid|agent)$")
    daily_limit: int = Field(default=100, ge=0, le=100000)
    brand_color: Optional[str] = None
    logo_url: Optional[str] = None
    custom_css: Optional[str] = None


class PublishedAppUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    kb_id: Optional[int] = None
    llm_model_id: Optional[int] = None
    welcome_message: Optional[str] = None
    suggested_questions: Optional[str] = None
    prompt_template: Optional[str] = None
    is_active: Optional[bool] = None
    default_chat_mode: Optional[str] = Field(default=None, pattern="^(auto|rag|sql|hybrid|agent)$")
    daily_limit: Optional[int] = Field(default=None, ge=0, le=100000)
    brand_color: Optional[str] = None
    logo_url: Optional[str] = None
    custom_css: Optional[str] = None
