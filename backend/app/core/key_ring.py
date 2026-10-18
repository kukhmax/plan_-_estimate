"""The data keys known to this process (EN-2a): a plain in-memory ring, no database.

Reading a stored value needs only the `key_id` written in it: the ring holds every data key that was unwrapped (loaded by
`data_key_service` at the start and at each request). Writing needs to know WHOSE key to use: the key of the owner in force, held in a
context variable that the authentication of a request (or a job of an owner) sets. The ring is switched on only when the server has
its key (`DATA_KEK`); without it the encrypted type passes plain text through (development, tests) and refuses to read ciphertext.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class OwnerKey:
    key_id: str
    dek: bytes

    def __repr__(self) -> str:  # a key never reaches a log, a traceback or a debugger line
        return f"OwnerKey(key_id={self.key_id!r})"


class KeyRing:
    def __init__(self) -> None:
        self._deks: dict[str, bytes] = {}
        self._owners: dict[UUID, OwnerKey] = {}
        self._enabled = False
        self.strict = False  # a value without the prefix in an encrypted column is refused (EN-2b-1, after the re-encoding)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False
        self.strict = False
        self._deks.clear()
        self._owners.clear()

    def add(self, key_id: str, dek: bytes) -> None:
        self._deks[key_id] = dek

    def get(self, key_id: str) -> bytes | None:
        return self._deks.get(key_id)

    def set_owner(self, owner_id: UUID, key: OwnerKey) -> None:
        self._deks[key.key_id] = key.dek
        self._owners[owner_id] = key

    def owner(self, owner_id: UUID) -> OwnerKey | None:
        return self._owners.get(owner_id)

    def forget_owner(self, owner_id: UUID) -> None:
        """Drop the cached active key of an owner (EN-3b: its data key was changed); the keys already unwrapped stay to read old values."""
        self._owners.pop(owner_id, None)

    def known(self) -> frozenset[str]:
        return frozenset(self._deks)


ring = KeyRing()
_owner_key: ContextVar[OwnerKey | None] = ContextVar("data_owner_key", default=None)


def set_owner_key(key: OwnerKey | None) -> None:
    _owner_key.set(key)


def current_owner_key() -> OwnerKey | None:
    return _owner_key.get()


@contextmanager
def owner_key_in_force(key: OwnerKey | None):
    """The key of an owner for a stretch of code (a job, a command, a test)."""
    token = _owner_key.set(key)
    try:
        yield
    finally:
        _owner_key.reset(token)
