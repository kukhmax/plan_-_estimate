"""Alembic revision contract for database backups (Stage 14D.2D.1).

Two separate facts (docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §16.3):

- the **observed** revision: the single `alembic_version.version_num` row
  read inside the exported backup snapshot (read by a later slice; parsed
  here by `observed_revision_from_rows`);
- the **expected** head: resolved OFFLINE from the repository migration
  scripts with Alembic's ScriptDirectory -- no database connection and no
  `env.py` execution (`resolve_expected_head`).

Policy v1 (owner decision D3): they must be exactly equal; a mismatch is
fatal before pg_dump starts. There is no override.
"""

import re
from collections.abc import Sequence
from pathlib import Path

from alembic.script import ScriptDirectory
from alembic.script.revision import RevisionError
from alembic.util.exc import CommandError

# alembic_version.version_num is VARCHAR(32); repository ids are [0-9a-z_].
REVISION_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,32}$", re.ASCII)
DEFAULT_SCRIPT_LOCATION = Path(__file__).resolve().parents[2] / "alembic"


class SchemaRevisionError(RuntimeError):
    """Base class: the schema revision contract is not satisfied."""


class ObservedRevisionError(SchemaRevisionError):
    """The snapshot's alembic_version content is missing, ambiguous or malformed."""


class ExpectedHeadError(SchemaRevisionError):
    """The repository migration scripts do not resolve to exactly one head."""


class SchemaRevisionMismatchError(SchemaRevisionError):
    """The database revision is not the repository head."""

    def __init__(self, observed: str, expected: str) -> None:
        # Both values are validated revision ids (safe, non-secret).
        super().__init__(f"database revision {observed} is not the expected repository head {expected}")
        self.observed = observed
        self.expected = expected


def validate_revision(value: object, what: str = "revision") -> str:
    if not isinstance(value, str) or not REVISION_PATTERN.fullmatch(value):
        raise ObservedRevisionError(f"{what} is not a valid Alembic revision id")
    return value


def observed_revision_from_rows(rows: Sequence[Sequence[object]]) -> str:
    """Parse the result of `SELECT version_num FROM alembic_version`:
    exactly one row with exactly one valid revision id."""
    if len(rows) != 1:
        raise ObservedRevisionError(f"alembic_version must contain exactly one row (found {len(rows)})")
    row = rows[0]
    if len(row) != 1:
        raise ObservedRevisionError("alembic_version row must have exactly one column")
    return validate_revision(row[0], "observed alembic_version")


def resolve_expected_head(script_location: Path = DEFAULT_SCRIPT_LOCATION) -> str:
    """The single head of the repository migration scripts, read offline.

    ScriptDirectory only parses the revision files; `env.py` is executed
    only by `run_env()`, which is never called here."""
    try:
        script = ScriptDirectory(str(script_location))
        heads = script.get_heads()
    except (CommandError, RevisionError, ImportError, SyntaxError, OSError) as exc:
        raise ExpectedHeadError(f"Alembic scripts cannot be resolved ({type(exc).__name__})") from None
    if len(heads) != 1:
        raise ExpectedHeadError(f"repository must have exactly one Alembic head (found {len(heads)})")
    try:
        return validate_revision(heads[0], "repository head")
    except ObservedRevisionError:
        raise ExpectedHeadError("repository head is not a valid Alembic revision id") from None


def check_revision(observed: str, expected: str) -> None:
    """Policy v1: observed must exactly equal expected (no override)."""
    observed = validate_revision(observed, "observed revision")
    expected = validate_revision(expected, "expected head")
    if observed != expected:
        raise SchemaRevisionMismatchError(observed, expected)
