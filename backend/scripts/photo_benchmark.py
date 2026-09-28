"""Stage 14B.3 image-pipeline benchmark (manual; not part of the test suite).

Measures, per case: source format / dimensions / byte size, processing wall
time, process peak RSS, and display/thumbnail output sizes.

Safety model (designed to run on a VM that also serves production):

- Imports only the stdlib in the parent; the child imports Pillow, anyio and
  `app.domain.photos` (no application config, database, models, boto3 or
  network code). No network access, no credentials.
- Strictly sequential. For every case: one subprocess generates the synthetic
  input, a second subprocess processes it, then the input is deleted before
  the next case starts. At most one synthetic image exists at a time, and the
  parent process never holds image data.
- Synthetic cases are capped at the approved 60 MP envelope (`--scale` may
  only shrink them).
- Before each case, MemAvailable (Linux) must be at least
  `--min-available-mb` (default 1536); otherwise the remaining cases are
  skipped and reported.
- Children run with `nice` +10 by default so a serving workload keeps CPU
  priority.
- All files live in one `pe-photo-bench-*` temp directory, removed at the end.

Peak RSS: Linux `/proc/self/status` VmHWM of the processing child (fresh
address space; `ru_maxrss` would include a pre-exec parent's peak); other
platforms fall back to `ru_maxrss`. `baseline_rss_mb` is the same child's
peak just before processing, so `peak - baseline` approximates the
pipeline's own peak. A high-water mark is coarse (no allocator detail).

Usage (from backend/, dependencies: Pillow, anyio):

    python scripts/photo_benchmark.py                 # all synthetic cases
    python scripts/photo_benchmark.py --cases jpeg_12mp exif_rotated
    python scripts/photo_benchmark.py --input /tmp/IMG_0001.jpg --json
    python scripts/photo_benchmark.py --scale 0.1     # quick smoke run
"""

import argparse
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

MAX_SYNTHETIC_PIXELS = 60_000_000  # approved decoded-pixel envelope

# name -> (format, width, height, alpha, exif_orientation)
CASES: dict[str, tuple[str, int, int, bool, int | None]] = {
    "jpeg_12mp": ("JPEG", 4000, 3000, False, None),
    "jpeg_48mp": ("JPEG", 8000, 6000, False, None),
    "png_alpha": ("PNG", 4000, 3000, True, None),
    "webp_12mp": ("WEBP", 4000, 3000, False, None),
    "near_60mp": ("JPEG", 10000, 5990, False, None),
    "exif_rotated": ("JPEG", 4000, 3000, False, 6),
}
assert all(w * h <= MAX_SYNTHETIC_PIXELS for _, w, h, _, _ in CASES.values())


@dataclass
class Result:
    case: str
    source_format: str
    source_width: int
    source_height: int
    source_bytes: int
    status: str
    duration_s: float | None = None
    baseline_rss_mb: float | None = None
    peak_rss_mb: float | None = None
    display: str | None = None
    display_bytes: int | None = None
    thumbnail: str | None = None
    thumbnail_bytes: int | None = None
    mem_available_before_mb: float | None = None
    mem_available_after_mb: float | None = None


def _ensure_import_path() -> None:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))


def mem_available_mb() -> float | None:
    """MemAvailable from /proc/meminfo (Linux), else None."""
    try:
        with open("/proc/meminfo", encoding="ascii") as meminfo:
            for line in meminfo:
                if line.startswith("MemAvailable:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    return None


def _peak_rss_mb() -> float:
    try:
        with open("/proc/self/status", encoding="ascii") as status:
            for line in status:
                if line.startswith("VmHWM:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024, 1)


def generate(case: str, directory: Path, scale: float = 1.0) -> Path:
    """Write one synthetic input (smooth gradients + upscaled noise)."""
    _ensure_import_path()
    from PIL import Image

    if not 0 < scale <= 1.0:
        raise ValueError("scale must be in (0, 1]")
    fmt, width, height, alpha, orientation = CASES[case]
    width, height = max(16, int(width * scale)), max(16, int(height * scale))
    if width * height > MAX_SYNTHETIC_PIXELS:
        raise ValueError("synthetic case exceeds the approved pixel envelope")
    red = Image.linear_gradient("L").resize((width, height))
    green = Image.linear_gradient("L").rotate(90).resize((width, height))
    blue = Image.effect_noise((max(1, width // 8), max(1, height // 8)), 64).resize(
        (width, height), Image.Resampling.BILINEAR
    )
    bands = [red, green, blue]
    if alpha:
        bands.append(Image.radial_gradient("L").resize((width, height)))
    image = Image.merge("RGBA" if alpha else "RGB", bands)
    params: dict = {}
    if fmt == "JPEG":
        params["quality"] = 90
        if orientation:
            exif = Image.Exif()
            exif[0x0112] = orientation
            params["exif"] = exif.tobytes()
    elif fmt == "WEBP":
        params["quality"] = 85
    path = directory / f"{case}.{fmt.lower()}"
    image.save(path, format=fmt, **params)
    return path


def run_one(case: str, source: Path) -> Result:
    """Process one file in the current process and measure it."""
    _ensure_import_path()
    from PIL import Image

    from app.domain.photos.image_processing import ImagePipelineConfig, process_image_file

    with Image.open(source) as probe:
        fmt, (width, height) = probe.format or "?", probe.size
    result = Result(case, fmt, width, height, source.stat().st_size, status="ok")
    workspace = Path(tempfile.mkdtemp(prefix="pe-photo-bench-ws-", dir=source.parent))
    try:
        result.baseline_rss_mb = _peak_rss_mb()
        started = time.perf_counter()
        processed = process_image_file(source, workspace, ImagePipelineConfig())
        result.duration_s = round(time.perf_counter() - started, 3)
        result.peak_rss_mb = _peak_rss_mb()
        result.display = f"{processed.display.width}x{processed.display.height}"
        result.display_bytes = processed.display.byte_size
        result.thumbnail = f"{processed.thumbnail.width}x{processed.thumbnail.height}"
        result.thumbnail_bytes = processed.thumbnail.byte_size
    except Exception as exc:  # reported per case, never swallowed silently
        result.status = f"rejected: {type(exc).__name__}"
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    return result


def _child(args: list[str], nice: int) -> subprocess.CompletedProcess:
    def lower_priority() -> None:
        if nice:
            os.nice(nice)

    return subprocess.run(
        [sys.executable, __file__, *args],
        capture_output=True,
        text=True,
        check=False,
        preexec_fn=lower_priority if os.name == "posix" else None,
    )


def _failed(case: str, stage: str, completed: subprocess.CompletedProcess) -> Result:
    tail = (completed.stderr or "").strip().splitlines()[-1:] or [f"exit {completed.returncode}"]
    return Result(case, "?", 0, 0, 0, status=f"{stage} failed: {tail[0][:200]}")


def run_benchmark(
    cases: list[str],
    inputs: list[Path],
    *,
    scale: float = 1.0,
    isolate: bool = True,
    nice: int = 10,
    min_available_mb: float = 1536,
    tmp_dir: str | None = None,
) -> list[Result]:
    if not 0 < scale <= 1.0:
        raise ValueError("scale must be in (0, 1]")
    results: list[Result] = []
    work = Path(tempfile.mkdtemp(prefix="pe-photo-bench-", dir=tmp_dir))
    try:
        jobs: list[tuple[str, Path | None]] = [(case, None) for case in cases]
        jobs += [(f"input:{path.name}", path) for path in inputs]
        for index, (case, given) in enumerate(jobs):
            available = mem_available_mb()
            if available is not None and available < min_available_mb:
                reason = f"skipped: MemAvailable {available} MB < {min_available_mb} MB"
                results.extend(Result(name, "?", 0, 0, 0, status=reason) for name, _ in jobs[index:])
                break
            source = given
            if source is None:
                if isolate:
                    completed = _child(["--generate", case, str(work), str(scale)], nice)
                    if completed.returncode != 0:
                        results.append(_failed(case, "generate", completed))
                        continue
                    source = Path(completed.stdout.strip().splitlines()[-1])
                else:
                    source = generate(case, work, scale)
            try:
                if isolate:
                    completed = _child(["--child", case, str(source)], nice)
                    result = (
                        Result(**json.loads(completed.stdout.strip().splitlines()[-1]))
                        if completed.returncode == 0
                        else _failed(case, "process", completed)
                    )
                else:
                    result = run_one(case, source)
            finally:
                if given is None:
                    source.unlink(missing_ok=True)  # at most one synthetic input on disk
            result.mem_available_before_mb = available
            result.mem_available_after_mb = mem_available_mb()
            results.append(result)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return results


def print_table(results: list[Result]) -> None:
    header = (
        f"{'case':<16}{'fmt':<6}{'source':>12}{'bytes':>11}{'time s':>8}{'base MB':>9}{'peak MB':>9}"
        f"{'display':>11}{'bytes':>9}{'thumb':>9}{'bytes':>8}{'avail MB':>10}  status"
    )
    print(header)
    for r in results:
        print(
            f"{r.case[:15]:<16}{r.source_format:<6}{f'{r.source_width}x{r.source_height}':>12}"
            f"{r.source_bytes:>11}{r.duration_s if r.duration_s is not None else '-':>8}"
            f"{r.baseline_rss_mb or '-':>9}{r.peak_rss_mb or '-':>9}{r.display or '-':>11}"
            f"{r.display_bytes or 0:>9}{r.thumbnail or '-':>9}{r.thumbnail_bytes or 0:>8}"
            f"{r.mem_available_before_mb or '-':>10}  {r.status}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cases", nargs="*", choices=sorted(CASES), default=None)
    parser.add_argument("--input", nargs="*", type=Path, default=[], help="owner-supplied images (outside Git)")
    parser.add_argument("--scale", type=float, default=1.0, help="shrink synthetic dimensions, 0 < scale <= 1")
    parser.add_argument("--nice", type=int, default=10, help="CPU niceness increment for child processes")
    parser.add_argument("--min-available-mb", type=float, default=1536)
    parser.add_argument("--tmp-dir", default=None, help="parent directory for the temporary work dir")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--child", nargs=2, metavar=("CASE", "FILE"), help=argparse.SUPPRESS)
    parser.add_argument("--generate", nargs=3, metavar=("CASE", "DIR", "SCALE"), help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.generate:
        case, directory, scale = args.generate
        print(generate(case, Path(directory), float(scale)))
        return
    if args.child:
        print(json.dumps(asdict(run_one(args.child[0], Path(args.child[1])))))
        return
    if not 0 < args.scale <= 1.0:
        parser.error("--scale must be in (0, 1]")

    cases = args.cases if args.cases is not None else ([] if args.input else list(CASES))
    before = mem_available_mb()
    results = run_benchmark(
        cases,
        args.input,
        scale=args.scale,
        nice=args.nice,
        min_available_mb=args.min_available_mb,
        tmp_dir=args.tmp_dir,
    )
    after = mem_available_mb()
    print(
        f"# python {platform.python_version()} | {platform.machine()} | cpus={os.cpu_count()} | "
        f"nice=+{args.nice} | MemAvailable before={before} MB after={after} MB | "
        f"failed={sum(r.status != 'ok' for r in results)}"
    )
    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2))
    else:
        print_table(results)


if __name__ == "__main__":
    main()
