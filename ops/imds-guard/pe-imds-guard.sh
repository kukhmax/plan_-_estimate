#!/usr/bin/env bash
# Plan & Estimate — IMDS guard for Docker containers (Stage 14D.4, O4 gate).
# Design: docs/STAGE_14D4_CONNECTIVITY_SEMANTICS_SMOKE.md §4.
#
# On an OCI VM every container whose traffic is forwarded by the host can reach
# the instance metadata service (IMDS, 169.254.169.254) and therefore obtain the
# instance principal of the VM. Oracle's own InstanceServices rules sit on the
# OUTPUT chain and do not cover forwarded (container) traffic.
#
# This script owns exactly one chain, PE-IMDS-GUARD, jumped to from the first
# position of Docker's DOCKER-USER chain:
#   1. the backup uploader bridge may reach IMDS over HTTP (tcp/80);
#   2. every container may reach the VCN DNS resolver (169.254.169.254:53);
#   3. every other packet from a Docker bridge to 169.254.0.0/16 is rejected.
#
# It never touches Docker's or Oracle's chains, never changes a policy, never
# runs `netfilter-persistent save` and never writes /etc/iptables/rules.v4.
# Persistence across reboots / Docker restarts is the systemd unit
# plan-estimate-imds-guard.service, which runs `apply` after docker.service.
#
# Usage: pe-imds-guard.sh apply|remove|status
#   apply   create or atomically replace PE-IMDS-GUARD, ensure one jump at DOCKER-USER #1
#   remove  delete every jump and the chain (rollback to the pre-guard state)
#   status  exit 0 only if the chain and the jump are exactly as designed
#
# Environment (defaults are the production values):
#   PE_UPLOAD_BRIDGE  uploader bridge interface name (default br-pe-upload)
#   IPTABLES          iptables binary (default iptables)
#   IPTABLES_RESTORE  iptables-restore binary (default iptables-restore)

set -euo pipefail

CHAIN="PE-IMDS-GUARD"
PARENT="DOCKER-USER"
IMDS="169.254.169.254/32"
LINK_LOCAL="169.254.0.0/16"
UPLOAD_BRIDGE="${PE_UPLOAD_BRIDGE:-br-pe-upload}"
IPTABLES="${IPTABLES:-iptables}"
IPTABLES_RESTORE="${IPTABLES_RESTORE:-iptables-restore}"

die() {
    echo "pe-imds-guard: $*" >&2
    exit 1
}

# Interface names: at most 15 characters, no wildcard, no whitespace.
case "$UPLOAD_BRIDGE" in
    "" | *[!A-Za-z0-9_.-]*) die "invalid PE_UPLOAD_BRIDGE '$UPLOAD_BRIDGE'" ;;
esac
[ "${#UPLOAD_BRIDGE}" -le 15 ] || die "PE_UPLOAD_BRIDGE '$UPLOAD_BRIDGE' is longer than 15 characters"

# The guard rules in the canonical order printed by `iptables -S`.
expected_rules() {
    cat <<EOF
-A $CHAIN -d $IMDS -i $UPLOAD_BRIDGE -p tcp -m tcp --dport 80 -j RETURN
-A $CHAIN -d $IMDS -p udp -m udp --dport 53 -j RETURN
-A $CHAIN -d $IMDS -p tcp -m tcp --dport 53 -j RETURN
-A $CHAIN -d $LINK_LOCAL -i docker0 -p tcp -j REJECT --reject-with tcp-reset
-A $CHAIN -d $LINK_LOCAL -i docker0 -j REJECT --reject-with icmp-port-unreachable
-A $CHAIN -d $LINK_LOCAL -i br-+ -p tcp -j REJECT --reject-with tcp-reset
-A $CHAIN -d $LINK_LOCAL -i br-+ -j REJECT --reject-with icmp-port-unreachable
EOF
}

require_parent() {
    "$IPTABLES" -S "$PARENT" >/dev/null 2>&1 \
        || die "chain $PARENT does not exist (is Docker running with the iptables firewall backend?)"
}

chain_exists() {
    "$IPTABLES" -S "$CHAIN" >/dev/null 2>&1
}

jump_count() {
    # Exact-line match on the canonical form; prints a number, never fails.
    "$IPTABLES" -S "$PARENT" | grep -cxF -- "-A $PARENT -j $CHAIN" || true
}

remove_jumps() {
    while "$IPTABLES" -C "$PARENT" -j "$CHAIN" >/dev/null 2>&1; do
        "$IPTABLES" -D "$PARENT" -j "$CHAIN"
    done
}

cmd_apply() {
    require_parent
    # One iptables-restore transaction: declaring the chain creates or flushes
    # it, so the rules are replaced atomically; --noflush leaves every other
    # chain of the filter table untouched.
    {
        echo "*filter"
        echo ":$CHAIN - [0:0]"
        expected_rules
        echo "COMMIT"
    } | "$IPTABLES_RESTORE" --noflush
    remove_jumps
    "$IPTABLES" -I "$PARENT" 1 -j "$CHAIN"
    cmd_status
}

cmd_remove() {
    if "$IPTABLES" -S "$PARENT" >/dev/null 2>&1; then
        remove_jumps
    fi
    if chain_exists; then
        "$IPTABLES" -F "$CHAIN"
        "$IPTABLES" -X "$CHAIN"
    fi
    echo "pe-imds-guard: removed (no $CHAIN chain, no jump from $PARENT)"
}

cmd_status() {
    require_parent
    local ok=1 actual first
    if ! chain_exists; then
        echo "pe-imds-guard: FAIL chain $CHAIN is missing"
        return 1
    fi
    actual="$("$IPTABLES" -S "$CHAIN" | grep -v -- "^-N $CHAIN\$" || true)"
    if [ "$actual" != "$(expected_rules)" ]; then
        echo "pe-imds-guard: FAIL rules of $CHAIN differ from the design"
        echo "--- expected"
        expected_rules
        echo "--- actual"
        echo "$actual"
        ok=0
    fi
    if [ "$(jump_count)" != "1" ]; then
        echo "pe-imds-guard: FAIL expected exactly one jump $PARENT -> $CHAIN, found $(jump_count)"
        ok=0
    fi
    first="$("$IPTABLES" -S "$PARENT" | grep -m1 -- "^-A $PARENT " || true)"
    if [ "$first" != "-A $PARENT -j $CHAIN" ]; then
        echo "pe-imds-guard: FAIL the jump to $CHAIN is not the first rule of $PARENT"
        ok=0
    fi
    if [ "$ok" -ne 1 ]; then
        return 1
    fi
    echo "pe-imds-guard: OK ($CHAIN at $PARENT #1; uploader bridge $UPLOAD_BRIDGE)"
}

case "${1:-}" in
    apply) cmd_apply ;;
    remove) cmd_remove ;;
    status) cmd_status ;;
    *)
        echo "usage: $0 apply|remove|status" >&2
        exit 2
        ;;
esac
