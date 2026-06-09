from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ChatRequest(BaseModel):
    conversation_id: Optional[int] = None
    kb_id: int
    llm_model_id: Optional[int] = None
    question: str = Field(min_length=1, max_length=10000)
    top_k: int = Field(default=5, ge=1, le=50)
    score_threshold: Optional[float] = Field(default=None, ge=0, le=1)
    enable_rewrite: bool = True
    published_app_id: Optional[int] = None
    visitor_id: Optional[str] = Field(default=None, max_length=64)
    prompt_template: Optional[str] = Field(default=None, max_length=5000)
    prompt_template_id: Optional[int] = None
    chat_mode: str = Field(default="auto", pattern="^(auto|rag|sql|hybrid|agent|multi_agent)$")
    context_strategy: Optional[str] = Field(default=None, pattern="^(sliding_window|semantic_summary|full_context)$")
    agentic_rag: Optional[dict] = Field(default=None, description="Per-request agentic RAG config overrides")


class PublicChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=10000)
    conversation_id: Optional[int] = None
    visitor_id: Optional[str] = Field(default=None, max_length=64)
    top_k: int = Field(default=5, ge=1, le=50)
    score_threshold: Optional[float] = Field(default=None, ge=0, le=1)


class ChatMessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    references: Optional[str] = None
    token_count: int
    feedback: Optional[str] = None
    latency_ms: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: int
    user_id: int
    kb_id: int
    title: Optional[str] = None
    llm_model_id: Optional[int] = None
    is_pinned: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetail(ConversationResponse):
    messages: List[ChatMessageResponse] = []


class RetrievalResult(BaseModel):
    content: str
    score: float
    doc_name: str
    chunk_index: int
    source_type: Optional[str] = None


class SearchRequest(BaseModel):
    kb_id: int
    query: str = Field(min_length=1, max_length=5000)
    top_k: int = Field(default=5, ge=1, le=50)
    score_threshold: Optional[float] = Field(default=None, ge=0, le=1)


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=200)


VALID_FEEDBACK_REASONS = {
    "like": ["accurate", "helpful", "well_written", "creative"],
    "dislike": ["inaccurate", "irrelevant", "incomplete", "harmful", "too_long"],
}


class MessageFeedbackRequest(BaseModel):
    feedback: Optional[str] = Field(default=None, pattern="^(like|dislike)$")
    feedback_reason: Optional[str] = Field(default=None, max_length=100)


class MultiKBSearchRequest(BaseModel):
    kb_ids: List[int] = Field(min_length=1, max_length=20)
    query: str = Field(min_length=1, max_length=5000)
    top_k: int = Field(default=5, ge=1, le=50)
    score_threshold: Optional[float] = Field(default=None, ge=0, le=1)


class BatchDeleteRequest(BaseModel):
    ids: List[int] = Field(min_length=1, max_length=100)


class MessageResponse(BaseModel):
    message: str


class FeedbackResponse(BaseModel):
    message: str


class UsageTrendItem(BaseModel):
    date: str
    tokens: int
    message_count: int


class UsageTrendResponse(BaseModel):
    days: int
    trend: List[UsageTrendItem]


class ConversationSearchItem(BaseModel):
    id: int
    title: Optional[str] = None
    kb_id: int
    created_at: datetime
    snippets: List[str] = []

    model_config = {"from_attributes": True}


class ConversationSearchResponse(BaseModel):
    items: List[ConversationSearchItem]
    total: int


class PaginatedConversations(BaseModel):
    items: List[ConversationResponse]
    total: int
    page: int
    page_size: int
