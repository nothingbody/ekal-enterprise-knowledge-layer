"""SkillChain model — represents a sequential workflow of chained skills."""

from __future__ import annotations

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.database import Base


class SkillChain(Base):
    """A sequential chain of skills that execute one after another.

    The ``steps`` column stores a JSON array like::

        [
            {"skill_id": 1, "input_mapping": {"query": "{{initial_input}}"}, "output_key": "step1"},
            {"skill_id": 2, "input_mapping": {"text": "{{step1.output}}"}, "output_key": "step2"},
        ]

    Each step can reference outputs from previous steps via ``{{step_name.output}}``.
    """

    __tablename__ = "skill_chains"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    steps = Column(Text, nullable=False)  # JSON array
    is_public = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
