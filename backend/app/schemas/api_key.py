from pydantic import BaseModel, Field
from typing import Optional


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ApiKeyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None
