"""Stage 14D.5 — the drill tool: fixture, seeding through the REAL upload endpoint, serving check, inventories."""

import io
import json
import os
import stat
from types import SimpleNamespace
from urllib.parse import unquote, urlparse

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.backup import manifest as mf
from app.core.config import settings
from app.main import app
from scripts import stage14d5_drill_tool as tool
from tests.test_stage14c4_photos_api import (
    api,  # noqa: F401 - the real app with in-memory storage (fixture)
)

RUN = "20261004T120000Z-0123abcd"


@pytest.fixture(autouse=True)
def scratch_backend_environment(monkeypatch):
    """The scratch backend the tool talks to runs in the development environment with mock authentication. Another test
    module leaves APP_ENV="production" behind, so the environment is pinned here (and restored afterwards)."""
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "MOCK_TELEGRAM_AUTH", True)


# --- the synthetic fixture -----------------------------------------------------------------------------------------------


def test_the_fixture_is_four_generated_images_of_the_required_kinds():
    images = tool.build_fixture_images()
    assert [i.content_type for i in images] == ["image/jpeg", "image/png", "image/webp", "image/jpeg"]
    assert len({i.name for i in images}) == 4 and len({tool.sha256_hex(i.data) for i in images}) == 4
    for image, fmt in zip(images, ("JPEG", "PNG", "WEBP", "JPEG"), strict=True):
        decoded = Image.open(io.BytesIO(image.data))
        decoded.load()
        assert decoded.format == fmt and image.data.startswith(b"\xff\xd8" if fmt == "JPEG" else image.data[:2])
    exif = Image.open(io.BytesIO(images[3].data)).getexif()
    assert exif.get(0x0112) == 6 and images[3].expect_rotated and not any(i.expect_rotated for i in images[:3])
    assert Image.open(io.BytesIO(images[3].data)).size == (600, 300)  # landscape as stored; displayed as portrait


def test_the_fixture_is_deterministic():
    first, second = tool.build_fixture_images(), tool.build_fixture_images()
    assert [i.data for i in first] == [i.data for i in second]


# --- guards ------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        ("http://127.0.0.1:8000", True),
        ("http://localhost:8000/", True),
        ("http://scratch-backend:8000", True),
        ("https://drill-scratch.internal", True),
        ("https://plan-estimate.pl", False),
        ("https://api.plan-estimate.pl/api", False),
        ("ftp://localhost", False),
        ("http://user:pw@localhost", False),
        ("http://localhost?x=1", False),
        ("localhost:8000", False),
        ("", False),
    ],
)
def test_the_backend_must_be_a_scratch_or_loopback_service(url, ok):
    if ok:
        assert tool.check_scratch_url(url).startswith("http")
    else:
        with pytest.raises(tool.DrillToolError):
            tool.check_scratch_url(url)


def test_an_explicit_host_allowance_is_honoured_and_exact():
    assert tool.check_scratch_url("http://drill-backend:8000", ["drill-backend"]) == "http://drill-backend:8000"
    with pytest.raises(tool.DrillToolError):
        tool.check_scratch_url("http://drill-backend2:8000", ["drill-backend"])


def test_the_production_host_is_never_accepted_even_with_a_scratch_looking_path():
    with pytest.raises(tool.DrillToolError):
        tool.check_scratch_url("https://plan-estimate.pl/scratch")


def test_private_files_are_exclusive_and_private(tmp_path):
    path = tmp_path / "f.json"
    tool.write_private_file(path, b"x\n")
    assert path.read_bytes() == b"x\n" and stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        tool.write_private_file(path, b"y")
    link = tmp_path / "link"
    os.symlink(path, link)
    with pytest.raises(FileExistsError):
        tool.write_private_file(link, b"z")
    assert path.read_bytes() == b"x\n"


# --- seeding through the real endpoint and checking the result ---------------------------------------------------------------------


@pytest.fixture
async def http(api):  # noqa: F811
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def seeded(api, http):  # noqa: F811
    return await tool.seed(tool.DrillApi(http), tool.build_fixture_images())


def manifest_objects_from(api, fixture) -> list[mf.ManifestObject]:  # noqa: F811
    """What a sealed manifest would say about the objects the real upload pipeline just stored."""
    objects = []
    for entry in fixture["images"]:
        base = f"photos/v1/{entry['asset_id']}/"
        for role, name, content_type in (
            (mf.Role.ORIGINAL, f"original.{ {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}[entry['content_type']] }", entry["content_type"]),
            (mf.Role.DISPLAY, "display.jpg", "image/jpeg"),
            (mf.Role.THUMBNAIL, "thumb.jpg", "image/jpeg"),
        ):
            data = api.storage.inner._objects[base + name].data
            objects.append(
                mf.ManifestObject(
                    asset_id=entry["asset_id"], role=role, key=base + name, size=len(data), sha256=tool.sha256_hex(data),
                    content_type=content_type, action=mf.Action.COPIED, sha_provenance=mf.DOWNLOADED, verified_at="2026-10-04T12:00:00Z",
                )
            )
    return objects


def memory_fetch(api):  # noqa: F811
    async def fetch(url: str) -> tuple[int, bytes]:
        parsed = urlparse(url)
        assert parsed.scheme == "memory"
        obj = api.storage.inner._objects.get(unquote(parsed.path.removeprefix("/")))
        return (200, obj.data) if obj else (404, b"")

    return fetch


async def test_seeding_goes_through_the_real_endpoint_and_records_the_fixture(api, http):  # noqa: F811
    fixture = await seeded(api, http)
    assert fixture["format"] == tool.FIXTURE_FORMAT and len(fixture["images"]) == 4
    assert len({e["asset_id"] for e in fixture["images"]}) == 4 and len({e["upload_id"] for e in fixture["images"]}) == 4
    originals = {e["asset_id"]: api.storage.inner._objects[next(k for k in api.storage.inner._objects if k.startswith(f"photos/v1/{e['asset_id']}/original"))].data
                 for e in fixture["images"]}
    for entry in fixture["images"]:
        assert tool.sha256_hex(originals[entry["asset_id"]]) == entry["original_sha256"]  # stored bytes = uploaded bytes
    exif = next(e for e in fixture["images"] if e["expect_rotated"])
    assert exif["stored_height"] > exif["stored_width"]  # the pipeline applied the orientation
    assert tool.parse_fixture(tool.canonical(fixture)) == fixture


async def test_the_serving_check_passes_on_what_the_real_pipeline_stored(api, http):  # noqa: F811
    fixture = await seeded(api, http)
    results = await tool.verify_serving(tool.DrillApi(http), fixture, manifest_objects_from(api, fixture), memory_fetch(api))
    assert [r.name for r in results] == [
        "list_matches_fixture_and_manifest", "list_thumbnail_urls_present", "detail_ready_with_urls",
        "derivative_bytes_match_manifest", "originals_match_fixture", "dimensions_unchanged_by_the_restore",
        "exif_orientation_case_is_applied", "original_is_never_exposed",
    ]
    assert all(r.passed for r in results), [r for r in results if not r.passed]
    assert "RESULT: PASS (8/8 checks passed)" in tool.format_results("t", results)


async def serving(api, http, fixture, objects, fetch=None):  # noqa: F811
    results = await tool.verify_serving(tool.DrillApi(http), fixture, objects, fetch or memory_fetch(api))
    return {r.name: r.passed for r in results}


async def test_a_missing_object_in_the_manifest_is_caught_by_the_listing_check(api, http):  # noqa: F811
    fixture = await seeded(api, http)
    objects = [o for o in manifest_objects_from(api, fixture) if o.asset_id != fixture["images"][0]["asset_id"]]
    outcome = await serving(api, http, fixture, objects)
    assert not outcome["list_matches_fixture_and_manifest"]


async def test_derivative_bytes_that_do_not_hash_to_the_manifest_are_caught(api, http):  # noqa: F811
    fixture = await seeded(api, http)
    inner = memory_fetch(api)

    async def corrupt_thumbnails(url: str) -> tuple[int, bytes]:
        status, body = await inner(url)
        return (status, body[:-1] + bytes([body[-1] ^ 1])) if "thumb" in url else (status, body)

    outcome = await serving(api, http, fixture, manifest_objects_from(api, fixture), corrupt_thumbnails)
    assert not outcome["derivative_bytes_match_manifest"] and outcome["detail_ready_with_urls"]


async def test_an_unreachable_url_is_caught(api, http):  # noqa: F811
    fixture = await seeded(api, http)

    async def gone(url: str) -> tuple[int, bytes]:
        return 404, b""

    assert not (await serving(api, http, fixture, manifest_objects_from(api, fixture), gone))["derivative_bytes_match_manifest"]

    async def broken(url: str) -> tuple[int, bytes]:
        raise httpx.ConnectError("down")

    assert not (await serving(api, http, fixture, manifest_objects_from(api, fixture), broken))["derivative_bytes_match_manifest"]


async def test_originals_that_differ_from_the_fixture_are_caught(api, http):  # noqa: F811
    fixture = await seeded(api, http)
    objects = [
        mf.ManifestObject(**{**o.__dict__, "sha256": "f" * 64}) if o.role is mf.Role.ORIGINAL and o.asset_id == fixture["images"][1]["asset_id"] else o
        for o in manifest_objects_from(api, fixture)
    ]
    outcome = await serving(api, http, fixture, objects)
    assert not outcome["originals_match_fixture"] and outcome["derivative_bytes_match_manifest"]


async def test_changed_dimensions_and_a_lost_orientation_are_caught(api, http):  # noqa: F811
    fixture = await seeded(api, http)
    drifted = json.loads(json.dumps(fixture))
    drifted["images"][0]["stored_width"] += 1
    assert not (await serving(api, http, drifted, manifest_objects_from(api, fixture)))["dimensions_unchanged_by_the_restore"]
    flat = json.loads(json.dumps(fixture))
    for entry in flat["images"]:
        if entry["expect_rotated"]:
            entry["stored_width"], entry["stored_height"] = 600, 300
    outcome = await serving(api, http, flat, manifest_objects_from(api, fixture))
    assert outcome["exif_orientation_case_is_applied"]  # the check reads the backend's answer, not the fixture's numbers


async def test_an_asset_the_backend_does_not_know_is_caught(api, http):  # noqa: F811
    fixture = await seeded(api, http)
    ghost = json.loads(json.dumps(fixture))
    ghost["images"][0]["asset_id"] = "00000000-0000-4000-8000-000000000000"
    outcome = await serving(api, http, ghost, manifest_objects_from(api, fixture))
    assert not outcome["detail_ready_with_urls"] and not outcome["list_matches_fixture_and_manifest"]


async def test_a_wrong_backend_answer_is_a_tool_error_without_secrets(api, http):  # noqa: F811
    fixture = await seeded(api, http)
    ghost = tool.DrillApi(http)
    await ghost.login()
    with pytest.raises(tool.DrillToolError) as excinfo:
        await ghost.detail(fixture["project_id"], "00000000-0000-4000-8000-000000000000")
    assert "404" in str(excinfo.value) and "Bearer" not in str(excinfo.value)


# --- fixture file ----------------------------------------------------------------------------------------------------------------------


def test_parse_fixture_refuses_anything_incomplete():
    good = {"format": tool.FIXTURE_FORMAT, "client_id": "c", "project_id": "p", "images": [{"asset_id": "a", "original_sha256": "a" * 64}]}
    assert tool.parse_fixture(tool.canonical(good)) == good
    bad = [
        b"not json", b"[]", tool.canonical({**good, "format": "x"}), tool.canonical({**good, "images": []}),
        tool.canonical({**good, "images": ["x"]}), tool.canonical({**good, "project_id": 1}),
        tool.canonical({**good, "images": [{"asset_id": "a", "original_sha256": "zz"}]}),
    ]
    for data in bad:
        with pytest.raises(tool.DrillToolError):
            tool.parse_fixture(data)


# --- inventory --------------------------------------------------------------------------------------------------------------------------------


def test_the_inventory_digest_is_order_independent_and_sensitive():
    a = [("k1", 10, "e1"), ("k2", 20, "e2")]
    base = tool.inventory_document("r2", "b", a)
    assert base == tool.inventory_document("r2", "b", list(reversed(a)))
    assert base["objects"] == 2 and base["bytes"] == 30 and "k1" not in json.dumps(base)
    for changed in ([("k1", 10, "e1")], [("k1", 10, "e1"), ("k2", 21, "e2")], [("k1", 10, "e1"), ("k2", 20, "eX")],
                    [("k1", 10, "e1"), ("k3", 20, "e2")], [*a, ("k3", 0, "")]):
        assert tool.inventory_document("r2", "b", changed)["digest"] != base["digest"]


def test_compare_names_the_differing_fields():
    before = tool.inventory_document("r2", "b", [("k", 1, "e")])
    assert tool.compare_inventories(before, dict(before)) == []
    after = tool.inventory_document("r2", "b", [("k", 1, "e"), ("j", 2, "f")])
    assert tool.compare_inventories(before, after) == ["objects", "bytes", "digest"]
    assert tool.compare_inventories(before, {**before, "bucket": "other"}) == ["bucket"]
    with pytest.raises(tool.DrillToolError):
        tool.compare_inventories(before, {"format": "x"})


class FakeS3:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def list_objects_v2(self, **kwargs):
        self.calls.append(kwargs)
        return self.pages[len(self.calls) - 1]

    def __getattr__(self, name):  # any other S3 verb is a test failure
        raise AssertionError(f"inventory must only list, not {name}")


def test_r2_listing_follows_continuation_and_only_lists():
    client = FakeS3([
        {"Contents": [{"Key": "a", "Size": 1, "ETag": '"e1"'}], "IsTruncated": True, "NextContinuationToken": "t1"},
        {"Contents": [{"Key": "b", "Size": 2, "ETag": '"e2"'}], "IsTruncated": False},
    ])
    assert tool.r2_listing(client, "bucket") == [("a", 1, "e1"), ("b", 2, "e2")]
    assert client.calls == [{"Bucket": "bucket"}, {"Bucket": "bucket", "ContinuationToken": "t1"}]
    assert tool.r2_listing(FakeS3([{"IsTruncated": False}]), "bucket") == []


class FakeOci:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def list_objects(self, namespace, bucket, **kwargs):
        self.calls.append((namespace, bucket, kwargs))
        objects, nxt = self.pages[len(self.calls) - 1]
        return SimpleNamespace(data=SimpleNamespace(objects=objects, next_start_with=nxt))

    def __getattr__(self, name):
        raise AssertionError(f"inventory must only list, not {name}")


def test_oci_listing_follows_the_start_marker_and_only_lists():
    obj = lambda n, s, m: SimpleNamespace(name=n, size=s, md5=m)
    client = FakeOci([([obj("a", 1, "m1")], "b"), ([obj("b", None, None)], None)])
    assert tool.oci_listing(client, "ns", "bucket") == [("a", 1, "m1"), ("b", 0, "")]
    assert [c[2]["start"] for c in client.calls] == [None, "b"]


# --- command line ---------------------------------------------------------------------------------------------------------------------------------


def test_compare_command_exit_codes(tmp_path, capsys):
    one = tool.inventory_document("r2", "b", [("k", 1, "e")])
    two = tool.inventory_document("r2", "b", [("k", 2, "e")])
    paths = {}
    for name, doc in (("one", one), ("same", one), ("two", two)):
        paths[name] = tmp_path / name
        paths[name].write_bytes(tool.canonical(doc))
    assert tool.main(["compare-inventory", str(paths["one"]), str(paths["same"])]) == tool.EXIT_PASS
    assert tool.main(["compare-inventory", str(paths["one"]), str(paths["two"])]) == tool.EXIT_FAIL
    assert "bytes, digest" in capsys.readouterr().out
    assert tool.main(["compare-inventory", "relative", str(paths["one"])]) == tool.EXIT_CANNOT_RUN


def test_seed_refuses_a_production_url_and_an_existing_fixture_file(tmp_path, capsys):
    fixture = tmp_path / "fixture.json"
    assert tool.main(["seed", "--base-url", "https://plan-estimate.pl", "--fixture-file", str(fixture)]) == tool.EXIT_CANNOT_RUN
    fixture.write_text("precious")
    assert tool.main(["seed", "--base-url", "http://localhost:1", "--fixture-file", str(fixture)]) == tool.EXIT_CANNOT_RUN
    assert fixture.read_text() == "precious" and "refusing to overwrite" in capsys.readouterr().err


def test_inventory_refuses_bad_input_before_any_network(tmp_path, capsys):
    out = tmp_path / "inv.json"
    assert tool.main(["inventory", "--provider", "r2", "--bucket", "Bad Bucket", "--output", str(out)], env={}) == tool.EXIT_CANNOT_RUN
    assert tool.main(["inventory", "--provider", "r2", "--bucket", "good-bucket", "--output", str(out)], env={}) == tool.EXIT_CANNOT_RUN
    assert "INVENTORY_S3_ENDPOINT_URL" in capsys.readouterr().err and not out.exists()
    out.write_text("x")
    assert tool.main(["inventory", "--provider", "r2", "--bucket", "good-bucket", "--output", str(out)], env={}) == tool.EXIT_CANNOT_RUN
    assert out.read_text() == "x"
    assert tool.main(["inventory", "--provider", "r2", "--bucket", "good-bucket", "--output", "relative"], env={}) == tool.EXIT_CANNOT_RUN


def test_verify_serving_refuses_a_production_url(tmp_path):
    fixture = tmp_path / "f.json"
    fixture.write_text("{}")
    args = ["verify-serving", "--base-url", "https://plan-estimate.pl", "--fixture-file", str(fixture), "--run-id", RUN]
    assert tool.main(args) == tool.EXIT_CANNOT_RUN


# --- gaps found by mutation testing --------------------------------------------------------------------------------------------------


class Rewriting(httpx.AsyncBaseTransport):
    """The real app behind ASGI, with one JSON response rewritten on the way (a backend that misbehaves)."""

    def __init__(self, rewrite) -> None:
        self.inner = ASGITransport(app=app)
        self.rewrite = rewrite

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self.inner.handle_async_request(request)
        await response.aread()
        try:
            document = json.loads(response.content)
        except ValueError:
            return response
        self.rewrite(request.url.path, document)
        content = json.dumps(document).encode()
        return httpx.Response(response.status_code, headers={"content-type": "application/json"}, content=content, request=request)


def rewriting_client(rewrite) -> AsyncClient:
    return AsyncClient(transport=Rewriting(rewrite), base_url="http://test")


async def outcome_with(api, rewrite):  # noqa: F811
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as plain:
        fixture = await seeded(api, plain)
    async with rewriting_client(rewrite) as client:
        results = await tool.verify_serving(tool.DrillApi(client), fixture, manifest_objects_from(api, fixture), memory_fetch(api))
    return {r.name: r.passed for r in results}


async def test_a_list_without_thumbnail_urls_is_caught(api):  # noqa: F811
    def rewrite(path, doc):
        if path.endswith("/photos"):
            for item in doc["items"]:
                item["thumbnail_url"] = None

    outcome = await outcome_with(api, rewrite)
    assert not outcome["list_thumbnail_urls_present"] and outcome["list_matches_fixture_and_manifest"]


@pytest.mark.parametrize("field", ["thumbnail_url", "display_url"])
async def test_a_detail_without_urls_is_caught(api, field):  # noqa: F811
    def rewrite(path, doc):
        if "asset" in doc and "attachments" in doc:
            doc[field] = None

    assert not (await outcome_with(api, rewrite))["detail_ready_with_urls"]


async def test_a_detail_that_is_not_ready_is_caught(api):  # noqa: F811
    def rewrite(path, doc):
        if "asset" in doc and "attachments" in doc:
            doc["asset"]["status"] = "PENDING"

    assert not (await outcome_with(api, rewrite))["detail_ready_with_urls"]


async def test_a_lost_orientation_in_the_backend_answer_is_caught(api):  # noqa: F811
    def rewrite(path, doc):
        if "asset" in doc and "attachments" in doc:
            doc["asset"]["width"], doc["asset"]["height"] = max(doc["asset"]["width"], doc["asset"]["height"]), min(doc["asset"]["width"], doc["asset"]["height"])

    outcome = await outcome_with(api, rewrite)
    assert not outcome["exif_orientation_case_is_applied"]


async def test_an_exposed_original_is_caught(api):  # noqa: F811
    def rewrite(path, doc):
        if "asset" in doc and "attachments" in doc:
            doc["original_url"] = "https://example.invalid/photos/v1/x/original.jpg"

    assert not (await outcome_with(api, rewrite))["original_is_never_exposed"]


async def test_a_non_200_answer_is_unreachable_even_when_the_bytes_are_right(api, http):  # noqa: F811
    fixture = await seeded(api, http)
    inner = memory_fetch(api)

    async def teapot(url: str) -> tuple[int, bytes]:
        _, body = await inner(url)
        return 500, body

    assert not (await serving(api, http, fixture, manifest_objects_from(api, fixture), teapot))["derivative_bytes_match_manifest"]


async def test_seeded_attachments_carry_the_requested_metadata(api, http):  # noqa: F811
    fixture = await seeded(api, http)
    drill = tool.DrillApi(http)
    await drill.login()
    items = await drill.list_photos(fixture["project_id"])
    by_asset = {i["asset"]["id"]: i["attachment"] for i in items}
    for entry in fixture["images"]:
        attachment = by_asset[entry["asset_id"]]
        assert attachment["include_in_report"] is True and attachment["category"] == entry["category"]
        assert attachment["caption"] == f"DRILL {entry['name'].split('-')[1].split('.')[0]}" and attachment["context"] == "PROJECT"


async def test_the_presigned_fetch_sends_no_authorization_and_follows_no_redirect():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(302, headers={"location": "https://elsewhere.invalid/x"}, content=b"")

    status, _ = await tool.http_fetch("https://bucket.example/obj?sig=1", transport=httpx.MockTransport(handler))
    assert status == 302 and len(seen) == 1 and "authorization" not in seen[0].headers


class NeverListed:
    called = False


def forbid_listing(monkeypatch):
    def listing(*args, **kwargs):
        NeverListed.called = True
        return []

    NeverListed.called = False
    monkeypatch.setattr(tool, "r2_listing", listing)


R2_ENV = {
    "INVENTORY_S3_ENDPOINT_URL": "https://0123456789abcdef0123456789abcdef.eu.r2.cloudflarestorage.com",
    "INVENTORY_S3_ACCESS_KEY_ID": "AKIAFAKE",
    "INVENTORY_S3_SECRET_ACCESS_KEY": "fakeSecret",
}


def test_a_bad_bucket_name_stops_before_any_listing(tmp_path, monkeypatch):
    forbid_listing(monkeypatch)
    out = tmp_path / "inv.json"
    assert tool.main(["inventory", "--provider", "r2", "--bucket", "Bad Bucket", "--output", str(out)], env=R2_ENV) == tool.EXIT_CANNOT_RUN
    assert not NeverListed.called and not out.exists()


def test_an_existing_output_file_stops_before_any_listing(tmp_path, monkeypatch):
    forbid_listing(monkeypatch)
    out = tmp_path / "inv.json"
    out.write_text("precious")
    assert tool.main(["inventory", "--provider", "r2", "--bucket", "good-bucket", "--output", str(out)], env=R2_ENV) == tool.EXIT_CANNOT_RUN
    assert not NeverListed.called and out.read_text() == "precious"


def test_a_good_inventory_run_writes_a_private_secret_free_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tool, "r2_listing", lambda client, bucket: [("photos/v1/a/original.jpg", 5, "e")])
    out = tmp_path / "inv.json"
    assert tool.main(["inventory", "--provider", "r2", "--bucket", "good-bucket", "--output", str(out)], env=R2_ENV) == tool.EXIT_PASS
    document = json.loads(out.read_bytes())
    assert document["objects"] == 1 and document["bytes"] == 5 and stat.S_IMODE(out.stat().st_mode) == 0o600
    shown = capsys.readouterr().out
    for secret in ("fakeSecret", "AKIAFAKE", "photos/v1/a"):
        assert secret not in shown and secret not in out.read_text()
