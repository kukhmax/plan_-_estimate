"""The render process (Stage 15B): `python -m app.domain.documents.render_worker WORKDIR MEMORY_MB CPU_SECONDS MAX_PDF_BYTES`.

Runs WeasyPrint outside the API process, so a heavy or runaway document can neither stall the event loop nor take the API
down: the caller limits its time (kills the process group) and this process limits its own address space, CPU time and
output size. It reads `WORKDIR/document.html`, writes `WORKDIR/document.pdf` and prints `{"pages": N, "pid": P}`.

Resources: only `data:` URIs, the bundled fonts and the document's own `WORKDIR/assets/*` files are readable. Everything
else (http, ftp, any other file) is refused before it is opened, so a template, a caption or a name cannot make the
renderer fetch a URL or read a file of the server.
"""

import json
import os
import resource
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

from weasyprint import HTML
from weasyprint.urls import URLFetcher

from app.domain.documents.templating import FONTS_DIR


class RestrictedFetcher(URLFetcher):
    def __init__(self, roots: tuple[Path, ...]) -> None:
        super().__init__(timeout=1, allowed_protocols={"file", "data"}, allow_redirects=False)
        self._roots = tuple(root.resolve() for root in roots)

    def fetch(self, url, headers=None):
        if url[:5].lower() == "data:":
            return super().fetch(url, headers)
        parts = urlsplit(url)
        if parts.scheme.lower() != "file" or parts.netloc not in ("", "localhost"):
            raise ValueError("resource refused: only data: URIs and the document's own files are readable")
        path = Path(unquote(parts.path)).resolve()
        if not path.is_file() or not any(path.is_relative_to(root) for root in self._roots):
            raise ValueError("resource refused: outside the document's own files")
        return super().fetch(url, headers)


def apply_limits(memory_mb: int, cpu_seconds: int, max_pdf_bytes: int) -> None:
    resource.setrlimit(resource.RLIMIT_AS, (memory_mb * 1024 * 1024, memory_mb * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_FSIZE, (max_pdf_bytes, max_pdf_bytes))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def main(argv: list[str]) -> int:
    workdir = Path(argv[1]).resolve()
    memory_mb, cpu_seconds, max_pdf_bytes = int(argv[2]), int(argv[3]), int(argv[4])
    html = (workdir / "document.html").read_text(encoding="utf-8")
    apply_limits(memory_mb, cpu_seconds, max_pdf_bytes)
    fetcher = RestrictedFetcher((FONTS_DIR, workdir / "assets"))
    document = HTML(string=html, base_url=workdir.as_uri() + "/", url_fetcher=fetcher).render()
    document.write_pdf(workdir / "document.pdf")
    sys.stdout.write(json.dumps({"pages": len(document.pages), "pid": os.getpid()}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
