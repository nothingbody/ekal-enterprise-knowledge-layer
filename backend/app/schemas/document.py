from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
import json


class DocumentResponse(BaseModel):
    id: int
    kb_id: int
    filename: str
    file_size: Optional[int] = None
    file_type: str
    chunk_count: int
    status: str
    error_message: Optional[str] = None
    auto_tags: Optional[list[str]] = None
    content_hash: Optional[str] = None
    expires_at: Optional[datetime] = None
    is_archived: bool = False
    is_stalled: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("auto_tags", mode="before")
    @classmethod
    def parse_auto_tags(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return None
        return v


class DocumentChunkResponse(BaseModel):
    id: int
    doc_id: int
    content: str
    chunk_index: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ChunkUpdateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10000)


class ChunkCreateRequest(BaseModel):
    doc_id: int
    kb_id: int
    content: str = Field(min_length=1, max_length=10000)


class TagUpdateRequest(BaseModel):
    tags: list[str] = Field(..., min_length=1, max_length=20)


class ExpiryUpdateRequest(BaseModel):
    expires_at: Optional[datetime] = None


class DuplicateCheckRequest(BaseModel):
    kb_id: int
    content_hash: str


class DuplicateCheckResponse(BaseModel):
    is_duplicate: bool
    existing_document: Optional[DocumentResponse] = None


class SuggestKBRequest(BaseModel):
    filename: str
    content_preview: str = Field(max_length=5000)


class KBSuggestion(BaseModel):
    kb_id: int
    kb_name: str
    confidence: float


class SuggestKBResponse(BaseModel):
    suggestions: list[KBSuggestion]
