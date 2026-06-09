from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class DatabaseSourceConnectionBase(BaseModel):
    db_type: str = Field(pattern="^(postgresql|mysql)$")
    host: Optional[str] = Field(default=None, max_length=255)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    database_name: Optional[str] = Field(default=None, max_length=255)
    schema_name: Optional[str] = Field(default=None, max_length=255)
    username: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = None
    table_names: Optional[List[str]] = None
    column_filter: Optional[dict] = None  # {"table_name": ["col1", "col2"]}
    row_limit: int = Field(default=200, ge=1, le=5000)

    @field_validator("table_names")
    @classmethod
    def normalize_table_names(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        items = []
        for item in value:
            if item and item.strip() and item.strip() not in items:
                items.append(item.strip())
        return items or None

    @model_validator(mode="after")
    def validate_connection(self):
        if not self.host:
            raise ValueError("数据库主机不能为空")
        if not self.database_name:
            raise ValueError("数据库名称不能为空")
        if not self.username:
            raise ValueError("数据库用户名不能为空")
        return self


class DatabaseSourceCreate(DatabaseSourceConnectionBase):
    kb_id: int
    name: str = Field(min_length=1, max_length=200)


class DatabaseSourceUpdate(BaseModel):
    kb_id: Optional[int] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    db_type: Optional[str] = Field(default=None, pattern="^(postgresql|mysql)$")
    host: Optional[str] = Field(default=None, max_length=255)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    database_name: Optional[str] = Field(default=None, max_length=255)
    schema_name: Optional[str] = Field(default=None, max_length=255)
    username: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = None
    table_names: Optional[List[str]] = None
    column_filter: Optional[dict] = None
    row_limit: Optional[int] = Field(default=None, ge=1, le=5000)

    @field_validator("table_names")
    @classmethod
    def normalize_table_names(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        items = []
        for item in value:
            if item and item.strip() and item.strip() not in items:
                items.append(item.strip())
        return items or None


class DatabaseSourceTestRequest(DatabaseSourceConnectionBase):
    pass


class DatabaseServerConnectRequest(BaseModel):
    """连接数据库服务器（不指定具体数据库），列出所有数据库。"""
    db_type: str = Field(pattern="^(postgresql|mysql)$")
    host: str = Field(max_length=255)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    username: str = Field(max_length=255)
    password: Optional[str] = None


class CreateKbWithDatabaseRequest(DatabaseSourceConnectionBase):
    kb_name: str = Field(min_length=1, max_length=200)
    kb_description: Optional[str] = Field(default="", max_length=1000)
    source_name: Optional[str] = Field(default=None, max_length=200)
    embedding_model_id: Optional[int] = Field(default=None, ge=1)


class DatabaseTableColumnResponse(BaseModel):
    name: str
    type: str


class DatabaseSourceTableResponse(BaseModel):
    name: str
    kind: str
    columns: List[DatabaseTableColumnResponse]


class DatabaseSourceResponse(BaseModel):
    id: int
    kb_id: int
    name: str
    db_type: str
    host: Optional[str] = None
    port: Optional[int] = None
    database_name: Optional[str] = None
    schema_name: Optional[str] = None
    username: Optional[str] = None
    table_names: List[str] = Field(default_factory=list)
    column_filter: Optional[dict] = None
    row_limit: int
    has_password: bool
    status: str
    last_synced_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SyncRunResponse(BaseModel):
    id: int
    source_id: int
    status: str
    table_count: int = 0
    row_count: int = 0
    chunk_count: int = 0
    duration_seconds: Optional[float] = None
    tables_detail: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
