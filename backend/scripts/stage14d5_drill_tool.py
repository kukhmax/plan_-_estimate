"""Stage 14D.5 drill tool: seed the synthetic fixture, check serving of restored data, inventory buckets.

Contract: docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §11-§12, §16.17; runbook: docs/STAGE_14D5_DRILL_RUNBOOK.md.

    seed               generate the synthetic images (JPEG, PNG, WebP, EXIF-orientation JPEG -- generated here, no real
                       media) and upload them through the REAL upload endpoint of a SCRATCH backend (plan §11 step 1).
                       Writes a fixture file (ids, sizes, original SHA-256) for the later checks.
    verify-serving     plan §11 step 6: a scratch backend pointed at the restored database and the drill-restore bucket
                       serves the list, the detail and the presigned thumbnail / display URLs; the bytes of every URL
                       hash to the sealed manifest of the drill run; the originals match the fixture.
    inventory          read-only listing digest of one bucket (R2 or Oracle): object count, bytes and a SHA-256 over the
                       sorted "key, size, etag" lines. Run before and after the drill against production resources.
    compare-inventory  two inventory files must be identical (the "no write to any production resource" proof).

`seed` and `verify-serving` talk only to a scratch backend (loopback, a host containing `scratch`, or --allowed-host) and
the scratch backend must run in the development environment with mock authentication -- it is a throw-away drill service,
never the production API. `inventory` only lists. Nothing here prints a secret, a presigned URL or an object key.

Exit codes: 0 PASS, 1 FAIL (a check failed / inventories differ), 2 cannot run (configuration, guard, missing library),
3 no OCI principal.
"""

import argparse
import asyncio
import hashlib
import io
import json
import os
import re
import sys
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import httpx
from PIL import Image

EXIT_PASS, EXIT_FAIL, EXIT_CANNOT_RUN, EXIT_NO_PRINCIPAL = 0, 1, 2, 3

FIXTURE_FORMAT = "plan-estimate/drill-fixture/v1"
INVENTORY_FORMAT = "plan-estimate/bucket-inventory/v1"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
SCRATCH_HOST_MARKER = "scratch"
FILE_MODE = 0o600
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DrillToolError(RuntimeError):
    """A condition that stops the tool. The message never contains a secret, a URL or an object key."""


# --- the synthetic fixture (plan §12) -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class FixtureImage:
    name: str  # also the original filename
    content_type: str
    data: bytes
    category: str
    caption: str
    expect_rotated: bool = False  # EXIF orientation 6: the stored size is the displayed (swapped) size


def _gradient(width: int, height: int, seed: int) -> Image.Image:
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    assert pixels is not None
    for y in range(height):
        for x in range(width):
            pixels[x, y] = ((x * 255 // width + seed * 40) % 256, (y * 255 // height) % 256, ((x + y) * 255 // (width + height) + seed * 70) % 256)
    return image


def _encode(image: Image.Image, fmt: str, **options: Any) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **options)
    return buffer.getvalue()


def build_fixture_images() -> list[FixtureImage]:
    """Deterministic, generated images only: a JPEG, a PNG, a WebP and a JPEG with EXIF orientation 6."""
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90 deg clockwise to display
    return [
        FixtureImage("drill-jpeg.jpg", "image/jpeg", _encode(_gradient(640, 480, 1), "JPEG", quality=85), "BEFORE", "DRILL jpeg"),
        FixtureImage("drill-png.png", "image/png", _encode(_gradient(320, 240, 2), "PNG"), "GENERAL", "DRILL png"),
        FixtureImage("drill-webp.webp", "image/webp", _encode(_gradient(400, 300, 3), "WEBP", quality=80), "AFTER", "DRILL webp"),
        FixtureImage(
            "drill-exif.jpg", "image/jpeg", _encode(_gradient(600, 300, 4), "JPEG", quality=85, exif=exif), "DEFECT", "DRILL exif",
            expect_rotated=True,
        ),
    ]


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- guards -----------------------------------------------------------------------------------------------------------------


def check_scratch_url(base_url: str, allowed_hosts: Sequence[str] = ()) -> str:
    """The backend must be recognisably a scratch / loopback service. Returns the normalized base URL."""
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise DrillToolError("the backend URL is not a plain http(s) URL")
    if host not in LOOPBACK_HOSTS and SCRATCH_HOST_MARKER not in host and host not in {h.lower() for h in allowed_hosts}:
        raise DrillToolError(f"the backend host must be loopback, contain '{SCRATCH_HOST_MARKER}' or be explicitly allowed")
    return f"{parsed.scheme}://{parsed.netloc}"


def write_private_file(path: Path, data: bytes) -> None:
    """Exclusive create (never overwrite, never follow a symlink), 0600, full write, fsync."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, FILE_MODE)
    try:
        os.fchmod(fd, FILE_MODE)
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
        os.fsync(fd)
    finally:
        os.close(fd)


def canonical(document: Mapping[str, Any]) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


# --- the scratch backend's API ---------------------------------------------------------------------------------------------------


class DrillApi:
    """The few calls the drill makes against a scratch backend (httpx client injected)."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._headers: dict[str, str] = {}

    async def _json(self, response: httpx.Response, *expected: int) -> Any:
        if response.status_code not in expected:
            code = ""
            try:
                code = str(response.json()["detail"]["code"])
            except (ValueError, KeyError, TypeError):
                pass
            raise DrillToolError(f"unexpected HTTP {response.status_code}{' ' + code if code else ''} from the backend")
        return response.json()

    async def login(self) -> None:
        body = await self._json(await self._client.post("/api/auth/telegram", json={"init_data": "mock"}), 200)
        self._headers = {"Authorization": f"Bearer {body['access_token']}"}

    async def create_client(self) -> str:
        payload = {"client_type": "PRIVATE_PERSON", "first_name": "DRILL", "last_name": "Fixture"}
        return str((await self._json(await self._client.post("/api/clients", json=payload, headers=self._headers), 201))["id"])

    async def create_project(self, client_id: str) -> str:
        payload = {"name": "DRILL fixture", "address": "Drill 1", "city": "Drillville", "postal_code": "00-000", "client_id": client_id}
        return str((await self._json(await self._client.post("/api/projects", json=payload, headers=self._headers), 201))["id"])

    async def upload(self, project_id: str, image: FixtureImage, upload_id: str) -> dict[str, Any]:
        data = {"upload_id": upload_id, "context": "PROJECT", "category": image.category, "caption": image.caption, "include_in_report": "true"}
        files = {"file": (image.name, image.data, image.content_type)}
        response = await self._client.post(f"/api/projects/{project_id}/photos", data=data, files=files, headers=self._headers)
        result: dict[str, Any] = await self._json(response, 200, 201)
        return result

    async def list_photos(self, project_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params: dict[str, str] = {"limit": "50"}
            if cursor:
                params["cursor"] = cursor
            page = await self._json(await self._client.get(f"/api/projects/{project_id}/photos", params=params, headers=self._headers), 200)
            items.extend(page["items"])
            cursor = page["next_cursor"]
            if not cursor:
                return items

    async def detail(self, project_id: str, asset_id: str) -> dict[str, Any]:
        result: dict[str, Any] = await self._json(
            await self._client.get(f"/api/projects/{project_id}/photos/{asset_id}", headers=self._headers), 200
        )
        return result


# --- seed ----------------------------------------------------------------------------------------------------------------------------


async def seed(api: DrillApi, images: Sequence[FixtureImage]) -> dict[str, Any]:
    """Upload the images through the real endpoint; return the fixture document."""
    await api.login()
    client_id = await api.create_client()
    project_id = await api.create_project(client_id)
    entries = []
    for image in images:
        upload_id = str(uuid.uuid4())
        result = await api.upload(project_id, image, upload_id)
        asset = result["asset"]
        if asset["status"] != "READY":
            raise DrillToolError("an uploaded photo is not READY")
        entries.append(
            {
                "name": image.name,
                "content_type": image.content_type,
                "upload_id": upload_id,
                "asset_id": asset["id"],
                "original_sha256": sha256_hex(image.data),
                "original_size": len(image.data),
                "stored_width": asset["width"],
                "stored_height": asset["height"],
                "expect_rotated": image.expect_rotated,
                "category": image.category,
            }
        )
    return {"format": FIXTURE_FORMAT, "client_id": client_id, "project_id": project_id, "images": entries}


def parse_fixture(data: bytes) -> dict[str, Any]:
    try:
        document = json.loads(data)
    except ValueError:
        raise DrillToolError("the fixture file is not JSON") from None
    if not isinstance(document, dict) or document.get("format") != FIXTURE_FORMAT:
        raise DrillToolError("the fixture file has the wrong format")
    images = document.get("images")
    if not isinstance(images, list) or not images or not all(isinstance(i, dict) for i in images):
        raise DrillToolError("the fixture file has no images")
    for key in ("project_id", "client_id"):
        if not isinstance(document.get(key), str):
            raise DrillToolError("the fixture file is incomplete")
    for image in images:
        if not isinstance(image.get("asset_id"), str) or not _SHA256.match(str(image.get("original_sha256", ""))):
            raise DrillToolError("the fixture file is incomplete")
    return document


# --- verify-serving (plan §11 step 6) -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


Fetch = Callable[[str], Awaitable[tuple[int, bytes]]]


async def http_fetch(url: str, *, transport: httpx.AsyncBaseTransport | None = None) -> tuple[int, bytes]:
    """GET a presigned URL WITHOUT the API's Authorization header (it is a bearer URL of its own); no redirect is followed."""
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False, transport=transport) as client:
        response = await client.get(url)
        return response.status_code, response.content


def manifest_hashes(manifest_objects: Sequence[Any]) -> dict[tuple[str, str], str]:
    """(asset_id, role) -> SHA-256 from the sealed manifest's object lines."""
    return {(obj.asset_id, obj.role.value): obj.sha256 for obj in manifest_objects}


async def verify_serving(api: DrillApi, fixture: Mapping[str, Any], manifest_objects: Sequence[Any], fetch: Fetch) -> list[CheckResult]:
    results: list[CheckResult] = []
    project_id = str(fixture["project_id"])
    images = list(fixture["images"])
    expected_ids = {str(i["asset_id"]) for i in images}
    hashes = manifest_hashes(manifest_objects)
    manifest_ids = {asset for asset, _ in hashes}

    def record(name: str, passed: bool, detail: str) -> None:
        results.append(CheckResult(name, passed, detail))

    await api.login()
    items = await api.list_photos(project_id)
    listed = {str(i["asset"]["id"]) for i in items}
    record(
        "list_matches_fixture_and_manifest",
        listed == expected_ids == manifest_ids and len(items) == len(expected_ids),
        f"listed={len(listed)} fixture={len(expected_ids)} manifest={len(manifest_ids)}",
    )
    record("list_thumbnail_urls_present", all(i.get("thumbnail_url") for i in items), f"items={len(items)}")

    details: dict[str, dict[str, Any]] = {}
    for image in images:
        asset_id = str(image["asset_id"])
        try:
            details[asset_id] = await api.detail(project_id, asset_id)
        except DrillToolError:
            pass
    record(
        "detail_ready_with_urls",
        len(details) == len(images)
        and all(d["asset"]["status"] == "READY" and d["thumbnail_url"] and d["display_url"] for d in details.values()),
        f"details={len(details)}/{len(images)}",
    )

    mismatched = unreachable = 0
    for asset_id, detail in details.items():
        for role, field in (("thumbnail", "thumbnail_url"), ("display", "display_url")):
            expected = hashes.get((asset_id, role))
            url = detail.get(field)
            if not url:
                unreachable += 1
                continue
            try:
                status, body = await fetch(url)
            except (httpx.HTTPError, OSError):
                unreachable += 1
                continue
            if status != 200:
                unreachable += 1
            elif expected is None or sha256_hex(body) != expected:
                mismatched += 1
    record(
        "derivative_bytes_match_manifest",
        bool(details) and mismatched == 0 and unreachable == 0,
        f"urls={2 * len(details)} unreachable={unreachable} mismatched={mismatched}",
    )

    original_mismatch = sum(1 for i in images if hashes.get((str(i["asset_id"]), "original")) != i["original_sha256"])
    record("originals_match_fixture", original_mismatch == 0, f"images={len(images)} mismatched={original_mismatch}")

    drift = 0
    for image in images:
        asset = details.get(str(image["asset_id"]), {}).get("asset")
        if asset is None or (asset["width"], asset["height"]) != (image["stored_width"], image["stored_height"]):
            drift += 1
    record("dimensions_unchanged_by_the_restore", drift == 0, f"images={len(images)} drifted={drift}")

    rotated = [i for i in images if i["expect_rotated"]]
    portrait = all(
        (a := details.get(str(i["asset_id"]), {}).get("asset")) is not None and a["height"] > a["width"] for i in rotated
    )
    record("exif_orientation_case_is_applied", bool(rotated) and portrait, f"cases={len(rotated)}")

    leaked = any("/original" in json.dumps(d) for d in details.values())
    record("original_is_never_exposed", not leaked, "no /original in any detail response")
    return results


# --- inventory ----------------------------------------------------------------------------------------------------------------------------


def inventory_document(provider: str, bucket: str, lines: Sequence[tuple[str, int, str]]) -> dict[str, Any]:
    ordered = sorted(lines)
    digest = hashlib.sha256()
    for key, size, etag in ordered:
        digest.update(f"{key}\t{size}\t{etag}\n".encode())
    return {
        "format": INVENTORY_FORMAT,
        "provider": provider,
        "bucket": bucket,
        "objects": len(ordered),
        "bytes": sum(size for _, size, _ in ordered),
        "digest": digest.hexdigest(),
    }


def r2_listing(client: Any, bucket: str) -> list[tuple[str, int, str]]:
    """List a bucket with the S3 API. Only `list_objects_v2` is ever called."""
    lines: list[tuple[str, int, str]] = []
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket}
        if token:
            kwargs["ContinuationToken"] = token
        page = client.list_objects_v2(**kwargs)
        lines += [(o["Key"], int(o["Size"]), str(o.get("ETag", "")).strip('"')) for o in page.get("Contents", [])]
        if not page.get("IsTruncated"):
            return lines
        token = page["NextContinuationToken"]


def oci_listing(client: Any, namespace: str, bucket: str) -> list[tuple[str, int, str]]:
    """List a bucket with the OCI API. Only `list_objects` is ever called."""
    lines: list[tuple[str, int, str]] = []
    start: str | None = None
    while True:
        response = client.list_objects(namespace, bucket, fields="name,size,md5", start=start)
        data = response.data
        lines += [(o.name, int(o.size or 0), str(getattr(o, "md5", "") or "")) for o in data.objects]
        start = data.next_start_with
        if not start:
            return lines


def compare_inventories(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    """Names of the differing fields (empty = identical)."""
    for document in (before, after):
        if document.get("format") != INVENTORY_FORMAT:
            raise DrillToolError("not an inventory file")
    return [field for field in ("provider", "bucket", "objects", "bytes", "digest") if before.get(field) != after.get(field)]


# --- command line --------------------------------------------------------------------------------------------------------------------------


def format_results(title: str, results: Sequence[CheckResult]) -> str:
    lines = [title]
    lines += [f"  [{'PASS' if r.passed else 'FAIL'}] {r.name}: {r.detail}" for r in results]
    passed = sum(1 for r in results if r.passed)
    lines.append(f"RESULT: {'PASS' if passed == len(results) else 'FAIL'} ({passed}/{len(results)} checks passed)")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("seed", "verify-serving"):
        sub = commands.add_parser(name)
        sub.add_argument("--base-url", required=True, help="the SCRATCH backend, e.g. http://scratch-backend:8000")
        sub.add_argument("--allowed-host", action="append", default=[])
        sub.add_argument("--fixture-file", required=True, help="absolute path (seed: a NEW file; verify-serving: the seeded file)")
    verify = commands.choices["verify-serving"]
    verify.add_argument("--run-id", required=True, help="the drill run whose sealed manifest is the reference")
    verify.add_argument("--oci-config", default=None, help="API-key config of the restore principal (else instance principal)")
    verify.add_argument("--oci-profile", default="DEFAULT")
    inv = commands.add_parser("inventory")
    inv.add_argument("--provider", required=True, choices=("r2", "oci"))
    inv.add_argument("--bucket", required=True)
    inv.add_argument("--namespace", default=os.environ.get("OCI_NAMESPACE", ""))
    inv.add_argument("--region", default="eu-frankfurt-1")
    inv.add_argument("--oci-config", default=None)
    inv.add_argument("--oci-profile", default="DEFAULT")
    inv.add_argument("--output", required=True, help="absolute path of a NEW inventory file")
    cmp_ = commands.add_parser("compare-inventory")
    cmp_.add_argument("before")
    cmp_.add_argument("after")
    return parser


def _absolute(value: str, what: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise DrillToolError(f"{what} must be an absolute path")
    return path


async def cmd_seed(args: argparse.Namespace) -> int:
    base = check_scratch_url(args.base_url, args.allowed_host)
    path = _absolute(args.fixture_file, "--fixture-file")
    if os.path.lexists(path):
        raise DrillToolError("the fixture file already exists; refusing to overwrite it")
    async with httpx.AsyncClient(base_url=base, timeout=60.0) as client:
        fixture = await seed(DrillApi(client), build_fixture_images())
    write_private_file(path, canonical(fixture))
    print(f"seeded: project={fixture['project_id']} images={len(fixture['images'])} (fixture file written)")
    return EXIT_PASS


def _oci_reader(args: argparse.Namespace) -> Any:
    from app.backup.oci_target import OciBackupReader

    namespace, bucket = os.environ.get("BACKUP_OCI_NAMESPACE", ""), os.environ.get("BACKUP_OCI_BUCKET", "")
    region = os.environ.get("BACKUP_OCI_REGION", "eu-frankfurt-1")
    if not namespace or not bucket:
        raise DrillToolError("BACKUP_OCI_NAMESPACE and BACKUP_OCI_BUCKET are required")
    if args.oci_config:
        return OciBackupReader.from_api_key_config(
            namespace=namespace, bucket=bucket, config_file=_absolute(args.oci_config, "--oci-config"), profile=args.oci_profile, region=region
        )
    return OciBackupReader.from_instance_principal(namespace=namespace, bucket=bucket, region=region)


async def cmd_verify_serving(args: argparse.Namespace) -> int:
    from app.backup.media_sync import load_prior_run
    from app.backup.run_id import validate_run_id
    from app.domain.exceptions import MediaStorageError

    base = check_scratch_url(args.base_url, args.allowed_host)
    fixture = parse_fixture(_absolute(args.fixture_file, "--fixture-file").read_bytes())
    run_id = validate_run_id(args.run_id)
    try:
        reader = _oci_reader(args)
    except MediaStorageError as exc:
        if exc.error_code is None:
            raise DrillToolError(str(exc)) from None
        print(f"oci principal: NOT obtainable ({type(exc).__name__})")
        return EXIT_NO_PRINCIPAL
    import tempfile

    with tempfile.TemporaryDirectory(prefix="drill-verify-") as scratch:
        run = await load_prior_run(reader, run_id, scratch_dir=Path(scratch))
    async with httpx.AsyncClient(base_url=base, timeout=60.0) as client:
        results = await verify_serving(DrillApi(client), fixture, run.manifest.objects, http_fetch)
    print(format_results("14D.5 serving check (restored scratch database + drill-restore bucket):", results))
    return EXIT_PASS if all(r.passed for r in results) else EXIT_FAIL


async def cmd_inventory(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    if not _BUCKET.match(args.bucket):
        raise DrillToolError("--bucket is not a valid bucket name")
    path = _absolute(args.output, "--output")
    if os.path.lexists(path):
        raise DrillToolError("the output file already exists; refusing to overwrite it")
    if args.provider == "r2":
        import boto3  # type: ignore[import-untyped,unused-ignore]
        from botocore.config import Config  # type: ignore[import-untyped,unused-ignore]

        names = ("INVENTORY_S3_ENDPOINT_URL", "INVENTORY_S3_ACCESS_KEY_ID", "INVENTORY_S3_SECRET_ACCESS_KEY")
        missing = [n for n in names if not env.get(n, "").strip()]
        if missing:
            raise DrillToolError(f"{', '.join(missing)} required")
        client = boto3.session.Session().client(
            "s3", endpoint_url=env[names[0]].strip(), region_name="auto", aws_access_key_id=env[names[1]].strip(),
            aws_secret_access_key=env[names[2]].strip(),
            config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}, s3={"addressing_style": "path"}),
        )  # fmt: skip
        lines = await asyncio.to_thread(r2_listing, client, args.bucket)
    else:
        if not args.namespace:
            raise DrillToolError("--namespace (or OCI_NAMESPACE) is required")
        try:
            import oci  # type: ignore[import-untyped,import-not-found,unused-ignore]
        except ImportError:
            raise DrillToolError("the OCI SDK is not installed (pip install oci==2.187.1)") from None
        if args.oci_config:
            config = oci.config.from_file(str(_absolute(args.oci_config, "--oci-config")), args.oci_profile)
            oci_client = oci.object_storage.ObjectStorageClient(config, retry_strategy=oci.retry.NoneRetryStrategy())
        else:
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            oci_client = oci.object_storage.ObjectStorageClient(
                {"region": args.region}, signer=signer, retry_strategy=oci.retry.NoneRetryStrategy()
            )
        lines = await asyncio.to_thread(oci_listing, oci_client, args.namespace, args.bucket)
    document = inventory_document(args.provider, args.bucket, lines)
    write_private_file(path, canonical(document))
    print(f"inventory: provider={args.provider} bucket={args.bucket} objects={document['objects']} bytes={document['bytes']}")
    return EXIT_PASS


def cmd_compare(args: argparse.Namespace) -> int:
    before = json.loads(_absolute(args.before, "before").read_bytes())
    after = json.loads(_absolute(args.after, "after").read_bytes())
    differing = compare_inventories(before, after)
    if differing:
        print(f"inventories DIFFER in: {', '.join(differing)}")
        return EXIT_FAIL
    print(f"inventories identical: objects={after['objects']} bytes={after['bytes']}")
    return EXIT_PASS


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    environment = os.environ if env is None else env
    try:
        if args.command == "seed":
            return asyncio.run(cmd_seed(args))
        if args.command == "verify-serving":
            return asyncio.run(cmd_verify_serving(args))
        if args.command == "inventory":
            return asyncio.run(cmd_inventory(args, environment))
        return cmd_compare(args)
    except (DrillToolError, OSError, ImportError) as exc:
        print(f"cannot run: {exc if isinstance(exc, DrillToolError) else type(exc).__name__}", file=sys.stderr)
        return EXIT_CANNOT_RUN


if __name__ == "__main__":
    sys.exit(main())
