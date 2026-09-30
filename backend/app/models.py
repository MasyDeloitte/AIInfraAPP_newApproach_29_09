from datetime import datetime
from sqlalchemy import DateTime, Integer, String, Text, Float
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str] = mapped_column(String(120), nullable=False, default="General")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    latest_result_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

class SizingResult(Base):
    __tablename__ = "sizing_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
