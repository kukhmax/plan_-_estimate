"""Archive cleanup AC-3b -- the owner's tool that removes the backup copies of deleted photos (a fake Object Storage client, no network)."""
import importlib.util
import io
import os
import sys
import types
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.backup import purge_ledger as pl
from app.backup.purge_report import parse_report

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "purge_backup_objects.py"
spec = importlib.util.spec_from_file_location("purge_backup_objects", SCRIPT)
tool = importlib.util.module_from_spec(spec)
sys.modules["purge_backup_objects"] = tool
spec.loader.exec_module(tool)

NS = "ns-secret"
NOW = datetime(2026, 10, 16, 21, 0, tzinfo=UTC)


def keys_of(n: int) -> tuple[str, str, str]:
    base = f"photos/v1/{uuid.UUID(int=n)}/"
    return f"{base}original.jpg", f"{base}display.jpg", f"{base}thumb.jpg"


def entry(n: int) -> pl.LedgerEntry:
    original, display, thumb = keys_of(n)
    return pl.LedgerEntry(
        id=uuid.UUID(int=500 + n), asset_id=uuid.UUID(int=n), storage_name="r2", key_original=original, key_display=display, key_thumbnail=thumb,
        sha256="c" * 64, size_original=3, size_display=2, size_thumbnail=1, purged_at="2026-10-16T19:00:00Z",
    )


def ledger_file(tmp_path: Path, *numbers: int) -> Path:
    path = tmp_path / "ledger.jsonl"
    path.write_bytes(pl.serialize_ledger([entry(n) for n in numbers], exported_at="2026-10-16T20:00:00Z"))
    return path


class Fake:
    """A versioned bucket: `versions` is a list of (name, version_id, is_delete_marker). Deleting without a version id only adds a marker."""

    def __init__(self, *names: str, versions_each: int = 2) -> None:
        self.versions = [(name, f"{name[-12:]}-v{i}", False) for name in names for i in range(versions_each)]
        self.calls: list[tuple] = []
        self.fail_on: str | None = None
        self.stubborn: set[str] = set()  # names whose versions the fake refuses to remove (they reappear)

    def list_object_versions(self, ns, bucket, prefix=""):
        self.calls.append(("list", ns, bucket, prefix))
        items = [types.SimpleNamespace(name=n, version_id=v, is_delete_marker=m) for n, v, m in self.versions if n.startswith(prefix)]
        return types.SimpleNamespace(data=types.SimpleNamespace(items=items))

    def delete_object(self, ns, bucket, name, version_id=None):
        self.calls.append(("delete", ns, bucket, name, version_id))
        if self.fail_on and name == self.fail_on:
            raise RuntimeError("access denied")
        if version_id is None:
            self.versions.append((name, "marker", True))
            return
        if name not in self.stubborn:
            self.versions = [v for v in self.versions if v[1] != version_id or v[0] != name]

    def names(self) -> set[str]:
        return {n for n, _, _ in self.versions}

    def deletes(self) -> list[tuple]:
        return [c for c in self.calls if c[0] == "delete"]


def run(tmp_path: Path, fake: Fake, *args: str, phrase: str | None = None, ledger: Path | None = None):
    out = io.StringIO()
    argv = ["--ledger", str(ledger or ledger_file(tmp_path, 1, 2)), "--namespace", NS, "--config", "/x/config", *args]
    asked: list[str] = []

    def confirm(prompt: str) -> str:
        asked.append(prompt)
        return phrase or ""

    code = tool.main(argv, out, make_client=lambda a: fake, confirm=confirm, now=lambda: NOW)
    return code, out.getvalue(), asked


ALL = [k for n in (1, 2, 3) for k in keys_of(n)]


def test_a_dry_run_lists_what_exists_and_deletes_nothing(tmp_path):
    fake = Fake(*ALL)
    code, text, asked = run(tmp_path, fake, "--bucket", tool.DRILL_BUCKET)
    assert code == 0 and "DRY RUN" in text and "versions found=6 deleted=0" in text and asked == []
    assert fake.deletes() == [] and len(fake.versions) == 18


def test_the_rehearsal_deletes_every_version_of_exactly_the_ledger_objects_and_nothing_else(tmp_path):
    other = ["runs/20261016T000000Z-aaaaaaaa/manifest.jsonl", "db/20261016T000000Z-aaaaaaaa/plan-estimate.sql.gz.age", *keys_of(3)]
    fake = Fake(*keys_of(1), *keys_of(2), *other)
    report = tmp_path / "report.jsonl"
    code, text, asked = run(tmp_path, fake, "--bucket", tool.DRILL_BUCKET, "--execute", "--report", str(report), phrase=tool.CONFIRM_PHRASES["drill"])
    assert code == 0 and len(asked) == 1
    assert fake.names() == set(other)  # the manifests, the dump and the third photo are untouched
    assert all(call[4] is not None for call in fake.deletes()), "never a delete without a version id: that would only add a marker"
    assert {c[3] for c in fake.deletes()} == set(keys_of(1) + keys_of(2)) and len(fake.deletes()) == 12
    parsed = parse_report(report.read_bytes())
    assert parsed.bucket_kind == "drill" and [(e.outcome, e.versions_deleted) for e in parsed.entries] == [("deleted", 6), ("deleted", 6)]
    assert oct(os.stat(report).st_mode & 0o777) == "0o600"


def test_delete_markers_are_removed_too(tmp_path):
    fake = Fake(*keys_of(1), versions_each=1)
    fake.versions.append((keys_of(1)[0], "marker-1", True))
    code, _, _ = run(tmp_path, fake, "--bucket", tool.DRILL_BUCKET, "--execute", "--report", str(tmp_path / "r.jsonl"), phrase=tool.CONFIRM_PHRASES["drill"], ledger=ledger_file(tmp_path, 1))
    assert code == 0 and fake.versions == []


def test_a_longer_name_that_only_shares_the_prefix_is_never_touched(tmp_path):
    longer = keys_of(1)[0] + ".backup"
    fake = Fake(*keys_of(1), longer)
    run(tmp_path, fake, "--bucket", tool.DRILL_BUCKET, "--execute", "--report", str(tmp_path / "r.jsonl"), phrase=tool.CONFIRM_PHRASES["drill"], ledger=ledger_file(tmp_path, 1))
    assert fake.names() == {longer}


def test_without_the_typed_phrase_nothing_is_deleted(tmp_path):
    for wrong in ("", "да", tool.CONFIRM_PHRASES["drill"] + " "[:0] + "x", tool.CONFIRM_PHRASES["prod"]):
        fake = Fake(*ALL)
        code, text, _ = run(tmp_path, fake, "--bucket", tool.DRILL_BUCKET, "--execute", "--report", str(tmp_path / f"r{abs(hash(wrong))}.jsonl"), phrase=wrong)
        assert code == tool.EXIT_DECLINED and fake.deletes() == [] and "declined" in text


def test_the_production_bucket_asks_for_its_own_phrase_and_marks_its_report_as_production(tmp_path):
    fake = Fake(*keys_of(1), *keys_of(2))
    refused, _, _ = run(tmp_path, fake, "--bucket", tool.PROD_BUCKET, "--execute", "--report", str(tmp_path / "a.jsonl"), phrase=tool.CONFIRM_PHRASES["drill"])
    assert refused == tool.EXIT_DECLINED and fake.deletes() == []  # the rehearsal phrase does not open the production bucket
    code, text, _ = run(tmp_path, fake, "--bucket", tool.PROD_BUCKET, "--execute", "--report", str(tmp_path / "b.jsonl"), phrase=tool.CONFIRM_PHRASES["prod"])
    assert code == 0 and "PROD" in text and parse_report((tmp_path / "b.jsonl").read_bytes()).bucket_kind == "prod"


def test_only_the_two_backup_buckets_are_accepted(tmp_path):
    for bucket in ("plan-estimate-media-prod", "plan-estimate-backup", "plan-estimate-backup-drill2", ""):
        fake = Fake(*ALL)
        code, text, _ = run(tmp_path, fake, "--bucket", bucket or "x")
        assert code == tool.EXIT_CANNOT_RUN and "refused" in text and fake.calls == []


def test_a_second_run_finds_nothing_and_says_already_absent(tmp_path):
    fake = Fake(*keys_of(1), *keys_of(2))
    args = ("--bucket", tool.DRILL_BUCKET, "--execute")
    run(tmp_path, fake, *args, "--report", str(tmp_path / "1.jsonl"), phrase=tool.CONFIRM_PHRASES["drill"])
    code, _, _ = run(tmp_path, fake, *args, "--report", str(tmp_path / "2.jsonl"), phrase=tool.CONFIRM_PHRASES["drill"])
    assert code == 0 and [e.outcome for e in parse_report((tmp_path / "2.jsonl").read_bytes()).entries] == ["already_absent"] * 2


def test_one_failed_set_is_reported_failed_and_does_not_stop_the_others(tmp_path):
    fake = Fake(*keys_of(1), *keys_of(2))
    fake.fail_on = keys_of(1)[1]
    code, text, _ = run(tmp_path, fake, "--bucket", tool.DRILL_BUCKET, "--execute", "--report", str(tmp_path / "r.jsonl"), phrase=tool.CONFIRM_PHRASES["drill"])
    assert code == tool.EXIT_FAILED and "could not be cleaned" in text
    outcomes = {str(e.asset_id).split("-")[-1][-2:]: e.outcome for e in parse_report((tmp_path / "r.jsonl").read_bytes()).entries}
    assert sorted(outcomes.values()) == ["deleted", "failed"]
    assert keys_of(2)[0] not in fake.names()


def test_versions_that_do_not_go_away_are_a_failure_not_a_success(tmp_path):
    fake = Fake(*keys_of(1))
    fake.stubborn = {keys_of(1)[0]}
    code, _, _ = run(tmp_path, fake, "--bucket", tool.DRILL_BUCKET, "--execute", "--report", str(tmp_path / "r.jsonl"), phrase=tool.CONFIRM_PHRASES["drill"], ledger=ledger_file(tmp_path, 1))
    assert code == tool.EXIT_FAILED
    assert [e.outcome for e in parse_report((tmp_path / "r.jsonl").read_bytes()).entries] == ["failed"]


def test_unusable_input_is_refused_before_any_call(tmp_path):
    fake = Fake(*ALL)
    bad = tmp_path / "bad.jsonl"
    bad.write_bytes(b'{"format":"x"}\n')
    cases = [
        (("--bucket", tool.DRILL_BUCKET, "--execute"), None),  # --execute without --report
        (("--bucket", tool.DRILL_BUCKET), bad),  # not a ledger
        (("--bucket", tool.DRILL_BUCKET, "--report", "relative.jsonl"), None),
    ]
    for args, ledger in cases:
        code, text, _ = run(tmp_path, fake, *args, ledger=ledger)
        assert code == tool.EXIT_CANNOT_RUN and fake.calls == [], args
    existing = tmp_path / "exists.jsonl"
    existing.write_bytes(b"x")
    code, _, _ = run(tmp_path, fake, "--bucket", tool.DRILL_BUCKET, "--execute", "--report", str(existing), phrase=tool.CONFIRM_PHRASES["drill"])
    assert code == tool.EXIT_CANNOT_RUN and existing.read_bytes() == b"x" and fake.calls == []


def test_nothing_secret_is_ever_printed(tmp_path):
    fake = Fake(*keys_of(1))
    code, text, _ = run(tmp_path, fake, "--bucket", tool.DRILL_BUCKET, "--execute", "--report", str(tmp_path / "r.jsonl"), phrase=tool.CONFIRM_PHRASES["drill"], ledger=ledger_file(tmp_path, 1))
    assert code == 0
    for secret in (NS, "photos/v1", "/x/config", "c" * 64):
        assert secret not in text
    assert "photos/v1" not in (tmp_path / "r.jsonl").read_text()


def test_an_empty_ledger_is_nothing_to_do(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_bytes(pl.serialize_ledger([], exported_at="2026-10-16T20:00:00Z"))
    fake = Fake(*ALL)
    code, text, _ = run(tmp_path, fake, "--bucket", tool.DRILL_BUCKET, ledger=empty)
    assert code == 0 and "empty" in text and fake.calls == []
