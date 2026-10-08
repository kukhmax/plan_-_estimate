"""Stage 15B — document templates: labels, escaping, strictness, registry and the static safety of the template files."""

import re
from datetime import date
from decimal import Decimal

import pytest

from app.domain.documents.labels import LOCALES_DIR, Labels, load_labels
from app.domain.documents.layout import DocumentLayout, DocumentMeta, Party
from app.domain.documents.registry import TEMPLATES, DocumentKind, get_template
from app.domain.documents.templating import FONTS_DIR, TEMPLATES_DIR, render_html
from app.domain.exceptions import DocumentTemplateError

META = DocumentMeta("Dokument", date(2026, 10, 8), "DOC/1", "Kraków")
LAYOUT = DocumentLayout(META, Party("Jan Kowalski", "123-456-78-90", ("ul. Długa 1",), "+48 600", "j@example.pl"), Party("Anna Nowak"))
DIAGNOSTIC = get_template(DocumentKind.DIAGNOSTIC)
ROWS = [{"note": "n", "quantity": Decimal("12.5"), "amount": Decimal("1234.5")}]


def html_of(layout=LAYOUT, **extra):
    return render_html(DIAGNOSTIC, {"layout": layout, "rows": ROWS, "image": None, **extra})


# --- labels -----------------------------------------------------------------------------


def template_sources():
    return {path.name: path.read_text(encoding="utf-8") for path in TEMPLATES_DIR.iterdir()}


def used_label_keys() -> set[str]:
    keys: set[str] = set()
    for text in template_sources().values():
        keys |= set(re.findall(r"""\bt\(\s*['"]([a-z0-9_.]+)['"]""", text))
    return keys


def test_every_label_a_template_uses_exists_and_no_label_is_left_unused():
    labels = load_labels("pl")
    used = used_label_keys()
    assert used, "the scan found no label: the pattern is broken"
    assert used - labels.keys() == set(), "templates use labels that pl.json lacks"
    assert labels.keys() - used == set(), "pl.json holds labels no template uses"


def test_an_unknown_label_is_an_error_not_an_empty_string():
    with pytest.raises(DocumentTemplateError, match="unknown label"):
        Labels()("no.such.label")


def test_label_parameters():
    assert Labels()("diagnostic.sample_row", n=3) == "Przykładowa pozycja dokumentu 3"
    with pytest.raises(DocumentTemplateError, match="parameter"):
        Labels()("diagnostic.sample_row")


def test_only_polish_labels_exist_for_client_documents():
    assert sorted(path.stem for path in LOCALES_DIR.glob("*.json")) == ["pl"]
    with pytest.raises(DocumentTemplateError):
        Labels("ru")


def test_labels_are_polish():
    labels = load_labels("pl")
    assert labels["party.executor"] == "Wykonawca" and labels["party.client"] == "Zamawiający"
    assert labels["doc.page"] == "Strona" and labels["doc.of"] == "z"


# --- html -------------------------------------------------------------------------------


def test_the_page_is_polish_and_carries_the_layout():
    html = html_of()
    assert '<html lang="pl">' in html
    for expected in ("Dokument", "DOC/1", "08.10.2026", "Kraków", "Wykonawca", "Zamawiający", "Jan Kowalski", "123-456-78-90",
                     "ul. Długa 1", "Anna Nowak", "Podpis wykonawcy" if LAYOUT.signatures else "Wykonawca"):
        assert expected in html


def test_signatures_only_when_asked():
    assert "Podpis wykonawcy" not in html_of()
    signed = DocumentLayout(META, LAYOUT.executor, LAYOUT.client, signatures=True)
    assert "Podpis wykonawcy" in html_of(signed) and "Podpis zamawiającego" in html_of(signed)


def test_missing_parties_print_a_marker_not_nothing():
    html = html_of(DocumentLayout(META))
    assert "Wykonawca" not in html and "Zamawiający" not in html  # no parties block at all
    only_client = html_of(DocumentLayout(META, None, Party("Anna Nowak")))
    assert "— brak danych —" in only_client


def test_data_is_escaped_so_a_name_cannot_break_the_page():
    hostile = Party('<script>alert(1)</script> & "x"', "<b>1</b>", ("<i>x</i>",), "<u>1</u>", "<e>@x")
    html = html_of(DocumentLayout(META, hostile, Party("</div><h1>boom</h1>")))
    assert "<script>alert" not in html and "&lt;script&gt;alert(1)&lt;/script&gt; &amp; &#34;x&#34;" in html
    assert "<h1>boom</h1>" not in html and "&lt;/div&gt;&lt;h1&gt;boom&lt;/h1&gt;" in html
    assert "<b>1</b>" not in html and "<i>x</i>" not in html


def test_the_footer_text_is_html_not_css_so_it_cannot_inject_styles():
    meta = DocumentMeta('x"; } body { display:none } /*', date(2026, 10, 8), "N\\1\n2")
    html = html_of(DocumentLayout(meta))
    css = html.split("<style>", 1)[1].split("</style>", 1)[0]
    assert "display:none" not in css and "N\\1" not in css  # the data stays out of the stylesheet


def test_numbers_are_formatted_by_the_template_filters():
    html = html_of()
    assert "12,50 m²" in html and "1 234,50 zł" in html


def test_an_undefined_value_is_an_error():
    with pytest.raises(DocumentTemplateError):
        render_html(DIAGNOSTIC, {"layout": LAYOUT})  # `rows` is missing


def test_a_context_without_a_layout_is_refused():
    with pytest.raises(DocumentTemplateError, match="layout"):
        render_html(DIAGNOSTIC, {"rows": ROWS, "image": None})
    with pytest.raises(DocumentTemplateError, match="layout"):
        render_html(DIAGNOSTIC, {"layout": {"meta": META}, "rows": ROWS, "image": None})


def test_a_float_in_the_data_is_refused_by_the_filter():
    with pytest.raises(TypeError):
        html_of(rows=[{"note": "n", "quantity": 1.5, "amount": Decimal(1)}])


# --- registry and the template files ---------------------------------------------------------------


def test_every_registered_template_exists_and_is_versioned():
    assert DocumentKind.DIAGNOSTIC in TEMPLATES
    for kind, template in TEMPLATES.items():
        assert template.kind is kind and template.version.strip()
        assert (TEMPLATES_DIR / template.file).is_file()


def test_an_unknown_kind_has_no_template():
    with pytest.raises(DocumentTemplateError, match="no template"):
        get_template("CONTRACT")  # type: ignore[arg-type]


def test_templates_load_no_network_resource_and_run_no_script():
    for name, text in template_sources().items():
        assert not re.search(r"https?://", text, re.IGNORECASE), f"{name} references a network URL"
        assert "<script" not in text.lower() and "@import" not in text.lower(), f"{name} loads or runs code"
        assert not re.search(r"""url\(\s*(?!['"]?\{\{ fonts_url)""", text), f"{name} has an url() that is not a bundled font"


def test_the_bundled_fonts_and_their_license_are_present():
    names = {path.name for path in FONTS_DIR.iterdir()}
    assert {"DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "LICENSE-DejaVu.txt"} <= names
    css = (TEMPLATES_DIR / "document.css.j2").read_text(encoding="utf-8")
    for font in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"):
        assert font in css
