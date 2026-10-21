import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, utcnow


class UserProgress(UUIDMixin, Base):
    __tablename__ = "user_progress"
    __table_args__ = (UniqueConstraint("user_id", "category", name="uq_user_progress_user_category"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    rolling_score: Mapped[Decimal | None] = mapped_column(Numeric)
    rolling_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trend: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
