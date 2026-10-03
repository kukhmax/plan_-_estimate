"""Stage 14D.2D.5 — HOST-side checks (Python standard library only; no app imports, no Docker calls).

    python3 backend/tests/runtime_proof/check_host.py run DATA_DIR [--run-id ID] [--expect-runs N]
        bind persistence after `run --rm`: work/ and evidence/ empty, encrypted/<run_id>/ holds exactly
        the artifact + local-run.json, no plaintext, evidence complete, artifact SHA-256 / size match,
        run.lock present (0600); prints the run id and artifact SHA-256 for a later stability check
    docker inspect <backup container> | python3 .../check_host.py container
        effective HostConfig / Config: non-root user, read-only root, cap_drop ALL, no-new-privileges,
        not privileged, no published ports, single /backup bind + read-only pgpass outside it,
        /tmp tmpfs, limits, stop timeout 45 s, attached only to the proof network
    docker inspect <scratch postgres> | python3 .../check_host.py postgres
    docker network inspect <proof network> | python3 .../check_host.py network
    python3 .../check_host.py stale DATA_DIR NAME   the synthetic stale entry is untouched; nothing promoted

Every command prints one JSON object and exits 0 on PASS, 1 on FAIL.
"""

import argparse
import hashlib
import json
import stat
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

PROJECT = "plan-estimate-14d2d5-proof"
NETWORK = f"{PROJECT}_internal"
ARTIFACT = "plan-estimate.sql.gz.age"
EVIDENCE = "local-run.json"
PLAINTEXT = "plan-estimate.sql"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_run(data_dir: Path, run_id: str | None, expect_runs: int | None) -> dict[str, Any]:
    work, encrypted, evidence_dir = data_dir / "work", data_dir / "encrypted", data_dir / "evidence"
    runs = sorted(p.name for p in encrypted.iterdir())
    chosen = run_id or (runs[-1] if runs else "")
    run_dir = encrypted / chosen
    checks: dict[str, Any] = {
        "work_empty": list(work.iterdir()) == [],
        "evidence_dir_empty": list(evidence_dir.iterdir()) == [],
        "run_present": bool(chosen) and run_dir.is_dir(),
    }
    if expect_runs is not None:
        checks["completed_runs"] = len(runs) == expect_runs
    artifact_sha = None
    if checks["run_present"]:
        names = sorted(p.name for p in run_dir.iterdir())
        evidence = json.loads((run_dir / EVIDENCE).read_bytes())
        artifact = run_dir / ARTIFACT
        artifact_sha = sha256_file(artifact)
        checks.update({
            "exact_files": names == [EVIDENCE, ARTIFACT],
            "no_plaintext": not (run_dir / PLAINTEXT).exists() and not (work / chosen / PLAINTEXT).exists(),
            "evidence_complete": evidence.get("status") == "complete" and evidence.get("run_id") == chosen,
            "revision_is_head": evidence["database"]["alembic_revision"] == evidence["database"]["expected_alembic_head"],
            "artifact_sha256_matches": artifact_sha == evidence["artifact"]["sha256"],
            "artifact_size_matches": artifact.stat().st_size == evidence["artifact"]["size"],
            "artifact_mode_0600": stat.S_IMODE(artifact.stat().st_mode) == 0o600,
            "evidence_mode_0600": stat.S_IMODE((run_dir / EVIDENCE).stat().st_mode) == 0o600,
            "run_dir_mode_0700": stat.S_IMODE(run_dir.stat().st_mode) == 0o700,
        })
    lock = data_dir / "run.lock"
    checks["run_lock_persists_0600"] = lock.is_file() and stat.S_IMODE(lock.stat().st_mode) == 0o600
    return {"run_id": chosen, "artifact_sha256": artifact_sha, "checks": checks, "pass": all(checks.values())}


def _mounts(info: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {m["Destination"]: m for m in info.get("Mounts", [])}


def check_container(info: dict[str, Any]) -> dict[str, Any]:
    host, config = info["HostConfig"], info["Config"]
    mounts = _mounts(info)
    tmpfs = host.get("Tmpfs") or {}
    tmpfs_mounts = [m for m in host.get("Mounts") or [] if m.get("Type") == "tmpfs"]
    user = config.get("User", "")
    uid, _, gid = user.partition(":")
    networks = sorted((info.get("NetworkSettings") or {}).get("Networks", {}))
    checks = {
        "compose_project_is_proof": config.get("Labels", {}).get("com.docker.compose.project") == PROJECT,
        "non_root_user": bool(uid) and uid not in ("0", "root") and bool(gid) and gid != "0",
        "read_only_rootfs": host.get("ReadonlyRootfs") is True,
        "cap_drop_all": [c.upper() for c in host.get("CapDrop") or []] in (["ALL"], ["CAP_ALL"]),
        "no_cap_add": not host.get("CapAdd"),
        "no_new_privileges": any(o.replace("=", ":") == "no-new-privileges:true" for o in host.get("SecurityOpt") or []),
        "not_privileged": host.get("Privileged") is False,
        "no_published_ports": not any(host.get("PortBindings") or {}) and not host.get("PublishAllPorts"),
        "backup_single_rw_bind": "/backup" in mounts and mounts["/backup"]["Type"] == "bind" and mounts["/backup"]["RW"],
        "no_subdirectory_binds": not any(d.startswith("/backup/") for d in mounts),
        "pgpass_read_only_bind": "/run/secrets/pgpass" in mounts and not mounts["/run/secrets/pgpass"]["RW"],
        "pgpass_outside_backup_on_host": "/backup" in mounts and "/run/secrets/pgpass" in mounts
        and not mounts["/run/secrets/pgpass"]["Source"].startswith(mounts["/backup"]["Source"].rstrip("/") + "/"),
        "tmp_is_tmpfs": "/tmp" in tmpfs or any(m.get("Target") == "/tmp" for m in tmpfs_mounts),
        "no_docker_socket": not any("docker.sock" in (m.get("Source") or "") for m in info.get("Mounts", [])),
        "memory_limited": (host.get("Memory") or 0) == 512 * 1024 * 1024,
        "cpu_limited": (host.get("NanoCpus") or 0) == 500_000_000,
        "pids_limited": host.get("PidsLimit") == 64,
        "stop_timeout_45": config.get("StopTimeout") == 45,
        "init": host.get("Init") is True,
        "only_proof_network": networks == [NETWORK],
        "network_mode_proof": host.get("NetworkMode") in (NETWORK, *networks),
    }
    return {"user": user, "networks": networks, "checks": checks, "pass": all(checks.values())}


def check_postgres(info: dict[str, Any]) -> dict[str, Any]:
    host = info["HostConfig"]
    networks = sorted((info.get("NetworkSettings") or {}).get("Networks", {}))
    exposed = (info.get("NetworkSettings") or {}).get("Ports") or {}
    checks = {
        # an exposed but unpublished port appears as {"5432/tcp": null}
        "no_published_ports": not any(host.get("PortBindings") or {}) and not host.get("PublishAllPorts")
        and all(not bindings for bindings in exposed.values()),
        "only_proof_network": networks == [NETWORK],
        "image_postgres_16": str(info["Config"].get("Image", "")).startswith("postgres:16"),
    }
    return {"networks": networks, "checks": checks, "pass": all(checks.values())}


def check_network(info: dict[str, Any]) -> dict[str, Any]:
    containers = sorted(c.get("Name", "") for c in (info.get("Containers") or {}).values())
    labels = info.get("Labels") or {}
    checks = {
        "name": info.get("Name") == NETWORK,
        "internal_no_egress": info.get("Internal") is True,
        "compose_labels": labels.get("com.docker.compose.project") == PROJECT
        and labels.get("com.docker.compose.network") == "internal",
        "only_proof_containers": all("proof" in name for name in containers),
    }
    return {"containers": containers, "checks": checks, "pass": all(checks.values())}


def check_stale(data_dir: Path, name: str, expected_sha: str, runs_before: int) -> dict[str, Any]:
    entry = data_dir / "work" / name
    checks = {
        "stale_entry_untouched": entry.is_file() and sha256_file(entry) == expected_sha,
        "only_the_stale_entry_in_work": sorted(p.name for p in (data_dir / "work").iterdir()) == [name],
        "nothing_promoted": len(list((data_dir / "encrypted").iterdir())) == runs_before,
        "no_failure_evidence": list((data_dir / "evidence").iterdir()) == [],
    }
    return {"checks": checks, "pass": all(checks.values())}


def _single(stdin_text: str) -> dict[str, Any]:
    data = json.loads(stdin_text)
    return data[0] if isinstance(data, list) else data


def main(argv: Sequence[str] | None = None, stdin_text: str | None = None) -> int:
    parser = argparse.ArgumentParser(prog="check_host.py")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("data_dir", type=Path)
    run.add_argument("--run-id")
    run.add_argument("--expect-runs", type=int)
    for name in ("container", "postgres", "network"):
        commands.add_parser(name)
    stale = commands.add_parser("stale")
    stale.add_argument("data_dir", type=Path)
    stale.add_argument("name")
    stale.add_argument("--sha256", required=True)
    stale.add_argument("--runs-before", type=int, required=True)
    args = parser.parse_args(argv)
    if args.command == "run":
        result = check_run(args.data_dir, args.run_id, args.expect_runs)
    elif args.command == "stale":
        result = check_stale(args.data_dir, args.name, args.sha256, args.runs_before)
    else:
        info = _single(stdin_text if stdin_text is not None else sys.stdin.read())
        result = {"container": check_container, "postgres": check_postgres, "network": check_network}[args.command](info)
    print(json.dumps({"check": args.command, **result}, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
