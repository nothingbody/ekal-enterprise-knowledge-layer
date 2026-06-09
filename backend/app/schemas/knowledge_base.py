from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    workspace_id: Optional[int] = None
    embedding_model_id: Optional[int] = None
    chunk_strategy: str = "fixed"
    chunk_size: int = 500
    chunk_overlap: int = 50
    search_mode: str = "hybrid"
    vector_weight: float = 0.7
    context_window: int = 1
    welcome_message: Optional[str] = None
    suggested_questions: Optional[str] = None
    prompt_template: Optional[str] = None
    prompt_template_id: Optional[int] = None


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    workspace_id: Optional[int] = None
    embedding_model_id: Optional[int] = None
    chunk_strategy: Optional[str] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    search_mode: Optional[str] = None
    vector_weight: Optional[float] = None
    context_window: Optional[int] = None
    welcome_message: Optional[str] = None
    suggested_questions: Optional[str] = None
    prompt_template: Optional[str] = None
    prompt_template_id: Optional[int] = None


class KnowledgeBaseResponse(BaseModel):
    id: int
    user_id: int
    name: str
    description: Optional[str] = None
    workspace_id: Optional[int] = None
    workspace_name: Optional[str] = None
    embedding_model_id: Optional[int] = None
    chunk_strategy: str = "fixed"
    chunk_size: int = 500
    chunk_overlap: int = 50
    search_mode: str = "hybrid"
    vector_weight: float = 0.7
    context_window: int = 1
    reindexing: bool = False
    welcome_message: Optional[str] = None
    suggested_questions: Optional[str] = None
    prompt_template: Optional[str] = None
    prompt_template_id: Optional[int] = None
    doc_count: int
    chunk_count: int
    access_role: Optional[str] = None
    can_write: bool = False
    can_manage: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
