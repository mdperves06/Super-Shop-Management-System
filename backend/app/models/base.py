from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Numeric, false, func
from sqlalchemy.orm import Mapped, mapped_column

Money = Numeric(14, 2)
Qty = Numeric(14, 3)
Rate = Numeric(6, 2)


def utcnow() -> datetime:
    """Naive UTC timestamp; all datetimes are stored as UTC."""
    return datetime.now(UTC).replace(tzinfo=None)


ZERO = Decimal("0")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, server_default=func.now(), nullable=False
    )


class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
