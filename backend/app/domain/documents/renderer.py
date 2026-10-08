"""HTML -> PDF in a separate, resource-limited process (Stage 15B).

One render at a time (the server has one OCPU): a second caller waits up to `wait_seconds`, then gets
`DocumentRenderBusyError`. The worker is a child process in its own process group; on a timeout, a cancellation or any
error the whole group is killed and reaped, and the temporary directory is removed. The worker gets a minimal
environment (no database URL, no tokens, no storage keys) and no network use by the templates (see `render_worker`).
"""

import asyncio
import json
import logging
import os
import re
import shutil
import signal
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

from app.domain.exceptions import (
    DocumentRenderBusyError,
    DocumentRenderError,
    DocumentRenderTimeoutError,
    DocumentTemplateError,
    DocumentTooLargeError,
)

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[3]
ASSET_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
STDERR_TAIL = 400


@dataclass(frozen=True, slots=True)
class RenderLimits:
    timeout_seconds: float = 90.0
    wait_seconds: float = 30.0
    memory_mb: int = 2048
    max_pages: int = 200
    max_pdf_bytes: int = 40_000_000
    max_html_bytes: int = 8_000_000
    max_assets: int = 300
    max_asset_bytes: int = 60_000_000

    @classmethod
    def from_settings(cls, settings: "Settings") -> "RenderLimits":
        return cls(
            timeout_seconds=settings.DOCUMENT_RENDER_TIMEOUT_SECONDS,
            wait_seconds=settings.DOCUMENT_RENDER_WAIT_SECONDS,
            memory_mb=settings.DOCUMENT_RENDER_MEMORY_MB,
            max_pages=settings.DOCUMENT_MAX_PAGES,
            max_pdf_bytes=settings.DOCUMENT_MAX_PDF_BYTES,
            max_html_bytes=settings.DOCUMENT_MAX_HTML_BYTES,
            max_assets=settings.DOCUMENT_MAX_ASSETS,
            max_asset_bytes=settings.DOCUMENT_MAX_ASSET_BYTES,
        )


@dataclass(frozen=True, slots=True)
class RenderedPdf:
    pdf: bytes
    pages: int
    sha256: str
    byte_size: int
    render_seconds: float
    worker_pid: int


def worker_environment(workdir: Path) -> dict[str, str]:
    """The render process gets no application secret: no database URL, token or storage key is inherited."""
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "PYTHONPATH": str(BACKEND_DIR),
        "LANG": "C.UTF-8",
        "HOME": str(workdir),
        "XDG_CACHE_HOME": str(workdir),
    }


def _kill_group(process: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # the whole group has already exited


class DocumentRenderer:
    def __init__(self, limits: RenderLimits | None = None, temp_dir: str | os.PathLike[str] | None = None) -> None:
        self.limits = limits or RenderLimits()
        self._temp_dir = None if temp_dir is None else str(temp_dir)
        self._slot = asyncio.Semaphore(1)
        self.last_worker_pid: int | None = None  # of the latest render process (diagnostics and tests)

    def _validate(self, html: str, assets: Mapping[str, bytes]) -> bytes:
        encoded = html.encode("utf-8")
        if len(encoded) > self.limits.max_html_bytes:
            raise DocumentTooLargeError("the document HTML is too large")
        if len(assets) > self.limits.max_assets:
            raise DocumentTooLargeError("the document has too many images")
        if sum(len(data) for data in assets.values()) > self.limits.max_asset_bytes:
            raise DocumentTooLargeError("the document images are too large")
        for name in assets:
            if not ASSET_NAME.match(name) or ".." in name:
                raise DocumentTemplateError(f"asset name {name!r} is not allowed")
        return encoded

    async def render(self, html: str, assets: Mapping[str, bytes] | None = None) -> RenderedPdf:
        assets = assets or {}
        encoded = self._validate(html, assets)
        try:
            async with asyncio.timeout(self.limits.wait_seconds):
                await self._slot.acquire()
        except TimeoutError:
            raise DocumentRenderBusyError("another document is being rendered") from None
        try:
            return await self._render_locked(encoded, assets)
        finally:
            self._slot.release()

    async def _render_locked(self, encoded: bytes, assets: Mapping[str, bytes]) -> RenderedPdf:
        workdir = Path(tempfile.mkdtemp(prefix="pe-doc-", dir=self._temp_dir))
        try:
            (workdir / "document.html").write_bytes(encoded)
            if assets:
                (workdir / "assets").mkdir()
                for name, data in assets.items():
                    (workdir / "assets" / name).write_bytes(data)
            return await self._run_worker(workdir)
        finally:
            shutil.rmtree(workdir, onexc=lambda _func, path, exc: logger.warning("document temp cleanup failed: %s: %s", path, exc))

    async def _run_worker(self, workdir: Path) -> RenderedPdf:
        limits = self.limits
        cpu_seconds = max(1, int(limits.timeout_seconds) + 5)
        started = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "app.domain.documents.render_worker", str(workdir), str(limits.memory_mb),
            str(cpu_seconds), str(limits.max_pdf_bytes + 1_000_000),
            cwd=str(BACKEND_DIR), env=worker_environment(workdir), start_new_session=True,
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        self.last_worker_pid = process.pid
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=limits.timeout_seconds)
        except TimeoutError:
            _kill_group(process)
            await process.wait()
            raise DocumentRenderTimeoutError("the document took too long to render") from None
        except BaseException:
            _kill_group(process)
            await process.wait()
            raise
        _kill_group(process)  # nothing of the worker's group may outlive the render
        if process.returncode == -signal.SIGXFSZ:
            raise DocumentTooLargeError("the PDF is too large")
        if process.returncode != 0:
            tail = stderr.decode("utf-8", errors="replace")[-STDERR_TAIL:].strip()
            raise DocumentRenderError(f"the render process failed (exit {process.returncode}): {tail}")
        try:
            report = json.loads(stdout.decode("utf-8"))
            pages, worker_pid = int(report["pages"]), int(report["pid"])
        except (ValueError, KeyError, TypeError):
            raise DocumentRenderError("the render process gave no result") from None
        if pages > limits.max_pages:
            raise DocumentTooLargeError(f"the document has {pages} pages; the limit is {limits.max_pages}")
        pdf = (workdir / "document.pdf").read_bytes()
        if len(pdf) > limits.max_pdf_bytes:
            raise DocumentTooLargeError("the PDF is too large")
        return RenderedPdf(pdf, pages, sha256(pdf).hexdigest(), len(pdf), time.monotonic() - started, worker_pid)


def renderer_from_settings(settings: "Settings") -> DocumentRenderer:
    return DocumentRenderer(RenderLimits.from_settings(settings))
