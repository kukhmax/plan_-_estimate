"""The owner's standard terms of a contract ("Moje standardowe warunki umowy", UX walk B2).

One row per owner: the answers of the questionnaire "compose the contract" that describe his way of working and are the same for
every order (the warranty, the advance, the payment, the penalties, the downtime, the acceptance, the premises; the keys are
`app/domain/contracts/prefill.STANDARD_TERM_KEYS`). A new contract draft takes them first; a term left empty here comes from his
latest contract of another object. The answers are stored in the same normalised form as the contract's and encrypted like them.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.encrypted_text import EncryptedJSON


class OwnerContractTerms(Base):
    __tablename__ = "owner_contract_terms"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    answers: Mapped[dict] = mapped_column(EncryptedJSON("owner_contract_terms.answers"), nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (UniqueConstraint("owner_id", name="uq_owner_contract_terms_owner"),)
