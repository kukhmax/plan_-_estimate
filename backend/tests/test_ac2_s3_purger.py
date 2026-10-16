"""Archive cleanup AC-2 -- the S3 / R2 adapter of the purge port, against botocore's stubbed responses (no network)."""
import pytest

from app.core.s3_media_purger import S3MediaPurger
from app.domain.exceptions import MediaStorageDisabled, MediaStorageUnavailable
from app.domain.services.media_purger import DisabledMediaPurger, MediaPurger
from app.domain.services.media_storage import InMemoryMediaStorage
from tests.test_stage14b_media_storage import BUCKET, make_s3

KEYS = ["media/p/a/original", "media/p/a/display", "media/p/a/thumbnail"]


async def test_each_object_is_deleted_by_key_from_the_bucket():
    storage, stubber = make_s3()
    for key in KEYS:
        stubber.add_response("delete_object", {}, {"Bucket": BUCKET, "Key": key})
    with stubber:
        await S3MediaPurger(storage).delete_objects(KEYS)
        stubber.assert_no_pending_responses()


async def test_a_provider_failure_is_a_storage_error_not_a_botocore_one_and_stops_at_the_failed_key():
    storage, stubber = make_s3()
    stubber.add_response("delete_object", {}, {"Bucket": BUCKET, "Key": KEYS[0]})
    stubber.add_client_error("delete_object", service_error_code="ServiceUnavailable", http_status_code=503, expected_params={"Bucket": BUCKET, "Key": KEYS[1]})
    with stubber, pytest.raises(MediaStorageUnavailable):
        await S3MediaPurger(storage).delete_objects(KEYS)


async def test_an_invalid_key_is_refused_before_anything_is_deleted():
    storage, stubber = make_s3()
    with stubber, pytest.raises(ValueError):
        await S3MediaPurger(storage).delete_objects([KEYS[0], "../escape"])
    stubber.assert_no_pending_responses()


async def test_the_disabled_purger_refuses_and_every_purger_is_a_media_purger():
    with pytest.raises(MediaStorageDisabled):
        await DisabledMediaPurger().delete_objects(KEYS)
    assert isinstance(DisabledMediaPurger(), MediaPurger) and isinstance(S3MediaPurger(make_s3()[0]), MediaPurger)


def test_the_storage_port_still_has_no_delete_and_the_purger_is_a_separate_object():
    storage, _ = make_s3()
    for impl in (storage, InMemoryMediaStorage()):
        assert not hasattr(impl, "delete_object") and not hasattr(impl, "delete_objects")
