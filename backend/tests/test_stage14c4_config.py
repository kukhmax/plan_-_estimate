"""Stage 14C.4 — PHOTO_MAX_REQUEST_BYTES (contract C3, §10)."""

import pytest

from app.core.config import MediaConfigurationError, Settings


def make(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_request_limit_default_is_27_000_000_decimal_bytes():
    s = make()
    assert s.PHOTO_MAX_REQUEST_BYTES == 27_000_000
    assert s.PHOTO_MAX_UPLOAD_BYTES == 25_000_000
    assert s.PHOTO_UPLOADS_ENABLED is False


@pytest.mark.parametrize("request_bytes", [25_000_000, 24_000_000])
def test_request_limit_must_exceed_the_image_limit(request_bytes):
    with pytest.raises(MediaConfigurationError) as exc:
        make(PHOTO_MAX_REQUEST_BYTES=request_bytes)
    assert "PHOTO_MAX_REQUEST_BYTES" in str(exc.value)


def test_request_limit_must_be_positive():
    with pytest.raises(ValueError):
        make(PHOTO_MAX_REQUEST_BYTES=0)
