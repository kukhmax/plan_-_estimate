# Stage 14D.3 — Oracle Object Storage / IAM provisioning design and owner runbook

> **Status:** **DESIGN APPROVED — PROVISIONING NOT YET EXECUTED** (owner decisions 2026-10-04: O1–O7 approved, O8
> deferred hardening; buckets renamed). **Nothing in this document has been executed.** No bucket, compartment, dynamic
> group, user, group, policy, key or secret exists yet because of it. The IAM statements in §6.2 remain **PROPOSED**
> until validated in the OCI Console and empirically proven in 14D.4. The owner performs every Console step manually.
>
> Builds on `docs/STAGE_14D_BACKUP_RESTORE_PLAN.md` (accepted 14D architecture: §3 independence, §4 resources, §5
> layout, §8 provenance, §9 encrypted DB chain, §10 integrity, §13 credentials, §14 retention, §16 backup runtime).
> This document does not redesign that architecture; where it proposes a change, the change is marked as an
> **owner decision**.
>
> Labels used below: **[ACCEPTED]** = already accepted project architecture; **[ORACLE-DOC]** = current Oracle
> documentation, read on 2026-10-03 (sources in §15); **[RECOMMENDATION]** = this design's inference / proposal;
> **[VERIFY]** = must be verified by the owner in the Console / current docs before or while executing.

---

## 1. Scope

In scope: the independent backup target (Oracle Cloud Infrastructure Object Storage) for media objects copied from
the private Cloudflare R2 bucket and for encrypted PostgreSQL artifacts (and, later, manifests / `COMPLETE.json`);
its buckets, IAM, authentication, retention, the production-VM credential exposure, the age disaster-recovery key
custody, and the ARM64 production gate.

Out of scope here (later sub-stages, unchanged): upload / sync tooling and manifest writer (14D.2 tooling), the
connectivity / semantics smoke (14D.4), the drill (14D.5), the first production run (14D.6). R2 stays the primary
media store; nothing changes for R2 in this document except the read-only token already planned in §13 of the plan.

---

## 2. Owner decisions (2026-10-04)

| # | Decision | Status |
|---|---|---|
| O1 | Instance Principal (dynamic group of the production VM) for the future uploader; dedicated API-key IAM user only if Instance Principal proves impractical or cannot be safely isolated on the production Docker host. | **APPROVED** |
| O2 | Keep the proven `backup` service local-only (database, pgpass, writable `/backup`, **no** Internet, **no** OCI / R2 authority). Add a separate future **`backup-upload`** service (**no** database, **no** pgpass, `/backup` read-only, controlled outbound HTTPS, R2 read-only authority, narrowly scoped OCI backup authority). Neither runtime changes now. | **APPROVED** |
| O3 | Native OCI Object Storage API through a pinned official OCI SDK in the future uploader; Oracle is **not** forced through the existing S3 adapter (replaces the 14D.1 assumption, plan §1 gap 4). | **APPROVED** |
| O4 | Instance Principal is used only if 14D.4 proves **on the actual production Docker host** that access to OCI IMDS is restricted to the uploader boundary. **No real uploader authority is granted before that isolation proof passes**; if it cannot be demonstrated reliably, stop and reconsider the API-key fallback. | **APPROVED WITH MANDATORY GATE** |
| O5 | v1 protection: create-only IAM; only the required read / inspect; no `OBJECT_OVERWRITE`, `OBJECT_DELETE`, `OBJECT_VERSION_DELETE`; versioning enabled; no retention rule; no lifecycle deletion; immutable application keys; `COMPLETE.json` last. Retention-lock evaluation = deferred hardening. | **APPROVED** |
| O6 | Restore authority stays **off** the production VM; the VM never permanently holds restore credentials or an age identity. | **APPROVED** |
| O7 | Dedicated compartment `plan-estimate-backup` under the `kukhmax` root compartment. | **APPROVED** |
| O8 | Second encrypted DB backup outside OCI (owner-held offline copy, a separate private R2 DB bucket or another provider) as defence against Oracle account / region / administrative failure. **Not** provisioned, no credentials, no uploader work, **not** a prerequisite for `PHOTO_UPLOADS_ENABLED`, 14D.4–14D.7 are not expanded around it. | **DEFERRED HARDENING** (not a 14D readiness gate) |
| — | Bucket names: `plan-estimate-backup-prod` / `plan-estimate-backup-drill` (the earlier `plan-estimate-media-*` names were misleading — the buckets hold media **and** DB backups). | **OWNER CHANGE** |

## 3. Bucket topology [ACCEPTED + RECOMMENDATION]

| Property | Production | Drill |
|---|---|---|
| Name | `plan-estimate-backup-prod` [OWNER CHANGE 2026-10-04] | `plan-estimate-backup-drill` [OWNER CHANGE 2026-10-04] |
| Compartment | `plan-estimate-backup` (O7) | `plan-estimate-backup` |
| Region | the tenancy home region (Frankfurt, `eu-frankfurt-1`) — same region as the VM; Always-Free tenancies are limited to the home region [VERIFY region identifier in the Console] | same |
| Storage tier | **Standard** (Archive / Infrequent Access add retrieval delay, minimum-retention and retrieval charges that do not fit a restore-ready backup) | Standard |
| Visibility | **Private** (no public access); no pre-authenticated requests | Private |
| Versioning | **Enabled** at creation [ACCEPTED §14] | Enabled |
| Retention rules | **None** in v1 (incompatible with versioning — O5) | None |
| Lifecycle policy | **None** (no automatic deletion until a retention policy is approved [ACCEPTED §14]) | None (cleanup of drill data is a manual owner step) |
| Encryption at rest | Oracle-managed keys (default) [ORACLE-DOC: "Object Storage ensures security of the stored data using data encryption"]; DB artifacts are additionally `age`-encrypted client-side; a customer-managed Vault key adds cost / key-loss risk without a v1 benefit | Oracle-managed |
| Object events / auto-tiering | Off | Off |
| Replication | None in v1 (home-region constraint; a replication destination cannot carry retention rules) | None |

**One bucket with prefixes** for DB and media (the accepted §5 layout); the names deliberately say `backup`, not
`media`, because the bucket holds both. Separate buckets would only pay off if DB and media later need different
protection (e.g. a retention rule on DB artifacts while media keep versioning) — deferred hardening.

**Independence [ACCEPTED §3]:** R2 (Cloudflare) and OCI (Oracle) are different providers with separate credentials;
nothing deleted / missing in R2 propagates (create-only, never synced as deletions). The DB-side gap (database and its
backups in one Oracle account / region) is recorded as **O8 — deferred hardening**.

---

## 4. Canonical object layout [ACCEPTED §5]

```
<bucket>/
  photos/v1/{asset_uuid}/original.{ext}       same immutable keys as R2
  photos/v1/{asset_uuid}/display.jpg
  photos/v1/{asset_uuid}/thumb.jpg
  db/{run_id}/plan-estimate.sql.gz.age         encrypted DB dump
  runs/{run_id}/manifest.jsonl
  runs/{run_id}/COMPLETE.json                  written last
```

What exists **today** (14D.2D, local only): `/backup/encrypted/{run_id}/plan-estimate.sql.gz.age` and
`local-run.json`. Nothing is uploaded yet. `db/…` appears with the uploader; `photos/…`, `runs/…/manifest.jsonl` and
`COMPLETE.json` appear with the manifest / media tooling. `local-run.json` is **not** uploaded by default (it carries
the plaintext SHA-256, which plan §16.3 / D5 keeps local unless separately decided).

All keys are **immutable**: a key is written once and never rewritten. That is what makes create-only IAM workable.

**Gap for the later media / manifest stage (not a 14D.3 blocker):** the local run currently records only the READY
count and digest, not the READY asset list the uploader needs. The list must come from the same exported snapshot —
the 14D.2D.3 metadata hook can read it in the imported snapshot (no 14D.2A change) and write it into the run
directory; its digest must equal the exporter's.

---

## 5. Authentication model [O1 APPROVED, from ORACLE-DOC facts]

| Option | Static secret on VM | Works for | Scope / revocation | Assessment |
|---|---|---|---|---|
| **1. Instance Principal** (dynamic group) | **none** — certificates are created, assigned and rotated by OCI several times a day [ORACLE-DOC] | native OCI API / SDK (`InstancePrincipalsSecurityTokenSigner`) | policy on the dynamic group; revoke by editing the policy / matching rule | **Approved (O1)**, subject to the O4 gate. Oracle documents that any user who can access the instance inherits its privileges, and every instance principal implicitly has `compartment_inspect` (compartment names / descriptions / tags) [ORACLE-DOC]. |
| 2. IAM user + API signing key | RSA private key file (0600), mounted only into the uploader | native API / SDK / CLI | group policy; revoke by deleting the API key | Fallback if O4 cannot be made reliable: exposure limited to the uploader container + host root; manual rotation. |
| 3. Customer Secret Key (S3 compatibility) | access / secret key pair, long-lived, user-bound | S3 Compatibility API only (SigV4) [ORACLE-DOC] | group policy; revoke by deleting the key | **Not chosen**: long-lived static secret; S3-compat conditional-PUT semantics are not documented; choosing it only because R2 is S3-style is rejected by the brief. |

With option 1, the IAM permission model is identical to the user case: the dynamic group gets exactly the
create / inspect / read permissions of §6.

---

## 6. IAM policy model [ORACLE-DOC permissions + RECOMMENDATION statements]

### 6.1 Object Storage permissions that matter [ORACLE-DOC]

| API operation | Required permission |
|---|---|
| PutObject (name does **not** exist) | `OBJECT_CREATE` |
| PutObject (name **already exists**) | `OBJECT_OVERWRITE` |
| HeadObject | `OBJECT_READ` or `OBJECT_INSPECT` |
| ListObjects / ListObjectVersions | `OBJECT_INSPECT` |
| GetObject | `OBJECT_READ` |
| DeleteObject | `OBJECT_DELETE` |
| DeleteObjectVersion | `OBJECT_VERSION_DELETE` |
| CreateMultipartUpload / UploadPart | `OBJECT_CREATE` **and** `OBJECT_OVERWRITE` |
| RenameObject | `OBJECT_CREATE` and `OBJECT_OVERWRITE` |
| Verb `use objects` | `read` + `OBJECT_OVERWRITE` (PutObject overwrite) — **not acceptable** |
| Verb `manage objects` | adds `OBJECT_CREATE`, `OBJECT_DELETE`, `OBJECT_VERSION_DELETE`, `OBJECT_RESTORE`, `OBJECT_UPDATE_TIER` — **acceptable only when narrowed by `request.permission`** |
| Retention rules / bucket delete / PARs | `RETENTION_RULE_MANAGE`, `BUCKET_DELETE`, `PAR_MANAGE` (verb `manage buckets`) — never granted |

Consequences:
- **Create-only is IAM-enforceable**: without `OBJECT_OVERWRITE`, an upload to an existing name is refused by IAM;
  without `OBJECT_DELETE` / `OBJECT_VERSION_DELETE`, nothing can be deleted.
- **Multipart upload is impossible** for a create-only principal (it needs `OBJECT_OVERWRITE`). The uploader must use
  single PutObject requests; Oracle documents a maximum PutObject size of 50 GiB [ORACLE-DOC], far above current
  object sizes (≤ ~25 MB photos, small encrypted dumps).
- The uploader should additionally send `if-none-match: *` on PutObject so the server itself rejects an existing name
  [VERIFY in 14D.4 against the native API]; IAM is the primary control, the header a second one.

### 6.2 Proposed statements — **PROPOSED, awaiting OCI Console validation and 14D.4 empirical proof**

These statements follow Oracle's documented syntax but are **not** operational facts until the Console accepts them
and 14D.4 proves the behaviour on the drill bucket. They contain placeholders only (no OCIDs in the repository).

Dynamic group **`plan-estimate-backup-uploader-dg`** — matching rule (Oracle syntax `variable = 'value'`):

```
instance.id = '<OCID of the production VM "plan-estimate">'
```

Uploader policy — **two phases because of the O4 gate**: no real (production) uploader authority exists before the
14D.4 isolation proof passes.

**Phase A — drill only** (created in 14D.3 provisioning; exercised by 14D.4). Policy
**`plan-estimate-backup-uploader-drill-policy`**, attached to the **root compartment** (tenancy) [VERIFY whether the
owner prefers attaching it to `plan-estimate-backup`; dynamic-group policies are commonly kept in the tenancy]:

```
Allow dynamic-group plan-estimate-backup-uploader-dg to read buckets in compartment plan-estimate-backup where target.bucket.name = 'plan-estimate-backup-drill'
Allow dynamic-group plan-estimate-backup-uploader-dg to read objects in compartment plan-estimate-backup where target.bucket.name = 'plan-estimate-backup-drill'
Allow dynamic-group plan-estimate-backup-uploader-dg to manage objects in compartment plan-estimate-backup where all {target.bucket.name = 'plan-estimate-backup-drill', request.permission = 'OBJECT_CREATE'}
```

**Phase B — production** (added **only after** 14D.4 PASS, including the O4 IMDS-isolation proof, and a separate owner
approval). Policy **`plan-estimate-backup-uploader-prod-policy`**:

```
Allow dynamic-group plan-estimate-backup-uploader-dg to read buckets in compartment plan-estimate-backup where target.bucket.name = 'plan-estimate-backup-prod'
Allow dynamic-group plan-estimate-backup-uploader-dg to read objects in compartment plan-estimate-backup where target.bucket.name = 'plan-estimate-backup-prod'
Allow dynamic-group plan-estimate-backup-uploader-dg to manage objects in compartment plan-estimate-backup where all {target.bucket.name = 'plan-estimate-backup-prod', request.permission = 'OBJECT_CREATE'}
```

Notes for both phases:
- Statement 1: GetBucket for the bucket only (preflight: bucket exists, versioning enabled). Oracle documents that
  `target.bucket.name` cannot scope operations involving multiple buckets such as ListBucket, so bucket listing is
  deliberately not granted; the namespace is configured statically (non-secret) instead of discovered [VERIFY that
  GetNamespace is not needed by the SDK path chosen].
- Statement 2: `OBJECT_INSPECT` + `OBJECT_READ` (HEAD, list, download). Download is required by the accepted
  provenance / post-copy verification (plan §8, §10: "full re-download and SHA-256 comparison") — the accepted §13
  already lists "create / read / list" for the backup identity.
- Statement 3: `manage objects` narrowed to **`OBJECT_CREATE` only** — the pattern Oracle documents in "Let users
  write objects to Object Storage buckets" (`manage objects … where any {request.permission='OBJECT_CREATE',
  request.permission='OBJECT_INSPECT'}`), combined with the documented `target.bucket.name` condition.
- Never granted: `OBJECT_OVERWRITE`, `OBJECT_DELETE`, `OBJECT_VERSION_DELETE`, `OBJECT_RESTORE`,
  `OBJECT_UPDATE_TIER`, any `manage buckets`, retention / lifecycle / PAR / replication management, any IAM verb.

Restore group **`plan-estimate-backup-restore`** (IAM users, operator only — O6); policy
**`plan-estimate-backup-restore-policy`**:

```
Allow group plan-estimate-backup-restore to read buckets in compartment plan-estimate-backup where any {target.bucket.name = 'plan-estimate-backup-prod', target.bucket.name = 'plan-estimate-backup-drill'}
Allow group plan-estimate-backup-restore to read objects in compartment plan-estimate-backup where any {target.bucket.name = 'plan-estimate-backup-prod', target.bucket.name = 'plan-estimate-backup-drill'}
```

Bucket administration (versioning, future retention, drill cleanup) stays with the owner's existing administrator
account — not delegated to any automated principal.

**Security invariants (what 14D.4 must prove, on the drill bucket):** the uploader MAY read bucket metadata as
required, inspect / read / list objects as required by verification, and `OBJECT_CREATE`; it MUST NOT have
`OBJECT_OVERWRITE`, `OBJECT_DELETE`, `OBJECT_VERSION_DELETE`, bucket mutation, retention / lifecycle mutation or IAM
administration. PASS = a new unique object is created; HEAD / GET work as designed; list works only as required; an
overwrite of an existing object, an object delete, a version delete and any bucket mutation are **denied**; the
native-API conditional create (`if-none-match: *`) refuses an existing name; the restore principal cannot write;
**and** (O4 gate) IMDS is reachable from the uploader boundary only — the backend and other containers cannot obtain an
instance-principal token. Real uploader authority on the production bucket is granted only after this passes.

[VERIFY] before saving each policy: the Console policy editor validates syntax; any rejection or a changed Oracle
example is a stop-and-report point, not something to "fix" by widening verbs.

---

## 7. Append-only, versioning, retention, lifecycle

**[ORACLE-DOC]**
- Versioning on: an upload with an existing name makes the old object a *previous version*; a delete creates a
  *delete marker* and keeps the data; versions can be removed only with `OBJECT_VERSION_DELETE`.
- Retention rules: while active, objects cannot be updated, overwritten or deleted (time-bound rules per object
  from its Last-Modified time); **a retention rule cannot be added to a versioning-enabled bucket, and versioning
  cannot be enabled while retention rules are active**; locking a rule is irreversible (not even a tenancy
  administrator or Oracle Support can delete it) after a mandatory 14-day delay.

**v1 (O5 approved):** versioning **enabled**; **no** retention rule — Oracle documents that retention rules cannot be
added while versioning is enabled and versioning cannot be enabled while active retention rules exist, so a retention
lock is **not** part of v1 (deferred hardening); **no** lifecycle deletion. Protection stack against the stated
threats:

| Threat | Control |
|---|---|
| Accidental overwrite by the backup process | immutable keys + no `OBJECT_OVERWRITE` (IAM refusal) + `if-none-match: *` |
| Accidental delete by the backup process | no `OBJECT_DELETE` / `OBJECT_VERSION_DELETE` — there is also no delete code path [ACCEPTED §14] |
| Compromised backup process / uploader / VM | the same: it can only add objects (and read / list); it cannot destroy or alter existing ones |
| Operator mistake in the Console | versioning keeps previous versions / delete markers recoverable (only deliberate version deletion by an administrator destroys data) |
| Partial / failed runs | COMPLETE-last protocol [ACCEPTED §6]: a run without a valid `COMPLETE.json` is not a backup; nothing is deleted to "clean up" |
| Malicious administrator / compromised owner account | **not covered in v1** — would need a locked retention rule (which in turn means no versioning); deferred to 14D.7 / later, once growth and retention are known |

No lifecycle policy and no automatic deletion in v1 [ACCEPTED §14]. Versioning does not grow storage for a
create-only writer (no overwrites / deletes happen); previous versions appear only after Console actions.

---

## 8. Production-VM credential exposure and the local / uploader boundary [O2 APPROVED, O4 GATE]

**Today (14D.2D, proven):** the `backup` service is non-root, read-only root filesystem, `cap_drop: ALL`,
no-new-privileges, no Docker socket, a DB passfile, and — as proven in 14D.2D.5 — **no internet egress**. It cannot
upload anything, by design.

**Approved split (O2; future tooling stage — neither runtime changes now):**

| | `backup` (exists) | `backup-upload` (future) |
|---|---|---|
| Job | snapshot → pg_dump → age → local evidence → promote | read completed local runs, copy R2 → OCI, upload encrypted DB artifacts, manifest, `COMPLETE.json` last |
| Network | internal only (PostgreSQL); no egress | its own network with outbound HTTPS to R2 and OCI (+ IMDS for Instance Principal); **no** access to PostgreSQL |
| `/backup` | read-write (its data root) | **read-only** mount; its own writable state directory for upload progress |
| Secrets | pgpass (read-only), age **recipients** only | R2 **read-only** token (file, 0600, read-only mount); OCI via Instance Principal (no file) or the O1 fallback key |
| Hardening | as today | same baseline (non-root, ro root, cap_drop ALL, no-new-privileges, limits, no Docker socket) |

Why: the process that can read the database never gets internet access or cloud credentials; the process that
talks to clouds never sees the database, the pgpass or plaintext — only age-encrypted DB artifacts and the media it
copies. A compromise of either side is contained to its own capabilities. Whether `backup-upload` uses the same image
(different entrypoint) or its own image is a tooling-stage decision.

**What exists on disk with Instance Principal:** no OCI key / config file at all. Tokens are obtained at runtime from
the instance metadata service (`http://169.254.169.254/opc/…`) [ORACLE-DOC]; the uploader needs network reachability
to it. The non-secret settings (region, namespace, bucket names, compartment name) go into the backup env file.

**IMDS exposure (O4 — approved with mandatory gate):** Oracle documents that everyone with access to the instance
inherits the instance principal's privileges. On a Docker host, every container whose traffic is NATed to the host can
normally reach `169.254.169.254` — that would include the internet-facing backend, frontend, Caddy and PostgreSQL
containers. **Gate:** 14D.4 must prove on the **actual production Docker host** that IMDS is reachable only from the
uploader boundary (candidate control: a host `DOCKER-USER` iptables rule dropping traffic to `169.254.169.254` from
every Docker network except the uploader's; proof: the backend and other containers cannot obtain an
instance-principal token, the uploader can). Until then only the drill-bucket policy (Phase A) exists; while it does,
any process on the VM could at most add / read synthetic drill objects. If reliable isolation cannot be demonstrated,
stop and reconsider the API-key fallback (O1).

**No change to networking or Compose now** — this is design only.

---

## 9. age disaster-recovery key custody [ACCEPTED §9, confirmed 2026-10-04]

- The production VM holds **only public recipients** (`BACKUP_AGE_RECIPIENTS`); the backup path never needs an
  identity [ACCEPTED §9.1].
- **Two independent identities, two recipients** (`age-keygen` run on the owner's workstation — never on the VM):
  identity A and identity B, each able to decrypt every artifact on its own.
- Storage: A in the owner's password manager (as a secure note), B on an offline medium (e.g. an encrypted USB stick or
  a printed copy in a safe place); optionally each copy passphrase-wrapped with `age -p`. Neither copy on the
  production VM, in the repository, in R2 or in OCI.
- Record (non-secret) the two **recipient** strings and where each identity is kept; verify each copy off the VM with
  `age-keygen -y <identity file>` = the configured recipient.
- Proof: the 14D.5 drill decrypts an artifact produced by the VM configuration with a custody copy brought from
  outside the VM. Loss of the VM therefore never loses restore capability.

---

## 10. ARM64 production gate (mandatory before 14D.6) [OWNER CONFIRMED — not performed now]

14D.2D.5 proved the runtime on the owner's amd64 host. Before the first production backup the owner runs, on the
production ARM64 VM, without touching the production database or project:

1. build the backup image natively (`linux/arm64`) — PGDG key + age arm64 checksum verified in the build;
2. Python 3.12.x, `pg_dump (PostgreSQL) 16.x`, age / age-keygen 1.3.2 in the image;
3. non-root runtime with the production Compose service hardening (self-inspection as in §16.7 of the plan);
4. the real `/backup` host filesystem: `renameat2(RENAME_NOREPLACE)` promotion proof, fsync of run / parent
   directories, `flock` contention and SIGKILL release;
5. an encrypted local DB backup end to end against a **scratch** PostgreSQL 16 on an isolated network, independently
   decrypted and restored (reuse `backend/tests/runtime_proof/`), then cleanup of the scratch resources.

---

## 11. Destructive-action matrix

| Operation | Production backup principal (uploader) | Restore operator (off-VM) | Owner administrator |
|---|---|---|---|
| PutObject, new immutable name | **allowed** (`OBJECT_CREATE`) | no | yes |
| HeadObject / ListObjects (bucket-scoped) | **allowed** (`OBJECT_INSPECT`) | allowed | yes |
| GetObject / download | **allowed** (`OBJECT_READ`, verification) | allowed | yes |
| GetBucket (bucket-scoped) | allowed | allowed | yes |
| PutObject over an existing name | **forbidden** (no `OBJECT_OVERWRITE`) | forbidden | (versioning keeps the old one) |
| Multipart upload | forbidden (needs `OBJECT_OVERWRITE`) | forbidden | yes |
| DeleteObject / DeleteObjectVersion | **forbidden** | forbidden | break-glass only |
| Bucket delete / update, versioning change | **forbidden** | forbidden | yes |
| Retention / lifecycle / replication / PAR management | **forbidden** | forbidden | yes (only after approval) |
| IAM administration | **forbidden** | forbidden | yes |
| Access to the age identity | never | yes (custody copy) | yes |

---

## 12. Cost considerations [ORACLE-DOC allowances; prices: VERIFY]

- Always Free (official doc, read 2026-10-03): an Always-Free-only account has **20 GB combined** Standard /
  Infrequent Access / Archive data and **50,000 Object Storage API requests per month**; a paid account or one with
  trial credits has 10 GB Standard + 10 GB Infrequent Access + 10 GB Archive and 50,000 requests per month.
- The design must not depend on the allowance. Request volume grows with the asset count: a full-set run issues at
  least one HEAD per object (3 objects per READY asset) plus uploads / verification downloads for new objects — e.g.
  1,000 assets × 3 HEADs = 3,000 requests per run; daily runs would exceed 50,000 per month. The §8 "inherited
  provenance" rule and run frequency (decided before 14E) keep this bounded.
- Paid prices for Standard storage, requests and outbound data transfer, and whether this tenancy is Always-Free-only
  or upgraded: **[VERIFY]** on the official OCI price list / the tenancy's Cost Analysis before 14D.6; no number is
  assumed here. Inbound transfer (uploads) and the VM → Object Storage path in the same region are expected not to be
  billed as egress [VERIFY].
- Archive tier is not used: restore latency (hours) and retrieval charges conflict with restore-readiness.

---

## 13. Owner manual provisioning runbook (OCI Console) — design approved, not yet executed

Region for every step: the home region (Frankfurt) [VERIFY]. Record only names and non-secret identifiers in the
project notes; never put OCIDs, keys or secrets into the repository.

1. **Verify the tenancy state.** Console → Governance & Administration → *Tenancy details*: home region; Billing →
   account type (Always Free only / paid). Object Storage → *Namespace* (record it; non-secret configuration).
   ✔ Verification: region identifier and namespace noted.
2. **Compartment** `plan-estimate-backup` under the root compartment `kukhmax`
   (Identity & Security → Compartments → Create). Description: "Stage 14D independent backup target".
   ✔ Verification: compartment ACTIVE; nothing else in it.
3. **Production bucket** `plan-estimate-backup-prod` in `plan-estimate-backup`
   (Storage → Buckets → Create): Default Storage Tier **Standard**; **Enable Object Versioning: on**; Auto-Tiering
   off; Emit Object Events off; Encryption **Oracle-managed keys**; no retention rule; no lifecycle rule.
   ✔ Verification: bucket details show Visibility *Private*, Versioning *Enabled*, Storage tier *Standard*, no
   pre-authenticated requests, no retention / lifecycle rules.
4. **Drill bucket** `plan-estimate-backup-drill` — identical settings.
   ✔ Verification: as step 3.
5. **Dynamic group** `plan-estimate-backup-uploader-dg` (Identity & Security → Domains → Default domain → Dynamic
   groups; tenancies without identity domains: Identity → Dynamic Groups [VERIFY the Console path]): matching rule `instance.id = '<OCID of the VM "plan-estimate">'` (copy the OCID from Compute → Instances
   → plan-estimate; do not record it in the repository).
   ✔ Verification: the rule lists exactly one instance; no compartment-wide rule.
6. **Uploader policy, Phase A only** — `plan-estimate-backup-uploader-drill-policy` with exactly the three drill
   statements of §6.2. **Do not create the Phase B (production) policy in 14D.3** — it is added only after 14D.4 PASS
   (incl. the O4 IMDS-isolation proof) and a separate owner approval.
   ✔ Verification: policy saved without validation errors (syntax still **PROPOSED** until 14D.4 proves behaviour);
   text re-read: only `plan-estimate-backup-drill`; no `use objects`, no unrestricted `manage objects`, no `manage
   buckets`, no `OBJECT_OVERWRITE` / `OBJECT_DELETE` / `OBJECT_VERSION_DELETE`.
7. **Restore group** `plan-estimate-backup-restore` and policy `plan-estimate-backup-restore-policy` (§6.2). Restore
   user (e.g. `plan-estimate-restore-operator`) with an API signing key generated **on the owner's workstation**;
   the private key stays off the VM (password manager / offline). If the owner prefers, the restore user can instead
   be created only when needed (drill / disaster); the group and policy still exist.
   ✔ Verification: the user is a member of the restore group only; its key fingerprint (non-secret) noted.
8. **age custody** (§9): generate identities A and B on the workstation; store them; note the two recipients.
   ✔ Verification: `age-keygen -y` of each stored copy prints the noted recipient.
9. **R2 (from plan §13, unchanged):** a new R2 API token with **Object Read only** on `plan-estimate-media-prod` for
   the uploader; R2 drill buckets `plan-estimate-media-drill-source` / `-drill-restore` and their drill tokens.
   ✔ Verification: token scope shows read-only, single bucket.
10. **Env / secret files** are **not** created on the VM in 14D.3; their layout is defined with the uploader tooling
    and applied in 14D.4 / 14D.6 with owner approval (backup env file 0600 outside the repository; never
    `.env.production`).
11. **Stop.** Report the recorded non-secret facts (region, namespace, compartment / bucket / group / dynamic-group /
    policy names, versioning state, account type, recipients). Connectivity and permission semantics are tested only
    in 14D.4 on the **drill** bucket: create succeeds; second create of the same name is refused; delete is refused;
    head / get / list succeed; the restore user cannot write; the backend container cannot obtain an instance
    principal token.

---

## 14. Open questions / [VERIFY] list

1. Home-region identifier and whether the tenancy is Always-Free-only or upgraded (affects allowances and regions).
2. ~~Single-PutObject size limit~~ — documented as 50 GiB (no multipart for a create-only principal).
3. Native API behaviour of `if-none-match: *` on PutObject, and the exact IAM refusal for an existing name without
   `OBJECT_OVERWRITE` — 14D.4 on the drill bucket.
4. Whether the SDK's instance-principal path needs any permission beyond §6.2 (e.g. namespace lookup).
5. Reachability of IMDS from Docker containers on this VM and the effectiveness of the `DOCKER-USER` block — 14D.4.
6. Current paid prices for storage / requests / egress (if the account is upgraded).
7. ~~O8~~ — deferred hardening (not a 14D gate).
8. Where the policies are attached (tenancy vs `plan-estimate-backup`).

## 15. Sources (official Oracle documentation, read 2026-10-03)

- Details for Object Storage, Archive Storage, and Data Transfer (IAM policy reference):
  https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm
- Common Policies ("Let users write objects to Object Storage buckets"):
  https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/commonpolicies.htm
- Using Retention Rules: https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingretentionrules.htm
- Object Versioning: https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning.htm
- Object Storage overview (encryption, limits incl. PutObject 50 GiB):
  https://docs.oracle.com/en-us/iaas/Content/Object/Concepts/objectstorageoverview.htm
- Calling Services from an Instance (instance principals):
  https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/callingservicesfrominstances.htm
- Writing Matching Rules to Define Dynamic Groups:
  https://docs.oracle.com/en-us/iaas/Content/Identity/dynamicgroups/Writing_Matching_Rules_to_Define_Dynamic_Groups.htm
- Amazon S3 Compatibility API: https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/s3compatibleapi.htm
- Always Free Resources: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
