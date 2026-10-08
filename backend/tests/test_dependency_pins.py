"""Stage 14C.7B — production dependency pin guard.

requirements.txt (installed by backend/Dockerfile) is the single source of
truth: every entry must be an exact `==` pin, the transitive packages the
application imports directly (or whose drift would change the runtime
contract) must be pinned explicitly, and the installed environment must
match. Run inside a built image to reject a drifted build before deployment:

    docker run --rm --network none <image> python -m pytest -q tests/test_dependency_pins.py

No network access; no second version table lives here.
"""

import re
from importlib import metadata
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

REQUIREMENTS = Path(__file__).resolve().parents[1] / "requirements.txt"

# Imported directly by app code or part of the runtime contract, yet only
# transitive dependencies of the declared packages.
REQUIRED_EXPLICIT = (
    "starlette", "anyio", "botocore", "greenlet", "s3transfer",
    # Stage 15: the PDF rendering chain (the output depends on every package of it)
    "jinja2", "markupsafe", "weasyprint", "pydyf", "tinycss2", "tinyhtml5", "cssselect2", "fonttools", "pyphen", "cffi",
    "tzdata",
)

PIN = re.compile(
    r"^(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
    r"(?:\[(?P<extras>[A-Za-z0-9._-]+(?:\s*,\s*[A-Za-z0-9._-]+)*)\])?"
    r"\s*==\s*(?P<version>[A-Za-z0-9.+!_-]+)$"
)


def normalize(name: str) -> str:
    """PEP 503 name normalization (case, '-', '_' and '.' are equivalent)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_pin(line: str) -> tuple[str, tuple[str, ...], str]:
    match = PIN.match(line)
    if match is None:
        raise ValueError(f"not an exact == pin: {line!r}")
    extras = tuple(e.strip() for e in match["extras"].split(",")) if match["extras"] else ()
    return normalize(match["name"]), extras, match["version"]


def requirement_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def pins() -> dict[str, tuple[tuple[str, ...], str]]:
    result: dict[str, tuple[tuple[str, ...], str]] = {}
    for line in requirement_lines(REQUIREMENTS.read_text()):
        name, extras, version = parse_pin(line)
        assert name not in result, f"duplicate requirement: {name}"
        result[name] = (extras, version)
    return result


# --- parser behaviour (synthetic input, not a version table) -------------------------


@pytest.mark.parametrize(
    "line, expected",
    [
        ("uvicorn[standard]==1.2.3", ("uvicorn", ("standard",), "1.2.3")),
        ("sqlalchemy[asyncio]==2.1.1", ("sqlalchemy", ("asyncio",), "2.1.1")),
        ("pkg[a, b]==1.0", ("pkg", ("a", "b"), "1.0")),
        ("PyJWT==2.15.0", ("pyjwt", (), "2.15.0")),
        ("Pillow == 12.3.0", ("pillow", (), "12.3.0")),
        ("python_multipart==0.0.32", ("python-multipart", (), "0.0.32")),
        ("Zope.Interface==6.0", ("zope-interface", (), "6.0")),
        ("python-dateutil==2.9.0.post0", ("python-dateutil", (), "2.9.0.post0")),
    ],
)
def test_parse_pin_handles_extras_and_normalization(line, expected):
    assert parse_pin(line) == expected


@pytest.mark.parametrize(
    "line",
    [
        "fastapi>=0.110.0",
        "fastapi>=0.110.0,<1.0.0",
        "fastapi~=0.141.0",
        "fastapi",
        "fastapi==0.141.*x",
        "fastapi===0.141.1",
        "uvicorn[standard]",
        "-r other.txt",
        "git+https://example.invalid/pkg.git",
    ],
)
def test_parse_pin_rejects_non_exact_requirements(line):
    with pytest.raises(ValueError):
        parse_pin(line)


def test_comments_and_blank_lines_are_ignored():
    text = (
        "# Production manifest header\n"
        "\n"
        "# Web framework / ASGI server\n"
        "fastapi==1.0  # inline note\n"
        "   \n"
        "#x==1\n"
        "  # indented comment\n"
        "uvicorn[standard]==0.54.0 # extras + inline comment\n"
    )
    lines = requirement_lines(text)
    assert lines == ["fastapi==1.0", "uvicorn[standard]==0.54.0"]
    assert [parse_pin(line) for line in lines] == [
        ("fastapi", (), "1.0"),
        ("uvicorn", ("standard",), "0.54.0"),
    ]


# --- the real manifest ----------------------------------------------------------------


def test_every_production_requirement_is_an_exact_pin():
    lines = requirement_lines(REQUIREMENTS.read_text())
    assert lines, "requirements.txt is empty"
    bad = [line for line in lines if PIN.match(line) is None]
    assert not bad, f"non-exact requirements: {bad}"


def test_directly_used_transitive_packages_are_pinned_explicitly():
    pinned = pins()
    missing = [name for name in REQUIRED_EXPLICIT if normalize(name) not in pinned]
    assert not missing, f"must be pinned explicitly in requirements.txt: {missing}"


def test_installed_versions_match_requirements():
    mismatches = []
    for name, (_extras, version) in pins().items():
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            mismatches.append(f"{name}: not installed (pinned {version})")
            continue
        if Version(installed) != Version(version):
            mismatches.append(f"{name}: installed {installed}, pinned {version}")
    assert not mismatches, "environment does not match requirements.txt: " + "; ".join(mismatches)


def test_pinned_extras_are_installed():
    """uvicorn[standard] / sqlalchemy[asyncio] must actually bring their extras."""
    for name, (extras, _version) in pins().items():
        for extra in extras:
            needed = [
                req
                for req in map(Requirement, metadata.requires(name) or [])
                if req.marker is not None
                and "extra" in str(req.marker)
                and req.marker.evaluate({"extra": extra})
            ]
            assert needed, f"{name} declares no extra {extra!r} for this platform"
            for req in needed:
                try:
                    metadata.version(req.name)
                except metadata.PackageNotFoundError:
                    pytest.fail(f"{name}[{extra}] dependency {req.name} is not installed")
