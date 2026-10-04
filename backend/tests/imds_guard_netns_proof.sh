#!/usr/bin/env bash
# Packet-level proof of ops/imds-guard/pe-imds-guard.sh (Stage 14D.4).
# Needs root, iproute2, iptables, python3. Run only through
# tests/test_stage14d4_imds_guard.py (TEST_REAL_NETNS=1).
#
# Topology, all in private network namespaces (the real host is untouched):
#   <p>h   "host": FORWARD -> DOCKER-USER, ip_forward=1
#   <p>u   "uploader container", host side veth named br-pe-upload
#   <p>b   "other container",    host side veth named br-other1  (matches br-+)
#   <p>d   "default bridge",     host side veth named docker0
#   <p>m   "IMDS": 169.254.169.254 and 169.254.0.2 serving tcp 80/53/3260, udp 53
# Output: one line per probe, "<phase> <client> <proto> <ip>:<port> <result>".

set -euo pipefail

GUARD="$1"
P="pe$$"
H="${P}h" U="${P}u" B="${P}b" D="${P}d" M="${P}m"
SRV=""

cleanup() {
    [ -n "$SRV" ] && kill "$SRV" 2>/dev/null || true
    for n in "$H" "$U" "$B" "$D" "$M"; do ip netns del "$n" 2>/dev/null || true; done
}
trap cleanup EXIT

for n in "$H" "$U" "$B" "$D" "$M"; do
    ip netns add "$n"
    ip -n "$n" link set lo up
done

client() {  # client <ns> <host-side ifname> <subnet-octet>
    ip link add "$2" netns "$H" type veth peer name eth0 netns "$1"
    ip -n "$H" addr add "10.10.$3.1/24" dev "$2"
    ip -n "$H" link set "$2" up
    ip -n "$1" addr add "10.10.$3.2/24" dev eth0
    ip -n "$1" link set eth0 up
    ip -n "$1" route add default via "10.10.$3.1"
}
client "$U" br-pe-upload 1
client "$B" br-other1 2
client "$D" docker0 3

ip link add imds0 netns "$H" type veth peer name eth0 netns "$M"
ip -n "$H" addr add 169.254.0.1/16 dev imds0
ip -n "$H" link set imds0 up
ip -n "$M" addr add 169.254.169.254/16 dev eth0
ip -n "$M" addr add 169.254.0.2/16 dev eth0
ip -n "$M" link set eth0 up
ip -n "$M" route add default via 169.254.0.1

ip netns exec "$H" sysctl -qw net.ipv4.ip_forward=1
ip netns exec "$H" iptables -N DOCKER-USER
ip netns exec "$H" iptables -A FORWARD -j DOCKER-USER

ip netns exec "$M" python3 -c '
import socket, threading
def tcp(port):
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", port)); s.listen()
    while True:
        c, _ = s.accept(); c.sendall(b"ok"); c.close()
def udp(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(("0.0.0.0", port))
    while True:
        _, a = s.recvfrom(100); s.sendto(b"ok", a)
for p in (80, 53, 3260):
    threading.Thread(target=tcp, args=(p,), daemon=True).start()
threading.Thread(target=udp, args=(53,), daemon=True).start()
threading.Event().wait()
' &
SRV=$!
sleep 0.5

probe() {  # probe <ns> <proto> <ip> <port>
    ip netns exec "$1" python3 -c '
import socket, sys
proto, ip, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
try:
    if proto == "tcp":
        s = socket.create_connection((ip, port), timeout=2)
        print("ok" if s.recv(10) == b"ok" else "bad")
    else:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(2)
        s.sendto(b"q", (ip, port)); print("ok" if s.recv(10) == b"ok" else "bad")
except ConnectionRefusedError:
    print("rejected")
except OSError as exc:
    print(type(exc).__name__)
' "$2" "$3" "$4"
}

matrix() {
    local phase="$1" name ns proto ip port
    while read -r name ns proto ip port; do
        echo "$phase $name $proto $ip:$port $(probe "$ns" "$proto" "$ip" "$port")"
    done <<EOF
uploader $U tcp 169.254.169.254 80
uploader $U udp 169.254.169.254 53
uploader $U tcp 169.254.169.254 3260
uploader $U tcp 169.254.0.2 80
other $B tcp 169.254.169.254 80
other $B udp 169.254.169.254 53
other $B tcp 169.254.169.254 53
other $B tcp 169.254.0.2 80
default $D tcp 169.254.169.254 80
default $D udp 169.254.169.254 53
EOF
}

matrix before
ip netns exec "$H" "$GUARD" apply >/dev/null
matrix applied
ip netns exec "$H" "$GUARD" apply >/dev/null
matrix reapplied
ip netns exec "$H" "$GUARD" remove >/dev/null
matrix removed
