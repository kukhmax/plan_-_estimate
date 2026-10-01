"""Stage 14C.4 — production templates: compose / env example defaults and
the route-scoped Caddy request-body cap. (The Caddyfile was also validated
with the real Caddy binaries; see docs/development-progress.md.)"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CADDYFILE = (ROOT / "Caddyfile").read_text()


def test_compose_wires_request_limit_and_keeps_uploads_off():
    env = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text())["services"]["backend"]["environment"]
    assert env["PHOTO_MAX_REQUEST_BYTES"] == "${PHOTO_MAX_REQUEST_BYTES:-27000000}"
    assert env["PHOTO_MAX_UPLOAD_BYTES"] == "${PHOTO_MAX_UPLOAD_BYTES:-25000000}"
    assert env["PHOTO_UPLOADS_ENABLED"] == "${PHOTO_UPLOADS_ENABLED:-false}"


def test_env_example_has_request_limit_and_uploads_off():
    lines = (ROOT / ".env.production.example").read_text().splitlines()
    assert "PHOTO_MAX_REQUEST_BYTES=27000000" in lines
    assert "PHOTO_UPLOADS_ENABLED=false" in lines


def test_caddy_caps_only_the_upload_route():
    block = re.search(r"@photo_upload \{(.*?)\n    \}", CADDYFILE, re.S).group(1)
    assert "method POST" in block
    assert r"path_regexp ^/api/projects/[^/]+/photos$" in block
    handle = re.search(r"handle @photo_upload \{(.*?)\n    \}\n", CADDYFILE, re.S).group(1)
    assert re.search(r"request_body \{\s*max_size 27000000\s*\}", handle)
    assert "reverse_proxy backend:8000" in handle
    assert CADDYFILE.count("max_size") == 1  # no global body limit


def test_caddy_upload_handle_precedes_generic_api_and_spa():
    upload = CADDYFILE.index("handle @photo_upload")
    api = CADDYFILE.index("handle @api")
    spa = CADDYFILE.index("    handle {")
    assert upload < api < spa
    assert "@api path /api/*" in CADDYFILE and "reverse_proxy frontend:80" in CADDYFILE
