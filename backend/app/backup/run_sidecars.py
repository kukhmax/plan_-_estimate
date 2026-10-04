"""The two facts a local run must keep for its later upload (Stage 14D.2J.1).

`db-dump` (database credentials, no object storage) and `upload` (object storage, no database credentials) are two
containers (plan §12). The upload needs two things only the dump step knows: the READY assets of the snapshot (the digest
in the evidence is only a hash) and the age recipients the artifact was encrypted for. Both are written next to the
artifact, before `local-run.json`, and are bound to it again at upload time:

    ready-assets.txt   the canonical READY set v1 bytes (`media_backup_ready_set.canonical_bytes`); its SHA-256 must
                       equal `snapshot.ready_set_sha256` of the evidence
    recipients.txt     the public `age1...` recipients, one per line; their number must equal
                       `artifact.recipient_count` of the evidence

Parsing is strict: a file is accepted only when serializing what was parsed reproduces the file byte for byte, so
non-canonical order, duplicates, padding or foreign lines are refused, never normalized.
"""

import uuid
from collections.abc import Iterable

from app.core.db_dump_encryption import AgeRecipientError, parse_age_recipients
from app.domain.services.media_backup_ready_set import (
    FIELD_SEPARATOR,
    READY_SET_HEADER,
    ReadyAsset,
    ReadySetFormatError,
    canonical_bytes,
)

READY_ASSETS_NAME = "ready-assets.txt"
RECIPIENTS_NAME = "recipients.txt"
SIDECAR_NAMES = frozenset({READY_ASSETS_NAME, RECIPIENTS_NAME})
MAX_SIDECAR_BYTES = 256 * 1024 * 1024  # a READY set line is ~400 bytes: far beyond any real set, still bounded


class SidecarError(ValueError):
    """A sidecar file is malformed. The message never contains file content."""


def ready_assets_bytes(assets: Iterable[ReadyAsset]) -> bytes:
    return canonical_bytes(assets)


def parse_ready_assets(data: bytes) -> tuple[ReadyAsset, ...]:
    if not data.startswith(READY_SET_HEADER):
        raise SidecarError("the READY set file has no v1 header")
    try:
        text = data[len(READY_SET_HEADER) :].decode("ascii")
    except UnicodeDecodeError:
        raise SidecarError("the READY set file is not ASCII") from None
    assets: list[ReadyAsset] = []
    for line in text.splitlines():
        fields = line.split(FIELD_SEPARATOR)
        if len(fields) != 8:
            raise SidecarError("a READY set line does not have 8 fields")
        try:
            assets.append(
                ReadyAsset(
                    asset_id=uuid.UUID(fields[0]),
                    key_original=fields[1],
                    key_display=fields[2],
                    key_thumbnail=fields[3],
                    byte_size=int(fields[4]),
                    display_byte_size=int(fields[5]),
                    thumbnail_byte_size=int(fields[6]),
                    sha256=fields[7],
                )
            )
        except ValueError:
            raise SidecarError("a READY set line holds an invalid value") from None
    try:
        reproduced = canonical_bytes(assets)
    except ReadySetFormatError:
        raise SidecarError("the READY set file is not canonical") from None
    if reproduced != data:
        raise SidecarError("the READY set file is not canonical")
    return tuple(assets)


def recipients_bytes(recipients: Iterable[str]) -> bytes:
    values = parse_age_recipients(recipients)
    return ("\n".join(values) + "\n").encode("ascii")


def parse_recipients(data: bytes) -> tuple[str, ...]:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        raise SidecarError("the recipients file is not ASCII") from None
    try:
        recipients = parse_age_recipients(text.splitlines())
    except AgeRecipientError:
        raise SidecarError("the recipients file holds an invalid recipient") from None
    if recipients_bytes(recipients) != data:
        raise SidecarError("the recipients file is not canonical")
    return recipients
