"""`EncryptedText`: a text column stored as `enc1:...` (EN-2a). The service layer, the schemas and the front end do not change.

Writing: encrypted with the key of the owner in force (a request or a job of an owner); with no key in force the write is refused
(never silently stored in the open) -- unless encryption is off in this process (no DATA_KEK: development, tests), when the text passes
through unchanged. Reading: a value without the prefix is old plain text and is returned as it is (the soft read of the migration
period; the re-encoding command of EN-2b turns it into ciphertext); a value with the prefix is decrypted with the key named in it. In the strict mode (`DATA_STRICT_READ`, after the re-encoding of EN-2b) a value without the prefix is refused.
`label` is the "table.column" that makes the associated data of the value.
"""
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core import data_crypto
from app.core.key_ring import current_owner_key, ring


class EncryptedText(TypeDecorator):
    impl = Text
    cache_ok = True

    def __init__(self, label: str) -> None:
        super().__init__()
        self.label = label

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        if value is None or not ring.enabled:
            return value
        key = current_owner_key()
        if key is None:
            raise data_crypto.DataEncryptionContextMissingError(f"a value of {self.label} was written with no owner key in force")
        return data_crypto.encrypt_text(key.dek, key.key_id, self.label, value)

    def process_result_value(self, value: str | None, dialect) -> str | None:
        if value is None:
            return value
        if not data_crypto.is_encrypted(value):
            if ring.enabled and ring.strict:
                raise data_crypto.DataPlainValueError(f"a value of {self.label} is not encrypted")
            return value
        key_id, nonce, body = data_crypto.split_value(value)
        dek = ring.get(key_id) if ring.enabled else None
        if dek is None:
            raise data_crypto.DataKeyUnavailableError(f"the data key {key_id} of a value of {self.label} is not loaded")
        return data_crypto.decrypt_text(dek, self.label, nonce, body)
