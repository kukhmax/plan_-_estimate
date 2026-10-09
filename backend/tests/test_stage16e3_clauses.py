"""Stage 16E.3: the clause catalogue of the contract -- placeholders, variants, three-valued conditions, stable numbers, notes."""

import copy
import itertools
from decimal import Decimal

import pytest

from app.domain.contracts.clause_render import (
    build_flags, build_values, days, gross_of, months, percent, render_annexes, render_sections, text_segments, working_days,
)
from app.domain.contracts.clauses import PLACEHOLDER, PLACEHOLDERS, ClauseCatalog, load_clause_catalog, parse_condition

CATALOG = load_clause_catalog()
NB = " "


def dump() -> dict:
    return copy.deepcopy(CATALOG.model_dump(mode="json"))


def plain(text) -> str:
    return "".join("___" if s.kind == "blank" else s.text for s in text)


def values(**answers):
    return build_values(
        answers, object_address="ul. Zielona 5, 00-001 Warszawa", estimate_version=3, net=Decimal("147.00"), currency="PLN",
        executor=("Jan Wykonawca", "ul. Prosta 1, 00-002 Warszawa", "jan@example.pl", "+48 600 000 000"), client=("anna@example.pl", None),
    )


def section(rendered, key):
    return next(s for s in rendered if s.key == key)


# --- the values ------------------------------------------------------------------------------------------------------------------


def test_polish_forms_follow_the_number():
    assert (days(1), days(2), days(14), days(0)) == (f"1{NB}dnia", f"2{NB}dni", f"14{NB}dni", f"0{NB}dni")
    assert (working_days(1), working_days(3)) == (f"1{NB}Dnia roboczego", f"3{NB}Dni roboczych")
    assert (months(1), months(24)) == (f"1{NB}miesiąca", f"24{NB}miesięcy")
    assert percent(30) == f"30{NB}%" and days(None) is None and days(True) is None and days("3") is None


def test_gross_and_advance_are_computed_from_the_net_price_and_the_vat_rate_the_owner_gave():
    assert gross_of(Decimal("147.00"), 23) == Decimal("180.81") and gross_of(Decimal("100"), 8) == Decimal("108.00")
    assert gross_of(Decimal("10.50"), 23) == Decimal("12.92")  # half up: 12.915
    assert gross_of(Decimal("147.00"), None) is None and gross_of(None, 23) is None
    v = values(vat_rate_percent=23, advance_percent=30)
    assert (v["net_price"], v["gross_price"], v["advance_amount"]) == (f"147,00{NB}zł", f"180,81{NB}zł", f"54,24{NB}zł")
    unknown = values(advance_percent=30)  # no VAT rate: no gross price, no advance amount -- nothing is invented
    assert (unknown["vat_rate"], unknown["gross_price"], unknown["advance_amount"]) == (None, None, None)


def test_every_placeholder_has_a_value_and_every_value_is_used_by_the_catalogue():
    assert set(values()) == PLACEHOLDERS
    used = set()
    for text in _all_texts():
        used |= set(PLACEHOLDER.findall(text))
    assert used == PLACEHOLDERS  # no dead value, no placeholder without a value


def _all_texts():
    for s in CATALOG.sections:
        yield s.title_pl
        if s.else_pl:
            yield s.else_pl
        for c in s.clauses:
            for v in c.variants:
                yield v.text_pl
    for a in CATALOG.annexes:
        yield from a.paragraphs_pl
        yield from a.fields_pl


def test_an_unknown_value_is_a_blank_and_a_known_one_is_marked_as_a_value():
    segments = text_segments("od {work_start_date} do {work_end_date}.", values(work_start_date="2026-10-20"))
    assert [(s.kind, s.text) for s in segments] == [("text", "od "), ("value", "20.10.2026"), ("text", " do "), ("blank", ""), ("text", ".")]


# --- the facts -------------------------------------------------------------------------------------------------------------------


def test_the_facts_are_three_valued_and_nothing_is_guessed():
    assert build_flags({})["consumer"] is None and build_flags({})["offsite_consumer"] is None and build_flags({})["payment_by_stages"] is None
    assert build_flags({"client_status": "ENTREPRENEUR"})["offsite_consumer"] is False  # an entrepreneur: false whatever the place is
    assert build_flags({"client_status": "CONSUMER", "conclusion_mode": "PREMISES_OF_EXECUTOR"})["offsite_consumer"] is False
    assert build_flags({"client_status": "CONSUMER", "conclusion_mode": "OFF_PREMISES"})["offsite_consumer"] is True
    assert build_flags({"client_status": "CONSUMER_RIGHTS_ENTREPRENEUR", "conclusion_mode": "DISTANCE"})["offsite_consumer"] is True
    assert build_flags({"client_status": "CONSUMER"})["offsite_consumer"] is None  # place not chosen yet
    assert build_flags({"conclusion_mode": "DISTANCE"})["offsite_consumer"] is None  # status not chosen yet
    assert build_flags({"materials_supplier": "CUSTOMER"})["materials_customer"] is True
    assert build_flags({"penalty_mode": "NONE"})["penalty_per_day"] is False and build_flags({"insurance_sum": "1000.00"})["has_insurance"] is True
    assert build_flags({})["has_insurance"] is False and build_flags({"reinspection_limit": 0})["reinspection_limit"] is True


def test_conditions_accept_a_negation_and_refuse_an_unknown_fact():
    assert parse_condition("consumer") == (False, "consumer") and parse_condition("!consumer") == (True, "consumer")
    with pytest.raises(ValueError):
        parse_condition("lawyer_says_so")


# --- the choice of a variant ----------------------------------------------------------------------------------------------------


def render(**answers):
    return render_sections(CATALOG, build_flags(answers), values(**answers))


def test_a_decided_clause_prints_one_text_and_an_undecided_one_prints_boxes_to_tick():
    undecided = section(render(), "advance_and_payments").clauses[1]
    assert undecided.is_choice and len(undecided.alternatives) == 2
    assert "etapami" in plain(undecided.alternatives[0]) and "jednorazowo po odbiorze końcowym" in plain(undecided.alternatives[1])
    for mode, expected in (("BY_STAGES", "etapami"), ("ON_ACCEPTANCE", "jednorazowo")):
        decided = section(render(payment_mode=mode), "advance_and_payments").clauses[1]
        assert not decided.is_choice and expected in plain(decided.alternatives[0])


def test_the_supplier_of_the_materials_has_three_variants_and_the_penalty_two():
    assert len(section(render(), "materials").clauses[0].alternatives) == 3
    assert "Materiały dostarcza Zamawiający" in plain(section(render(materials_supplier="CUSTOMER"), "materials").clauses[0].alternatives[0])
    assert "zgodnie z podziałem wskazanym w Kosztorysie" in plain(section(render(materials_supplier="PER_ESTIMATE"), "materials").clauses[0].alternatives[0])
    penalty = section(render(penalty_mode="PER_DAY_DELAY", penalty_rate_per_day="50"), "liability").clauses[2]
    assert not penalty.is_choice and "w wysokości 50,00" in plain(penalty.alternatives[0]) and "nie więcej niż ___" in plain(penalty.alternatives[0])
    assert plain(section(render(penalty_mode="NONE"), "liability").clauses[2].alternatives[0]) == "Kara umowna: nie przewiduje się."
    assert len(section(render(), "liability").clauses[2].alternatives) == 2


def test_partial_acceptance_and_the_reinspection_limit_choose_their_wording():
    assert "wyłącznie odbiór końcowy" in plain(section(render(partial_acceptance=False), "acceptance").clauses[0].alternatives[0])
    assert "odbiory częściowe" in plain(section(render(partial_acceptance=True), "acceptance").clauses[0].alternatives[0])
    assert "wynosi 2." in plain(section(render(reinspection_limit=2), "evaluation_rules").clauses[4].alternatives[0])
    assert "nie jest limitowana" in plain(section(render(), "evaluation_rules").clauses[4].alternatives[0])


def test_the_optional_insurance_clause_is_left_out_without_a_sum_and_the_other_numbers_stay():
    organisation = lambda r: [c.number for c in section(r, "organisation").clauses]  # noqa: E731
    assert organisation(render()) == [1, 2, 3] and organisation(render(insurance_sum="100000")) == [1, 2, 3, 4]
    assert "sumę 100 000,00" in plain(section(render(insurance_sum="100000"), "organisation").clauses[3].alternatives[0])


def test_the_consumer_section_and_annex_apply_only_to_a_consumer_outside_the_premises():
    off = {"client_status": "CONSUMER", "conclusion_mode": "OFF_PREMISES"}
    here = {"client_status": "CONSUMER", "conclusion_mode": "PREMISES_OF_EXECUTOR"}
    firm = {"client_status": "ENTREPRENEUR", "conclusion_mode": "OFF_PREMISES"}
    for answers, applies in ((off, True), (here, False), (firm, False), ({}, True)):  # nothing answered: printed in full for the talk
        withdrawal = section(render(**answers), "consumer_withdrawal")
        assert bool(withdrawal.clauses) is applies and (withdrawal.instead is None) is applies
        annexes = render_annexes(CATALOG, build_flags(answers), values(**answers))
        assert (11 in [a.number for a in annexes]) is applies
        assert [a.number for a in annexes if a.number != 11] == [6, 7, 8, 9, 10, 12]
    assert "Nie dotyczy" in plain(section(render(**here), "consumer_withdrawal").instead)
    assert section(render(**here), "consumer_withdrawal").number == 20  # a section that does not apply keeps its number


def test_the_numbers_of_the_clauses_never_change_whatever_the_answers_are():
    keys = {
        "client_status": [None, "CONSUMER", "ENTREPRENEUR"], "conclusion_mode": [None, "OFF_PREMISES"],
        "payment_mode": [None, "BY_STAGES"], "materials_supplier": [None, "EXECUTOR", "CUSTOMER"],
        "penalty_mode": [None, "NONE", "PER_DAY_DELAY"], "partial_acceptance": [None, True, False],
        "reinspection_limit": [None, 2], "insurance_sum": [None, "100"],
    }
    full = {s.key: len(s.clauses) for s in CATALOG.sections}
    for combination in itertools.product(*keys.values()):
        answers = {k: v for k, v in zip(keys, combination) if v is not None}
        for rendered in render(**answers):
            numbers = [c.number for c in rendered.clauses]
            if rendered.instead is None:
                assert numbers == list(range(1, len(numbers) + 1)), (rendered.key, answers)  # no gap
                assert len(numbers) >= full[rendered.key] - (1 if rendered.key == "organisation" else 0)


# --- the catalogue itself --------------------------------------------------------------------------------------------------------


def test_every_reference_in_the_wording_points_to_a_clause_that_exists():
    base = dump()
    base["sections"][1]["clauses"][0]["variants"][0]["text_pl"] += " Zob. § 99."
    with pytest.raises(ValueError, match="points to nothing"):
        ClauseCatalog.model_validate(base)
    base = dump()
    base["sections"][1]["clauses"][0]["variants"][0]["text_pl"] += " Zob. § 14 ust. 9."
    with pytest.raises(ValueError, match="points to nothing"):
        ClauseCatalog.model_validate(base)
    ok = dump()
    ok["sections"][1]["clauses"][0]["variants"][0]["text_pl"] += " Zob. art. 355 § 99 KC i § 14 ust. 4."  # a Civil Code article is not a section
    ClauseCatalog.model_validate(ok)


@pytest.mark.parametrize(
    "edit, message",
    [
        (lambda d: d["sections"][1]["clauses"][0]["variants"][0].update(text_pl="Cena {tajna_cena}."), "unknown placeholders"),
        (lambda d: d["sections"][1]["clauses"][0]["variants"][0].update(text_pl="Cena {net_price."), "stray brace"),
        (lambda d: d["sections"][1]["clauses"][0]["variants"][0].update(when="nobody_knows"), "unknown condition"),
        (lambda d: d["sections"][1]["clauses"][0].update(n=2), "numbered 1, 2, 3"),
        (lambda d: d["sections"][19].update(else_pl=None), "go together"),
        (lambda d: d["sections"][21].update(numbered=True) or d["sections"][0].update(numbered=False), "only a one-paragraph section"),
        (lambda d: d["annexes"][0].update(number=5), "annexes of the catalogue must be"),
        (lambda d: d["sections"][1]["clauses"].append(copy.deepcopy(d["sections"][1]["clauses"][-1])) or None, "numbered 1, 2, 3"),
    ],
)
def test_the_catalogue_refuses_a_broken_text(edit, message):
    base = dump()
    edit(base)
    with pytest.raises(ValueError, match=message):
        ClauseCatalog.model_validate(base)


def test_a_conditional_clause_in_the_middle_is_refused_because_it_would_leave_a_gap():
    base = dump()
    clause = base["sections"][1]["clauses"][0]
    clause["variants"] = [{"when": "consumer", "text_pl": "Tylko dla konsumenta."}]
    with pytest.raises(ValueError, match="only the last clause may"):
        ClauseCatalog.model_validate(base)


def test_a_catalogue_cannot_be_approved_while_a_question_to_the_lawyer_is_open():
    base = dump()
    base.update(approved=True, approved_by="Jan Kowalski", approved_on="2026-10-11")
    with pytest.raises(ValueError, match="no open question to the lawyer"):
        ClauseCatalog.model_validate(base)
    for sec in base["sections"]:
        for clause in sec["clauses"]:
            for note in clause["review_notes"]:
                note["status"] = "RESOLVED"
    for annex in base["annexes"]:
        for note in annex["review_notes"]:
            note["status"] = "RESOLVED"
    assert ClauseCatalog.model_validate(base).approved


def test_the_prototype_is_all_there_the_sections_in_order_and_the_withdrawal_notes_of_the_owners_lawyer_list():
    titles = [s.title_pl for s in CATALOG.sections]
    assert titles[0] == "Definicje" and titles[9] == "Przestój z przyczyn dotyczących Zamawiającego" and titles[-1] == "Postanowienia końcowe"
    assert sum(len(s.clauses) for s in CATALOG.sections) == 112
    notes = {n.ref: n.text for s in CATALOG.sections for c in s.clauses for n in c.review_notes}
    assert set(notes) == {"L7", "L8", "L4", "L2", "L3", "L13", "L5"} and "385³" in notes["L4"] and "C-97/22" in notes["L5"]
    # the guarantee exclusions never touch the statutory warranty for a consumer (the prototype's balance)
    warranty = {c.n: c.variants[0].text_pl for c in next(s for s in CATALOG.sections if s.key == "warranty").clauses}
    assert "nie wyłącza ani nie ogranicza rękojmi" in warranty[1] and "nie ograniczają rękojmi" in warranty[4]


def test_a_negated_condition_selects_the_other_side_and_stays_undecided_when_the_fact_is_unknown():
    base = dump()
    clause = base["sections"][1]["clauses"][0]
    clause["variants"] = [{"when": "!consumer", "text_pl": "Dla przedsiębiorcy."}, {"when": None, "text_pl": "Dla konsumenta."}]
    catalog = ClauseCatalog.model_validate(base)

    def first(**answers):
        rendered = render_sections(catalog, build_flags(answers), values(**answers))
        return [plain(a) for a in section(rendered, "subject").clauses[0].alternatives]

    assert first(client_status="ENTREPRENEUR") == ["Dla przedsiębiorcy."]
    assert first(client_status="CONSUMER") == ["Dla konsumenta."]
    assert first() == ["Dla przedsiębiorcy.", "Dla konsumenta."]
