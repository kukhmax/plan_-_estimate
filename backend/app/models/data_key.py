"""The data key of an owner (EN-2a): 32 random bytes that encrypt the personal data of the owner, stored only WRAPPED.

V1: wrapped by the key of the server (`DATA_KEK`, in the environment, never in the database). V2 (EN-4) re-wraps the same data key with the
key of the owner: the data stays where it is, only this row changes. `key_id` is the name written in every stored value. One active key
per owner (a partial unique index); a rotation of the data key adds a new active row and the old one stays to read the old values.
"""
import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WrappedBy(str, enum.Enum):
    SERVER_KEK = "SERVER_KEK"
    OWNER_KEY = "OWNER_KEY"


class DataKey(Base):
    __tablename__ = "data_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    key_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    wrapped_dek: Mapped[str] = mapped_column(Text, nullable=False)
    wrapped_by: Mapped[str] = mapped_column(String(16), nullable=False, default=WrappedBy.SERVER_KEK.value)
    kek_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    __table_args__ = (
        CheckConstraint("wrapped_by IN ('SERVER_KEK', 'OWNER_KEY')", name="ck_data_keys_wrapped_by"),
        Index("uq_data_keys_one_active_per_owner", "owner_id", unique=True, postgresql_where=text("active"), sqlite_where=text("active")),
    )
