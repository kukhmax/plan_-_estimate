"""Stage 17C — the first content of the knowledge base: the provisions the contract template cites.

The entries are skeletons prepared by the program: title, place in the act, tags, link to the source. The key points
(summary_pl, explanation_ru) are written and approved by the owner and the lawyer (Q4, 2026-10-11); until then every
entry stays DRAFT with an open note saying what to check.
"""

import re

from app.domain.contracts.clauses import load_clause_catalog
from app.domain.knowledge.catalog import (
    CATALOG_DIR,
    application_references,
    read_catalog,
)

CATALOG = read_catalog(CATALOG_DIR, application_references())
ARTICLE = re.compile(r"\bart\.\s*\d")


def cited_places() -> set[str]:
    """The places of the contract template whose text cites an article of an act."""
    return {
        f"{section.key}.{clause.n}"
        for section in load_clause_catalog().sections
        for clause in section.clauses
        for variant in clause.variants
        if ARTICLE.search(variant.text_pl)
    }


def test_every_clause_citing_an_article_links_to_the_knowledge_base():
    linked = {link.target for link in CATALOG.links if link.target_kind == "CLAUSE"}
    assert cited_places()  # the template does cite articles; an empty set would make this test pass for nothing
    assert cited_places() <= linked


def test_the_sources_are_the_acts_the_contract_relies_on_each_with_a_link():
    assert {s.code for s in CATALOG.sources} == {"KC", "UPK", "RODO"}
    for source in CATALOG.sources:
        assert source.url and source.url.startswith(("https://isap.sejm.gov.pl/", "https://eur-lex.europa.eu/"))


def test_nothing_is_approved_before_the_owner_and_the_lawyer_check_it():
    assert all(s.status == "DRAFT" for s in CATALOG.sources)
    assert all(e.status == "DRAFT" for e in CATALOG.entries)


def test_a_draft_without_its_key_points_says_what_is_left_to_check():
    for entry in CATALOG.entries:
        if entry.status == "DRAFT" and not entry.summary_pl:
            assert any(n.ref == "UNVERIFIED" and n.status == "OPEN" for n in entry.review_notes), entry.code


def test_every_entry_has_its_place_in_the_act_and_both_titles():
    for entry in CATALOG.entries:
        assert entry.locator and entry.locator.startswith("art.")
        assert entry.title_pl and entry.title_ru and entry.tags


def test_the_contract_places_lead_to_the_provisions_they_cite():
    by_place = {link.target: link.entries for link in CATALOG.links}
    assert by_place["subject.5"] == ["KC.627", "KC.647"]
    assert by_place["warranty.1"] == ["KC.638", "KC.556", "KC.558"]
    assert by_place["consumer_withdrawal.2"] == ["UPK.35"]
    assert by_place["personal_data.1"] == ["RODO.6"]
