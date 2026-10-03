"""Stage 14D.2D.5 — proof operations inside the real `backup` service container.

Invoked as `docker compose ... run --rm --no-deps --entrypoint python backup -m tests.runtime_proof.bind_ops <cmd>`;
only the entrypoint changes, so the service's user, read-only root, tmpfs, cap_drop, no-new-privileges,
limits, mounts and network are exactly the production definition. Every command prints one JSON line
and exits 0 on PASS, 1 on FAIL (3 = lock held for `try-lock`).

    self-inspect [--hold SECONDS]  effective identity, capabilities, mounts, write probes, no Docker socket
    egress-check                   the backup network has no route to the internet
    promote-proof                  production BackupDataRoot.create_run / promote on the real bind:
                                   same st_dev, atomic appearance, collision refused (renameat2 NOREPLACE),
                                   no overwrite; removes only its own synthetic runs afterwards
    hold-lock [--seconds N]        production RunLock held until SIGTERM / timeout
    try-lock                       production RunLock acquisition attempt

No secret is read or printed: the pgpass mount is only stat-ed and write-probed, never opened for reading.
"""

import argparse
import errno
import json
import os
import shutil
import signal
import socket
import stat
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.backup import workspace as ws
from app.backup.run_id import new_run_id

DATA_ROOT = Path("/backup")
PASSFILE = Path("/run/secrets/pgpass")
SOCKET_PATHS = ("/var/run/docker.sock", "/run/docker.sock", "/run/containerd/containerd.sock", "/run/podman/podman.sock")
CAP_FIELDS = ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True), flush=True)


# --- self-inspection --------------------------------------------------------------------------


def parse_status(text: str) -> dict[str, str]:
    fields = {}
    for line in text.splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def parse_mountinfo(text: str) -> dict[str, dict[str, Any]]:
    """mount point -> {fstype, options (per-mount + super options)} from /proc/self/mountinfo."""
    mounts: dict[str, dict[str, Any]] = {}
    for line in text.splitlines():
        left, _, right = line.partition(" - ")
        parts, tail = left.split(), right.split()
        if len(parts) < 6 or len(tail) < 3:
            continue
        mount_point = parts[4].replace("\\040", " ")
        options = set(parts[5].split(",")) | set(tail[2].split(","))
        mounts[mount_point] = {"fstype": tail[0], "options": sorted(options), "dev": parts[2]}
    return mounts


def write_probe(path: Path) -> str:
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as exc:
        return errno.errorcode.get(exc.errno or 0, "error")
    os.close(fd)
    os.unlink(path)
    return "writable"


def self_inspect(data_root: Path = DATA_ROOT, passfile: Path = PASSFILE, *, status_text: str | None = None,
                 mountinfo_text: str | None = None) -> dict[str, Any]:
    status = parse_status(status_text if status_text is not None else Path("/proc/self/status").read_text())
    mounts = parse_mountinfo(mountinfo_text if mountinfo_text is not None else Path("/proc/self/mountinfo").read_text())
    uid = status.get("Uid", "").split()
    gid = status.get("Gid", "").split()
    caps = {name: status.get(name, "") for name in CAP_FIELDS}
    try:
        passfile_mode = oct(stat.S_IMODE(os.stat(passfile).st_mode))
        passfile_write = "EROFS/EACCES expected"
        try:
            fd = os.open(passfile, os.O_WRONLY | os.O_APPEND)
        except OSError as exc:
            passfile_write = errno.errorcode.get(exc.errno or 0, "error")
        else:
            os.close(fd)
            passfile_write = "WRITABLE"
    except OSError:
        passfile_mode, passfile_write = "missing", "missing"
    result: dict[str, Any] = {
        "uid": uid[:2], "gid": gid[:2],
        "non_root": bool(uid) and uid[0] != "0" and uid[1] != "0",
        "capabilities": caps,
        "no_capabilities": all(set(v) <= {"0"} for v in caps.values() if v),
        "no_new_privs": status.get("NoNewPrivs") == "1",
        "root_mount": mounts.get("/", {}),
        "root_read_only": "ro" in mounts.get("/", {}).get("options", []),
        "root_write_probe": write_probe(Path("/pe-proof-root-probe")),
        "tmp_mount": mounts.get("/tmp", {}),
        "tmp_is_tmpfs": mounts.get("/tmp", {}).get("fstype") == "tmpfs",
        "tmp_write_probe": write_probe(Path("/tmp/pe-proof-tmp-probe")),
        "backup_mount": mounts.get(str(data_root), {}),
        "backup_is_separate_rw_mount": str(data_root) in mounts and "rw" in mounts[str(data_root)]["options"],
        "backup_write_probe": write_probe(data_root / ".pe-proof-backup-probe"),
        "no_subdirectory_mounts_under_backup": not any(
            m.startswith(str(data_root) + "/") for m in mounts
        ),
        "passfile_mount": mounts.get(str(passfile), {}),
        "passfile_read_only_mount": "ro" in mounts.get(str(passfile), {}).get("options", []),
        "passfile_outside_backup": not str(passfile).startswith(str(data_root) + "/"),
        "passfile_mode": passfile_mode,
        "passfile_write_attempt": passfile_write,
        "docker_sockets_present": [p for p in SOCKET_PATHS if os.path.exists(p)],
    }
    result["pass"] = all((
        result["non_root"], result["no_capabilities"], result["no_new_privs"], result["root_read_only"],
        result["root_write_probe"] in ("EROFS", "EACCES"), result["tmp_is_tmpfs"],
        result["tmp_write_probe"] == "writable", result["backup_is_separate_rw_mount"],
        result["backup_write_probe"] == "writable", result["no_subdirectory_mounts_under_backup"],
        result["passfile_read_only_mount"], result["passfile_outside_backup"],
        result["passfile_write_attempt"] in ("EROFS", "EACCES"), not result["docker_sockets_present"],
    ))
    return result


def egress_check(timeout: float = 3.0) -> dict[str, Any]:
    """Expect NO internet route on the proof network (internal bridge)."""
    outcomes = {}
    for host, port in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                outcomes[f"{host}:{port}"] = "CONNECTED"
        except OSError as exc:
            outcomes[f"{host}:{port}"] = type(exc).__name__
    try:
        socket.getaddrinfo("example.com", 443)
        outcomes["dns:example.com"] = "RESOLVED"
    except OSError as exc:
        outcomes["dns:example.com"] = type(exc).__name__
    return {"outcomes": outcomes, "pass": not any(v in ("CONNECTED", "RESOLVED") for v in outcomes.values())}


# --- promotion on the real bind ------------------------------------------------------------------


def promote_proof(data_root: Path = DATA_ROOT) -> dict[str, Any]:
    root = ws.BackupDataRoot(data_root)
    root.prepare(create_missing=False)
    root.assert_no_stale_work()
    work, encrypted = data_root / ws.WORK_DIR, data_root / ws.ENCRYPTED_DIR
    before = sorted(p.name for p in encrypted.iterdir())
    synthetic: list[str] = []
    result: dict[str, Any] = {"same_st_dev": os.stat(work).st_dev == os.stat(encrypted).st_dev == os.stat(data_root).st_dev}
    try:
        run_id = new_run_id()
        while run_id in before:
            time.sleep(1)
            run_id = new_run_id()
        synthetic.append(run_id)
        workspace = root.create_run(run_id)
        marker = workspace.directory / "pe-proof-marker.txt"
        marker.write_bytes(b"first")
        destination = root.promote(run_id)
        result["promoted"] = destination == encrypted / run_id
        result["source_gone"] = not (work / run_id).exists()
        result["destination_content"] = (destination / "pe-proof-marker.txt").read_bytes().decode()

        # collision: same run id again in work/ -> promotion must refuse, destination unchanged
        again = root.create_run(run_id)
        (again.directory / "pe-proof-marker.txt").write_bytes(b"second")
        try:
            root.promote(run_id)
            result["collision"] = "OVERWRITTEN"
        except ws.PromotionError:
            result["collision"] = "refused"
        result["destination_unchanged"] = (destination / "pe-proof-marker.txt").read_bytes() == b"first"
        result["second_source_kept"] = (work / run_id / "pe-proof-marker.txt").read_bytes() == b"second"

        # renameat2(RENAME_NOREPLACE) itself on this filesystem: an EMPTY destination must also be refused
        probe = new_run_id()
        while probe in before or probe == run_id:
            time.sleep(1)
            probe = new_run_id()
        synthetic.append(probe)
        (work / probe).mkdir(mode=0o700)
        (encrypted / probe).mkdir(mode=0o700)
        fd_w = os.open(work, os.O_RDONLY | os.O_DIRECTORY)
        fd_e = os.open(encrypted, os.O_RDONLY | os.O_DIRECTORY)
        try:
            ws._rename_noreplace(fd_w, probe, fd_e)
            result["noreplace_empty_destination"] = "REPLACED"
        except FileExistsError:
            result["noreplace_empty_destination"] = "refused (EEXIST)"
        except OSError as exc:
            result["noreplace_empty_destination"] = f"unsupported ({errno.errorcode.get(exc.errno or 0, 'error')})"
        finally:
            os.close(fd_w)
            os.close(fd_e)
    finally:
        # proof tooling removes ONLY the synthetic runs it created (the application never deletes work)
        for name in synthetic:
            for parent in (work, encrypted):
                target = parent / name
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
    result["encrypted_unchanged_after_cleanup"] = sorted(p.name for p in encrypted.iterdir()) == before
    result["work_empty_after_cleanup"] = list(work.iterdir()) == []
    result["pass"] = all((
        result["same_st_dev"], result.get("promoted"), result.get("source_gone"),
        result.get("destination_content") == "first", result.get("collision") == "refused",
        result.get("destination_unchanged"), result.get("second_source_kept"),
        result.get("noreplace_empty_destination") == "refused (EEXIST)",
        result["encrypted_unchanged_after_cleanup"], result["work_empty_after_cleanup"],
    ))
    return result


# --- lock ---------------------------------------------------------------------------------------


def hold_lock(data_root: Path, seconds: float) -> int:
    lock = ws.BackupDataRoot(data_root).acquire_lock()
    stop: dict[str, int | None] = {"signal": None}

    def on_signal(signum: int, frame: object) -> None:
        stop["signal"] = signum

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    emit({"state": "LOCKED", "pid": os.getpid()})
    deadline = time.monotonic() + seconds
    while stop["signal"] is None and time.monotonic() < deadline:
        time.sleep(0.2)
    lock.release()
    emit({"state": "RELEASED", "reason": "signal" if stop["signal"] else "timeout"})
    return 0


def try_lock(data_root: Path) -> int:
    try:
        with ws.BackupDataRoot(data_root).acquire_lock():
            emit({"state": "ACQUIRED", "lock_file_mode": oct(stat.S_IMODE(os.stat(data_root / ws.LOCK_FILE).st_mode))})
            return 0
    except ws.LockHeldError:
        emit({"state": "LOCK_HELD"})
        return 3


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.runtime_proof.bind_ops")
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("self-inspect")
    inspect.add_argument("--hold", type=float, default=0.0)
    commands.add_parser("egress-check")
    commands.add_parser("promote-proof")
    hold = commands.add_parser("hold-lock")
    hold.add_argument("--seconds", type=float, default=300.0)
    commands.add_parser("try-lock")
    args = parser.parse_args(argv)

    if args.command == "self-inspect":
        result = self_inspect(args.data_root)
        emit({"check": "self-inspect", **result})
        if args.hold > 0:
            stop = {"done": False}
            signal.signal(signal.SIGTERM, lambda *_: stop.update(done=True))
            deadline = time.monotonic() + args.hold
            while not stop["done"] and time.monotonic() < deadline:
                time.sleep(0.2)
        return 0 if result["pass"] else 1
    if args.command == "egress-check":
        result = egress_check()
        emit({"check": "egress", **result})
        return 0 if result["pass"] else 1
    if args.command == "promote-proof":
        result = promote_proof(args.data_root)
        emit({"check": "promote-proof", **result})
        return 0 if result["pass"] else 1
    if args.command == "hold-lock":
        return hold_lock(args.data_root, args.seconds)
    return try_lock(args.data_root)


if __name__ == "__main__":
    sys.exit(main())
