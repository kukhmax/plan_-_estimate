"""Creating a record under an id chosen by the client, safely repeatable (Stage 19C).

The phone queues "create" requests made without a signal and sends them when the signal returns; a request whose answer was lost is
sent again. So a create with a client id is **idempotent**: the same id with the same parent and the same content gives back the
record already there; the id taken by anything else (another parent, another content, another owner) is `ClientIdConflictError`.
"""
import uuid
from decimal import Decimal
from enum import Enum
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import ClientIdConflictError

T = TypeVar("T")


def _same(stored: Any, wanted: Any) -> bool:
    if isinstance(stored, Enum):
        stored = stored.value
    if isinstance(wanted, Enum):
        wanted = wanted.value
    if isinstance(stored, (Decimal, int, float)) and isinstance(wanted, (Decimal, int, float)) and not isinstance(stored, bool):
        return Decimal(str(stored)) == Decimal(str(wanted))
    return stored == wanted


async def find_repeat(db: AsyncSession, model: type[T], client_id: uuid.UUID | None, expected: dict[str, Any]) -> T | None:
    """The record already created by this very request, or `None` when the id is free (or the client sent none).

    `expected` holds the parent ids and the content the request carries; every one must match what is stored.
    """
    if client_id is None:
        return None
    existing = await db.get(model, client_id)
    if existing is None:
        return None
    if all(_same(getattr(existing, name), value) for name, value in expected.items()):
        return existing
    raise ClientIdConflictError(f"The id {client_id} is already used by another record")
