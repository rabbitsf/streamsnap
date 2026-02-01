from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    downloads = relationship("Download", back_populates="user", cascade="all, delete-orphan")


class Download(Base):
    __tablename__ = "downloads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    url = Column(String(2048), nullable=False)
    title = Column(String(500))
    filename = Column(String(255), nullable=False)
    file_path = Column(String(1024), nullable=False)
    file_size = Column(BigInteger)  # Size in bytes
    format_type = Column(String(50))  # "video" or "audio"
    quality = Column(String(50))  # e.g., "1080p", "720p", "mp3"
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="downloads")
