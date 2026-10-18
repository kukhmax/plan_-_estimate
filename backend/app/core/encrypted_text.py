"""`EncryptedText` and `EncryptedJSON`: columns stored as `enc1:...` (EN-2a, EN-2b-2). The service layer, the schemas and the front end do not change.

Writing: encrypted with the key of the owner in force (a request or a job of an owner); with no key in force the write is refused
(never silently stored in the open) -- unless encryption is off in this process (no DATA_KEK: development, tests), when the text passes
through unchanged. Reading: a value without the prefix is old plain text and is returned as it is (the soft read of the migration
period; the re-encoding command turns it into ciphertext); a value with the prefix is decrypted with the key named in it. In the strict mode
(`DATA_STRICT_READ`, after the re-encoding) a value without the prefix is refused.
`label` is the "table.column" that makes the associated data of the value.

`EncryptedJSON` keeps a JSON value (a snapshot, a list of attendees) in a TEXT column: the JSON text is what is encrypted, so the re-encoding command
treats it as any other text. A plain (old) value is the JSON text itself.
"""
import json
from typing import Any

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core import data_crypto
from app.core.key_ring import current_owner_key, ring


class EncryptedColumnType(TypeDecorator):
    """The common base: a TEXT column with a `label` (the associated data). The re-encoding command finds the columns by this class."""

    impl = Text
    cache_ok = True

    def __init__(self, label: str) -> None:
        super().__init__()
        self.label = label

    def _seal(self, text: str) -> str:
        if not ring.enabled:
            return text
        key = current_owner_key()
        if key is None:
            raise data_crypto.DataEncryptionContextMissingError(f"a value of {self.label} was written with no owner key in force")
        return data_crypto.encrypt_text(key.dek, key.key_id, self.label, text)

    def _open(self, stored: str) -> str:
        if not data_crypto.is_encrypted(stored):
            if ring.enabled and ring.strict:
                raise data_crypto.DataPlainValueError(f"a value of {self.label} is not encrypted")
            return stored
        key_id, nonce, body = data_crypto.split_value(stored)
        dek = ring.get(key_id) if ring.enabled else None
        if dek is None:
            raise data_crypto.DataKeyUnavailableError(f"the data key {key_id} of a value of {self.label} is not loaded")
        return data_crypto.decrypt_text(dek, self.label, nonce, body)


class EncryptedText(EncryptedColumnType):
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        return None if value is None else self._seal(value)

    def process_result_value(self, value: str | None, dialect) -> str | None:
        return None if value is None else self._open(value)


class EncryptedJSON(EncryptedColumnType):
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> str | None:
        return None if value is None else self._seal(json.dumps(value, ensure_ascii=False))

    def process_result_value(self, value: str | None, dialect) -> Any:
        return None if value is None else json.loads(self._open(value))
