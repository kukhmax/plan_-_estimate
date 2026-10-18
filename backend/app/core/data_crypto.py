"""Encryption of the personal data of the clients (EN-2a; docs/CLIENT_DATA_ENCRYPTION_PLAN_RU.md section 4).

The primitives only: AES-256-GCM, the format of a stored value, the wrapping of a data key by the key of the server. No database, no
framework. Nothing here prints a key or a plain value: every failure is a typed error with a code and no data in its text.

Stored value: `enc1:<key_id>:<nonce>:<ciphertext>` (nonce and ciphertext are urlsafe base64 without padding; the ciphertext carries the
GCM tag). The associated data (AAD) of a value is "table.column": a ciphertext cannot be moved into another column. It can be moved
between rows of the same column of the same owner (owner decision of 2026-10-18, variant (a)): that matters for someone who can WRITE to
the database, not for a leak of a dump.
"""
import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIX = "enc1:"
KEY_BYTES = 32
NONCE_BYTES = 12
WRAP_AAD = b"data_keys.wrapped_dek:"


class DataCryptoError(Exception):
    """Base of the errors of the encryption of the data. `code` is machine readable; the text never holds a key or a value."""

    code = "DATA_ENCRYPTION_ERROR"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.code)


class DataKeyUnavailableError(DataCryptoError):
    """The data key of a stored value is not known to this process (not loaded, or encryption is off while the data is encrypted)."""

    code = "DATA_KEY_UNAVAILABLE"


class DataDecryptError(DataCryptoError):
    """A stored value did not decrypt: damaged, wrong column, or a wrong key."""

    code = "DATA_DECRYPT_FAILED"


class DataPlainValueError(DataCryptoError):
    """Strict read: a value of an encrypted column is not ciphertext (the re-encoding missed it, or someone wrote to the database directly)."""

    code = "DATA_PLAIN_VALUE_REFUSED"


class DataEncryptionContextMissingError(DataCryptoError):
    """A value was to be written encrypted but no owner key is in force (a write outside of an authenticated request or a job of an owner)."""

    code = "DATA_ENCRYPTION_CONTEXT_MISSING"


class DataKeyConfigurationError(DataCryptoError):
    """The key of the server (DATA_KEK) is not a base64 text of 32 bytes."""

    code = "DATA_KEK_INVALID"


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text + "=" * (-len(text) % 4), altchars=b"-_", validate=True)


def new_key() -> bytes:
    return os.urandom(KEY_BYTES)


def parse_kek(text: str) -> bytes:
    """The key of the server from its text form (base64, standard or urlsafe, 32 bytes). Never echoes the text."""
    try:
        raw = base64.b64decode(text.strip().replace("-", "+").replace("_", "/") + "=" * (-len(text.strip()) % 4), validate=True)
    except (binascii.Error, ValueError):
        raise DataKeyConfigurationError("DATA_KEK is not base64") from None
    if len(raw) != KEY_BYTES:
        raise DataKeyConfigurationError("DATA_KEK must be 32 bytes")
    return raw


def wrap_key(kek: bytes, dek: bytes, key_id: str) -> str:
    """A data key wrapped by the key of the server; bound to its key_id so a wrapped key cannot be passed off as another."""
    nonce = os.urandom(NONCE_BYTES)
    return f"{_b64e(nonce)}.{_b64e(AESGCM(kek).encrypt(nonce, dek, WRAP_AAD + key_id.encode()))}"


def unwrap_key(kek: bytes, wrapped: str, key_id: str) -> bytes:
    try:
        nonce_text, body_text = wrapped.split(".", 1)
        dek = AESGCM(kek).decrypt(_b64d(nonce_text), _b64d(body_text), WRAP_AAD + key_id.encode())
    except (InvalidTag, ValueError, binascii.Error):
        raise DataDecryptError("a data key did not unwrap (wrong DATA_KEK or a damaged key)") from None
    if len(dek) != KEY_BYTES:
        raise DataDecryptError("a data key has a wrong size")
    return dek


def is_encrypted(value: str | None) -> bool:
    return value is not None and value.startswith(PREFIX)


def encrypt_text(dek: bytes, key_id: str, aad: str, plain: str) -> str:
    nonce = os.urandom(NONCE_BYTES)
    body = AESGCM(dek).encrypt(nonce, plain.encode("utf-8"), aad.encode("utf-8"))
    return f"{PREFIX}{key_id}:{_b64e(nonce)}:{_b64e(body)}"


def split_value(stored: str) -> tuple[str, bytes, bytes]:
    """key_id, nonce, ciphertext of a stored value."""
    parts = stored[len(PREFIX):].split(":")
    if len(parts) != 3 or not parts[0]:
        raise DataDecryptError("a stored value is not in the format enc1:<key_id>:<nonce>:<ciphertext>")
    try:
        return parts[0], _b64d(parts[1]), _b64d(parts[2])
    except (ValueError, binascii.Error):
        raise DataDecryptError("a stored value is not valid base64") from None


def decrypt_text(dek: bytes, aad: str, nonce: bytes, body: bytes) -> str:
    try:
        return AESGCM(dek).decrypt(nonce, body, aad.encode("utf-8")).decode("utf-8")
    except (InvalidTag, ValueError):
        raise DataDecryptError(f"a value of {aad} did not decrypt (damaged, moved to another column, or a wrong key)") from None
