"""Project-level metadata (single-row settings table)."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class ProjectMeta(Base):
    __tablename__ = "project_meta"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    name: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    working_directory: Mapped[str] = mapped_column(String(500), default="")
