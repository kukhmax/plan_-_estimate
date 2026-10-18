import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.encrypted_text import EncryptedText


class ClientType(str, enum.Enum):
    PRIVATE_PERSON = "PRIVATE_PERSON"
    COMPANY = "COMPANY"


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_type: Mapped[ClientType] = mapped_column(
        Enum(ClientType, name="clienttype"),
        nullable=False,
    )
    first_name: Mapped[str | None] = mapped_column(EncryptedText("clients.first_name"), nullable=True)
    last_name: Mapped[str | None] = mapped_column(EncryptedText("clients.last_name"), nullable=True)
    company_name: Mapped[str | None] = mapped_column(EncryptedText("clients.company_name"), nullable=True)
    phone: Mapped[str | None] = mapped_column(EncryptedText("clients.phone"), nullable=True)
    email: Mapped[str | None] = mapped_column(EncryptedText("clients.email"), nullable=True)
    nip: Mapped[str | None] = mapped_column(EncryptedText("clients.nip"), nullable=True)
    # Address of the customer for contracts and protocols (Stage 16B.1); the postal code is stored as `00-000`.
    street: Mapped[str | None] = mapped_column(EncryptedText("clients.street"), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(EncryptedText("clients.postal_code"), nullable=True)
    city: Mapped[str | None] = mapped_column(EncryptedText("clients.city"), nullable=True)
    # Contact field only — never used for Telegram Mini App authentication
    # (that identity lives on User.telegram_user_id). Stored normalized as
    # "@username" (Stage 10G.4 client contact correction).
    telegram_username: Mapped[str | None] = mapped_column(EncryptedText("clients.telegram_username"), nullable=True)
    notes: Mapped[str | None] = mapped_column(EncryptedText("clients.notes"), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
