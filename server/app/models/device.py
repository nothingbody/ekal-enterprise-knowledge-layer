from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String(100), unique=True, nullable=False, index=True)
    device_name = Column(String(200), nullable=True)
    os_info = Column(String(200), nullable=True)
    app_version = Column(String(50), nullable=True)
    mac_address = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    last_heartbeat = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="devices")
