"""Stage 14B.4 — non-secret production templates and compose wiring."""

import re
from pathlib import Path

import yaml

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.prod.yml"
EXAMPLE = ROOT / ".env.production.example"
MEDIA_PREFIXES = ("MEDIA_", "PHOTO_")
MEDIA_SETTINGS = sorted(n for n in Settings.model_fields if n.startswith(MEDIA_PREFIXES))


def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text())


def resolve_default(value: str) -> str:
    """${VAR:-default} -> default (what the container gets when unset)."""
    match = re.fullmatch(r"\$\{(\w+):-(.*)\}", str(value))
    assert match, f"expected ${{VAR:-default}} form, got {value!r}"
    return match.group(2)


def example_values() -> dict[str, str]:
    values = {}
    for line in EXAMPLE.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def test_media_settings_wired_to_backend_only():
    services = compose()["services"]
    backend_env = services["backend"]["environment"]
    assert sorted(k for k in backend_env if k.startswith(MEDIA_PREFIXES)) == MEDIA_SETTINGS
    for name, service in services.items():
        if name == "backend":
            continue
        env = service.get("environment") or {}
        keys = env.keys() if isinstance(env, dict) else [e.split("=")[0] for e in env]
        assert not [k for k in keys if k.startswith(MEDIA_PREFIXES)], name
        assert "MEDIA_" not in str(service.get("build", "")), name


def test_no_new_ports_or_build_args_for_backend():
    services = compose()["services"]
    assert "ports" not in services["backend"]
    build = services["backend"].get("build", {})
    assert "args" not in build  # credentials are runtime environment only


def test_compose_defaults_start_safely_with_media_disabled():
    backend_env = compose()["services"]["backend"]["environment"]
    env = {k: resolve_default(v) for k, v in backend_env.items() if k.startswith(MEDIA_PREFIXES)}
    settings = Settings(_env_file=None, **env)
    assert settings.MEDIA_STORAGE_BACKEND == "disabled"
    assert settings.PHOTO_UPLOADS_ENABLED is False
    assert settings.MEDIA_STORAGE_NAME == "r2-primary"
    assert settings.PHOTO_MAX_UPLOAD_BYTES == 25_000_000
    assert settings.PHOTO_MAX_DECODED_PIXELS == 60_000_000
    assert settings.PHOTO_PROCESSING_WAIT_SECONDS == 30
    assert settings.PHOTO_TEMP_STALE_AFTER_SECONDS == 86400
    assert env["MEDIA_S3_SECRET_ACCESS_KEY"] == "" and env["MEDIA_S3_ACCESS_KEY_ID"] == ""


def test_example_has_safe_placeholders_only():
    values = example_values()
    assert sorted(k for k in values if k.startswith(MEDIA_PREFIXES)) == MEDIA_SETTINGS
    assert values["MEDIA_STORAGE_BACKEND"] == "disabled"
    assert values["PHOTO_UPLOADS_ENABLED"] == "false"
    for secretish in ("MEDIA_S3_ACCESS_KEY_ID", "MEDIA_S3_SECRET_ACCESS_KEY", "MEDIA_S3_ENDPOINT_URL", "MEDIA_S3_BUCKET"):
        assert values[secretish] == "", secretish
    text = EXAMPLE.read_text()
    assert not re.search(r"[0-9a-f]{32}", text)  # no Cloudflare account id
    assert "<ACCOUNT_ID>" in text
    Settings(_env_file=None, **{k: v for k, v in values.items() if k.startswith(MEDIA_PREFIXES)})
