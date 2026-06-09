from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ModelConfigCreate(BaseModel):
    model_type: str = Field(pattern="^(llm|embedding|reranker)$")
    provider: str = Field(pattern="^(openai|anthropic|ollama|custom)$")
    api_base: str = Field(min_length=1, max_length=500)
    api_key: Optional[str] = None
    model_name: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    params: Optional[str] = None
    is_default: bool = False


class ModelConfigUpdate(BaseModel):
    provider: Optional[str] = Field(default=None, pattern="^(openai|anthropic|ollama|custom)$")
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    display_name: Optional[str] = None
    params: Optional[str] = None
    is_default: Optional[bool] = None


class ModelConfigResponse(BaseModel):
    id: int
    user_id: int
    model_type: str
    provider: str
    api_base: str
    model_name: str
    display_name: str
    params: Optional[str] = None
    is_default: bool
    is_platform: bool = False
    created_at: datetime
    api_key_set: bool = False

    model_config = {"from_attributes": True}


class ModelTestRequest(BaseModel):
    model_type: str = Field(pattern="^(llm|embedding|reranker)$")
    provider: str = Field(pattern="^(openai|anthropic|ollama|custom)$")
    api_base: str
    api_key: Optional[str] = None
    model_name: str
