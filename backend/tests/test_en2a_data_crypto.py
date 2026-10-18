"""EN-2a -- the primitives of the encryption of the data: the format of a value, the associated data, the wrapping of a data key."""
import base64

import pytest

from app.core import data_crypto as dc
from app.core.key_ring import OwnerKey, ring


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def test_a_value_has_the_documented_format_and_round_trips():
    dek, key_id = dc.new_key(), "abc123"
    stored = dc.encrypt_text(dek, key_id, "clients.phone", "500 600 700")
    assert stored.startswith("enc1:abc123:") and stored.count(":") == 3 and "500" not in stored
    got_id, nonce, body = dc.split_value(stored)
    assert got_id == key_id and len(nonce) == dc.NONCE_BYTES
    assert dc.decrypt_text(dek, "clients.phone", nonce, body) == "500 600 700"


@pytest.mark.parametrize("text", ["", " ", "Łódź żółć", "Иван Петров", "emoji 🏠", "enc1:looks:like:cipher", "x" * 20000])
def test_any_text_round_trips(text):
    dek = dc.new_key()
    _, nonce, body = dc.split_value(dc.encrypt_text(dek, "k", "t.c", text))
    assert dc.decrypt_text(dek, "t.c", nonce, body) == text


def test_the_same_text_never_gives_the_same_ciphertext():
    dek = dc.new_key()
    assert dc.encrypt_text(dek, "k", "t.c", "same") != dc.encrypt_text(dek, "k", "t.c", "same")


def test_a_ciphertext_does_not_open_in_another_column():
    dek = dc.new_key()
    _, nonce, body = dc.split_value(dc.encrypt_text(dek, "k", "clients.first_name", "Jan"))
    with pytest.raises(dc.DataDecryptError) as caught:
        dc.decrypt_text(dek, "clients.last_name", nonce, body)
    assert caught.value.code == "DATA_DECRYPT_FAILED" and "Jan" not in str(caught.value)


def test_a_damaged_ciphertext_a_wrong_key_and_a_wrong_nonce_are_refused():
    dek = dc.new_key()
    _, nonce, body = dc.split_value(dc.encrypt_text(dek, "k", "t.c", "secret"))
    flipped = bytes([body[0] ^ 1]) + body[1:]
    for key, n, b in ((dek, nonce, flipped), (dc.new_key(), nonce, body), (dek, bytes(12), body), (dek, nonce, body[:-1])):
        with pytest.raises(dc.DataDecryptError):
            dc.decrypt_text(key, "t.c", n, b)


@pytest.mark.parametrize(
    "stored", ["enc1:", "enc1:k", "enc1:k:a", "enc1::a:b", "enc1:k:a:b:c", "enc1:k:***:***", "enc1:k:AAAA", "enc1::AAAA:AAAA", "enc1:k:AAAA:AAAA:AAAA"]
)
def test_a_malformed_stored_value_is_a_typed_error(stored):
    with pytest.raises(dc.DataDecryptError):
        dc.split_value(stored)


def test_is_encrypted_only_by_the_prefix():
    assert dc.is_encrypted("enc1:k:a:b") and not dc.is_encrypted("Jan") and not dc.is_encrypted("") and not dc.is_encrypted(None)


def test_a_data_key_wraps_and_unwraps_and_is_bound_to_its_id_and_to_the_kek():
    kek, dek = dc.new_key(), dc.new_key()
    wrapped = dc.wrap_key(kek, dek, "key-1")
    assert dek.hex() not in wrapped and dc.unwrap_key(kek, wrapped, "key-1") == dek
    with pytest.raises(dc.DataDecryptError):
        dc.unwrap_key(kek, wrapped, "key-2")
    with pytest.raises(dc.DataDecryptError):
        dc.unwrap_key(dc.new_key(), wrapped, "key-1")
    with pytest.raises(dc.DataDecryptError):
        dc.unwrap_key(kek, "not-a-wrapped-key", "key-1")


def test_the_kek_text_is_base64_of_32_bytes_and_never_echoed():
    raw = dc.new_key()
    assert dc.parse_kek(b64(raw)) == raw and dc.parse_kek("  " + b64(raw) + "\n") == raw
    assert dc.parse_kek(base64.urlsafe_b64encode(raw).decode()) == raw
    for bad in ("", "short", b64(b"x" * 16), b64(b"x" * 33), "***not base64***" * 3):
        with pytest.raises(dc.DataKeyConfigurationError) as caught:
            dc.parse_kek(bad)
        assert caught.value.code == "DATA_KEK_INVALID"
        assert not bad.strip() or bad.strip() not in str(caught.value)


def test_a_key_never_shows_in_its_repr():
    key = OwnerKey("kid", b"\x01" * 32)
    assert "kid" in repr(key) and "01" not in repr(key) and "x01" not in repr(key)
    ring.disable()
