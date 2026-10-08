"""Stage 15B — HTML -> PDF in a separate, resource-limited process.

PDF facts (A4, Polish and Cyrillic text, embedded font, page numbering, repeated table header), process isolation (another
process, a minimal environment, gone afterwards), safety (no network, no file outside the document's own), limits (HTML,
assets, pages, PDF size, time, memory), one render at a time, cancellation, and the temporary directory in every outcome.
"""

import asyncio
import io
import os
import socket
import time
from datetime import date
from decimal import Decimal

import pytest
from PIL import Image
from pypdf import PdfReader

from app.domain.documents.layout import DocumentLayout, DocumentMeta, Party
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.documents.renderer import (
    DocumentRenderer,
    RenderedPdf,
    RenderLimits,
    worker_environment,
)
from app.domain.documents.templating import render_html
from app.domain.exceptions import (
    DocumentRenderBusyError,
    DocumentRenderError,
    DocumentRenderTimeoutError,
    DocumentTemplateError,
    DocumentTooLargeError,
)

LAYOUT = DocumentLayout(
    DocumentMeta("Strona kontrolna", date(2026, 10, 8), "KO/2026/10/0001", "Kraków"),
    Party("Jan Kowalski", "123-456-78-90", ("ul. Długa 1", "30-001 Kraków"), "+48 600 100 200", "jan@example.pl"),
    Party("Иван Петров"),
    signatures=True,
)


def html_with(rows: int = 3, image: str | None = None) -> str:
    sample = [{"note": "x", "quantity": Decimal("12.5"), "amount": Decimal("1234.5")}] * rows
    return render_html(get_template(DocumentKind.DIAGNOSTIC), {"layout": LAYOUT, "rows": sample, "image": image})


def png(color=(200, 30, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(buffer, format="PNG")
    return buffer.getvalue()


def reader(rendered: RenderedPdf) -> PdfReader:
    return PdfReader(io.BytesIO(rendered.pdf))


@pytest.fixture
def renderer(tmp_path):
    return DocumentRenderer(RenderLimits(timeout_seconds=60, wait_seconds=30), temp_dir=tmp_path)


def leftovers(tmp_path) -> list[str]:
    return sorted(path.name for path in tmp_path.iterdir())


# --- the PDF ----------------------------------------------------------------------------


async def test_the_pdf_is_a_valid_a4_document_with_polish_and_cyrillic_text(renderer):
    rendered = await renderer.render(html_with(70))
    assert rendered.pdf.startswith(b"%PDF-") and rendered.byte_size == len(rendered.pdf)
    pdf = reader(rendered)
    assert len(pdf.pages) == rendered.pages >= 3
    width, height = float(pdf.pages[0].mediabox.width), float(pdf.pages[0].mediabox.height)
    assert (round(width), round(height)) == (595, 842)  # A4 in points
    first = pdf.pages[0].extract_text()
    for expected in ("zażółć gęślą jaźń", "ZAŻÓŁĆ GĘŚLĄ JAŹŃ", "Съешь ещё этих мягких французских булок", "Иван Петров",
                     "Jan Kowalski", "Wykonawca".upper(), "ZAMAWIAJĄCY", "08.10.2026", "KO/2026/10/0001", "12,50 m²", "1 234,50 zł"):
        assert expected.replace(" ", "") in first.replace(" ", "").replace(" ", ""), expected


async def test_every_page_is_numbered_and_carries_the_document_number(renderer):
    rendered = await renderer.render(html_with(70))
    pdf = reader(rendered)
    for number, page in enumerate(pdf.pages, start=1):
        text = " ".join(page.extract_text().split())
        assert f"Strona {number} z {rendered.pages}" in text
        assert "KO/2026/10/0001 · Strona kontrolna" in text


async def test_the_table_header_repeats_on_each_page_and_the_signatures_end_the_document(renderer):
    rendered = await renderer.render(html_with(70))
    pdf = reader(rendered)
    for page in pdf.pages:
        assert "Pozycja" in page.extract_text() and "Kwota" in page.extract_text()
    assert "Podpis wykonawcy" in pdf.pages[-1].extract_text() and "Podpis zamawiającego" in pdf.pages[-1].extract_text()


async def test_the_font_is_embedded_so_the_document_looks_the_same_everywhere(renderer):
    pdf = reader(await renderer.render(html_with(3)))
    fonts = {str(font.get_object()["/BaseFont"]) for page in pdf.pages for font in page["/Resources"]["/Font"].values()}
    assert fonts and all("DejaVu-Sans" in name for name in fonts), fonts
    descendants = [font.get_object()["/DescendantFonts"][0].get_object() for page in pdf.pages for font in page["/Resources"]["/Font"].values()]
    descriptors = [d["/FontDescriptor"].get_object() for d in descendants]
    assert descriptors and all("/FontFile2" in d for d in descriptors)  # the glyphs travel inside the PDF (TrueType program)


async def test_the_same_input_gives_the_same_structure_and_text(renderer):
    first, second = await renderer.render(html_with(40)), await renderer.render(html_with(40))
    assert first.pages == second.pages
    assert [p.extract_text() for p in reader(first).pages] == [p.extract_text() for p in reader(second).pages]


async def test_the_result_describes_the_pdf(renderer):
    import hashlib

    rendered = await renderer.render(html_with(3))
    assert rendered.sha256 == hashlib.sha256(rendered.pdf).hexdigest() and rendered.render_seconds > 0 and rendered.pages == 1


# --- images -----------------------------------------------------------------------------


async def test_the_documents_own_images_are_embedded(renderer):
    rendered = await renderer.render(html_with(1, image="photo.png"), {"photo.png": png()})
    assert len(reader(rendered).pages[0].images) == 1


async def test_without_the_asset_the_image_is_simply_missing(renderer):
    rendered = await renderer.render(html_with(1, image="photo.png"))  # referenced but not supplied
    assert len(reader(rendered).pages[0].images) == 0


# --- safety: no network, no foreign file ---------------------------------------------------------


async def test_a_template_cannot_make_the_renderer_fetch_a_url_or_read_a_server_file(renderer, tmp_path_factory):
    secret = tmp_path_factory.mktemp("secret") / "secret.png"
    secret.write_bytes(png((1, 2, 3)))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    listener.setblocking(False)
    port = listener.getsockname()[1]
    html = html_with(1).replace(
        "</body>",
        f'<img src="http://127.0.0.1:{port}/x.png"><img src="file://{secret}"><img src="file:///etc/hostname">'
        f'<img src="//127.0.0.1:{port}/y.png"><div style="background:url(http://127.0.0.1:{port}/z.png)">z</div>'
        f'<link rel="stylesheet" href="http://127.0.0.1:{port}/c.css"></body>',
    )
    try:
        rendered = await renderer.render(html)
        with pytest.raises(BlockingIOError):
            listener.accept()  # nothing connected to the listener
    finally:
        listener.close()
    assert len(reader(rendered).pages[0].images) == 0  # none of the foreign images got in


async def test_the_data_uri_of_the_document_itself_is_allowed(renderer):
    import base64

    data = base64.b64encode(png()).decode()
    rendered = await renderer.render(html_with(1).replace("</body>", f'<img src="data:image/png;base64,{data}"></body>'))
    assert len(reader(rendered).pages[0].images) == 1


async def test_a_path_that_climbs_out_of_the_assets_is_refused(renderer, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "o.png"
    outside.write_bytes(png())
    html = html_with(1).replace("</body>", f'<img src="assets/../../../..{outside}"></body>')
    rendered = await renderer.render(html, {"ok.png": png()})
    assert len(reader(rendered).pages[0].images) == 0


def test_the_render_process_inherits_no_application_secret(monkeypatch, tmp_path):
    for name in ("DATABASE_URL", "TELEGRAM_BOT_TOKEN", "JWT_SECRET_KEY", "MEDIA_S3_SECRET_ACCESS_KEY", "MEDIA_S3_ACCESS_KEY_ID"):
        monkeypatch.setenv(name, "secret-value")
    environment = worker_environment(tmp_path)
    assert "secret-value" not in "".join(environment.values())
    assert set(environment) == {"PATH", "PYTHONPATH", "LANG", "HOME", "XDG_CACHE_HOME"}
    assert environment["HOME"] == str(tmp_path)


# --- process isolation ----------------------------------------------------------------------


async def test_the_pdf_is_made_by_another_process_that_is_gone_afterwards(renderer):
    rendered = await renderer.render(html_with(1))
    assert rendered.worker_pid != os.getpid() and rendered.worker_pid == renderer.last_worker_pid
    with pytest.raises(ProcessLookupError):
        os.kill(rendered.worker_pid, 0)


# --- limits -------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["../x.png", "a/b.png", ".hidden.png", "", "x" * 101 + ".png", "sp ace.png", "ü.png", "a\x00.png"])
async def test_asset_names_are_checked(renderer, name):
    with pytest.raises(DocumentTemplateError, match="not allowed"):
        await renderer.render(html_with(1), {name: png()})


async def test_the_html_size_limit(tmp_path):
    small = DocumentRenderer(RenderLimits(max_html_bytes=2000), temp_dir=tmp_path)
    with pytest.raises(DocumentTooLargeError, match="HTML"):
        await small.render(html_with(1))
    assert leftovers(tmp_path) == []


async def test_the_asset_count_and_size_limits(tmp_path):
    many = DocumentRenderer(RenderLimits(max_assets=2), temp_dir=tmp_path)
    with pytest.raises(DocumentTooLargeError, match="too many"):
        await many.render(html_with(1), {f"{n}.png": png() for n in range(3)})
    heavy = DocumentRenderer(RenderLimits(max_asset_bytes=100), temp_dir=tmp_path)
    with pytest.raises(DocumentTooLargeError, match="images are too large"):
        await heavy.render(html_with(1), {"a.png": png()})
    assert leftovers(tmp_path) == []


async def test_the_page_limit(tmp_path):
    renderer = DocumentRenderer(RenderLimits(max_pages=2), temp_dir=tmp_path)
    with pytest.raises(DocumentTooLargeError, match="pages"):
        await renderer.render(html_with(70))
    assert leftovers(tmp_path) == []
    assert (await renderer.render(html_with(2))).pages == 1  # the limit refuses only what exceeds it


async def test_the_pdf_size_limit(tmp_path):
    renderer = DocumentRenderer(RenderLimits(max_pdf_bytes=1000), temp_dir=tmp_path)
    with pytest.raises(DocumentTooLargeError, match="PDF"):
        await renderer.render(html_with(3))
    assert leftovers(tmp_path) == []


async def test_a_render_that_takes_too_long_is_killed_at_once(tmp_path):
    # A document that needs many seconds: only a real kill ends the call quickly (a worker left alone would run on).
    renderer = DocumentRenderer(RenderLimits(timeout_seconds=0.6), temp_dir=tmp_path)
    started = time.monotonic()
    with pytest.raises(DocumentRenderTimeoutError):
        await renderer.render(html_with(2500))
    assert time.monotonic() - started < 3, "the render process was not killed"
    with pytest.raises(ProcessLookupError):
        os.kill(renderer.last_worker_pid, 0)  # killed and reaped
    assert leftovers(tmp_path) == []


async def test_a_render_that_needs_too_much_memory_fails_cleanly(tmp_path):
    renderer = DocumentRenderer(RenderLimits(memory_mb=64), temp_dir=tmp_path)
    with pytest.raises(DocumentRenderError) as caught:
        await renderer.render(html_with(70))
    assert type(caught.value) is DocumentRenderError and "the render process failed" in str(caught.value)
    assert "<html" not in str(caught.value)  # the message never repeats the document
    with pytest.raises(ProcessLookupError):
        os.kill(renderer.last_worker_pid, 0)
    assert leftovers(tmp_path) == []


# --- one at a time, cancellation, cleanup ---------------------------------------------------------


async def test_a_second_caller_gets_busy_when_the_slot_stays_taken(tmp_path):
    renderer = DocumentRenderer(RenderLimits(wait_seconds=0.05), temp_dir=tmp_path)
    await renderer._slot.acquire()
    try:
        with pytest.raises(DocumentRenderBusyError):
            await renderer.render(html_with(1))
    finally:
        renderer._slot.release()
    assert (await renderer.render(html_with(1))).pages == 1  # free again
    assert leftovers(tmp_path) == []


async def test_two_renders_at_once_run_one_after_the_other(tmp_path):
    renderer = DocumentRenderer(RenderLimits(wait_seconds=30), temp_dir=tmp_path)
    spans: list[tuple[float, float]] = []
    original = renderer._run_worker

    async def timed(workdir):
        started = time.monotonic()
        try:
            return await original(workdir)
        finally:
            spans.append((started, time.monotonic()))

    renderer._run_worker = timed  # type: ignore[method-assign]
    first, second = await asyncio.gather(renderer.render(html_with(8)), renderer.render(html_with(8)))
    assert first.worker_pid != second.worker_pid and first.pages == second.pages
    (_, a_end), (b_start, _) = sorted(spans)
    assert a_end <= b_start, "the two renders overlapped"


async def test_a_cancelled_render_kills_its_process_and_frees_the_slot(tmp_path):
    renderer = DocumentRenderer(RenderLimits(timeout_seconds=60), temp_dir=tmp_path)
    task = asyncio.create_task(renderer.render(html_with(70)))
    for _ in range(200):
        if renderer.last_worker_pid is not None:
            break
        await asyncio.sleep(0.01)
    assert renderer.last_worker_pid is not None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(ProcessLookupError):
        os.kill(renderer.last_worker_pid, 0)
    assert leftovers(tmp_path) == [] and not renderer._slot.locked()
    assert (await renderer.render(html_with(1))).pages == 1


async def test_the_temporary_directory_is_removed_after_a_success(renderer, tmp_path):
    await renderer.render(html_with(1, image="a.png"), {"a.png": png()})
    assert leftovers(tmp_path) == []


# --- the resource fetcher on its own (defence in depth: its own rule AND the protocol list) ---------------------


def test_the_restricted_fetcher_refuses_everything_but_data_and_the_documents_own_files(tmp_path):
    from app.domain.documents.render_worker import RestrictedFetcher

    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "ok.png").write_bytes(png())
    (tmp_path / "outside.png").write_bytes(png())
    fetcher = RestrictedFetcher((assets,))
    assert fetcher._allowed_protocols == {"file", "data"}  # the second line of defence: the protocol list itself
    for refused in ("http://example.org/x.png", "https://example.org/x.png", "ftp://example.org/x.png", "gopher://x/",
                    f"file://{tmp_path}/outside.png", f"file://{assets}/../outside.png", "file://remote-host/etc/passwd",
                    f"file://{assets}/missing.png", f"file://{assets}", "/etc/passwd", "relative/x.png", ""):
        with pytest.raises((ValueError, OSError)):
            fetcher.fetch(refused)
    assert fetcher.fetch(f"file://{assets}/ok.png").read() == png()
    assert fetcher.fetch("data:text/plain;base64,aGk=").read() == b"hi"
