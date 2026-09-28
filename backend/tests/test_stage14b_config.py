"""Stage 14B.3 — media configuration (plan §11, §12)."""

import pytest
from pydantic import ValidationError

from app.core.config import MediaConfigurationError, Settings
from app.core.s3_media_storage import S3MediaStorage, create_media_storage
from app.domain.services.media_storage import DisabledMediaStorage

FAKE_KEY_ID = "FAKEKEYID-not-real-0000"
FAKE_SECRET = "fake-secret-value-must-never-leak-1234567890"

S3_OK = dict(
    MEDIA_STORAGE_BACKEND="s3",
    MEDIA_S3_ENDPOINT_URL="https://example-account.eu.r2.cloudflarestorage.com",
    MEDIA_S3_BUCKET="test-bucket",
    MEDIA_S3_ACCESS_KEY_ID=FAKE_KEY_ID,
    MEDIA_S3_SECRET_ACCESS_KEY=FAKE_SECRET,
)


def make(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_defaults_are_the_approved_values():
    s = make()
    assert s.MEDIA_STORAGE_BACKEND == "disabled"
    assert s.PHOTO_UPLOADS_ENABLED is False
    assert s.PHOTO_SIGNED_URL_TTL_SECONDS == 300
    assert s.PHOTO_MAX_UPLOAD_BYTES == 25_000_000
    assert s.PHOTO_MAX_DECODED_PIXELS == 60_000_000
    assert s.PHOTO_STORAGE_WARNING_BYTES == 8_000_000_000
    assert s.PHOTO_STORAGE_SOFT_CAP_BYTES == 10_000_000_000
    assert s.MEDIA_S3_REGION == "auto"
    assert s.MEDIA_STORAGE_NAME == "r2-primary"
    # OWNER APPROVED initial defaults after the ARM64 benchmark (14B plan §23.12)
    assert s.PHOTO_TEMP_STALE_AFTER_SECONDS == 86400
    assert s.PHOTO_PROCESSING_WAIT_SECONDS == 30


def test_disabled_backend_starts_without_s3_configuration():
    s = make(MEDIA_STORAGE_BACKEND="disabled")
    assert isinstance(create_media_storage(s), DisabledMediaStorage)


def test_disabled_backend_ignores_partial_s3_values():
    s = make(MEDIA_STORAGE_BACKEND="disabled", MEDIA_S3_BUCKET="only-bucket")
    assert isinstance(create_media_storage(s), DisabledMediaStorage)


def test_complete_s3_configuration_selects_s3_adapter_without_connecting():
    s = make(**S3_OK)
    storage = create_media_storage(s)
    assert isinstance(storage, S3MediaStorage)
    assert FAKE_SECRET not in repr(storage)
    assert FAKE_KEY_ID not in repr(storage)


@pytest.mark.parametrize(
    "missing",
    ["MEDIA_S3_ENDPOINT_URL", "MEDIA_S3_BUCKET", "MEDIA_S3_ACCESS_KEY_ID", "MEDIA_S3_SECRET_ACCESS_KEY", "MEDIA_S3_REGION"],
)
def test_s3_backend_rejects_incomplete_configuration(missing):
    kw = dict(S3_OK)
    kw[missing] = "  "
    with pytest.raises(MediaConfigurationError) as exc_info:
        make(**kw)
    assert missing in str(exc_info.value)


def test_s3_endpoint_must_be_https():
    with pytest.raises(MediaConfigurationError):
        make(**{**S3_OK, "MEDIA_S3_ENDPOINT_URL": "http://example.com"})


def test_uploads_cannot_be_enabled_with_disabled_backend():
    with pytest.raises(MediaConfigurationError) as exc_info:
        make(PHOTO_UPLOADS_ENABLED=True)
    assert "PHOTO_UPLOADS_ENABLED" in str(exc_info.value)


def test_uploads_may_be_enabled_with_complete_s3_backend():
    assert make(**S3_OK, PHOTO_UPLOADS_ENABLED=True).PHOTO_UPLOADS_ENABLED is True


def test_invalid_backend_value_rejected():
    with pytest.raises(ValidationError):
        make(MEDIA_STORAGE_BACKEND="r2")


@pytest.mark.parametrize("ttl", [59, 3601, 0])
def test_signed_url_ttl_bounds(ttl):
    with pytest.raises(ValidationError):
        make(PHOTO_SIGNED_URL_TTL_SECONDS=ttl)


def test_soft_cap_must_not_be_below_warning():
    with pytest.raises(MediaConfigurationError):
        make(PHOTO_STORAGE_WARNING_BYTES=10, PHOTO_STORAGE_SOFT_CAP_BYTES=9)


def test_secrets_never_appear_in_repr_or_validation_errors():
    s = make(**S3_OK)
    assert FAKE_SECRET not in repr(s)
    assert FAKE_SECRET not in str(s.model_dump())
    assert FAKE_KEY_ID not in repr(s)
    assert s.MEDIA_S3_SECRET_ACCESS_KEY.get_secret_value() == FAKE_SECRET
    # A failing cross-field check (missing bucket) must not carry any input
    # value anywhere on the exception (message, args, cause, context).
    with pytest.raises(MediaConfigurationError) as exc_info:
        make(**{**S3_OK, "MEDIA_S3_BUCKET": ""})
    exc = exc_info.value
    rendered = " ".join(
        repr(x) for x in (exc, exc.args, exc.__cause__, exc.__context__, vars(exc))
    )
    assert FAKE_SECRET not in rendered
    assert FAKE_KEY_ID not in rendered
    # A field-level failure elsewhere must not echo secrets either.
    with pytest.raises(ValidationError) as exc_info:
        make(**{**S3_OK, "PHOTO_SIGNED_URL_TTL_SECONDS": 5})
    rendered = str(exc_info.value) + repr(exc_info.value.errors())
    assert FAKE_SECRET not in rendered
    assert FAKE_KEY_ID not in rendered


def test_application_settings_singleton_has_media_disabled():
    from app.core.config import settings

    assert settings.MEDIA_STORAGE_BACKEND == "disabled"
    assert settings.PHOTO_UPLOADS_ENABLED is False


async def test_application_starts_with_media_disabled(async_client):
    response = await async_client.get("/api/health")
    assert response.status_code == 200
