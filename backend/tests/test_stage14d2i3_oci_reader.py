"""Stage 14D.2I.3 — the OCI restore client: config validation and the real SDK with a stubbed transport."""

import os
import sys
from pathlib import Path

import pytest

from app.backup import oci_target as ot
from app.backup import target as tg
from app.domain.exceptions import (
    MediaStorageMisconfigured,
)

NAMESPACE, BUCKET = "testnamespace", "plan-estimate-backup-drill"
TENANCY = "ocid1.tenancy.oc1..aaaaaaaatesttenancy"
USER = "ocid1.user.oc1..aaaaaaaatestuser"
FINGERPRINT = "aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99"


def write_private(path: Path, text: str, mode: int = 0o600) -> Path:
    path.write_text(text)
    path.chmod(mode)
    return path


def make_config(tmp_path: Path, *, profile: str = "DEFAULT", key_text: str = "-----BEGIN PRIVATE KEY-----\nx\n", **extra: str) -> Path:
    key = write_private(tmp_path / "key.pem", key_text)
    fields = {"user": USER, "fingerprint": FINGERPRINT, "tenancy": TENANCY, "region": "eu-frankfurt-1", "key_file": str(key), **extra}
    body = "\n".join(f"{name}={value}" for name, value in fields.items())
    return write_private(tmp_path / "config", f"[{profile}]\n{body}\n")


# --- config validation (no SDK needed) ----------------------------------------------------------------------------------


def test_a_private_config_with_a_private_key_is_accepted(tmp_path: Path):
    ot.validate_api_key_config(make_config(tmp_path), "DEFAULT")
    other = tmp_path / "other"
    other.mkdir()
    ot.validate_api_key_config(make_config(other, profile="restore"), "restore")


@pytest.mark.parametrize("mode", [0o640, 0o644, 0o660, 0o604])
def test_a_config_with_group_or_other_permissions_is_refused(tmp_path: Path, mode: int):
    config = make_config(tmp_path)
    config.chmod(mode)
    with pytest.raises(MediaStorageMisconfigured, match="permissions"):
        ot.validate_api_key_config(config, "DEFAULT")


@pytest.mark.parametrize("mode", [0o640, 0o644, 0o666])
def test_a_key_with_group_or_other_permissions_is_refused(tmp_path: Path, mode: int):
    config = make_config(tmp_path)
    (tmp_path / "key.pem").chmod(mode)
    with pytest.raises(MediaStorageMisconfigured, match="signing key.*permissions"):
        ot.validate_api_key_config(config, "DEFAULT")


def test_relative_missing_symlinked_and_foreign_files_are_refused(tmp_path: Path):
    with pytest.raises(MediaStorageMisconfigured, match="absolute"):
        ot.validate_api_key_config(Path("config"), "DEFAULT")
    with pytest.raises(MediaStorageMisconfigured, match="exist"):
        ot.validate_api_key_config(tmp_path / "nope", "DEFAULT")
    config = make_config(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(config)
    with pytest.raises(MediaStorageMisconfigured, match="symlink"):
        ot.validate_api_key_config(link, "DEFAULT")
    with pytest.raises(MediaStorageMisconfigured, match="owned"):
        ot.validate_api_key_config(config, "DEFAULT", euid=os.geteuid() + 1)
    key = tmp_path / "key.pem"
    key.unlink()
    key.symlink_to(config)
    with pytest.raises(MediaStorageMisconfigured, match="signing key.*symlink"):
        ot.validate_api_key_config(config, "DEFAULT")


def test_an_empty_or_oversized_config_is_refused(tmp_path: Path):
    with pytest.raises(MediaStorageMisconfigured, match="empty or unexpectedly large"):
        ot.validate_api_key_config(write_private(tmp_path / "empty", ""), "DEFAULT")
    with pytest.raises(MediaStorageMisconfigured, match="empty or unexpectedly large"):
        ot.validate_api_key_config(write_private(tmp_path / "big", "[DEFAULT]\n" + "#" * 70_000), "DEFAULT")


def test_a_missing_profile_or_key_file_entry_is_refused(tmp_path: Path):
    config = make_config(tmp_path)
    with pytest.raises(MediaStorageMisconfigured, match="profile does not exist"):
        ot.validate_api_key_config(config, "other")
    bare = write_private(tmp_path / "bare", f"[DEFAULT]\nuser={USER}\n")
    with pytest.raises(MediaStorageMisconfigured, match="names no key_file"):
        ot.validate_api_key_config(bare, "DEFAULT")
    broken = write_private(tmp_path / "broken", "this is not an ini file\n")
    with pytest.raises(MediaStorageMisconfigured, match="parsed"):
        ot.validate_api_key_config(broken, "DEFAULT")


def test_errors_never_contain_paths_or_ocids(tmp_path: Path):
    config = make_config(tmp_path)
    config.chmod(0o644)
    with pytest.raises(MediaStorageMisconfigured) as excinfo:
        ot.validate_api_key_config(config, "DEFAULT")
    text = str(excinfo.value)
    assert str(tmp_path) not in text and USER not in text and TENANCY not in text and FINGERPRINT not in text
    assert excinfo.value.error_code == "ConfigFileUnsafe"


def test_a_missing_sdk_is_reported_as_such_not_as_a_bad_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(sys.modules, "oci", None)
    with pytest.raises(MediaStorageMisconfigured, match="oci==2.187.1") as excinfo:
        ot.OciBackupReader.from_api_key_config(namespace=NAMESPACE, bucket=BUCKET, config_file=make_config(tmp_path))
    assert excinfo.value.error_code is None


def test_the_reader_has_no_write_verb():
    public = {name for name in dir(ot.OciBackupReader) if not name.startswith("_")}
    assert public == {"head", "download_to", "from_api_key_config", "from_instance_principal"}
    assert {name for name in dir(tg.BackupReader) if not name.startswith("_")} == {"head", "download_to"}
    reader = ot.OciBackupReader(ot.OciBackupTarget(namespace=NAMESPACE, bucket=BUCKET, client=object()))
    assert NAMESPACE not in repr(reader) and BUCKET in repr(reader)
