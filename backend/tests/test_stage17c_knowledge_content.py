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
    statutes = [s for s in CATALOG.sources if s.kind == "STATUTE"]
    assert {s.code for s in statutes} == {"KC", "UPK", "RODO"}
    for source in statutes:
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
    kinds = {s.code: s.kind for s in CATALOG.sources}
    for entry in CATALOG.entries:
        assert entry.locator, entry.code
        if kinds[entry.source] == "STATUTE":
            assert entry.locator.startswith("art."), entry.code
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
        legal = [code for code in entries if not code.startswith("TECH.")]
        assert by_place[("PHRASE", f"COMM_RISK_{rule.code}")] == legal  # the phrase carries the law, the risk also its technique


def test_the_documents_that_carry_a_decision_or_a_downtime_name_their_basis():
    by_place = {(link.target_kind, link.target): link.entries for link in CATALOG.links}
    assert by_place[("DOCUMENT", "DECISION_PROTOCOL")] == ["KC.634", "KC.557"]
    assert set(by_place[("DOCUMENT", "DOWNTIME_NOTICE")]) == set(by_place[("DOCUMENT", "DOWNTIME_PROTOCOL")]) == {"KC.639", "KC.640"}
    assert "KC.627" in by_place[("DOCUMENT", "CONTRACT")]


def test_the_titles_say_what_the_provision_says():
    """17E.1: the owner found titles that promised something else than the provision (art. 557 is about the knowledge at the
    conclusion of the contract, art. 639 needs no fault, art. 634 is not only about the customer's material)."""
    titles = {e.code: (e.title_pl, e.title_ru) for e in CATALOG.entries}
    assert "zawarciu umowy" in titles["KC.557"][0] and "заключении договора" in titles["KC.557"][1]
    assert "вине" not in titles["KC.639"][1]
    assert "przeszkodach" in titles["KC.634"][0] and "препятствиях" in titles["KC.634"][1]
    kc = CATALOG.source("KC")
    assert "obowiązuje" in kc.title_pl and "2026" in kc.designation  # the act of 1964 in force, its current consolidated text


# --- Stage 17C.3: the technical basis of the risks ----------------------------------------------------------------------------


def test_every_risk_has_its_own_technical_basis_from_a_norm_itb_or_technical_card():
    from app.domain.data.risk_rules import build_baseline_risk_rules

    kinds = {s.code: s.kind for s in CATALOG.sources}
    entries = {e.code: e for e in CATALOG.entries}
    by_place = {(link.target_kind, link.target): link.entries for link in CATALOG.links}
    for rule in build_baseline_risk_rules():
        technical = [c for c in by_place[("RISK", rule.code)] if kinds[entries[c].source] != "STATUTE"]
        assert technical, rule.code


def test_the_technical_values_agree_with_the_thresholds_of_the_risk_rules():
    """The knowledge base must not say one number and the risk engine fire on another."""
    from app.domain.data.risk_rules import build_baseline_risk_rules

    rules = {r.code: r for r in build_baseline_risk_rules()}
    unevenness = next(c for c in rules["UNEVENNESS_PREP_INCREASED"].conditions if c.finding_key == "UNEVENNESS")
    assert unevenness.value == {"value": "3.000"}
    flatness = CATALOG.entry("TECH.FLATNESS")
    assert "kategorii III" in flatness.summary_pl and "3 mm" in flatness.summary_pl and "2 m" in flatness.summary_pl
    moisture = CATALOG.entry("TECH.MOISTURE")
    assert "3% mierzona metodą karbidową (CM)" in moisture.summary_pl  # the hint of the inspection: > 3% CM for concrete
    assert "1% (CM)" in moisture.summary_pl  # and > 1% for gypsum plaster


def test_a_norm_or_an_itb_instruction_is_told_in_own_words_never_copied():
    """Q4: key points and a link; the paid text of PN-EN / ITB is never copied -- a short summary only."""
    kinds = {s.code: s.kind for s in CATALOG.sources}
    for entry in CATALOG.entries:
        if kinds[entry.source] in ("NORM", "ITB"):
            assert entry.summary_pl and len(entry.summary_pl) <= 900, entry.code


# --- Stage 17C.4: the starter situations ----------------------------------------------------------------------------------------

SITUATIONS = {s.code: s for s in CATALOG.situations}
PL_PARAGRAPH = re.compile(r"§ (\d+)(?: ust\. (\d+))?")
RU_PARAGRAPH = re.compile(r"§ (\d+)(?: п\. (\d+))?")


def test_the_starter_situations_are_drafts_each_a_closed_tree():
    assert set(SITUATIONS) == {
        "SIT.RECOMMENDATION_REFUSED", "SIT.MOISTURE_HIGH", "SIT.ACCEPTANCE_NO_SHOW", "SIT.CLIENT_DOWNTIME",
        "SIT.CLIENT_WITHDRAWS", "SIT.CLIENT_NOT_PAYING", "SIT.WARRANTY_CLAIM", "SIT.HIDDEN_PROBLEM",
    }
    assert all(s.status == "DRAFT" for s in CATALOG.situations)
    for situation in CATALOG.situations:  # reading the catalogue already proved the tree; here only that each one decides something
        assert len(situation.outcomes) >= 3 and len(situation.questions) >= 2, situation.code


def test_every_outcome_says_what_to_do_and_leans_on_the_basis_of_the_law_or_the_technique():
    for situation in CATALOG.situations:
        for outcome in situation.outcomes:
            assert len(outcome.steps_pl) >= 2, (situation.code, outcome.id)
            assert outcome.entries or outcome.documents, (situation.code, outcome.id)


def test_an_outcome_that_sends_to_a_lawyer_carries_the_lawyer_mark_and_the_other_way_round():
    for situation in CATALOG.situations:
        for outcome in situation.outcomes:
            says_lawyer = any("prawnik" in step.lower() for step in outcome.steps_pl)
            says_lawyer_ru = any("юрист" in step.lower() for step in outcome.steps_ru)
            assert says_lawyer == outcome.lawyer == says_lawyer_ru, (situation.code, outcome.id)


def _texts(situation):
    """Every sentence of a situation with where it stands, per language: the questions, the answers and the steps."""
    pl, ru = [], []
    for question in situation.questions:
        pl += [(f"{question.id}", question.text_pl)] + [(f"{question.id}>{a.next}", a.text_pl) for a in question.answers]
        ru += [(f"{question.id}", question.text_ru)] + [(f"{question.id}>{a.next}", a.text_ru) for a in question.answers]
    for outcome in situation.outcomes:
        pl += [(f"{outcome.id}#{i}", step) for i, step in enumerate(outcome.steps_pl)]
        ru += [(f"{outcome.id}#{i}", step) for i, step in enumerate(outcome.steps_ru)]
    return pl, ru


def test_the_paragraphs_of_the_contract_named_anywhere_in_a_situation_exist_in_the_contract():
    """A sentence that says "§ 10 ust. 5" must point at a paragraph and a clause the contract really has, in a question, an
    answer or a step, and the Polish and the Russian sentence must name the same ones."""
    sections = [(s.key, len(s.clauses)) for s in load_clause_catalog().sections]
    for situation in CATALOG.situations:
        pl, ru = _texts(situation)
        assert [place for place, _ in pl] == [place for place, _ in ru], situation.code
        for (place, pl_text), (_, ru_text) in zip(pl, ru, strict=True):
            for text, pattern in ((pl_text, PL_PARAGRAPH), (ru_text, RU_PARAGRAPH)):
                for match in pattern.finditer(text):
                    number, clause = int(match.group(1)), match.group(2)
                    assert 1 <= number <= len(sections), (situation.code, place, match.group(0))
                    if clause:
                        assert 1 <= int(clause) <= sections[number - 1][1], (situation.code, place, match.group(0))
            pl_names = [m.group(0).replace(" ust. ", "/") for m in PL_PARAGRAPH.finditer(pl_text)]
            ru_names = [m.group(0).replace(" п. ", "/") for m in RU_PARAGRAPH.finditer(ru_text)]
            assert pl_names == ru_names, (situation.code, place, pl_names, ru_names)


def test_the_phrases_for_the_client_in_the_outcomes_belong_to_the_risks_of_the_situation():
    """A phrase offered with a situation about moisture is a phrase about moisture, not any phrase."""
    risk_of = {"SIT.MOISTURE_HIGH": {"MOISTURE_BLOCK_FINISHING"}}
    for code, risks in risk_of.items():
        for outcome in SITUATIONS[code].outcomes:
            for phrase in outcome.phrases:
                assert phrase.removeprefix("COMM_RISK_") in risks, (code, outcome.id, phrase)
