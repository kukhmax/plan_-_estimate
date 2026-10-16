"""Archive cleanup AC-3b -- the rehearsal ledger is made from the drill bucket only, by reading it."""
import importlib.util
import io
import sys
import types
import uuid
from pathlib import Path

from app.backup.purge_ledger import parse_ledger

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "purge_rehearsal_ledger.py"
spec = importlib.util.spec_from_file_location("purge_rehearsal_ledger", SCRIPT)
tool = importlib.util.module_from_spec(spec)
sys.modules["purge_rehearsal_ledger"] = tool
spec.loader.exec_module(tool)


def keys_of(n: int, *, thumb: bool = True) -> list[str]:
    base = f"photos/v1/{uuid.UUID(f'00000000-0000-4000-8000-{n:012x}')}/"
    return [f"{base}original.jpg", f"{base}display.jpg", *([f"{base}thumb.jpg"] if thumb else [])]


class Fake:
    def __init__(self, names: list[str], page: int = 2) -> None:
        self.names, self.page, self.calls = sorted(names), page, []

    def list_objects(self, ns, bucket, prefix="", fields="", start=None):
        self.calls.append((bucket, prefix, start))
        names = [n for n in self.names if n.startswith(prefix) and (start is None or n >= start)]
        chunk, rest = names[: self.page], names[self.page:]
        data = types.SimpleNamespace(objects=[types.SimpleNamespace(name=n, size=len(n)) for n in chunk], next_start_with=rest[0] if rest else None)
        return types.SimpleNamespace(data=data)


def run(tmp_path: Path, fake: Fake, *extra: str):
    out = io.StringIO()
    target = tmp_path / "rehearsal.jsonl"
    code = tool.main(["--namespace", "ns-secret", "--config", "/x", "--out", str(target), *extra], out, make_client=lambda a: fake)
    return code, out.getvalue(), target


def test_it_reads_only_the_drill_bucket_and_writes_complete_sets_as_a_valid_ledger(tmp_path):
    fake = Fake([*keys_of(1), *keys_of(2), *keys_of(3, thumb=False), "runs/x/manifest.jsonl", "db/x/dump.age"])
    code, text, target = run(tmp_path, fake, "--count", "2")
    assert code == 0 and "file_sets=2 (of 2 complete" in text
    assert {call[0] for call in fake.calls} == {tool.DRILL_BUCKET} and all(call[1] == "photos/v1/" for call in fake.calls)  # paged, never another bucket
    ledger = parse_ledger(target.read_bytes())
    assert len(ledger.entries) == 2 and ledger.purged_keys == set(keys_of(1) + keys_of(2))  # the incomplete set and the runs / db objects are left out
    assert "ns-secret" not in text and "photos/v1" not in text


def test_it_refuses_when_there_is_nothing_complete_to_rehearse_on_or_the_target_exists(tmp_path):
    code, text, _ = run(tmp_path, Fake([*keys_of(1, thumb=False)]))
    assert code == 2 and "no complete photo file set" in text
    existing = tmp_path / "rehearsal.jsonl"
    existing.write_bytes(b"x")
    code, _, _ = run(tmp_path, Fake(keys_of(1)))
    assert code == 2 and existing.read_bytes() == b"x"
    assert run(tmp_path / "nope", Fake(keys_of(1)))[0] == 2
    assert run(tmp_path, Fake(keys_of(1)), "--count", "11")[0] == 2


class ServiceError(Exception):
    def __init__(self, status: int, code: str) -> None:
        super().__init__("a message that must never be printed: namespace ns-secret, key photos/v1/x")
        self.status, self.code = status, code


class Broken:
    def list_objects(self, *args, **kwargs):
        raise ServiceError(404, "NotAuthorizedOrNotFound")


def test_a_refused_listing_says_the_status_and_the_code_but_never_the_message(tmp_path):
    code, text, _ = run(tmp_path, Broken())
    assert code == 2 and "ServiceError, HTTP 404, NotAuthorizedOrNotFound" in text
    assert "ns-secret" not in text and "photos/v1" not in text and "message" not in text


def test_an_error_that_is_not_an_oci_one_says_only_its_type(tmp_path):
    class Odd:
        def list_objects(self, *args, **kwargs):
            raise RuntimeError("secret detail")

    code, text, _ = run(tmp_path, Odd())
    assert code == 2 and "(RuntimeError)" in text and "secret detail" not in text
