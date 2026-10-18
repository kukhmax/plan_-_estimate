"""The rehearsal of a restore with the key (EN-3c; docs/CLIENT_ENCRYPTION_RESTORE_REHEARSAL_RU.md): can a restored backup be read with the saved key?

A backup holds ciphertext and the data keys wrapped by the key of the server; it is worth what the SAVED COPY of that key is worth. This service answers, on a
database restored into a scratch server (the existing restore chain, docs/PRODUCTION_DEPLOYMENT_RUNBOOK_RU.md 72.4), with the key the operator supplies
(`DATA_KEK`, and `DATA_KEK_PREVIOUS` for a backup made before a rotation of the key of the server): do the data keys open, does every encrypted value decrypt,
is anything personal left plain, and does a wrong key open nothing. Read only; counts and short fingerprints, never a key or a value. Refuses any database that
is not recognisably scratch (the guard of the restore chain: the name holds `pe_restore_scratch`, the host is loopback or holds `scratch`).
"""
import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.backup.restore_guards import (
    LOOPBACK_HOSTS,
    SCRATCH_DB_MARKER,
    SCRATCH_HOST_MARKER,
)
from app.backup.schema_revision import DEFAULT_SCRIPT_LOCATION, resolve_expected_head
from app.core import data_crypto
from app.core.config import settings
from app.domain.services.data_reencode_service import DataReencodeService
from app.domain.services.kek_rotation_service import KekRotationService, KekStatus
from app.models.data_key import DataKey, WrappedBy


class UnsafeRestoreCheckTargetError(RuntimeError):
    """The database is not recognisably a scratch one: nothing was opened. The message never holds a host, a name or a password."""


def validate_scratch_url(url: str) -> None:
    parsed = make_url(url)
    if SCRATCH_DB_MARKER not in (parsed.database or ""):
        raise UnsafeRestoreCheckTargetError(f"the database name must contain '{SCRATCH_DB_MARKER}'")
    host = (parsed.host or "").lower()
    if host not in LOOPBACK_HOSTS and SCRATCH_HOST_MARKER not in host:
        raise UnsafeRestoreCheckTargetError(f"the database host must be loopback or contain '{SCRATCH_HOST_MARKER}'")


def fingerprint(text_value: str) -> str:
    """The first 8 characters of the SHA-256 of the key as it is written (the same fingerprint the deployment scripts print)."""
    return hashlib.sha256(text_value.strip().encode()).hexdigest()[:8]


@dataclass(slots=True)
class RestoreKeyReport:
    revision: str | None = None
    code_head: str | None = None
    keys: KekStatus = field(default_factory=KekStatus)
    ciphertext: int = 0
    plain: int = 0
    undecryptable: int = 0
    wrong_key_opens: bool | None = None  # a random key opened a data key: never expected
    allow_plain: bool = False
    reasons: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.reasons


class RestoreKeyCheckService:
    def __init__(self, session_factory: Callable[[], AsyncSession], script_location: Path = DEFAULT_SCRIPT_LOCATION) -> None:
        self._sessions = session_factory
        self._script_location = script_location

    async def run(self, allow_plain: bool = False) -> RestoreKeyReport:
        report = RestoreKeyReport(allow_plain=allow_plain)
        async with self._sessions() as db:
            try:
                report.revision = (await db.execute(text("SELECT version_num FROM alembic_version"))).scalar_one_or_none()
            except DBAPIError:  # a database without the table is a failed restore: reported below, not a crash
                await db.rollback()
        try:
            report.code_head = resolve_expected_head(self._script_location)
        except RuntimeError:
            report.code_head = None
        if report.revision is None:
            report.reasons.append("NO_ALEMBIC_VERSION")
        report.keys = await KekRotationService(self._sessions).status()
        if report.keys.total == 0:
            report.reasons.append("NO_DATA_KEYS")
            return report
        if report.keys.unreadable:
            report.reasons.append("DATA_KEYS_DO_NOT_OPEN_WITH_THIS_KEY")
        async with self._sessions() as db:
            row = (await db.execute(select(DataKey).where(DataKey.wrapped_by == WrappedBy.SERVER_KEK.value).limit(1))).scalar_one_or_none()
            if row is not None:
                try:
                    data_crypto.unwrap_key(data_crypto.new_key(), row.wrapped_dek, row.key_id)
                    report.wrong_key_opens = True
                except data_crypto.DataDecryptError:
                    report.wrong_key_opens = False
        if report.wrong_key_opens:
            report.reasons.append("A_RANDOM_KEY_OPENED_A_DATA_KEY")
        if report.keys.unreadable:
            return report  # the values cannot be opened without their keys: say so, do not count them
        stats = await DataReencodeService(self._sessions).count(verify=True)
        report.ciphertext = sum(s.encrypted for s in stats)
        report.plain = sum(s.plain for s in stats)
        report.undecryptable = sum(s.undecryptable for s in stats)
        if report.undecryptable:
            report.reasons.append("VALUES_DO_NOT_DECRYPT")
        if report.plain and not allow_plain:
            report.reasons.append("PLAIN_VALUES_REMAIN")
        if report.ciphertext == 0:
            report.reasons.append("NO_ENCRYPTED_VALUES")
        return report


def key_fingerprints() -> tuple[str, str | None]:
    """The fingerprint of the key of the server in force, and of the previous one when it is set (for the report)."""
    current = settings.DATA_KEK.get_secret_value()
    previous = settings.DATA_KEK_PREVIOUS.get_secret_value()
    return fingerprint(current), (fingerprint(previous) if previous.strip() else None)
