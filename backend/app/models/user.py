from datetime import datetime, timezone
import uuid

from sqlalchemy import BigInteger, DateTime, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON as GenericJSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
        nullable=False,
    )
    username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    first_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    last_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    language_code: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )
    # The trades (packages of professions) the owner works in (V2-13): a list of keys of `domain/rules/trades.py`; NULL = never chosen = every trade on.
    trades: Mapped[list | None] = mapped_column(JSONB().with_variant(GenericJSON(), "sqlite"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Closed registration: not a column. The authentication of a request sets it from the access list (`AccessService`); the answers carry it.
    is_admin = False
