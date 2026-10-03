"""Stage 14D.2D.5 — Compose / runtime E2E proof helpers (owner-run; never part of production paths).

- `bind_ops`   runs INSIDE the real `backup` Compose service (entrypoint override only; all service
               hardening stays in force): self-inspection, egress check, renameat2 promotion proof,
               lock hold / try against the real /backup bind.
- `scratch`    runs in a separate tool container on the proof network: scratch database setup,
               independent decrypt / restore verification, tagged-session check.
- `check_host` runs on the HOST with the standard library only: bind persistence and
               `docker inspect` assertions.
"""
