from sqlalchemy import Column, Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from src.database.base import Base


class AiUsageDaily(Base):
    """AI usage counters for one UTC day.

    `scope` is "global" or "user:<id>". No foreign key on purpose: the rows are
    accounting data, they must not block deleting a user, and they are tiny.
    """

    __tablename__ = "ai_usage_daily"
    __table_args__ = (UniqueConstraint("scope", "usage_date", name="uq_ai_usage_daily_scope_date"),)

    id = Column(Integer, primary_key=True)
    scope = Column(String(64), nullable=False)
    usage_date = Column(Date, nullable=False)
    requests = Column(Integer, nullable=False, default=0, server_default="0")
    tokens = Column(Integer, nullable=False, default=0, server_default="0")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
