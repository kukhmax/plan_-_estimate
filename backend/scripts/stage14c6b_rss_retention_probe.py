#!/usr/bin/env python3
"""Stage 14C.6B — RSS retention probe for the image pipeline.

Processes the same input N times sequentially in ONE process (as the single
processing slot does in production) and prints the resident set size after
each iteration (after gc), plus the peak. The question is "does RSS grow
without bound across operations?", not "does Python return all memory to
the OS?" (allocator retention of one working set is expected).

The input must be a temporary, owner-supplied or generated image outside Git.

Usage (from backend/):
    .venv/bin/python scripts/stage14c6b_rss_retention_probe.py --input /tmp/x.png --iterations 20
"""

import argparse
import gc
import os
import resource
import shutil
import sys
import tempfile
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

PAGE = os.sysconf("SC_PAGE_SIZE")


def rss_mb() -> float:
    with open("/proc/self/statm") as fh:
        return int(fh.read().split()[1]) * PAGE / 1e6


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()

    from app.domain.photos.image_processing import ImagePipelineConfig, process_image_file

    config = ImagePipelineConfig()
    work = Path(tempfile.mkdtemp(prefix="pe-photo-rssprobe-"))
    try:
        gc.collect()
        start = rss_mb()
        print(f"input {args.input.name} ({args.input.stat().st_size:,} B); start RSS {start:.1f} MB")
        samples = []
        for i in range(1, args.iterations + 1):
            ws = work / str(i)
            ws.mkdir()
            t = time.perf_counter()
            process_image_file(args.input, ws, config)
            elapsed = time.perf_counter() - t
            shutil.rmtree(ws)
            gc.collect()
            samples.append(rss_mb())
            print(f"  iter {i:>2}: {elapsed:5.2f} s  RSS after gc {samples[-1]:7.1f} MB")
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # KiB -> MiB (Linux)
        first_half, second_half = samples[: len(samples) // 2], samples[len(samples) // 2:]
        print(f"peak RSS {peak:.1f} MiB | after-gc RSS: first {samples[0]:.1f}, last {samples[-1]:.1f}, "
              f"max {max(samples):.1f} MB | mean 1st half {sum(first_half) / len(first_half):.1f}, "
              f"2nd half {sum(second_half) / len(second_half):.1f} MB")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
