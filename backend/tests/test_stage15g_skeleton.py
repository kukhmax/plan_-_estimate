"""Stage 15G — skeletons of the contract and the protocols: the structure of a document, never its legal text."""

import io
import re
from datetime import date

import pytest
from pypdf import PdfReader

from app.domain.documents.labels import load_labels
from app.domain.documents.registry import (
    SKELETON_FILE,
    SKELETON_KINDS,
    SKELETON_VERSION,
    TEMPLATES,
    DocumentKind,
    get_template,
)
from app.domain.documents.renderer import DocumentRenderer
from app.domain.documents.skeleton_document import (
    SectionContent,
    SkeletonDocumentService,
    build_skeleton_document,
    document_title,
)
from app.domain.documents.templating import TEMPLATES_DIR
from app.domain.exceptions import (
    DocumentDataError,
    DocumentTemplateError,
    ProjectNotFoundError,
)
from app.domain.services.issued_document_service import NUMBER_PREFIX
from app.models.client import Client, ClientType
from app.models.executor_profile import ExecutorProfile
from app.models.issued_document import IssuedDocumentKind
from app.models.project import Project
from tests.test_stage15d_estimate_document import seed

K = DocumentKind
TODAY = date(2026, 10, 8)
PROJECT = Project(name="Mieszkanie Mokotów", address="ul. Dobra 10/12", city="Warszawa", postal_code="00-001")
CLIENT = Client(client_type=ClientType.PRIVATE_PERSON, first_name="Anna", last_name="Nowak")
EXECUTOR = ExecutorProfile(name="Jan Kowalski Wykończenia", nip="7740001454", city="Kraków")
TITLES = {K.CONTRACT: "Umowa", K.HANDOVER_PROTOCOL: "Protokół przekazania", K.CONCEALED_WORKS_PROTOCOL: "Protokół odbioru robót zanikających",
          K.FINAL_PROTOCOL: "Protokół odbioru końcowego"}


def build(kind=K.CONTRACT, **kw):
    return build_skeleton_document(kind, PROJECT, kw.pop("client", CLIENT), kw.pop("executor", EXECUTOR), issued_on=TODAY, **kw)


def html_of(document) -> str:
    return SkeletonDocumentService.html(document)


# --- the registry ------------------------------------------------------------------------------------------------------------


def test_the_contract_and_the_three_protocols_are_registered_as_skeletons():
    assert set(SKELETON_KINDS) == set(TITLES)
    for kind in SKELETON_KINDS:
        template = get_template(kind)
        assert (template.file, template.version) == (SKELETON_FILE, SKELETON_VERSION) and (TEMPLATES_DIR / template.file).is_file()
        assert len(template.sections) >= 3 and len(set(template.sections)) == len(template.sections)
        assert all(re.fullmatch(r"[a-z]+(_[a-z]+)*", key) for key in template.sections), "section keys are identifiers, not wording"


def test_the_version_fits_the_journal_column():
    assert len(SKELETON_VERSION) <= 16


def test_number_prefixes_are_unique_and_the_journal_uses_the_registry_ones():
    prefixes = [t.number_prefix for t in TEMPLATES.values() if t.number_prefix]
    assert len(prefixes) == len(set(prefixes)) == 7 and all(re.fullmatch(r"[A-Z]{3,6}", p) for p in prefixes)
    assert TEMPLATES[K.DIAGNOSTIC].number_prefix is None  # the control page is never numbered
    assert NUMBER_PREFIX == {IssuedDocumentKind.ESTIMATE: "KOSZ", IssuedDocumentKind.PHOTO_REPORT: "FOTO", IssuedDocumentKind.TECH_CARD: "KART"}
    assert {TEMPLATES[k].number_prefix for k in SKELETON_KINDS} == {"UMOWA", "PRZEK", "ZANIK", "ODBIOR"}


# --- no legal text -----------------------------------------------------------------------------------------------------------------

# Words that would make a label a clause or a quotation. The skeleton may only name things ("Umowa", "Załączniki").
CLAUSE_WORDS = ("§", "art.", "ust.", "kodeks", "ustaw", "rozporządz", "zgodnie z", "obowiązuj", "odpowiada", "odpowiedzialn", "kara", "kary",
                "gwarancj", "rękojm", "pn-", "itb", "din ", "prawo budowlane", "zobowiązuj", "strony ustalaj", "wynagrodzen", "zapłat",
                "termin", "wady", "reklamac", "rozwiąz", "siła wyższa", "poufn", "rodo", "wyłącz")


def skeleton_labels() -> dict[str, str]:
    return {key: text for key, text in load_labels("pl").items() if key.startswith("skeleton.")}


def test_the_skeleton_labels_are_names_and_placeholders_never_clauses():
    labels = skeleton_labels()
    assert len(labels) == 8
    for key, text in labels.items():
        assert len(text) <= 40, f"{key} is long enough to be a sentence"
        assert not text.rstrip().endswith("."), f"{key} reads as a sentence"
        lowered = text.lower()
        assert not [w for w in CLAUSE_WORDS if w in lowered], f"{key}: {text!r}"


def test_the_skeleton_template_has_no_prose_of_its_own():
    source = (TEMPLATES_DIR / SKELETON_FILE).read_text(encoding="utf-8")
    bare = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "", source, flags=re.DOTALL)
    bare = re.sub(r"<[^>]+>", "", bare)
    assert re.sub(r"[\s:.,;()\-–—]+", "", bare) == "", "every word of a skeleton comes from a label or from data"


def test_the_clause_guard_would_catch_a_clause():
    assert [w for w in CLAUSE_WORDS if w in "Wykonawca ponosi odpowiedzialność za wady".lower()]
    assert [w for w in CLAUSE_WORDS if w in "zgodnie z art. 647 Kodeksu cywilnego".lower()]


def test_the_titles_are_only_the_names_of_the_documents():
    for kind, title in TITLES.items():
        assert document_title(kind) == title
    for kind in (K.ESTIMATE, K.PHOTO_REPORT, K.DIAGNOSTIC):
        with pytest.raises(DocumentTemplateError):
            document_title(kind)


# --- the builder ---------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(SKELETON_KINDS, key=lambda k: k.value))
def test_an_empty_skeleton_has_numbered_placeholder_sections_and_nothing_else(kind):
    document = build(kind)
    template = get_template(kind)
    assert [s.key for s in document.sections] == list(template.sections) and [s.number for s in document.sections] == list(range(1, len(template.sections) + 1))
    html = html_of(document)
    assert html.count("— do uzupełnienia —") == len(template.sections)
    for n in range(1, len(template.sections) + 1):
        assert f"<h2>Sekcja {n}</h2>" in html
    assert f"<title>{TITLES[kind]}</title>" in html and "Załączniki" not in html
    assert not any(key in html for key in template.sections), "the internal keys never reach the page"


def test_the_header_the_parties_the_object_and_the_signatures_are_there():
    document = build(K.CONTRACT, number="UMOWA/2026/10/08/1953", sequence=4)
    html = html_of(document)
    for expected in ("UMOWA/2026/10/08/1953", "Nr kolejny dokumentu dla obiektu", "08.10.2026", "Kraków", "Wykonawca", "Jan Kowalski Wykończenia",
                     "774-000-14-54", "Zamawiający", "Anna Nowak", "Mieszkanie Mokotów", "ul. Dobra 10/12", "00-001 Warszawa",
                     "Podpis wykonawcy", "Podpis zamawiającego"):
        assert expected in html, expected
    assert document.layout.signatures and document.layout.executor.tax_id == "774-000-14-54"


def test_a_missing_client_prints_the_marker_and_a_missing_executor_is_refused():
    assert "— brak danych —" in html_of(build(client=None))
    with pytest.raises(DocumentDataError) as caught:
        build(executor=None)
    assert caught.value.reason == "EXECUTOR_PROFILE_REQUIRED"


def test_the_caller_supplies_titles_and_paragraphs_as_data():
    document = build(K.HANDOVER_PROTOCOL, content={
        "site_description": SectionContent("Opis terenu", ("Pierwszy akapit.", "  ", "Drugi akapit.")),
        "remarks": SectionContent(None, ("Tylko treść.",)),
    })
    html = html_of(document)
    assert "<h2>Opis terenu</h2>" in html and "<p>Pierwszy akapit.</p>" in html and "<p>Drugi akapit.</p>" in html
    assert html.count("<p></p>") == 0 and "<p>  </p>" not in html
    assert "<h2>Sekcja 4</h2>" in html and "<p>Tylko treść.</p>" in html  # a section with text but no title keeps its number
    assert html.count("— do uzupełnienia —") == 2  # the two sections nobody filled


def test_data_is_escaped():
    document = build(K.CONTRACT, content={"subject": SectionContent("<script>x</script>", ("<b>a</b> & \"b\"",))},
                     attachments=("<i>Plan</i>",))
    html = html_of(document)
    assert "<script>x" not in html and "<b>a</b>" not in html and "<i>Plan</i>" not in html
    assert "&lt;script&gt;x&lt;/script&gt;" in html and "&lt;b&gt;a&lt;/b&gt; &amp;" in html


def test_a_section_the_kind_does_not_have_is_an_error_with_the_known_ones():
    with pytest.raises(DocumentDataError) as caught:
        build(K.FINAL_PROTOCOL, content={"price": SectionContent("x")})  # a contract section
    assert caught.value.reason == "SKELETON_SECTION_UNKNOWN"
    assert caught.value.details["unknown"] == ["price"] and "defects_found" in caught.value.details["known"]


@pytest.mark.parametrize("kind", [K.ESTIMATE, K.PHOTO_REPORT, K.DIAGNOSTIC])
def test_only_a_skeleton_kind_can_be_built_as_a_skeleton(kind):
    with pytest.raises(DocumentTemplateError):
        build(kind)


def test_attachments_are_listed_and_numbered_only_when_there_are_some():
    html = html_of(build(K.CONTRACT, attachments=("Kosztorys nr 1", "")))
    assert "<h2>Załączniki</h2>" in html and "Załącznik 1</strong>: Kosztorys nr 1" in html and "Załącznik 2</strong></li>" in html
    assert "Załączniki" not in html_of(build(K.CONTRACT))


def test_a_skeleton_has_no_vat_and_no_prices():
    html = html_of(build(K.CONTRACT)).lower()
    assert "vat" not in html and "zł" not in html


# --- from the database and as a PDF -------------------------------------------------------------------------------------------------------


async def test_the_service_builds_from_the_database_for_the_owner_only(db_session):
    owner, project, _ = await seed(db_session, telegram_id=9951)
    stranger, _, _ = await seed(db_session, telegram_id=9952)
    owner_id, project_id, stranger_id = owner.id, project.id, stranger.id
    document = await SkeletonDocumentService(db_session).build(K.CONTRACT, owner_id, project_id, issued_on=TODAY)
    assert document.layout.client.name == "Anna Nowak" and document.layout.executor.tax_id == "774-000-14-54"
    assert document.object_name == "Mokotów" and document.layout.meta.place == "Kraków"
    with pytest.raises(ProjectNotFoundError):
        await SkeletonDocumentService(db_session).build(K.CONTRACT, stranger_id, project_id, issued_on=TODAY)


@pytest.mark.parametrize("kind", sorted(SKELETON_KINDS, key=lambda k: k.value))
async def test_every_skeleton_is_a_valid_pdf_with_signatures_and_page_numbers(db_session, kind):
    owner, project, _ = await seed(db_session, telegram_id=9953)
    rendered = await SkeletonDocumentService(db_session).render(kind, owner.id, project.id, DocumentRenderer(), issued_on=TODAY, number="X/1", sequence=1)
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(rendered.pdf)).pages)
    assert rendered.pdf.startswith(b"%PDF") and rendered.pages >= 1
    for expected in (TITLES[kind], "Sekcja 1", "— do uzupełnienia —", "Podpis wykonawcy", "Podpis zamawiającego", "Jan Kowalski Wykończenia", "Strona 1 z"):
        assert expected in text, expected


async def test_a_long_skeleton_keeps_the_footer_and_numbering_on_every_page():
    document = build(K.CONTRACT, content={"subject": SectionContent("Dane", tuple(f"Akapit numer {n}. " * 12 for n in range(60)))})
    rendered = await DocumentRenderer().render(html_of(document))
    pages = [p.extract_text() for p in PdfReader(io.BytesIO(rendered.pdf)).pages]
    assert rendered.pages >= 3 and all(f"Strona {n} z {rendered.pages}" in page for n, page in enumerate(pages, 1))
