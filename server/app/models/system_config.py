"""System configuration key-value store for admin-editable settings."""

from sqlalchemy import Column, Integer, String, Text

from app.models.base import Base


class SystemConfig(Base):
    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
