"""Stage 17C — the first content of the knowledge base: the provisions the contract template cites.

The entries were prepared by the program: title, place in the act, tags, link to the source and (17C.1) a draft of the key points
(summary_pl, explanation_ru), which the owner and the lawyer check and approve (Q4, 2026-10-11); until then every
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


def test_a_draft_says_what_is_left_to_check():
    # the key points written by the program (17C.1) are a draft too, until the owner or the lawyer checks them
    for entry in CATALOG.entries:
        if entry.status == "DRAFT":
            assert any(n.ref == "UNVERIFIED" and n.status == "OPEN" for n in entry.review_notes), entry.code


def test_every_entry_tells_its_key_points_in_both_languages():
    for entry in CATALOG.entries:
        assert entry.summary_pl and entry.explanation_ru, entry.code


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


# --- Stage 17E: the contextual links -------------------------------------------------------------------------------------------


def test_every_risk_and_its_client_phrase_has_a_basis():
    from app.domain.data.risk_rules import build_baseline_risk_rules

    by_place = {(link.target_kind, link.target): link.entries for link in CATALOG.links}
    for rule in build_baseline_risk_rules():
        entries = by_place[("RISK", rule.code)]
        assert entries[0] == "KC.634"  # the duty to tell the customer about what may hinder the work
        assert ("KC.557" in entries) == rule.warranty_exclusion_candidate  # the customer's knowledge only where a warranty exclusion is possible
        assert by_place[("PHRASE", f"COMM_RISK_{rule.code}")] == entries


def test_the_documents_that_carry_a_decision_or_a_downtime_name_their_basis():
    by_place = {(link.target_kind, link.target): link.entries for link in CATALOG.links}
    assert by_place[("DOCUMENT", "DECISION_PROTOCOL")] == ["KC.634", "KC.557"]
    assert set(by_place[("DOCUMENT", "DOWNTIME_NOTICE")]) == set(by_place[("DOCUMENT", "DOWNTIME_PROTOCOL")]) == {"KC.639", "KC.640"}
    assert "KC.627" in by_place[("DOCUMENT", "CONTRACT")]
