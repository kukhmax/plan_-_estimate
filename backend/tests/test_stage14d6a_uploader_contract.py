"""Stage 14D.6A — static contract of the uploader image and the `backup-upload` Compose service (no Docker).

The uploader is the only process that talks to R2 and Oracle. These tests pin what keeps it separate from the database
side: its own pinned SDK layer, its own network, its own R2 variable names, no database, no pgpass.
"""

import hashlib
import re
from pathlib import Path

import pytest
import yaml

from app.backup.oci_target import OCI_SDK_PIN

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
COMPOSE = REPO / "docker-compose.prod.yml"
UPLOADER_DOCKERFILE = BACKEND / "Dockerfile.uploader"
BACKUP_DOCKERFILE = BACKEND / "Dockerfile.backup"
REQUIREMENTS = BACKEND / "requirements.txt"
REQUIREMENTS_OCI = BACKEND / "requirements-oci.txt"
# backend/Dockerfile.backup as accepted in 14D.2C (the local-only image must not change when the uploader is added)
BACKUP_DOCKERFILE_SHA256 = "a3f598f06c04e29d381a7c53ea54e003a4e2133cf3412629a9e9ac44ffa1e204"

pytestmark = pytest.mark.skipif(not COMPOSE.exists(), reason="repository checkout only (not inside the image)")


def instructions(dockerfile: Path) -> list[str]:
    joined = re.sub(r"\\\n", " ", dockerfile.read_text())
    return [line.strip() for line in joined.splitlines() if line.strip() and not line.strip().startswith("#")]


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text())


@pytest.fixture(scope="module")
def uploader(compose) -> dict:
    return compose["services"]["backup-upload"]


@pytest.fixture(scope="module")
def backup(compose) -> dict:
    return compose["services"]["backup"]


def pins(path: Path) -> dict[str, str]:
    found = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            name, version = line.split("==")
            found[name.strip().lower().split("[")[0]] = version.strip()
    return found


# --- image ------------------------------------------------------------------------------------------------------------------


def test_the_local_only_backup_image_is_unchanged():
    assert hashlib.sha256(BACKUP_DOCKERFILE.read_bytes()).hexdigest() == BACKUP_DOCKERFILE_SHA256


def test_the_uploader_image_is_one_pinned_layer_on_the_backup_image():
    instr = instructions(UPLOADER_DOCKERFILE)
    assert instr[0] == "ARG BACKUP_IMAGE=plan-estimate-backup:local"
    assert [i for i in instr if i.startswith("FROM ")] == ["FROM ${BACKUP_IMAGE}"]
    assert [i for i in instr if i.startswith(("COPY", "ADD"))] == ["COPY requirements-oci.txt ./"]
    run = " ".join(i for i in instr if i.startswith("RUN"))
    assert "pip install --no-cache-dir --no-deps -r requirements-oci.txt" in run and "pip check" in run
    assert len(re.findall(r"pip install", run)) == 1  # no floating second dependency set
    users = [i for i in instr if i.startswith("USER ")]
    assert users == ["USER 0:0", "USER 65534:65534"]  # root only for the install layer, non-root at the end
    assert 'ENTRYPOINT ["python", "-m", "app.backup"]' in instr


def test_the_uploader_image_carries_no_secret_or_identity():
    text = UPLOADER_DOCKERFILE.read_text()
    assert "AGE-SECRET-KEY" not in text
    assert not re.search(r"identity|pgpass|\.env\b|secret", " ".join(i for i in instructions(UPLOADER_DOCKERFILE) if i.startswith(("COPY", "ADD"))), re.IGNORECASE)


def test_the_oci_requirements_are_fully_pinned_and_do_not_touch_the_base_set():
    oci = pins(REQUIREMENTS_OCI)
    base = pins(REQUIREMENTS)
    lines = [ln.strip() for ln in REQUIREMENTS_OCI.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    assert all(re.fullmatch(r"[A-Za-z0-9._-]+==[0-9A-Za-z.!+_-]+", ln) for ln in lines), "every line is name==exact version"
    assert len(oci) == len(lines), "no duplicate package"
    assert f"oci=={oci['oci']}" == OCI_SDK_PIN
    assert not set(oci) & set(base), "requirements-oci.txt must not re-pin a package of requirements.txt"


def test_the_web_image_does_not_get_the_sdk():
    assert "oci" not in pins(REQUIREMENTS)
    assert "oci" not in (BACKEND / "Dockerfile").read_text()


# --- Compose service ---------------------------------------------------------------------------------------------------------


def test_profile_gated_one_shot_and_harmless_by_default(uploader, compose):
    assert uploader["profiles"] == ["backup-upload"]
    assert uploader["restart"] == "no" and uploader["init"] is True
    assert uploader["entrypoint"] == ["python", "-m", "app.backup"] and uploader["command"] == ["upload", "--help"]
    assert "depends_on" not in uploader
    for name, service in compose["services"].items():
        if name != "backup-upload":
            assert "backup-upload" not in str(service.get("depends_on", "")), name


def test_builds_the_uploader_image_from_the_backup_image(uploader):
    assert uploader["build"] == {
        "context": "./backend",
        "dockerfile": "Dockerfile.uploader",
        "args": {"BACKUP_IMAGE": "plan-estimate-backup:local"},
    }
    assert uploader["image"] == "plan-estimate-backup-upload:local"


def test_hardening_equals_the_backup_service(uploader, backup):
    for key in ("user", "read_only", "cap_drop", "security_opt", "mem_limit", "cpus", "pids_limit", "stop_grace_period", "init", "restart"):
        assert uploader[key] == backup[key], key
    for forbidden in ("privileged", "network_mode", "ports", "expose", "extra_hosts", "links", "external_links", "devices", "cap_add", "pid", "ipc"):
        assert forbidden not in uploader, forbidden


def test_its_only_network_is_the_external_pe_upload_bridge(uploader, backup, compose):
    assert uploader["networks"] == ["pe-upload"]
    assert compose["networks"]["pe-upload"] == {"external": True, "name": "pe-upload"}
    assert backup["networks"] == ["internal"], "the database side never joins pe-upload (IMDS guard)"
    for name, service in compose["services"].items():
        if name != "backup-upload":
            assert "pe-upload" not in (service.get("networks") or []), name


def test_no_database_no_pgpass_no_secrets_directory(uploader):
    text = yaml.safe_dump(uploader)
    for forbidden in ("pgpass", "PGHOST", "PGUSER", "PGDATABASE", "PGPASSFILE", "POSTGRES", "DATABASE_URL", "JWT_", "TELEGRAM", "/secrets"):
        assert forbidden not in text, forbidden
    assert "internal" not in uploader["networks"]


def test_only_the_data_root_and_a_tmpfs_are_mounted(uploader):
    mounts = uploader["volumes"]
    assert len(mounts) == 2
    data = next(m for m in mounts if m["type"] == "bind")
    assert data["target"] == "/backup" and data["source"].endswith("/data") and not data.get("read_only")
    assert data["bind"] == {"create_host_path": False}
    assert data["source"].startswith("${BACKUP_HOST_ROOT:-/nonexistent/")
    tmp = next(m for m in mounts if m["type"] == "tmpfs")
    assert tmp["target"] == "/tmp" and tmp["tmpfs"]["size"] == 268435456
    assert "docker.sock" not in yaml.safe_dump(uploader)


def test_environment_names_are_explicit_and_use_the_uploader_only_variables(uploader):
    env = uploader["environment"]
    assert set(env) == {
        "MEDIA_S3_ENDPOINT_URL", "MEDIA_S3_BUCKET", "MEDIA_S3_REGION", "MEDIA_S3_ACCESS_KEY_ID", "MEDIA_S3_SECRET_ACCESS_KEY",
        "MEDIA_STORAGE_NAME", "BACKUP_OCI_NAMESPACE", "BACKUP_OCI_BUCKET", "BACKUP_OCI_REGION", "BACKUP_TOOL_COMMIT", "BACKUP_AGE_RECIPIENTS",
    }
    for name, value in env.items():
        assert re.fullmatch(r"\$\{[A-Z0-9_]+:-[^}]*\}", str(value)), (name, value)  # fail-closed defaults, never ${VAR:?}
    for name in ("MEDIA_S3_ENDPOINT_URL", "MEDIA_S3_BUCKET", "MEDIA_S3_REGION", "MEDIA_S3_ACCESS_KEY_ID", "MEDIA_S3_SECRET_ACCESS_KEY", "MEDIA_STORAGE_NAME"):
        assert str(env[name]).startswith("${BACKUP_UPLOAD_"), name  # never the backend's own read-write R2 variables
    assert not re.search(r"\$\{MEDIA_S3_|\$\{MEDIA_STORAGE", yaml.safe_dump(uploader))


def test_no_required_variable_syntax_anywhere_in_the_uploader_service():
    service_text = COMPOSE.read_text().split("\n  backup-upload:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    assert ":?" not in service_text


def test_the_service_set_is_exactly_the_known_one(compose):
    assert set(compose["services"]) == {"postgres", "backend", "frontend", "caddy", "backup", "backup-upload"}
    assert compose["services"]["backend"]["build"] == {"context": "./backend", "dockerfile": "Dockerfile"}
