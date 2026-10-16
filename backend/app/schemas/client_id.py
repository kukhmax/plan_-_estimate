"""An id chosen by the client (Stage 19C): the phone creates records without a signal and sends them later.

Optional on the create routes. The server accepts only a random UUID (version 4) so that two phones (or a phone and the server)
never meet on one id by design; a repeat of the same request with the same id and the same content returns the record already
created, anything else on that id is a conflict (`CLIENT_ID_CONFLICT`).
"""
import uuid
from typing import Annotated

from pydantic import AfterValidator, Field


def _random_uuid(value: uuid.UUID | None) -> uuid.UUID | None:
    if value is not None and value.version != 4:
        raise ValueError("id must be a random UUID (version 4)")
    return value


ClientId = Annotated[
    uuid.UUID | None,
    AfterValidator(_random_uuid),
    Field(default=None, description="Optional id chosen by the client (UUIDv4); repeating the same request is safe"),
]
