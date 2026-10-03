"""Backup execution package (Stage 14D.2C).

Runs only in the dedicated backup image (`backend/Dockerfile.backup`), never
in the web backend: it does not import `app.main` and has no web, migration
or server entrypoint. `docs/STAGE_14D_BACKUP_RESTORE_PLAN.md` §16.
"""
