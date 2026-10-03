"""Stage 14D.2D.1 — Alembic revision contract: observed vs expected (pure / offline)."""

import re
import socket
from pathlib import Path

import pytest

from app.backup.schema_revision import (
    DEFAULT_SCRIPT_LOCATION,
    ExpectedHeadError,
    ObservedRevisionError,
    SchemaRevisionMismatchError,
    check_revision,
    observed_revision_from_rows,
    resolve_expected_head,
)

REPO_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def independent_repository_head() -> str:
    """Head computed without Alembic: the revision nobody revises."""
    revisions, parents = set(), set()
    for path in REPO_VERSIONS.glob("*.py"):
        text = path.read_text()
        revision = re.search(r"^revision[^=]*=\s*['\"]([^'\"]+)['\"]", text, re.MULTILINE)
        assert revision is not None, path.name
        revisions.add(revision.group(1))
        down = re.search(r"^down_revision[^=]*=\s*['\"]([^'\"]+)['\"]", text, re.MULTILINE)
        if down:
            parents.add(down.group(1))
    (head,) = revisions - parents
    return head


def write_scripts(root: Path, revisions: list[tuple[str, str | None]], *, env_marker: Path | None = None) -> Path:
    versions = root / "versions"
    versions.mkdir(parents=True)
    marker = env_marker or (root / "ENV_PY_WAS_EXECUTED")
    (root / "env.py").write_text(f"open({str(marker)!r}, 'w').close()\nraise RuntimeError('env.py must not run')\n")
    for rev, down in revisions:
        down_literal = repr(down)
        (versions / f"{rev}.py").write_text(
            f"revision = {rev!r}\ndown_revision = {down_literal}\nbranch_labels = None\ndepends_on = None\n"
            "def upgrade():\n    pass\n\ndef downgrade():\n    pass\n"
        )
    return root


# --- observed revision (parsing boundary for SELECT version_num FROM alembic_version) ---------


def test_single_valid_row_is_the_observed_revision():
    assert observed_revision_from_rows([("0032_photo_attachments",)]) == "0032_photo_attachments"


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [("0031_photo_assets",), ("0032_photo_attachments",)],
        [("0032_photo_attachments", "extra")],
        [()],
        [(None,)],
        [("",)],
        [(32,)],
        [("0032 photo",)],
        [("0032_photo_attachments;DROP",)],
        [("x" * 33,)],
        [("0032_photo_attachments\n",)],
    ],
)
def test_empty_multiple_or_malformed_observed_rows_are_invalid(rows):
    with pytest.raises(ObservedRevisionError):
        observed_revision_from_rows(rows)


# --- policy -------------------------------------------------------------------------------


def test_equal_revisions_pass():
    check_revision("0032_photo_attachments", "0032_photo_attachments")


@pytest.mark.parametrize("observed", ["0031_photo_assets", "0033_future", "0032_PHOTO_ATTACHMENTS"])
def test_any_mismatch_is_fatal(observed):
    with pytest.raises(SchemaRevisionMismatchError) as exc:
        check_revision(observed, "0032_photo_attachments")
    assert exc.value.observed == observed and exc.value.expected == "0032_photo_attachments"


def test_policy_has_no_override():
    import inspect

    assert list(inspect.signature(check_revision).parameters) == ["observed", "expected"]


def test_policy_validates_both_values():
    with pytest.raises(ObservedRevisionError):
        check_revision("bad value", "0032_photo_attachments")
    with pytest.raises(ObservedRevisionError):
        check_revision("0032_photo_attachments", "")


# --- expected head (offline) -------------------------------------------------------------------


def test_repository_head_resolves_offline_without_database(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://nobody:nothing@203.0.113.1:1/none")
    head = resolve_expected_head()
    assert head == independent_repository_head()
    assert DEFAULT_SCRIPT_LOCATION == Path(__file__).resolve().parents[1] / "alembic"


def test_resolver_never_executes_env_py(tmp_path):
    marker = tmp_path / "ENV_PY_WAS_EXECUTED"
    scripts = write_scripts(tmp_path / "alembic", [("0001_a", None), ("0002_b", "0001_a")], env_marker=marker)
    assert resolve_expected_head(scripts) == "0002_b"
    assert not marker.exists()


def test_zero_heads_is_fatal(tmp_path):
    scripts = write_scripts(tmp_path / "alembic", [])
    with pytest.raises(ExpectedHeadError, match="exactly one Alembic head"):
        resolve_expected_head(scripts)


def test_multiple_heads_are_fatal(tmp_path):
    scripts = write_scripts(tmp_path / "alembic", [("0001_a", None), ("0002_b", "0001_a"), ("0002_c", "0001_a")])
    with pytest.raises(ExpectedHeadError, match=r"found 2"):
        resolve_expected_head(scripts)


def test_missing_script_directory_is_fatal(tmp_path):
    with pytest.raises(ExpectedHeadError):
        resolve_expected_head(tmp_path / "does-not-exist")


def test_broken_revision_file_is_a_typed_error(tmp_path):
    scripts = write_scripts(tmp_path / "alembic", [("0001_a", None)])
    (scripts / "versions" / "0002_broken.py").write_text("revision = '0002_broken'\ndown_revision = (\n")
    with pytest.raises(ExpectedHeadError):
        resolve_expected_head(scripts)


def test_cycle_is_a_typed_error(tmp_path):
    scripts = write_scripts(tmp_path / "alembic", [("0001_a", "0002_b"), ("0002_b", "0001_a")])
    with pytest.raises(ExpectedHeadError):
        resolve_expected_head(scripts)


def test_invalid_head_id_is_fatal(tmp_path):
    scripts = write_scripts(tmp_path / "alembic", [("a" * 33, None)])  # Alembic accepts it; VARCHAR(32) does not
    with pytest.raises(ExpectedHeadError, match="not a valid"):
        resolve_expected_head(scripts)
