"""Stage 14B.3 — the manual benchmark tool works and is safe to run next to
production (tiny scale here; this is not a benchmark)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.photo_benchmark as bench
from scripts.photo_benchmark import CASES, MAX_SYNTHETIC_PIXELS, run_benchmark

BACKEND = Path(__file__).resolve().parent.parent


def test_benchmark_tool_smoke_in_process():
    results = run_benchmark(list(CASES), [], scale=0.02, isolate=False, min_available_mb=0)
    assert [r.case for r in results] == list(CASES)
    for r in results:
        assert r.status == "ok", r
        assert r.duration_s is not None and r.peak_rss_mb and r.display_bytes and r.thumbnail_bytes
    rotated = next(r for r in results if r.case == "exif_rotated")
    w, h = map(int, rotated.display.split("x"))
    assert h > w  # orientation 6 applied


def test_benchmark_tool_smoke_subprocess_with_nice(tmp_path):
    (result,) = run_benchmark(["png_alpha"], [], scale=0.02, isolate=True, tmp_dir=str(tmp_path), min_available_mb=0)
    assert result.status == "ok" and result.peak_rss_mb >= result.baseline_rss_mb
    assert list(tmp_path.iterdir()) == []  # work dir removed


def test_synthetic_cases_within_approved_envelope():
    assert MAX_SYNTHETIC_PIXELS == 60_000_000
    assert all(w * h <= MAX_SYNTHETIC_PIXELS for _, w, h, _, _ in CASES.values())
    for bad in (0, -1, 1.01, 2):
        with pytest.raises(ValueError):
            run_benchmark(["jpeg_12mp"], [], scale=bad, isolate=False)


def test_cases_run_sequentially_with_one_input_on_disk(tmp_path, monkeypatch):
    seen = []
    real_run_one = bench.run_one

    def spy(case, source):
        seen.append(sorted(p.name for p in source.parent.iterdir() if p.is_file()))
        return real_run_one(case, source)

    monkeypatch.setattr(bench, "run_one", spy)
    run_benchmark(list(CASES), [], scale=0.02, isolate=False, tmp_dir=str(tmp_path), min_available_mb=0)
    assert len(seen) == len(CASES)
    assert all(len(files) == 1 for files in seen)  # only the current case's input


def test_low_memory_guard_skips_remaining_cases(monkeypatch):
    monkeypatch.setattr(bench, "mem_available_mb", lambda: 100.0)
    results = run_benchmark(["jpeg_12mp", "near_60mp"], [], scale=0.02, isolate=False, min_available_mb=1536)
    assert [r.status.startswith("skipped") for r in results] == [True, True]


def test_benchmark_child_imports_no_application_startup_or_network_code(tmp_path):
    """The child imports only Pillow/anyio/app.domain.photos — never config,
    database, models, API, boto3/botocore or HTTP clients."""
    code = (
        "import sys, json, runpy; sys.argv=['x','--scale','0.02','--cases','jpeg_12mp'];"
        "import scripts.photo_benchmark as b;"
        "r=b.run_benchmark(['jpeg_12mp'], [], scale=0.02, isolate=False, min_available_mb=0); assert r[0].status=='ok', r;"
        "print(json.dumps(sorted(m for m in sys.modules)))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, check=True
    ).stdout.strip().splitlines()[-1]
    modules = set(json.loads(out))
    assert "app.domain.photos.image_processing" in modules
    forbidden = ("app.core", "app.models", "app.api", "app.main", "app.domain.services",
                 "sqlalchemy", "asyncpg", "boto3", "botocore", "httpx", "fastapi", "pydantic_settings")
    leaked = sorted(m for m in modules if m.split(".")[0] in forbidden or m.startswith(forbidden))
    assert leaked == []
