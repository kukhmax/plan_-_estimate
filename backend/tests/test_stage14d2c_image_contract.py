"""Stage 14D.2C — backup image and Compose service contract (static).

Reads backend/Dockerfile.backup, backend/Dockerfile and
docker-compose.prod.yml from the repository checkout; the Compose file is
parsed with PyYAML (already installed through uvicorn[standard]). Inside the
backup image the repository files are absent and these tests skip. The
built image and `docker compose config` are proven by the owner's local
Docker run (docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §16).
"""

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
BACKUP_DOCKERFILE = BACKEND / "Dockerfile.backup"
WEB_DOCKERFILE = BACKEND / "Dockerfile"
COMPOSE = REPO / "docker-compose.prod.yml"

pytestmark = pytest.mark.skipif(not COMPOSE.exists(), reason="repository checkout only (not inside the image)")

AGE_SHA256_AMD64 = "cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10"
AGE_SHA256_ARM64 = "6b8dc4333c53a5a57c9e5834e3a48f92605d7154014cd07269ff3327db5d37f4"
PGDG_KEY_URL = "https://www.postgresql.org/media/keys/ACCC4CF8.asc"
PGDG_KEY_SHA256 = "0144068502a1eddd2a0280ede10ef607d1ec592ce819940991203941564e8e76"
PGDG_KEY_FINGERPRINT = "B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8"
PGDG_KEY_PATH = "/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc"
# backend/Dockerfile at d8062c7 (web image; must stay byte-identical in Stage 14D.2C)
WEB_DOCKERFILE_SHA256 = "e47175e5eddb7336670af20c3cc103242d7f47b5c87297b4b7b9008f01c57885"


def instructions(dockerfile: Path) -> list[str]:
    """Dockerfile instructions with line continuations joined and comments dropped."""
    joined = re.sub(r"\\\n", " ", dockerfile.read_text())
    return [line.strip() for line in joined.splitlines() if line.strip() and not line.strip().startswith("#")]


@pytest.fixture(scope="module")
def backup_service() -> dict:
    services = yaml.safe_load(COMPOSE.read_text())["services"]
    return services["backup"]


@pytest.fixture(scope="module")
def all_services() -> dict:
    return yaml.safe_load(COMPOSE.read_text())["services"]


# --- Dockerfile.backup ------------------------------------------------------------------------


def test_dedicated_backup_dockerfile_exists():
    assert BACKUP_DOCKERFILE.is_file()


def test_base_image_is_pinned_python_3_12_by_digest():
    text = BACKUP_DOCKERFILE.read_text()
    assert re.search(r"^ARG PYTHON_IMAGE=python:3\.12\.\d+-slim-trixie@sha256:[0-9a-f]{64}$", text, re.MULTILINE)
    froms = [i for i in instructions(BACKUP_DOCKERFILE) if i.startswith("FROM ")]
    assert froms and all(i.split()[1] == "${PYTHON_IMAGE}" for i in froms)


def test_pg_dump_major_16_is_installed_and_asserted():
    text = " ".join(instructions(BACKUP_DOCKERFILE))
    assert "postgresql-client-16" in text
    assert not re.search(r"install[^;]*\bpostgresql-client\b(?!-)", text)  # never the floating meta package
    assert f"Signed-By: {PGDG_KEY_PATH}" in text
    assert "apt-key" not in text and "trusted.gpg" not in text
    assert "test \"$(command -v pg_dump)\" = /usr/lib/postgresql/16/bin/pg_dump" in text
    assert "grep -Eq '^pg_dump \\(PostgreSQL\\) 16\\.'" in text
    assert "ENV" in text and "PATH=/usr/lib/postgresql/16/bin:" in text


def stage_runs(stage_marker: str) -> list[str]:
    """RUN instructions of the stage starting at the FROM line containing `stage_marker`."""
    instr = instructions(BACKUP_DOCKERFILE)
    start = next(i for i, line in enumerate(instr) if line.startswith("FROM ") and stage_marker in line)
    runs = []
    for line in instr[start + 1:]:
        if line.startswith("FROM "):
            break
        if line.startswith("RUN "):
            runs.append(line)
    return runs


def runtime_runs() -> list[str]:
    instr = instructions(BACKUP_DOCKERFILE)
    start = max(i for i, line in enumerate(instr) if line.startswith("FROM "))
    return [line for line in instr[start:] if line.startswith("RUN ")]


def test_pgdg_key_is_not_taken_from_the_debian_postgresql_common_binary_package():
    """Owner build proof #2: postgresql-common 278 (binary) does not ship the key."""
    text = BACKUP_DOCKERFILE.read_text()
    assert "apt-get download" not in text
    assert "dpkg-deb" not in text
    assert "postgresql-common_" not in text
    assert "apt.postgresql.org.gpg" not in text


def test_pgdg_trust_anchor_is_pinned_and_official():
    text = " ".join(instructions(BACKUP_DOCKERFILE))
    assert f"ARG PGDG_KEY_URL={PGDG_KEY_URL}" in text
    assert f"ARG PGDG_KEY_SHA256={PGDG_KEY_SHA256}" in text
    assert f"ARG PGDG_KEY_FINGERPRINT={PGDG_KEY_FINGERPRINT}" in text
    assert PGDG_KEY_FINGERPRINT.endswith("ACCC4CF8")  # consistent with the official key file name
    assert "apt-key" not in text and "trusted.gpg" not in text


def test_pgdg_key_verification_is_mandatory_and_ordered():
    (run,) = stage_runs("AS pgdg-key")
    download = run.index('curl -fsSL --proto \'=https\' --tlsv1.2 -o /tmp/pgdg.asc "${PGDG_KEY_URL}"')
    sha_check = run.index('echo "${PGDG_KEY_SHA256}  /tmp/pgdg.asc" | sha256sum -c -;')
    parse = run.index("gpg --batch --with-colons --show-keys /tmp/pgdg.asc")
    single = run.index("test \"$(grep -c '^pub:' /tmp/pgdg.colons)\" = 1;")
    fpr = run.index('if [ "${fpr}" != "${PGDG_KEY_FINGERPRINT}" ]; then')
    publish = run.index("install -D -m 0644 /tmp/pgdg.asc /out/apt.postgresql.org.asc")
    assert download < sha_check < parse < single < fpr < publish
    assert "--import" not in run and "--recv" not in run and "keyserver" not in run


def test_runtime_rechecks_the_key_before_apt_trusts_it():
    text = " ".join(instructions(BACKUP_DOCKERFILE))
    assert f"COPY --from=pgdg-key /out/apt.postgresql.org.asc {PGDG_KEY_PATH}" in text
    (run,) = [r for r in runtime_runs() if "postgresql-client-16" in r]
    recheck = run.index(f'echo "${{PGDG_KEY_SHA256}}  {PGDG_KEY_PATH}" | sha256sum -c -;')
    sources = run.index("/etc/apt/sources.list.d/pgdg.sources")
    install = run.index("apt-get install -y --no-install-recommends postgresql-client-16;")
    assert recheck < sources < install
    assert "URIs: https://apt.postgresql.org/pub/repos/apt" in run
    assert "gnupg" not in run and "curl" not in run  # verification tooling stays in the key stage


def pgdg_verification(tmp_path: Path, key_bytes: bytes, sha: str, fingerprint: str) -> subprocess.CompletedProcess[str]:
    """Run the Dockerfile's own key-verification fragment (from the SHA-256
    check to the end of the fingerprint check) on `key_bytes`."""
    (run,) = stage_runs("AS pgdg-key")
    fragment = run[run.index('echo "${PGDG_KEY_SHA256}  /tmp/pgdg.asc"'): run.index("fi;") + len("fi;")]
    key = tmp_path / "pgdg.asc"
    key.write_bytes(key_bytes)
    fragment = fragment.replace("/tmp/pgdg.asc", str(key)).replace("/tmp/pgdg.colons", str(tmp_path / "colons"))
    fragment = fragment.replace('export GNUPGHOME="$(mktemp -d)";', f'export GNUPGHOME="{tmp_path / "gnupg-verify"}";')
    (tmp_path / "gnupg-verify").mkdir(mode=0o700, exist_ok=True)
    env = {"PATH": "/usr/bin:/bin", "PGDG_KEY_SHA256": sha, "PGDG_KEY_FINGERPRINT": fingerprint}
    return subprocess.run(
        ["/bin/sh", "-c", f"set -eu; {fragment} echo VERIFIED"], env=env, capture_output=True, text=True, check=False
    )


@pytest.fixture
def throwaway_keys(tmp_path) -> list[tuple[bytes, str]]:
    """Two disposable OpenPGP public keys (armored bytes, fingerprint), generated per test run."""
    if shutil.which("gpg") is None:
        pytest.skip("gpg not available")
    home = tmp_path / "gnupg-gen"
    home.mkdir(mode=0o700)
    env = {"GNUPGHOME": str(home), "PATH": "/usr/bin:/bin"}
    keys = []
    for name in ("throwaway-a@example.invalid", "throwaway-b@example.invalid"):
        subprocess.run(["gpg", "--batch", "--passphrase", "", "--quick-gen-key", name, "ed25519", "sign", "1d"],
                       env=env, check=True, capture_output=True)
        armored = subprocess.run(["gpg", "--batch", "--armor", "--export", name], env=env, check=True,
                                 capture_output=True).stdout
        colons = subprocess.run(["gpg", "--batch", "--with-colons", "--fingerprint", name], env=env, check=True,
                                capture_output=True, text=True).stdout
        fingerprint = next(line.split(":")[9] for line in colons.splitlines() if line.startswith("fpr:"))
        keys.append((armored, fingerprint))
    return keys


def test_pgdg_verification_accepts_only_the_pinned_key(tmp_path, throwaway_keys):
    key, fingerprint = throwaway_keys[0]
    result = pgdg_verification(tmp_path, key, hashlib.sha256(key).hexdigest(), fingerprint)
    assert result.returncode == 0 and "VERIFIED" in result.stdout, result.stderr


def test_pgdg_verification_rejects_a_sha256_mismatch_before_parsing(tmp_path, throwaway_keys):
    key, fingerprint = throwaway_keys[0]
    result = pgdg_verification(tmp_path, key + b"\n", hashlib.sha256(key).hexdigest(), fingerprint)
    assert result.returncode != 0 and "VERIFIED" not in result.stdout
    assert not (tmp_path / "colons").exists()  # gpg never ran


def test_pgdg_verification_rejects_a_fingerprint_mismatch(tmp_path, throwaway_keys):
    (key, _), (_, other_fingerprint) = throwaway_keys
    result = pgdg_verification(tmp_path, key, hashlib.sha256(key).hexdigest(), other_fingerprint)
    assert result.returncode != 0 and "does not match the pinned fingerprint" in result.stderr


def test_pgdg_verification_rejects_more_than_one_key(tmp_path, throwaway_keys):
    (key_a, fingerprint_a), (key_b, _) = throwaway_keys
    both = key_a + key_b
    result = pgdg_verification(tmp_path, both, hashlib.sha256(both).hexdigest(), fingerprint_a)
    assert result.returncode != 0 and "VERIFIED" not in result.stdout


def test_age_release_is_pinned_and_checksum_verified():
    text = " ".join(instructions(BACKUP_DOCKERFILE))
    assert "ARG AGE_VERSION=v1.3.2" in text
    assert f"ARG AGE_SHA256_AMD64={AGE_SHA256_AMD64}" in text
    assert f"ARG AGE_SHA256_ARM64={AGE_SHA256_ARM64}" in text
    assert "https://github.com/FiloSottile/age/releases/download/${AGE_VERSION}/age-${AGE_VERSION}-linux-${arch}.tar.gz" in text
    # the architecture (and with it the checksum) is fixed before anything is downloaded
    assert text.index('sha="${AGE_SHA256_AMD64}"') < text.index("curl -fsSL")
    assert 'sha256sum -c -' in text
    # checksum is verified before extraction
    assert text.index("sha256sum -c -") < text.index("tar -xzf /tmp/age.tar.gz")
    assert "case \"$(age --version)\" in v1.3.2|1.3.2) ;;" in text
    assert not re.search(r"apt-get install[^;]*\bage\b", text)  # no floating distribution age


def age_stage_run() -> str:
    for instruction in instructions(BACKUP_DOCKERFILE):
        if instruction.startswith("RUN") and "AGE_SHA256_AMD64" in instruction:
            return instruction
    raise AssertionError("age download RUN not found")


def arch_selection(native: str, targetarch: str | None, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Execute the Dockerfile's own architecture-selection fragment (from
    `stage_arch=` to the closing `esac;`) under /bin/sh with a stand-in
    `dpkg --print-architecture`, then print the chosen arch and checksum."""
    run = age_stage_run()
    fragment = run[run.index('stage_arch="$(dpkg --print-architecture)";'): run.index("esac;") + len("esac;")]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    dpkg = bin_dir / "dpkg"
    dpkg.write_text(f"#!/bin/sh\n[ \"$1\" = --print-architecture ] && echo {native}\n")
    dpkg.chmod(0o700)
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "AGE_SHA256_AMD64": AGE_SHA256_AMD64,
        "AGE_SHA256_ARM64": AGE_SHA256_ARM64,
    }
    if targetarch is not None:
        env["TARGETARCH"] = targetarch
    script = f'set -eu; {fragment} echo "RESULT ${{arch}} ${{sha}}"'
    return subprocess.run(["/bin/sh", "-c", script], env=env, capture_output=True, text=True, check=False)


def test_age_architecture_args_are_declared():
    text = " ".join(instructions(BACKUP_DOCKERFILE))
    assert "ARG TARGETARCH" in text
    assert 'stage_arch="$(dpkg --print-architecture)"' in text
    assert "uname" not in age_stage_run()


@pytest.mark.parametrize(("native", "expected_sha"), [("amd64", AGE_SHA256_AMD64), ("arm64", AGE_SHA256_ARM64)])
def test_buildkit_targetarch_is_used_when_it_matches(tmp_path, native, expected_sha):
    result = arch_selection(native, native, tmp_path)
    assert result.returncode == 0, result.stderr
    assert f"RESULT {native} {expected_sha}" in result.stdout
    assert "(TARGETARCH, BuildKit)" in result.stdout


@pytest.mark.parametrize("targetarch", [None, ""])
@pytest.mark.parametrize(("native", "expected_sha"), [("amd64", AGE_SHA256_AMD64), ("arm64", AGE_SHA256_ARM64)])
def test_classic_builder_falls_back_to_native_architecture(tmp_path, native, expected_sha, targetarch):
    result = arch_selection(native, targetarch, tmp_path)
    assert result.returncode == 0, result.stderr
    assert f"RESULT {native} {expected_sha}" in result.stdout
    assert "classic builder" in result.stdout


@pytest.mark.parametrize("native", ["armhf", "i386", "ppc64el", "riscv64", "s390x", "x86_64", "aarch64", ""])
def test_unsupported_native_architecture_fails(tmp_path, native):
    result = arch_selection(native, None, tmp_path)
    assert result.returncode != 0 and "RESULT" not in result.stdout


@pytest.mark.parametrize("targetarch", ["arm", "386", "riscv64", "x86_64", "aarch64", "AMD64"])
def test_unsupported_supplied_targetarch_fails_and_is_not_overridden(tmp_path, targetarch):
    result = arch_selection("amd64", targetarch, tmp_path)
    assert result.returncode != 0 and "RESULT" not in result.stdout


@pytest.mark.parametrize(("native", "targetarch"), [("amd64", "arm64"), ("arm64", "amd64")])
def test_targetarch_mismatching_the_stage_architecture_fails(tmp_path, native, targetarch):
    result = arch_selection(native, targetarch, tmp_path)
    assert result.returncode != 0 and "does not match" in result.stderr


def test_each_architecture_has_its_own_mandatory_checksum():
    run = age_stage_run()
    assert 'amd64) sha="${AGE_SHA256_AMD64}" ;;' in run
    assert 'arm64) sha="${AGE_SHA256_ARM64}" ;;' in run
    assert AGE_SHA256_AMD64 != AGE_SHA256_ARM64
    assert 'echo "${sha}  /tmp/age.tar.gz" | sha256sum -c -;' in run
    assert run.index("sha256sum -c -") < run.index("tar -xzf")


def test_no_private_identity_or_secrets_in_image():
    text = BACKUP_DOCKERFILE.read_text()
    assert "AGE-SECRET-KEY" not in text
    for instruction in instructions(BACKUP_DOCKERFILE):
        if instruction.startswith(("COPY", "ADD")):
            assert not re.search(r"identity|\.key\b|pgpass|\.env|secret", instruction, re.IGNORECASE), instruction
    copies = [i for i in instructions(BACKUP_DOCKERFILE) if i.startswith("COPY ")]
    assert "COPY . ." not in copies  # explicit sources only


def test_no_backend_entrypoint_migrations_or_web_server():
    instr = instructions(BACKUP_DOCKERFILE)
    text = " ".join(instr)
    assert "entrypoint.sh" not in text
    assert "uvicorn" not in text
    # D2: alembic scripts are copied for offline head resolution only; never executed by the image
    alembic_lines = [i for i in instr if "alembic" in i]
    assert alembic_lines == ["COPY alembic.ini ./", "COPY alembic ./alembic"]
    assert not any(i.startswith(("RUN", "ENTRYPOINT", "CMD")) and "alembic" in i for i in instr)
    assert 'ENTRYPOINT ["python", "-m", "app.backup"]' in instr
    assert 'CMD ["preflight"]' in instr
    assert "PYTHONDONTWRITEBYTECODE=1" in text


def test_same_pinned_requirements_as_web_image():
    instr = instructions(BACKUP_DOCKERFILE)
    assert "COPY requirements.txt pyproject.toml ./" in instr
    assert "RUN pip install --no-cache-dir -r requirements.txt" in instr
    pips = [i for i in instr if "pip install" in i]
    assert len(pips) == 1  # no second, floating dependency set


def test_default_user_is_non_root():
    users = [i for i in instructions(BACKUP_DOCKERFILE) if i.startswith("USER ")]
    assert users == ["USER 65534:65534"]


def test_web_backend_dockerfile_is_byte_identical():
    assert hashlib.sha256(WEB_DOCKERFILE.read_bytes()).hexdigest() == WEB_DOCKERFILE_SHA256


def test_web_backend_dockerfile_keeps_its_contract():
    instr = instructions(WEB_DOCKERFILE)
    text = " ".join(instr)
    assert instr[0] == "FROM python:3.12-slim"
    assert 'CMD ["./entrypoint.sh"]' in instr
    for tool in ("pg_dump", "postgresql", "age", "Dockerfile.backup", "app.backup"):
        assert not re.search(rf"\b{re.escape(tool)}\b", text), tool


# --- Compose backup service --------------------------------------------------------------------


def test_backup_service_is_profile_gated(backup_service, all_services):
    assert backup_service["profiles"] == ["backup"]
    for name, service in all_services.items():
        if name != "backup":
            assert "profiles" not in service, name  # normal services stay active by default


def test_backup_service_builds_the_dedicated_image(backup_service):
    assert backup_service["build"] == {"context": "./backend", "dockerfile": "Dockerfile.backup"}
    assert backup_service["image"] == "plan-estimate-backup:local"
    assert backup_service["entrypoint"] == ["python", "-m", "app.backup"]
    assert backup_service["command"] == ["preflight"]


def test_no_dependencies_ports_or_restart(backup_service):
    assert "depends_on" not in backup_service
    assert "ports" not in backup_service and "expose" not in backup_service
    assert backup_service["restart"] == "no"
    assert backup_service["networks"] == ["internal"]
    assert "network_mode" not in backup_service


def test_privileges_are_dropped(backup_service):
    assert backup_service["cap_drop"] == ["ALL"]
    assert "cap_add" not in backup_service
    assert backup_service["security_opt"] == ["no-new-privileges:true"]
    assert backup_service.get("privileged") in (None, False)
    assert backup_service["read_only"] is True
    assert backup_service["init"] is True
    for key in ("pid", "ipc", "devices", "userns_mode"):
        assert key not in backup_service


def test_explicit_non_root_user_contract(backup_service):
    assert backup_service["user"] == "${BACKUP_UID:-65534}:${BACKUP_GID:-65534}"
    assert "0" not in re.findall(r":-(\d+)", backup_service["user"])


def test_resource_limits(backup_service):
    assert backup_service["mem_limit"] == "512m"
    assert backup_service["cpus"] == 0.5
    assert backup_service["pids_limit"] == 64


def test_only_approved_mounts(backup_service):
    """Stage 14D.2D.2 (owner decision D1): ONE data mount at /backup (atomic
    work -> encrypted promotion needs one mount), pgpass separate and read-only."""
    mounts = backup_service["volumes"]
    root = "${BACKUP_HOST_ROOT:-/nonexistent/plan-estimate-backup-root-not-configured}"
    binds = {m["target"]: m for m in mounts if m["type"] == "bind"}
    assert set(binds) == {"/backup", "/run/secrets/pgpass"}
    assert binds["/backup"]["source"] == f"{root}/data"
    assert not binds["/backup"].get("read_only")
    assert binds["/run/secrets/pgpass"]["source"] == f"{root}/secrets/pgpass"
    assert binds["/run/secrets/pgpass"]["read_only"] is True
    for mount in binds.values():
        assert mount["bind"] == {"create_host_path": False}
    tmpfs = [m for m in mounts if m["type"] == "tmpfs"]
    assert tmpfs == [{"type": "tmpfs", "target": "/tmp", "tmpfs": {"size": 16777216}}]
    assert len(mounts) == 3


def test_no_individual_data_subdirectory_mounts_remain(backup_service):
    targets = [m["target"] for m in backup_service["volumes"]]
    for old in ("/backup/work", "/backup/encrypted", "/backup/evidence"):
        assert old not in targets
    sources = [str(m.get("source", "")) for m in backup_service["volumes"]]
    assert not any(src.endswith(("/work", "/encrypted", "/evidence")) for src in sources)


def test_secrets_are_outside_the_data_mount(backup_service):
    binds = {m["target"]: m["source"] for m in backup_service["volumes"] if m["type"] == "bind"}
    data, secret = binds["/backup"], binds["/run/secrets/pgpass"]
    assert not secret.startswith(data + "/")
    assert not "/run/secrets/pgpass".startswith("/backup/")


def test_stop_grace_period_allows_protected_cleanup(backup_service):
    assert backup_service["stop_grace_period"] == "45s"


def test_no_socket_data_volume_repository_or_frontend_mounts(backup_service):
    text = yaml.safe_dump(backup_service)
    for forbidden in ("docker.sock", "/var/run/docker", "postgres_data", "caddy", "Caddyfile", "certs", "./backend:",
                      "./:", "/app"):
        assert forbidden not in text, forbidden
    for mount in backup_service["volumes"]:
        source = str(mount.get("source", ""))
        assert not source.startswith(".") and "postgres" not in source


def test_environment_is_explicit_and_secret_free(backup_service):
    env = backup_service["environment"]
    assert set(env) == {
        "PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGSSLMODE", "PGPASSFILE", "BACKUP_AGE_RECIPIENTS"
    }
    assert env["PGPASSFILE"] == "/run/secrets/pgpass"
    assert env["PGSSLMODE"] == "${BACKUP_PGSSLMODE:-}"  # explicit configuration, no baked-in mode
    assert "env_file" not in backup_service
    text = yaml.safe_dump(env)
    for forbidden in ("PASSWORD", "POSTGRES_", "DATABASE_URL", "JWT", "TELEGRAM", "MEDIA_S3", "SECRET"):
        assert forbidden not in text, forbidden


def test_compose_file_avoids_required_variable_syntax_in_backup_service():
    """`${VAR:?}` would make every normal `docker compose up -d` fail while the
    backup variables are unset (Compose interpolates the whole file)."""
    service_text = COMPOSE.read_text().split("\n  backup:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    assert ":?" not in service_text


def test_other_services_unchanged_by_backup_contract(all_services):
    assert set(all_services) == {"postgres", "backend", "frontend", "caddy", "backup"}
    assert all_services["postgres"]["image"] == "postgres:16-alpine"
    assert "ports" not in all_services["postgres"]
    assert all_services["backend"]["build"] == {"context": "./backend", "dockerfile": "Dockerfile"}
