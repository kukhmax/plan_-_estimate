"""Stage 14D.2D.1 — backup run_id contract (pure)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.backup.run_id import RunIdError, new_run_id, run_id_timestamp, validate_run_id

FIXED = datetime(2026, 10, 3, 8, 15, 0, 999999, tzinfo=UTC)


def test_generated_run_id_has_the_canonical_form():
    run_id = new_run_id(FIXED, token_hex=lambda n: "3f9a1c2e")
    assert run_id == "20261003T081500Z-3f9a1c2e"
    assert validate_run_id(run_id) == run_id
    assert run_id_timestamp(run_id) == FIXED.replace(microsecond=0)


def test_generation_uses_utc_and_real_randomness():
    plus_two = timezone(timedelta(hours=2))
    assert new_run_id(datetime(2026, 10, 3, 10, 15, tzinfo=plus_two), token_hex=lambda n: "00000000").startswith(
        "20261003T081500Z-"
    )
    ids = {new_run_id() for _ in range(200)}
    assert len(ids) == 200
    for run_id in ids:
        validate_run_id(run_id)


def test_naive_time_is_refused():
    with pytest.raises(RunIdError):
        new_run_id(datetime(2026, 10, 3, 8, 15))  # noqa: DTZ001 - naive on purpose


@pytest.mark.parametrize("token", ["3F9A1C2E", "3f9a1c2", "3f9a1c2e0", "3f9a1c2g", "../../x1", ""])
def test_bad_random_suffix_from_generator_is_refused(token):
    with pytest.raises(RunIdError):
        new_run_id(FIXED, token_hex=lambda n: token)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "20261003T081500Z",
        "20261003T081500Z-",
        "20261003T081500-3f9a1c2e",
        "20261003t081500z-3f9a1c2e",
        "20261003T081500Z-3F9A1C2E",
        "20261003T081500Z-3f9a1c2e ",
        " 20261003T081500Z-3f9a1c2e",
        "20261003T081500Z-3f9a1c2e\n",
        "20261003T081500Z_3f9a1c2e",
        "2026-10-03T081500Z-3f9a1c2e",
        "20261003T081500Z-3f9a1c2e/..",
        "../20261003T081500Z-3f9a1c2e",
        "20261003T081500Z-3f9a1c2e/x",
        "20261332T081500Z-3f9a1c2e",  # month 13
        "20261003T256000Z-3f9a1c2e",  # hour 25
        "20260230T081500Z-3f9a1c2e",  # 30 February
        "２0261003T081500Z-3f9a1c2e",  # non-ASCII digit
        "٢٠٢٦١٠٠٣T081500Z-3f9a1c2e",
    ],
)
def test_validation_rejects_non_canonical_values(value):
    with pytest.raises(RunIdError) as exc:
        validate_run_id(value)
    if value.strip():
        assert value not in str(exc.value)


@pytest.mark.parametrize("value", [None, 20261003, b"20261003T081500Z-3f9a1c2e", ["x"]])
def test_validation_rejects_non_strings(value):
    with pytest.raises(RunIdError):
        validate_run_id(value)
