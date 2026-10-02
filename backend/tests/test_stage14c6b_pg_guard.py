"""Stage 14C.6B — the opt-in PostgreSQL harness can only target a loopback
scratch database whose name carries the `pe_scratch_test` marker."""

import pytest

from tests.pg_scratch_guard import UnsafeScratchDatabaseError, scratch_url


def test_unset_means_opt_out():
    assert scratch_url("") is None


def test_valid_scratch_url_is_accepted():
    url = scratch_url("postgresql+asyncpg://u:p@127.0.0.1:55432/pe_scratch_test_14c6b")
    assert url.database == "pe_scratch_test_14c6b"


@pytest.mark.parametrize(
    "raw",
    [
        "postgresql+asyncpg://u:p@127.0.0.1:55432/plan_estimate",  # no marker (production-like name)
        "postgresql+asyncpg://u:p@db.example.com:5432/pe_scratch_test_x",  # remote host
        "postgresql+asyncpg://u:p@10.0.0.5:5432/pe_scratch_test_x",  # private but not loopback
        "postgresql://u:p@127.0.0.1/pe_scratch_test_x",  # other driver
        "sqlite+aiosqlite:///pe_scratch_test.db",
        "not a url at all",
    ],
)
def test_unsafe_urls_are_refused(raw):
    with pytest.raises(UnsafeScratchDatabaseError) as exc:
        scratch_url(raw)
    assert "u:p" not in str(exc.value)  # credentials never echoed
