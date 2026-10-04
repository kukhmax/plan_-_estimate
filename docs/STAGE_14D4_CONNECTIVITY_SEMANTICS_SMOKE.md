# Stage 14D.4 — Connectivity / semantics smoke on drill resources and the IMDS gate (O4)

> **Status:** 14D.4.1 reconnaissance DONE (owner, 2026-10-04, read-only). 14D.4.2 tooling **IMPLEMENTED — automated
> verification PASS, OWNER ACCEPTED 2026-10-04** (this document, §9). 14D.4.3–14D.4.7 NOT STARTED; every production
> step requires explicit owner approval. Production unchanged; `PHOTO_UPLOADS_ENABLED=false`.
>
> Builds on `docs/STAGE_14D3_ORACLE_BACKUP_PROVISIONING.md` (§6.2 policy statements and security invariants, §8
> uploader boundary and the O4 gate, §11 destructive-action matrix) and `docs/STAGE_14D_BACKUP_RESTORE_PLAN.md` (§13
> credentials, §18 sub-stages). Owner decisions for 14D.4 (2026-10-04): native OCI SDK smoke (not a one-off CLI);
> IMDS guard keeps DNS (port 53) open; restore user created only for the 14D.4.6 proof and its API key deleted right
> after.

---

## 1. What 14D.4 must prove (drill resources only)

| # | Proof | Expected |
|---|---|---|
| 1 | uploader principal creates a **new** object in `plan-estimate-backup-drill` | allowed |
| 2 | uploader reads it: HEAD, GET, list, list versions | allowed |
| 3 | overwrite of an existing name (plain PutObject) | denied |
| 4 | conditional create `If-None-Match: *` on an existing name | denied |
| 5 | object delete, object-version delete, multipart upload, bucket update | denied |
| 6 | any access to `plan-estimate-backup-prod` (Phase B does not exist) | denied |
| 7 | restore principal reads both buckets and cannot write | read allowed / write denied |
| 8 | **O4:** only the uploader bridge obtains the instance principal; backend, caddy, frontend, postgres and any other container cannot | as stated |
| 9 | each R2 drill token works on its own bucket only | as stated |

Phase B (production uploader policy) is a separate owner decision after 14D.4 PASS.

## 2. 14D.4.1 reconnaissance (owner, read-only, 2026-10-04)

| Fact | Value |
|---|---|
| Host | Ubuntu 24.04.5, kernel 6.17 (oracle), aarch64; "System restart required" pending (not acted on) |
| Server checkout | `~/apps/plan_-_estimate` at `8c53e58` (production runtime; later commits are documentation / backup tooling only) |
| Containers | `plan_estimate_backend` (healthy), `plan_estimate_caddy`, `plan_estimate_frontend`, `plan_estimate_postgres` (healthy) |
| Docker | server 29.8.0, firewall backend **iptables** (userland proxy on) |
| Networks | `bridge` / `docker0` 172.17.0.0/16 (DOWN, unused); `plan-estimate_internal` / `br-88e80c29c406` 172.18.0.0/16; VCN `enp0s6` 10.0.0.83/24 |
| iptables | v1.8.10 (nf_tables); `FORWARD` policy DROP, first rule `-j DOCKER-USER` (empty), then `DOCKER-FORWARD`, then Oracle's `REJECT icmp-host-prohibited` |
| Oracle rules | chain `InstanceServices` on **OUTPUT only** (`-d 169.254.0.0/16`): host access to IMDS tcp/80 and DNS 53 allowed, other link-local rejected; loaded from `/etc/iptables/rules.v4` (17 references) by `netfilter-persistent` (enabled; `iptables-persistent` installed) |
| DNS | host `/etc/resolv.conf` → systemd-resolved `127.0.0.53`, upstream `169.254.169.254`; containers on the compose network use Docker's embedded resolver `127.0.0.11` with `ExtServers: host(127.0.0.53)` (queries leave from the host namespace) |
| **IMDS from the backend container** | `IMDS from backend: 200 eu-frankfurt-1` — **forwarded container traffic reaches IMDS** |

## 3. Consequence: the O4 risk is real

Oracle's `InstanceServices` chain filters only host-originated traffic (OUTPUT). Container traffic is forwarded
(FORWARD) and is not covered, so today the internet-facing backend container can fetch the instance-principal
certificate and act as the VM's dynamic group. With only the Phase A policy this means "create / read synthetic
objects in the drill bucket"; with a production policy it would mean "write into the production backup bucket from a
compromised backend". **No production uploader authority (Phase B) before the guard below is active and proven.**

## 4. IMDS guard (14D.4.4)

### 4.1 Design

One owned chain `PE-IMDS-GUARD`, jumped to from the **first** position of `DOCKER-USER`:

```
-A PE-IMDS-GUARD -d 169.254.169.254/32 -i br-pe-upload -p tcp -m tcp --dport 80 -j RETURN
-A PE-IMDS-GUARD -d 169.254.169.254/32 -p udp -m udp --dport 53 -j RETURN
-A PE-IMDS-GUARD -d 169.254.169.254/32 -p tcp -m tcp --dport 53 -j RETURN
-A PE-IMDS-GUARD -d 169.254.0.0/16 -i docker0 -p tcp -j REJECT --reject-with tcp-reset
-A PE-IMDS-GUARD -d 169.254.0.0/16 -i docker0 -j REJECT --reject-with icmp-port-unreachable
-A PE-IMDS-GUARD -d 169.254.0.0/16 -i br-+ -p tcp -j REJECT --reject-with tcp-reset
-A PE-IMDS-GUARD -d 169.254.0.0/16 -i br-+ -j REJECT --reject-with icmp-port-unreachable
```

- The uploader boundary is an **interface**, not an IP: the uploader network is created with the fixed bridge name
  `br-pe-upload`; a container on another network cannot appear on that interface.
- DNS to the VCN resolver stays open for every container (defence for containers on the default bridge, which use
  `169.254.169.254:53` directly); compose-network DNS already goes through the host.
- Every other forwarded packet from a Docker bridge (`docker0`, `br-+`, i.e. also future networks) to the link-local
  range is rejected — mirroring what Oracle's rules do for the host.
- `RETURN` hands accepted traffic back to Docker's normal processing (`DOCKER-FORWARD`); nothing is accepted that
  Docker would not accept anyway.

Files: `ops/imds-guard/pe-imds-guard.sh` (`apply` / `remove` / `status`) and
`ops/imds-guard/plan-estimate-imds-guard.service`.

- `apply` replaces the chain in **one `iptables-restore --noflush` transaction** (atomic; other chains untouched),
  removes any stale jump and inserts exactly one jump at `DOCKER-USER` #1, then verifies.
- `status` exits 0 only if the chain equals the design exactly and the jump is unique and first.
- `remove` deletes every jump and the chain (state before the guard).
- The script never runs `netfilter-persistent save`, never writes `/etc/iptables/rules.v4`, never touches
  `InstanceServices`, Docker's chains, policies or `ip6tables` (Docker networks here are IPv4-only).

**Persistence:** the systemd unit (oneshot, `After=` / `Requires=` / `PartOf=docker.service`, `WantedBy=docker.service`)
re-applies after every boot and every Docker restart. It has no `ExecStop`: stopping or restarting the unit never opens
IMDS. It executes a **root-owned copy** in `/usr/local/sbin`, never the user-writable checkout.

### 4.2 Owner procedure (each block only after explicit approval)

Pre-checks (read-only):

```bash
curl -fsS https://plan-estimate.pl/api/health
docker exec plan_estimate_backend python -c "import socket; print('DNS ok', socket.gethostbyname('api.telegram.org'))"
```

Uploader network (no container is attached yet; does not affect running services):

```bash
docker network create --driver bridge --subnet 172.30.250.0/24 \
  -o com.docker.network.bridge.name=br-pe-upload pe-upload
```

Install and activate the guard:

```bash
cd ~/apps/plan_-_estimate && git pull --ff-only
sudo install -o root -g root -m 0755 ops/imds-guard/pe-imds-guard.sh /usr/local/sbin/pe-imds-guard.sh
sudo install -o root -g root -m 0644 ops/imds-guard/plan-estimate-imds-guard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now plan-estimate-imds-guard.service
sudo /usr/local/sbin/pe-imds-guard.sh status
```

Verification (PASS = every line as expected):

```bash
IMG='python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f'
PROBE="import urllib.request as u
try:
    r = u.urlopen(u.Request('http://169.254.169.254/opc/v2/instance/region', headers={'Authorization': 'Bearer Oracle'}), timeout=3)
    print('IMDS', r.status)
except Exception as e:
    print('IMDS blocked', type(e).__name__)"
docker exec plan_estimate_backend python -c "$PROBE"                               # expect: IMDS blocked
docker run --rm --network plan-estimate_internal "$IMG" python -c "$PROBE"          # expect: IMDS blocked
docker run --rm "$IMG" python -c "$PROBE"                                           # expect: IMDS blocked (default bridge)
docker run --rm --network pe-upload "$IMG" python -c "$PROBE"                       # expect: IMDS 200
docker exec plan_estimate_backend python -c "import socket; print('DNS ok', socket.gethostbyname('api.telegram.org'))"
curl -fsS https://plan-estimate.pl/api/health
```

**Rollback** (one step, restores today's state):

```bash
sudo systemctl disable plan-estimate-imds-guard.service
sudo /usr/local/sbin/pe-imds-guard.sh remove
```

Reboot persistence is verified at the next owner-planned reboot (the pending kernel restart): after it,
`sudo /usr/local/sbin/pe-imds-guard.sh status` must print `OK` and the probes above must repeat. Docker is **not**
restarted in production for this test.

The future `backup-upload` Compose service joins `pe-upload` as an external network; that wiring belongs to the
uploader tooling stage.

## 5. OCI drill smoke (14D.4.5)

`backend/scripts/stage14d4_oci_drill_smoke.py` — standalone (stdlib + `oci==2.187.1`), instance-principal auth, no
retries, 16 checks:

| Check | Expect |
|---|---|
| `drill_get_bucket`, `drill_versioning_enabled` | allow / versioning `Enabled` |
| `drill_create_new_object` (`If-None-Match: *`, `Content-MD5`) | allow |
| `drill_head_object`, `drill_get_object` (SHA-256), `drill_list_objects`, `drill_list_object_versions` (exactly 1) | allow |
| `drill_overwrite_existing`, `drill_conditional_create_existing` | deny |
| `drill_delete_object`, `drill_delete_object_version` | deny |
| `drill_object_unchanged` (SHA-256 equal, exactly one live version, no delete marker) | invariant |
| `drill_multipart_upload` (aborted if it ever succeeds), `drill_update_bucket` (no-op `versioning=Enabled`) | deny |
| `prod_get_bucket`, `prod_list_objects` — the only calls on production; nothing is written there | deny |

"Denied" = an OCI service error with HTTP 401 / 403 / 404 / 409 / 412; a 5xx, throttling or transport error is an
**error**, never a denial. OCI reports `NotAuthorizedOrNotFound` both for a denial and for a missing bucket; the
production bucket's existence is known from 14D.3. The probe object `smoke/14d4/<utc>-<random>/probe.bin` (64 KiB
random bytes) stays in the drill bucket (the principal cannot delete); drill cleanup is a manual owner step. Output:
check table only — no token, certificate, OCID, request id, object content or provider message.

Run (after §4 PASS):

```bash
IMG='python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f'
SMOKE=~/apps/plan_-_estimate/backend/scripts/stage14d4_oci_drill_smoke.py
RUN='pip install -q --no-cache-dir --root-user-action=ignore oci==2.187.1 && python /smoke.py'
# positive: uploader bridge
docker run --rm --network pe-upload --cap-drop ALL --security-opt no-new-privileges \
  -e OCI_NAMESPACE='<namespace>' -v "$SMOKE":/smoke.py:ro "$IMG" sh -c "$RUN"
# negative (O4): no instance principal outside the uploader bridge -> exit 3
docker run --rm --network plan-estimate_internal --cap-drop ALL --security-opt no-new-privileges \
  -v "$SMOKE":/smoke.py:ro "$IMG" sh -c "$RUN --auth-only"; echo "exit=$?"
```

Exit codes: 0 all PASS, 1 a check failed, 2 cannot run, 3 instance principal not obtainable.

## 6. R2 drill tokens and smoke (14D.4.3)

Tokens (owner, Cloudflare → R2 → Manage API Tokens), created immediately before use and written straight into env
files on the VM:

| Token | Permission | Scope | Recommended hardening |
|---|---|---|---|
| `plan-estimate-drill-source` | Object Read & Write | `plan-estimate-media-drill-source` only | TTL until the end of 14D.5; client IP filter = VM public IP |
| `plan-estimate-drill-restore` | Object Read & Write | `plan-estimate-media-drill-restore` only | same |

Env files (never in the repository, never in `.env.production`; edited with an editor, not a heredoc, so secrets do
not reach the shell history):

```bash
install -d -m 700 ~/backups/plan-estimate/drill-secrets
install -m 600 /dev/null ~/backups/plan-estimate/drill-secrets/r2-drill-source.env
nano ~/backups/plan-estimate/drill-secrets/r2-drill-source.env
```

```
R2_ENDPOINT_URL=https://<account-id>.eu.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=<drill-source access key id>
R2_SECRET_ACCESS_KEY=<drill-source secret>
R2_BUCKET=plan-estimate-media-drill-source
R2_FORBIDDEN_BUCKETS=plan-estimate-media-prod,plan-estimate-media-drill-restore
```

(`r2-drill-restore.env` analogously with `R2_BUCKET=plan-estimate-media-drill-restore` and
`R2_FORBIDDEN_BUCKETS=plan-estimate-media-prod,plan-estimate-media-drill-source`.)

`backend/scripts/stage14d4_r2_drill_smoke.py` (standalone, boto3 with the production adapter's client settings):
create (`If-None-Match: *`), HEAD, GET (SHA-256), list → allowed; second conditional create → HTTP 412; object
unchanged; cleanup delete → allowed and verified absent; for every forbidden bucket `ListObjectsV2` and `HeadBucket`
→ HTTP 401 / 403 (nothing is written there). The endpoint must be the EU-jurisdiction https form; the bucket must
be a drill bucket and must not be listed as forbidden.

```bash
IMG='python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f'
for t in source restore; do
  docker run --rm --cap-drop ALL --security-opt no-new-privileges \
    --env-file ~/backups/plan-estimate/drill-secrets/r2-drill-$t.env \
    -v ~/apps/plan_-_estimate/backend/scripts/stage14d4_r2_drill_smoke.py:/smoke.py:ro "$IMG" \
    sh -c 'pip install -q --no-cache-dir --root-user-action=ignore boto3==1.43.103 botocore==1.43.103 s3transfer==0.19.2 urllib3==2.8.0 && python /smoke.py'
done
```

## 7. Restore principal proof (14D.4.6, owner workstation)

User `plan-estimate-restore-operator` (Default domain, member of `plan-estimate-backup-restore` only); API signing key
generated on the owner's Manjaro workstation, never on the VM. Proof with the OCI CLI: GET of the 14D.4.5 probe
object from the drill bucket and a list of the production bucket succeed; PutObject and DeleteObject on the drill
bucket are denied. Then the API key is deleted in the Console and the local private key is destroyed; the user stays
without a key until 14D.5. Exact commands are prepared when this step starts.

## 8. Order and approvals

| Step | Content | Production effect |
|---|---|---|
| 14D.4.2 | tooling + tests (this commit) | none |
| 14D.4.3 | R2 drill tokens → env files on the VM → R2 smoke (both tokens) | new files outside the repository only |
| 14D.4.4 | uploader network + IMDS guard + verification (§4.2) | **firewall** (`DOCKER-USER` jump + own chain), new Docker network; rollback ready |
| 14D.4.5 | OCI drill smoke positive + negative (§5) | drill bucket only; probe object remains |
| 14D.4.6 | restore principal proof (§7) | none on the VM |
| 14D.4.7 | results recorded, PASS / FAIL report; Phase B is a separate decision | none |

Each step is run by the owner with commands from this document, after explicit approval; any unexpected output is a
stop-and-report point, never something to "fix" by widening permissions.

## 9. 14D.4.2 automated verification (2026-10-04)

- `tests/test_stage14d4_imds_guard.py`: static contract (exact rules and order, atomic restore, first-position jump,
  forbidden operations absent, unsafe bridge names refused, systemd unit) — always run; **opt-in real proofs**
  (`TEST_REAL_NETNS=1`, root) on iptables v1.8.10 (nf_tables, the production version) in private network
  namespaces: idempotent apply, tamper detection (duplicate jump, extra rule), clean remove; packet matrix with veth
  interfaces named `br-pe-upload`, `br-other1`, `docker0` and a fake IMDS: before guard all open; after apply only the
  uploader reaches 169.254.169.254:80, DNS 53 (udp/tcp) open for all, every other link-local target rejected; after
  remove all open again.
- `tests/test_stage14d4_oci_drill_smoke.py`: fake versioned Object Storage with configurable policy — Phase A 16/16
  PASS; overwrite / delete / version delete / multipart / bucket update / production access / disabled versioning /
  denied create / 5xx / unexpected exceptions all FAIL (never a false PASS); production never written; report free of
  namespace, body and provider messages; CLI exit codes 2 / 3 / 0.
- `tests/test_stage14d4_r2_drill_smoke.py`: fake S3 (scoped / unscoped token, ignored If-None-Match, failed cleanup)
  and a botocore `Stubber` run validating every request against the S3 model of the pinned boto3 1.43.103; config
  refuses non-EU / non-https endpoints, non-drill buckets, missing forbidden list; no credential, endpoint or body in
  output or `repr`.
- Additionally (scratch venv, not committed): every OCI call of the smoke passed through the real `oci==2.187.1`
  `ObjectStorageClient` with a stubbed transport (unknown kwargs would raise): 16/16 on a simulated Phase A policy;
  `version_id` serialised as `versionId`, `If-None-Match` / `Content-MD5` headers present.

## 10. Accepted risks / deferred

- The disposable smoke containers install `oci==2.187.1` / boto3 pins with pip; transitive dependencies of `oci` are
  resolved at install time. Acceptable for a one-off drill smoke in an isolated container; the real uploader image
  (tooling stage) gets a fully pinned, hash-locked dependency set.
- Probe objects remain in `plan-estimate-backup-drill` (create-only principal); manual owner cleanup with the
  administrator account after 14D.5.
- `pe-upload` is created manually here; Compose wiring of the uploader is part of the uploader tooling stage.
