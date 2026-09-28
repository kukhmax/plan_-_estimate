"""Read-only media integrity check (Stage 14B.4; 14A §13.3, 14B plan §14).

Compares PhotoAsset metadata (DB snapshots) with the object inventory of one
storage target reached through the provider-neutral `MediaStorageAdmin`
port. Works the same against R2 or an independent backup target: nothing
here is provider-specific.

Safe by design: the only storage calls are `iter_keys`, `head_object` and --
only with `verify_sha256=True` -- `download_to` into a bounded temporary
workspace that is always removed. It never writes, deletes or repairs
objects, never changes DB rows, never presigns URLs and never prints
credentials.

Conservative orphan semantics: an object not referenced by any asset row is
an ORPHAN CANDIDATE only (e.g. an upload committed after the DB backup
point, or an abandoned upload). Nothing is ever classified as safe to
delete, and there is no cleanup.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

import anyio

from app.domain.exceptions import PhotoTooLargeError
from app.domain.photos.image_processing import hash_file_bounded
from app.domain.photos.keys import PHOTO_KEY_PREFIX
from app.domain.photos.temp import photo_workspace
from app.domain.services.media_storage import MediaStorageAdmin, ObjectInfo
from app.domain.services.photo_asset_service import PhotoAssetSnapshot
from app.models.photo_asset import PhotoAssetStatus

# photos/v1/{uuid}/original.{jpg|png|webp} | display.jpg | thumb.jpg
_KNOWN_KEY = re.compile(
    r"^photos/v1/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/"
    r"(original\.(jpg|png|webp)|display\.jpg|thumb\.jpg)$"
)


class Severity(StrEnum):
    ERROR = "ERROR"  # integrity failure -> non-zero exit
    WARNING = "WARNING"  # needs attention; not a failure unless --strict
    INFO = "INFO"


class FindingKind(StrEnum):
    MISSING_ORIGINAL = "MISSING_ORIGINAL"  # READY asset: evidence loss
    MISSING_DERIVATIVE = "MISSING_DERIVATIVE"  # READY asset: regenerable from the original
    SIZE_MISMATCH = "SIZE_MISMATCH"  # READY asset: stored size != persisted size
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"  # READY original: sha256 != persisted (opt-in)
    PENDING_INCOMPLETE = "PENDING_INCOMPLETE"  # storage finalization not completed
    FAILED_RELATED = "FAILED_RELATED"  # objects of a FAILED asset
    ORPHAN_CANDIDATE = "ORPHAN_CANDIDATE"  # known key layout, no asset row
    UNKNOWN_KEY = "UNKNOWN_KEY"  # under the prefix, unrecognized layout
    OTHER_STORAGE = "OTHER_STORAGE"  # asset rows of another logical store, not checked


@dataclass(frozen=True)
class Finding:
    kind: FindingKind
    severity: Severity
    key: str | None = None
    asset_id: str | None = None
    detail: str = ""


@dataclass
class IntegrityReport:
    storage_name: str
    checked_assets: Counter = field(default_factory=Counter)
    expected_present: int = 0
    findings: list[Finding] = field(default_factory=list)
    checksum_verified: int = 0

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.WARNING]

    def exit_code(self, strict: bool = False) -> int:
        if self.errors or (strict and self.warnings):
            return 1
        return 0



def _expected(asset: PhotoAssetSnapshot) -> list[tuple[str, str, int]]:
    return [
        ("original", asset.storage_key_original, asset.byte_size),
        ("display", asset.storage_key_display, asset.display_byte_size),
        ("thumbnail", asset.storage_key_thumbnail, asset.thumbnail_byte_size),
    ]


async def run_integrity_check(
    assets: list[PhotoAssetSnapshot],
    storage: MediaStorageAdmin,
    *,
    storage_name: str,
    temp_dir: str,
    verify_sha256: bool = False,
    pending_stale_after_seconds: int = 86400,
    prefix: str = PHOTO_KEY_PREFIX,
    now: datetime | None = None,
) -> IntegrityReport:
    """Check `assets` of logical store `storage_name` against `storage`.

    Storage errors (MediaStorageUnavailable / Misconfigured / Disabled)
    propagate: an incomplete run is never reported as a clean one.
    """
    now = now or datetime.now(timezone.utc)
    report = IntegrityReport(storage_name=storage_name)
    referenced: set[str] = set()

    other = [a for a in assets if a.storage_name != storage_name]
    if other:
        report.findings.append(
            Finding(
                FindingKind.OTHER_STORAGE,
                Severity.INFO,
                detail=f"{len(other)} asset(s) belong to another logical store and were not checked",
            )
        )

    for asset in (a for a in assets if a.storage_name == storage_name):
        report.checked_assets[asset.status.value] += 1
        expected = _expected(asset)
        referenced.update(key for _, key, _ in expected)
        heads: list[tuple[str, str, int, ObjectInfo | None]] = []
        for variant, key, size in expected:
            heads.append((variant, key, size, await storage.head_object(key)))

        if asset.status is PhotoAssetStatus.READY:
            await _check_ready(report, asset, heads, storage, temp_dir, verify_sha256)
        else:
            present = sum(1 for *_, info in heads if info is not None)
            mismatched = sum(1 for _, _, size, info in heads if info is not None and info.size != size)
            detail = f"{present}/3 objects present"
            if mismatched:
                detail += f", {mismatched} size mismatch(es)"
            if asset.status is PhotoAssetStatus.PENDING:
                age = (now - _aware(asset.created_at)).total_seconds()
                stale = age > pending_stale_after_seconds
                detail += "; stale PENDING (abandoned upload?)" if stale else "; upload may be in progress"
                report.findings.append(
                    Finding(
                        FindingKind.PENDING_INCOMPLETE,
                        Severity.WARNING if stale else Severity.INFO,
                        asset_id=str(asset.id),
                        detail=detail,
                    )
                )
            else:
                report.findings.append(
                    Finding(
                        FindingKind.FAILED_RELATED,
                        Severity.WARNING if present else Severity.INFO,
                        asset_id=str(asset.id),
                        detail=detail,
                    )
                )

    # Inventory: keys of this store that no asset row references.
    for asset in other:
        referenced.update(key for _, key, _ in _expected(asset))
    async for key in storage.iter_keys(prefix):
        if key in referenced:
            continue
        if _KNOWN_KEY.match(key):
            report.findings.append(
                Finding(
                    FindingKind.ORPHAN_CANDIDATE,
                    Severity.WARNING,
                    key=key,
                    detail="no asset row references this key (not deletable by this tool)",
                )
            )
        else:
            report.findings.append(
                Finding(FindingKind.UNKNOWN_KEY, Severity.WARNING, key=key, detail="unrecognized key layout")
            )
    return report


async def _check_ready(
    report: IntegrityReport,
    asset: PhotoAssetSnapshot,
    heads: list[tuple[str, str, int, ObjectInfo | None]],
    storage: MediaStorageAdmin,
    temp_dir: str,
    verify_sha256: bool,
) -> None:
    for variant, key, size, info in heads:
        if info is None:
            if variant == "original":
                kind, detail = FindingKind.MISSING_ORIGINAL, "original missing: evidence loss"
            else:
                kind, detail = FindingKind.MISSING_DERIVATIVE, f"{variant} missing: regenerable from the original"
            report.findings.append(Finding(kind, Severity.ERROR, key=key, asset_id=str(asset.id), detail=detail))
        elif info.size != size:
            report.findings.append(
                Finding(
                    FindingKind.SIZE_MISMATCH,
                    Severity.ERROR,
                    key=key,
                    asset_id=str(asset.id),
                    detail=f"{variant}: stored {info.size} bytes, expected {size}",
                )
            )
        else:
            report.expected_present += 1
            if verify_sha256 and variant == "original":
                if await _sha256_matches(storage, key, asset, temp_dir):
                    report.checksum_verified += 1
                else:
                    report.findings.append(
                        Finding(
                            FindingKind.CHECKSUM_MISMATCH,
                            Severity.ERROR,
                            key=key,
                            asset_id=str(asset.id),
                            detail="original sha256 differs from the persisted value",
                        )
                    )


async def _sha256_matches(
    storage: MediaStorageAdmin, key: str, asset: PhotoAssetSnapshot, temp_dir: str
) -> bool:
    with photo_workspace(temp_dir) as workspace:
        target = Path(workspace) / "original.bin"
        await storage.download_to(key, target)
        try:
            digest, _ = await anyio.to_thread.run_sync(hash_file_bounded, target, asset.byte_size)
        except PhotoTooLargeError:
            return False
        return digest == asset.sha256


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def format_report(report: IntegrityReport) -> str:
    """Human-readable summary: keys and asset ids only (no URLs, no secrets)."""
    lines = [
        f"Media integrity check — logical store: {report.storage_name}",
        "Assets checked: "
        + (", ".join(f"{k}={v}" for k, v in sorted(report.checked_assets.items())) or "none"),
        f"READY objects present with expected size: {report.expected_present}",
    ]
    if report.checksum_verified:
        lines.append(f"Originals verified by sha256: {report.checksum_verified}")
    counts = Counter(f.kind.value for f in report.findings)
    lines.append("Findings: " + (", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"))
    for finding in report.findings:
        target = finding.key or (f"asset {finding.asset_id}" if finding.asset_id else "-")
        suffix = f" (asset {finding.asset_id})" if finding.key and finding.asset_id else ""
        lines.append(f"  [{finding.severity.value}] {finding.kind.value}: {target}{suffix} — {finding.detail}")
    lines.append(
        f"Result: {len(report.errors)} error(s), {len(report.warnings)} warning(s). "
        "Read-only: nothing was modified or deleted."
    )
    return "\n".join(lines)
