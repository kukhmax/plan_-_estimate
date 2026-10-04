"""Stage 14D.4 — IMDS guard for Docker containers (O4 gate).

Static contract of ops/imds-guard/pe-imds-guard.sh and its systemd unit (always
run), plus opt-in proofs on real iptables in private network namespaces
(`TEST_REAL_NETNS=1`, root, iproute2 + iptables + unshare): rule-level
idempotency / tamper detection / rollback, and a packet-level matrix showing
that only the uploader bridge reaches IMDS while DNS keeps working.
Design: docs/STAGE_14D4_CONNECTIVITY_SEMANTICS_SMOKE.md §4.
"""

import configparser
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "ops" / "imds-guard" / "pe-imds-guard.sh"
UNIT = ROOT / "ops" / "imds-guard" / "plan-estimate-imds-guard.service"
NETNS_PROOF = Path(__file__).resolve().parent / "imds_guard_netns_proof.sh"

EXPECTED_RULES = [
    "-A PE-IMDS-GUARD -d 169.254.169.254/32 -i br-pe-upload -p tcp -m tcp --dport 80 -j RETURN",
    "-A PE-IMDS-GUARD -d 169.254.169.254/32 -p udp -m udp --dport 53 -j RETURN",
    "-A PE-IMDS-GUARD -d 169.254.169.254/32 -p tcp -m tcp --dport 53 -j RETURN",
    "-A PE-IMDS-GUARD -d 169.254.0.0/16 -i docker0 -p tcp -j REJECT --reject-with tcp-reset",
    "-A PE-IMDS-GUARD -d 169.254.0.0/16 -i docker0 -j REJECT --reject-with icmp-port-unreachable",
    "-A PE-IMDS-GUARD -d 169.254.0.0/16 -i br-+ -p tcp -j REJECT --reject-with tcp-reset",
    "-A PE-IMDS-GUARD -d 169.254.0.0/16 -i br-+ -j REJECT --reject-with icmp-port-unreachable",
]

real_netns = pytest.mark.skipif(os.environ.get("TEST_REAL_NETNS") != "1", reason="set TEST_REAL_NETNS=1 to run")


def code_lines() -> list[str]:
    """Script lines without comments (comments may name forbidden tools)."""
    return [ln for ln in GUARD.read_text().splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def run_guard(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(GUARD), *args], capture_output=True, text=True, env={**os.environ, **(env or {})}, check=False
    )


# -- static contract -----------------------------------------------------------


def test_guard_is_executable_bash_with_valid_syntax():
    assert GUARD.read_text().startswith("#!/usr/bin/env bash\n")
    assert os.access(GUARD, os.X_OK)
    subprocess.run(["bash", "-n", str(GUARD)], check=True)
    assert "set -euo pipefail" in code_lines()


def test_guard_rules_are_exactly_the_design_in_order():
    rendered = (
        GUARD.read_text()
        .replace("$CHAIN", "PE-IMDS-GUARD")
        .replace("$IMDS", "169.254.169.254/32")
        .replace("$LINK_LOCAL", "169.254.0.0/16")
        .replace("$UPLOAD_BRIDGE", "br-pe-upload")
    )
    block = rendered.split("expected_rules() {\n    cat <<EOF\n", 1)[1].split("\nEOF\n", 1)[0]
    assert block.splitlines() == EXPECTED_RULES


def test_guard_replaces_its_chain_atomically_and_jumps_first():
    code = "\n".join(code_lines())
    assert '"$IPTABLES_RESTORE" --noflush' in code
    assert 'echo ":$CHAIN - [0:0]"' in code
    assert '"$IPTABLES" -I "$PARENT" 1 -j "$CHAIN"' in code
    assert 'PARENT="DOCKER-USER"' in code


def test_guard_touches_nothing_but_its_own_chain():
    code = "\n".join(code_lines())
    for forbidden in (
        "netfilter-persistent",
        "rules.v4",
        "iptables-save",
        "ip6tables",
        "InstanceServices",
        "DOCKER-FORWARD",
        " -P ",
        "sysctl",
    ):
        assert forbidden not in code, forbidden
    flushes = [ln.strip() for ln in code_lines() if " -F " in ln or " -X " in ln]
    assert flushes == ['"$IPTABLES" -F "$CHAIN"', '"$IPTABLES" -X "$CHAIN"']


@pytest.mark.parametrize("bridge", ["br-+", "x" * 16, "br pe", "br;rm", "br/x"])
def test_guard_rejects_unsafe_uploader_bridge_before_touching_iptables(bridge):
    result = run_guard("status", env={"PE_UPLOAD_BRIDGE": bridge, "IPTABLES": "/nonexistent/iptables"})
    assert result.returncode == 1
    assert "PE_UPLOAD_BRIDGE" in result.stderr


def test_guard_usage_without_command():
    result = run_guard()
    assert result.returncode == 2
    assert "usage:" in result.stderr


def test_unit_runs_root_owned_guard_after_docker_without_stop_action():
    parser = configparser.ConfigParser(strict=True, interpolation=None)
    parser.optionxform = str  # type: ignore[assignment,method-assign]
    parser.read_string(UNIT.read_text())
    assert dict(parser["Unit"]) == {
        "Description": parser["Unit"]["Description"],
        "After": "docker.service",
        "Requires": "docker.service",
        "PartOf": "docker.service",
    }
    assert dict(parser["Service"]) == {
        "Type": "oneshot",
        "RemainAfterExit": "yes",
        "ExecStart": "/usr/local/sbin/pe-imds-guard.sh apply",
    }
    assert dict(parser["Install"]) == {"WantedBy": "docker.service"}


# -- opt-in proofs on real iptables (private network namespaces) ----------------


def _require_tools() -> None:
    if os.geteuid() != 0:
        pytest.fail("TEST_REAL_NETNS=1 needs root")
    for tool in ("ip", "iptables", "iptables-restore", "unshare", "python3"):
        if shutil.which(tool) is None:
            pytest.fail(f"TEST_REAL_NETNS=1 but {tool} is not on PATH")


def _in_netns(script: str) -> str:
    result = subprocess.run(
        ["unshare", "-n", "bash", "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ, "GUARD": str(GUARD)},
        check=False,
        timeout=60,
    )
    return result.stdout + result.stderr


@real_netns
def test_real_iptables_apply_is_idempotent_detects_tampering_and_removes_cleanly():
    _require_tools()
    out = _in_netns(
        """
        iptables -N DOCKER-USER; iptables -A FORWARD -j DOCKER-USER; iptables -A DOCKER-USER -j RETURN
        "$GUARD" status; echo "rc=$? (status before apply)"
        "$GUARD" apply >/dev/null; "$GUARD" apply >/dev/null; echo "rc=$? (second apply)"
        echo "--- DOCKER-USER"; iptables -S DOCKER-USER
        echo "--- CHAIN"; iptables -S PE-IMDS-GUARD
        iptables -A DOCKER-USER -j PE-IMDS-GUARD; "$GUARD" status >/dev/null; echo "rc=$? (duplicate jump)"
        "$GUARD" apply >/dev/null; iptables -A PE-IMDS-GUARD -j ACCEPT; "$GUARD" status >/dev/null; echo "rc=$? (extra rule)"
        "$GUARD" apply >/dev/null; "$GUARD" status >/dev/null; echo "rc=$? (reapplied)"
        "$GUARD" remove >/dev/null; echo "--- after remove"; iptables -S DOCKER-USER
        iptables -S PE-IMDS-GUARD >/dev/null 2>&1; echo "rc=$? (chain gone)"
        "$GUARD" remove >/dev/null; echo "rc=$? (remove again)"
        """
    )
    assert "rc=1 (status before apply)" in out
    assert "rc=0 (second apply)" in out
    docker_user = out.split("--- DOCKER-USER\n", 1)[1].split("--- CHAIN\n", 1)[0].splitlines()
    assert docker_user == ["-N DOCKER-USER", "-A DOCKER-USER -j PE-IMDS-GUARD", "-A DOCKER-USER -j RETURN"]
    chain = out.split("--- CHAIN\n", 1)[1].split("rc=", 1)[0].splitlines()
    assert chain == ["-N PE-IMDS-GUARD", *EXPECTED_RULES]
    assert "rc=1 (duplicate jump)" in out
    assert "rc=1 (extra rule)" in out
    assert "rc=0 (reapplied)" in out
    after = out.split("--- after remove\n", 1)[1].split("rc=", 1)[0].splitlines()
    assert after == ["-N DOCKER-USER", "-A DOCKER-USER -j RETURN"]
    assert "rc=1 (chain gone)" in out
    assert "rc=0 (remove again)" in out


@real_netns
def test_real_packets_only_uploader_reaches_imds_and_dns_keeps_working():
    _require_tools()
    result = subprocess.run(
        ["bash", str(NETNS_PROOF), str(GUARD)], capture_output=True, text=True, check=False, timeout=180
    )
    assert result.returncode == 0, result.stderr
    observed = {tuple(line.split()[:4]): line.split()[4] for line in result.stdout.splitlines()}
    open_everywhere = {key[1:]: "ok" for key in observed if key[0] == "before"}
    assert len(open_everywhere) == 10
    for phase in ("before", "removed"):
        assert {k[1:]: v for k, v in observed.items() if k[0] == phase} == open_everywhere
    guarded = {
        ("uploader", "tcp", "169.254.169.254:80"): "ok",
        ("uploader", "udp", "169.254.169.254:53"): "ok",
        ("uploader", "tcp", "169.254.169.254:3260"): "rejected",
        ("uploader", "tcp", "169.254.0.2:80"): "rejected",
        ("other", "tcp", "169.254.169.254:80"): "rejected",
        ("other", "udp", "169.254.169.254:53"): "ok",
        ("other", "tcp", "169.254.169.254:53"): "ok",
        ("other", "tcp", "169.254.0.2:80"): "rejected",
        ("default", "tcp", "169.254.169.254:80"): "rejected",
        ("default", "udp", "169.254.169.254:53"): "ok",
    }
    for phase in ("applied", "reapplied"):
        assert {k[1:]: v for k, v in observed.items() if k[0] == phase} == guarded
