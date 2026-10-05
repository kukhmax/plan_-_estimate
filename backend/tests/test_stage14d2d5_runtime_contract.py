"""Stage 14D.2D.5 — static runtime contract + proof-tooling tests (no Docker).

Proves: the production `backup` service definition carries the accepted runtime contract; the
scratch override only adds a fail-closed guard; the host checker, the in-service proof operations
(on a local temporary data root, real renameat2 / flock) and the scratch tool behave as designed.
It does NOT prove Compose / container runtime behaviour -- that is the owner-run proof (§16.7).
"""

import copy
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.backup import run_sidecars
from tests.runtime_proof import bind_ops, check_host

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
COMPOSE = REPO / "docker-compose.prod.yml"
OVERRIDE = BACKEND / "tests" / "runtime_proof" / "compose.proof-override.yml"
RUN_A = "20261003T081500Z-3f9a1c2e"

needs_repo = pytest.mark.skipif(not COMPOSE.exists(), reason="repository checkout only")


@pytest.fixture(scope="module")
def backup_service() -> dict:
    return yaml.safe_load(COMPOSE.read_text())["services"]["backup"]


# --- Part A: production Compose contract (additions to the 14D.2C contract tests) -----------------


@needs_repo
def test_backup_reaches_postgres_by_internal_service_name(backup_service):
    env = backup_service["environment"]
    assert env["PGHOST"] == "${BACKUP_PGHOST:-postgres}" and env["PGPORT"] == "${BACKUP_PGPORT:-5432}"
    for key in ("network_mode", "extra_hosts", "ports", "expose", "links", "external_links", "privileged"):
        assert key not in backup_service
    assert backup_service["networks"] == ["internal"]


@needs_repo
def test_backup_one_shot_cli_path(backup_service):
    from app.backup.__main__ import main

    assert backup_service["entrypoint"] == ["python", "-m", "app.backup"]
    assert backup_service["restart"] == "no"
    with pytest.raises(SystemExit) as exc:
        main(["db-dump", "--help"])
    assert exc.value.code == 0


@needs_repo
def test_backup_data_is_one_bind_and_secrets_are_separate(backup_service):
    binds = [m for m in backup_service["volumes"] if m["type"] == "bind"]
    targets = sorted(m["target"] for m in binds)
    assert targets == ["/backup", "/run/secrets/pgpass"]
    pgpass = next(m for m in binds if m["target"] == "/run/secrets/pgpass")
    assert pgpass["read_only"] is True and not pgpass["target"].startswith("/backup")
    assert backup_service["stop_grace_period"] == "45s"
    assert backup_service["read_only"] is True and backup_service["cap_drop"] == ["ALL"]
    assert backup_service["security_opt"] == ["no-new-privileges:true"]
    assert any(m["type"] == "tmpfs" and m["target"] == "/tmp" for m in backup_service["volumes"])


# --- Part B: the scratch override adds only a fail-closed guard --------------------------------------


@needs_repo
def test_override_only_adds_a_guard_variable():
    override = yaml.safe_load(OVERRIDE.read_text())
    assert set(override) == {"services"}
    assert set(override["services"]) == {"backup"}
    assert override["services"]["backup"] == {"environment": {"PE_PROOF_GUARD": override["services"]["backup"]["environment"]["PE_PROOF_GUARD"]}}


@needs_repo
def test_override_guard_requires_every_scratch_variable():
    guard = yaml.safe_load(OVERRIDE.read_text())["services"]["backup"]["environment"]["PE_PROOF_GUARD"]
    for name in ("PE_PROOF_ID", "BACKUP_HOST_ROOT", "BACKUP_UID", "BACKUP_GID", "BACKUP_PGHOST",
                 "BACKUP_PGDATABASE", "BACKUP_PGUSER", "BACKUP_PGSSLMODE"):
        assert f"${{{name}:?" in guard, name
    assert ":-" not in guard  # no silent default


@needs_repo
def test_override_does_not_weaken_the_merged_service(backup_service):
    override = yaml.safe_load(OVERRIDE.read_text())["services"]["backup"]
    merged = copy.deepcopy(backup_service)
    merged["environment"] = {**merged["environment"], **override["environment"]}
    for key in ("user", "read_only", "cap_drop", "security_opt", "mem_limit", "cpus", "pids_limit",
                "stop_grace_period", "volumes", "networks", "entrypoint", "init", "restart", "profiles"):
        assert merged[key] == backup_service[key], key
    assert "PGPASSWORD" not in merged["environment"]


# --- check_host ------------------------------------------------------------------------------------------


def make_data(tmp_path: Path, *, run_id: str = RUN_A, tamper: bool = False) -> Path:
    data = tmp_path / "data"
    for name in ("work", "encrypted", "evidence"):
        (data / name).mkdir(parents=True, mode=0o700)
    run = data / "encrypted" / run_id
    run.mkdir(mode=0o700)
    artifact = run / "plan-estimate.sql.gz.age"
    artifact.write_bytes(b"age-encryption.org/v1\nCIPHERTEXT")
    artifact.chmod(0o600)
    evidence: dict[str, Any] = {
        "status": "complete", "run_id": run_id,
        "database": {"alembic_revision": "0032_photo_attachments", "expected_alembic_head": "0032_photo_attachments"},
        "artifact": {"sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(), "size": artifact.stat().st_size},
    }
    if tamper:
        evidence["artifact"]["size"] += 1
    (run / "local-run.json").write_text(json.dumps(evidence))
    (run / "local-run.json").chmod(0o600)
    for sidecar in run_sidecars.SIDECAR_NAMES:       # written by `db-dump` since 14D.2J
        (run / sidecar).write_text("sidecar\n")
        (run / sidecar).chmod(0o600)
    lock = data / "run.lock"
    lock.write_text("")
    lock.chmod(0o600)
    return data


def test_check_run_passes_on_a_complete_layout(tmp_path):
    result = check_host.check_run(make_data(tmp_path), None, 1)
    assert result["pass"], result
    assert result["run_id"] == RUN_A and len(result["artifact_sha256"]) == 64


@pytest.mark.parametrize("problem", ["tamper", "work", "evidence", "plaintext", "lock", "mode", "no-sidecar", "extra-file"])
def test_check_run_detects_problems(tmp_path, problem):
    data = make_data(tmp_path, tamper=problem == "tamper")
    if problem == "work":
        (data / "work" / "leftover").mkdir()
    elif problem == "evidence":
        (data / "evidence" / f"{RUN_A}.failed.json").write_text("{}")
    elif problem == "plaintext":
        (data / "encrypted" / RUN_A / "plan-estimate.sql").write_text("x")
    elif problem == "lock":
        (data / "run.lock").unlink()
    elif problem == "mode":
        (data / "encrypted" / RUN_A / "plan-estimate.sql.gz.age").chmod(0o644)
    elif problem == "no-sidecar":
        (data / "encrypted" / RUN_A / run_sidecars.RECIPIENTS_NAME).unlink()
    elif problem == "extra-file":
        (data / "encrypted" / RUN_A / "unexpected.txt").write_text("x")
    assert not check_host.check_run(data, RUN_A, None)["pass"]


def test_proof_tooling_expects_exactly_the_files_db_dump_seals():
    """The host checker cannot import the app, so its literal names are pinned to the real constants; the in-container
    verifier derives its set from them (a stale list made the first ARM64 gate run fail on the sidecars)."""
    assert {check_host.READY_ASSETS, check_host.RECIPIENTS} == set(run_sidecars.SIDECAR_NAMES)
    assert check_host.EXPECTED_FILES == sorted(
        {"local-run.json", "plan-estimate.sql.gz.age"} | set(run_sidecars.SIDECAR_NAMES))
    scratch = (BACKEND / "tests" / "runtime_proof" / "scratch.py").read_text()
    assert "| SIDECAR_NAMES" in scratch and 'names == ["local-run.json"' not in scratch


def container_info(**overrides: Any) -> dict[str, Any]:
    info: dict[str, Any] = {
        "Config": {"User": "1000:1000", "StopTimeout": 45,
                   "Labels": {"com.docker.compose.project": "plan-estimate-14d2d5-proof"}},
        "HostConfig": {"ReadonlyRootfs": True, "CapDrop": ["ALL"], "CapAdd": None,
                       "SecurityOpt": ["no-new-privileges:true"], "Privileged": False, "PortBindings": {},
                       "PublishAllPorts": False, "Tmpfs": {}, "Mounts": [{"Type": "tmpfs", "Target": "/tmp"}],
                       "Memory": 536870912, "NanoCpus": 500000000, "PidsLimit": 64, "Init": True,
                       "NetworkMode": "plan-estimate-14d2d5-proof_internal"},
        "Mounts": [
            {"Type": "bind", "Source": "/tmp/pe-14d2d5-proof.x/root/data", "Destination": "/backup", "RW": True},
            {"Type": "bind", "Source": "/tmp/pe-14d2d5-proof.x/root/secrets/pgpass",
             "Destination": "/run/secrets/pgpass", "RW": False},
        ],
        "NetworkSettings": {"Networks": {"plan-estimate-14d2d5-proof_internal": {}}},
    }
    for path, value in overrides.items():
        target: Any = info
        *parents, leaf = path.split(".")
        for part in parents:
            target = target[part]
        target[leaf] = value
    return info


def test_check_container_passes_on_the_expected_runtime():
    result = check_host.check_container(container_info())
    assert result["pass"], result


@pytest.mark.parametrize(
    "path,value",
    [
        ("Config.User", "0:0"), ("Config.User", ""), ("HostConfig.ReadonlyRootfs", False),
        ("HostConfig.CapDrop", []), ("HostConfig.CapAdd", ["NET_ADMIN"]), ("HostConfig.SecurityOpt", []),
        ("HostConfig.Privileged", True), ("HostConfig.PortBindings", {"5432/tcp": [{"HostPort": "5432"}]}),
        ("HostConfig.Mounts", []), ("HostConfig.Memory", 0), ("HostConfig.PidsLimit", None),
        ("Config.StopTimeout", None), ("HostConfig.Init", None),
        ("NetworkSettings.Networks", {"plan-estimate_internal": {}}),
        ("Config.Labels", {"com.docker.compose.project": "plan-estimate"}),
    ],
)
def test_check_container_detects_weakened_runtime(path, value):
    assert not check_host.check_container(container_info(**{path: value}))["pass"]


def test_check_container_detects_bad_mounts():
    socket_mount = container_info()
    socket_mount["Mounts"].append({"Type": "bind", "Source": "/var/run/docker.sock",
                                   "Destination": "/var/run/docker.sock", "RW": True})
    assert not check_host.check_container(socket_mount)["pass"]
    writable_pgpass = container_info()
    writable_pgpass["Mounts"][1]["RW"] = True
    assert not check_host.check_container(writable_pgpass)["pass"]
    pgpass_inside = container_info()
    pgpass_inside["Mounts"][1]["Source"] = "/tmp/pe-14d2d5-proof.x/root/data/pgpass"
    assert not check_host.check_container(pgpass_inside)["pass"]
    split = container_info()
    split["Mounts"].append({"Type": "bind", "Source": "/x/work", "Destination": "/backup/work", "RW": True})
    assert not check_host.check_container(split)["pass"]


def test_check_postgres_and_network():
    pg: dict[str, Any] = {"HostConfig": {"PortBindings": {}}, "Config": {"Image": "postgres:16-alpine"},
          "NetworkSettings": {"Ports": {"5432/tcp": None}, "Networks": {"plan-estimate-14d2d5-proof_internal": {}}}}
    assert check_host.check_postgres(pg)["pass"]
    published = copy.deepcopy(pg)
    published["NetworkSettings"]["Ports"]["5432/tcp"] = [{"HostIp": "0.0.0.0", "HostPort": "5432"}]
    assert not check_host.check_postgres(published)["pass"]
    net = {"Name": "plan-estimate-14d2d5-proof_internal", "Internal": True,
           "Labels": {"com.docker.compose.project": "plan-estimate-14d2d5-proof", "com.docker.compose.network": "internal"},
           "Containers": {"a": {"Name": "pe14d2d5-proof-pg"}}}
    assert check_host.check_network(net)["pass"]
    assert not check_host.check_network({**net, "Internal": False})["pass"]
    assert not check_host.check_network({**net, "Containers": {"a": {"Name": "plan_estimate_postgres"}}})["pass"]


def test_check_host_cli_reads_docker_inspect_lists(capsys):
    assert check_host.main(["container"], stdin_text=json.dumps([container_info()])) == 0
    assert json.loads(capsys.readouterr().out)["pass"] is True


def test_check_stale(tmp_path):
    data = make_data(tmp_path)
    entry = data / "work" / "pe-proof-stale-entry"
    entry.write_bytes(b"synthetic stale proof entry\n")
    sha = hashlib.sha256(entry.read_bytes()).hexdigest()
    assert check_host.check_stale(data, entry.name, sha, 1)["pass"]
    entry.write_bytes(b"changed")
    assert not check_host.check_stale(data, entry.name, sha, 1)["pass"]


def test_check_host_is_standard_library_only():
    source = (BACKEND / "tests" / "runtime_proof" / "check_host.py").read_text()
    for forbidden in ("import app", "from app", "import pytest", "import asyncpg", "subprocess", "os.system"):
        assert forbidden not in source


# --- bind_ops ----------------------------------------------------------------------------------------------

STATUS = "Uid:\t1000\t1000\t1000\t1000\nGid:\t1000\t1000\t1000\t1000\nCapInh:\t0000000000000000\n" \
         "CapPrm:\t0000000000000000\nCapEff:\t0000000000000000\nCapBnd:\t0000000000000000\n" \
         "CapAmb:\t0000000000000000\nNoNewPrivs:\t1\n"


def mountinfo(data_root: Path, passfile: Path, *, root_opts: str = "ro", pass_opts: str = "ro") -> str:
    return "\n".join([
        f"1 0 0:1 / / {root_opts},relatime - overlay overlay {root_opts},lowerdir=x",
        "2 1 0:2 / /tmp rw,nosuid - tmpfs tmpfs rw,size=16384k",
        f"3 1 8:1 /x {data_root} rw,relatime - ext4 /dev/sda1 rw",
        f"4 1 8:1 /y {passfile} {pass_opts},relatime - ext4 /dev/sda1 rw",
    ])


def test_parse_status_and_mountinfo(tmp_path):
    status = bind_ops.parse_status(STATUS)
    assert status["CapEff"] == "0000000000000000" and status["NoNewPrivs"] == "1"
    mounts = bind_ops.parse_mountinfo(mountinfo(tmp_path / "d", tmp_path / "p"))
    assert mounts["/tmp"]["fstype"] == "tmpfs" and "ro" in mounts["/"]["options"]


def test_self_inspect_flags_a_writable_passfile_and_capabilities(tmp_path):
    data = tmp_path / "data"
    data.mkdir(mode=0o700)
    passfile = tmp_path / "pgpass"
    passfile.write_text("x")
    passfile.chmod(0o600)
    result = bind_ops.self_inspect(data, passfile, status_text=STATUS.replace("CapEff:\t0000000000000000", "CapEff:\t00000000a80425fb"),
                                   mountinfo_text=mountinfo(data, passfile, root_opts="rw", pass_opts="rw"))
    assert result["pass"] is False
    assert result["passfile_write_attempt"] == "WRITABLE" and result["no_capabilities"] is False
    assert result["root_read_only"] is False
    assert passfile.read_text() == "x"  # never read / modified


def test_promote_proof_on_a_local_data_root(tmp_path):
    data = tmp_path / "data"
    data.mkdir(mode=0o700)
    from app.backup.workspace import BackupDataRoot

    BackupDataRoot(data).prepare()
    existing = data / "encrypted" / RUN_A
    existing.mkdir(mode=0o700)
    (existing / "keep").write_text("real artifact")
    result = bind_ops.promote_proof(data)
    assert result["pass"], result
    assert sorted(p.name for p in (data / "encrypted").iterdir()) == [RUN_A]
    assert (existing / "keep").read_text() == "real artifact"


def run_bind_ops(data: Path, *args: str, **kwargs) -> subprocess.Popen[str]:
    return subprocess.Popen([sys.executable, "-m", "tests.runtime_proof.bind_ops", "--data-root", str(data), *args],
                            cwd=BACKEND, env={**os.environ, "PYTHONPATH": str(BACKEND)}, stdout=subprocess.PIPE,
                            text=True, **kwargs)


def test_lock_hold_and_try_across_processes(tmp_path):
    import signal

    data = tmp_path / "data"
    data.mkdir(mode=0o700)
    holder = run_bind_ops(data, "hold-lock", "--seconds", "60")
    assert holder.stdout is not None and json.loads(holder.stdout.readline())["state"] == "LOCKED"
    contender = run_bind_ops(data, "try-lock")
    out, _ = contender.communicate(timeout=30)
    assert contender.returncode == 3 and json.loads(out)["state"] == "LOCK_HELD"
    holder.send_signal(signal.SIGTERM)
    assert json.loads(holder.stdout.readline()) == {"reason": "signal", "state": "RELEASED"}
    holder.wait(timeout=30)
    after = run_bind_ops(data, "try-lock")
    out, _ = after.communicate(timeout=30)
    assert after.returncode == 0 and json.loads(out)["state"] == "ACQUIRED"
    crashed = run_bind_ops(data, "hold-lock", "--seconds", "60")
    assert crashed.stdout is not None and json.loads(crashed.stdout.readline())["state"] == "LOCKED"
    crashed.kill()
    crashed.wait(timeout=30)
    again = run_bind_ops(data, "try-lock")
    out, _ = again.communicate(timeout=30)
    assert again.returncode == 0
    assert stat.S_IMODE((data / "run.lock").stat().st_mode) == 0o600


# --- scratch tool guards ------------------------------------------------------------------------------------


def test_scratch_guards_and_backup_passfile_parsing(tmp_path):
    from tests.pg16_proof_support import ProofConfigError, ProofServer
    from tests.runtime_proof import scratch

    superuser = tmp_path / "su.pgpass"
    superuser.write_text("pe14d2d5-proof-pg:5432:*:postgres:" + "b" * 48 + "\n")
    superuser.chmod(0o600)
    server = ProofServer.from_env({"TEST_PG16_HOST": "pe14d2d5-proof-pg", "TEST_PG16_SUPERUSER_PASSFILE": str(superuser)})
    good = tmp_path / "backup.pgpass"
    password = "c" * 48
    good.write_text(f"pe14d2d5-proof-pg:5432:{scratch.DATABASE}:{scratch.BACKUP_ROLE}:{password}\n")
    assert scratch.backup_password(good, server) == password
    for content in (f"pe14d2d5-proof-pg:5432:plan_estimate:{scratch.BACKUP_ROLE}:{password}\n",
                    f"pe14d2d5-proof-pg:5432:{scratch.DATABASE}:postgres:{password}\n",
                    f"pe14d2d5-proof-pg:5432:{scratch.DATABASE}:{scratch.BACKUP_ROLE}:short\n", ""):
        bad = tmp_path / "bad.pgpass"
        bad.write_text(content)
        with pytest.raises(ProofConfigError):
            scratch.backup_password(bad, server)
    assert scratch.scratch_db("pe_scratch_test_14d2d5_verify_00aa") and scratch.scratch_db("postgres")
    for name in ("plan_estimate", "pe_scratch_test_14d2d4_x", "pe_scratch_test_14d2d5;drop"):
        with pytest.raises(ProofConfigError):
            scratch.scratch_db(name)
    assert password not in scratch.dsn(server, scratch.DATABASE)


# --- owner script static guards -------------------------------------------------------------------------------


def test_owner_script_targets_only_scratch_resources():
    script = (BACKEND / "tests" / "runtime_proof" / "owner_proof.sh").read_text()
    assert "PROJ=plan-estimate-14d2d5-proof" in script
    assert "-p plan-estimate " not in script and '-p "plan-estimate"' not in script
    for forbidden in (".env.production", "down -v", "docker.sock", "--privileged", " -p 5432", "--publish",
                      "rm -rf", "docker volume rm", "docker system prune"):
        assert forbidden not in script, forbidden
    assert script.count('-f "$HERE/compose.proof-override.yml"') >= 2  # every compose call carries the guard
    assert "case \"$ROOT\" in /tmp/pe-14d2d5-proof.*)" in script
    assert "run --rm --no-deps backup db-dump" in script
    assert "--network create" not in script and 'docker network create --internal' in script


def test_owner_script_never_puts_secrets_in_argv_or_output():
    script = (BACKEND / "tests" / "runtime_proof" / "owner_proof.sh").read_text()
    assert "unset SU BK" in script
    assert "POSTGRES_PASSWORD_FILE" in script and "POSTGRES_PASSWORD=" not in script
    assert "PGPASSWORD" not in script
    assert "grep -rqF -f" in script  # leak check reads patterns from a file, not argv
    assert "echo \"$SU" not in script and "echo \"$BK" not in script


def test_owner_script_needs_no_age_on_the_host():
    """14D.6A: the ARM64 gate runs on the production VM, which has no `age` (and must not get one): the throwaway
    identity of the synthetic proof is generated by the image under test, after the build."""
    script = (BACKEND / "tests" / "runtime_proof" / "owner_proof.sh").read_text()
    lines = script.splitlines()
    host_age = [ln for ln in lines if re.match(r"\s*(RECIPIENT=\$\()?age-keygen\b", ln.strip())]
    assert host_age == [], host_age
    assert script.count("--entrypoint age-keygen") == 2  # generate + derive the recipient, both inside the image
    build = next(i for i, ln in enumerate(lines) if "build backup" in ln)
    generated = next(i for i, ln in enumerate(lines) if "--entrypoint age-keygen" in ln)
    assert build < generated, "the identity is generated only after the image exists"
    assert "(umask 077;" in script and 'chmod 600 "$P/identity/identity.txt"' in script
    assert "refusing: the image did not produce an age recipient" in script
    assert 'sed -i "s/^BACKUP_AGE_RECIPIENTS=.*/BACKUP_AGE_RECIPIENTS=$RECIPIENT/" "$P/proof.env"' in script
