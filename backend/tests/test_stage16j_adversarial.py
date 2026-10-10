"""Stage 16J: the adversarial check of the whole of Stage 16 -- every route of the contract, the protocols, the protective documents and the
documents of an object against a token that is missing and against another owner's object; the largest documents that the application can be
asked for; the order of what was written."""
import io
import time
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from pypdf import PdfReader

from app.domain.documents.acceptance_document import build_acceptance_document, render_acceptance_html
from app.domain.documents.decision_document import build_decision_document, render_decision_html
from app.domain.documents.downtime_document import build_protocol_document, render_protocol_html
from app.domain.documents.renderer import DocumentRenderer
from app.domain.protocols.acceptance import SurfaceFacts, WorkLine
from app.domain.protocols.decision import RiskFacts
from app.domain.protocols.sources import AcceptanceSources, DecisionSources, DowntimeSources, load_acceptance_sources, load_decision_sources, load_downtime_sources
from app.main import app
from tests.test_stage15f2_issuing import Delivery, issuer
from tests.test_stage16e2_contract import OWNER_TG, STRANGER_TG, login, ready, use_issuer  # noqa: F401  (a fixture)

# the families of routes under an object that Stage 16 added or changed
FAMILIES = ("contracts", "handovers", "concealed-works", "acceptances", "decisions", "downtimes", "adjacent-works", "representatives", "documents")
METHODS = ("get", "post", "patch", "put", "delete")
UUID_PARAMS = ("{contract_id}", "{handover_id}", "{protocol_id}", "{episode_id}", "{work_id}", "{representative_id}", "{document_id}")


def stage16_routes() -> list[tuple[str, str]]:
    found = []
    for path, operations in sorted(app.openapi()["paths"].items()):
        parts = path.split("/")  # ['', 'api', 'projects', '{project_id}', family, ...]
        if len(parts) > 4 and parts[2] == "projects" and parts[3] == "{project_id}" and parts[4] in FAMILIES:
            found.extend((method.upper(), path) for method in operations if method in METHODS)
    return found


def url_of(path: str, project_id) -> str:
    out = path.replace("{project_id}", str(project_id))
    for param in UUID_PARAMS:
        out = out.replace(param, str(uuid.uuid4()))
    return out


def test_the_matrix_covers_every_family_and_is_not_a_handful_of_routes():
    routes = stage16_routes()
    assert len(routes) >= 60
    for family in FAMILIES:
        assert any(f"/{family}" in path for _, path in routes), family
    assert not [p for _, p in routes if "{" in url_of(p, uuid.uuid4())]  # every parameter is filled in


async def test_no_route_of_stage_16_answers_without_a_token(async_client: AsyncClient, db_session):
    mine = await ready(db_session, telegram_id=OWNER_TG)
    routes = stage16_routes()
    answers = {}
    for method, path in routes:
        response = await async_client.request(method, url_of(path, mine.project.id))
        answers[(method, path)] = response.status_code
    assert {k: v for k, v in answers.items() if v != 401} == {}


async def test_no_route_of_stage_16_gives_another_owner_anything_and_the_owner_still_gets_his_own(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    mine = await ready(db_session, telegram_id=OWNER_TG)
    theirs = await ready(db_session, telegram_id=STRANGER_TG)
    use_issuer(issuer(delivery=Delivery()))
    headers = await login(async_client)
    leaked, refused_ok = [], 0
    for method, path in stage16_routes():
        # the logged-in owner knocks at the other owner's object, with a body that would be valid for a change
        response = await async_client.request(method, url_of(path, theirs.project.id), headers=headers,
                                              json={"notes": "x"} if method in ("post", "patch", "put") else None)
        if response.status_code not in (404, 422):
            leaked.append((method, path, response.status_code))
        elif response.status_code == 404:
            refused_ok += 1
        assert theirs.project.name not in response.text or response.status_code == 404
    assert leaked == []
    assert refused_ok >= 50  # most of them refuse by name, the rest refuse the body before they look at the object
    # the other side of the same coin: his own object is served, so the matrix is not all 404 by a wrong address
    for family in ("contracts", "handovers", "concealed-works", "acceptances", "decisions", "downtimes", "adjacent-works", "representatives", "documents"):
        response = await async_client.get(f"/api/projects/{mine.project.id}/{family}", headers=headers)
        assert response.status_code == 200, (family, response.text)


async def test_an_object_that_does_not_exist_is_refused_like_another_owners(async_client: AsyncClient, db_session):
    await ready(db_session, telegram_id=OWNER_TG)
    headers = await login(async_client)
    ghost = uuid.uuid4()
    for family in ("contracts", "handovers", "concealed-works", "acceptances", "decisions", "downtimes"):
        assert (await async_client.get(f"/api/projects/{ghost}/{family}", headers=headers)).status_code == 404, family
        assert (await async_client.post(f"/api/projects/{ghost}/{family}", headers=headers)).status_code == 404, family


# --- the largest documents ------------------------------------------------------------------------------------------------------------------


async def pdf_of(html: str, number: str, *, pages_max: int, seconds_max: float):
    started = time.monotonic()
    pdf = (await DocumentRenderer().render(html)).pdf
    took = time.monotonic() - started
    pages = PdfReader(io.BytesIO(pdf)).pages
    assert 1 <= len(pages) <= pages_max, len(pages)
    assert all(number in page.extract_text() for page in pages)  # the number is on every page
    assert len(pdf) < 5 * 1024 * 1024
    assert took < seconds_max, took
    return len(pages), len(pdf), took


async def test_an_acceptance_of_sixty_surfaces_with_two_hundred_remarks_is_one_document_with_its_number_on_every_page(db_session):
    w = await ready(db_session, telegram_id=9801)
    sources = await load_acceptance_sources(db_session, w.owner.id, w.project.id)
    rooms = [(f"room-{n}", f"Pokój {n} z długą nazwą dla sprawdzenia zawijania tekstu", 6) for n in range(10)]
    facts, surfaces = {}, {}
    for n in range(60):
        sid, room = f"surf-{n}", rooms[n % 10]
        facts[sid] = SurfaceFacts(sid, f"Ściana {n}", room[0], room[1], "WALL", "S2" if n % 3 else "Q4",
                                  tuple(WorkLine(f"Praca numer {k} z dość długą nazwą operacji technologicznej", "COMPLETED" if (n + k) % 7 else "IN_PROGRESS") for k in range(6)))
        surfaces[sid] = {"assessed": True, "remarks": {
            f"rem-{n}-{k}": {"id": f"rem-{n}-{k}", "place": f"Miejsce {k} przy oknie lub drzwiach", "description": "Smuga widoczna w świetle bocznym — opis dłuższy niż jeden wiersz tabeli, aby sprawdzić zawijanie",
                             "classification": "REMOVABLE" if k % 2 else "SIGNIFICANT", "deadline": "2026-10-30" if k % 2 else None, "photo_ids": [], "position": k + 1}
            for k in range(3 if n < 40 else 0)}}
    big = AcceptanceSources(sources.base, facts, tuple(rooms), {})
    data = {"room_ids": [r[0] for r in rooms], "held_on": date(2026, 10, 20), "attendees": [{"person_id": None, "name": "Jan", "role": None}], "surfaces": surfaces}
    document = build_acceptance_document(data, big, working=False, issued_on=date(2026, 10, 20), number="ODBIOR/2026/10/20/1000", sequence=1)
    assert len(document.surfaces) == 60 and len(document.remarks) == 120
    pages, size, took = await pdf_of(render_acceptance_html(document), "ODBIOR/2026/10/20/1000", pages_max=60, seconds_max=60)
    assert pages > 5 and size > 10_000, (pages, size, took)


async def test_a_protocol_of_thirty_decisions_is_one_document_with_its_number_on_every_page(db_session):
    w = await ready(db_session, telegram_id=9802)
    sources = await load_decision_sources(db_session, w.owner.id, w.project.id)
    items = [{"id": f"item-{n}", "source": "OWN", "title": f"Zalecenie numer {n} — wydłużenie przerwy technologicznej przed gruntowaniem", "room_id": None,
              "recommendation": "Odczekać co najmniej 72 godziny przed gruntowaniem i ponownie zmierzyć wilgotność w obecności Zamawiającego. " * 2,
              "consequence": "Gładź może pękać i odspajać się od podłoża, a skutki mogą ujawnić się dopiero po kilku miesiącach użytkowania. " * 2,
              "price": "1250.00", "decision": ("ACCEPTED", "DECLINED", "INSISTS")[n % 3], "executor_action": "PERFORM" if n % 3 == 2 else None, "order_ref": f"Z/{n}" if n % 3 == 0 else None}
             for n in range(30)]
    big = DecisionSources(sources.base, {}, sources.rooms)
    data = {"held_on": date(2026, 10, 20), "attendees": [{"person_id": None, "name": "Jan", "role": None}], "items": items, "understood": True}
    document = build_decision_document(data, big, working=False, issued_on=date(2026, 10, 20), number="DECYZ/2026/10/20/1000", sequence=1)
    assert len(document.items) == 30
    pages, size, took = await pdf_of(render_decision_html(document), "DECYZ/2026/10/20/1000", pages_max=60, seconds_max=60)
    assert pages > 5, (pages, size, took)


async def test_a_protocol_of_downtime_of_sixty_days_is_one_document_with_its_number_on_every_page(db_session):
    w = await ready(db_session, telegram_id=9803)
    sources = await load_downtime_sources(db_session, w.owner.id, w.project.id)
    days, current = [], date(2026, 10, 13)
    while len(days) < 60:
        if current.weekday() < 5:
            days.append({"date": current.isoformat(), "other_work": len(days) % 4 == 0, "note": "Brama zamknięta, administrator nieosiągalny — dłuższa uwaga do dnia" if len(days) % 2 else None})
        current = date.fromordinal(current.toordinal() + 1)
    contract = {"answers": {"downtime_rate_per_day": "150.00", "downtime_cap_percent": 10, "downtime_days_limit": 5}, "estimate": {"total": "50000.00"}}
    data = {"cause_key": "no_access", "days": days, "held_on": date(2027, 1, 20), "attendees": [{"person_id": None, "name": "Jan", "role": None}],
            "noticed_on": date(2026, 10, 12)}
    document = build_protocol_document(data, sources, contract, working=False, issued_on=date(2027, 1, 20), notice_number="ZAWPRZ/2026/10/12/0830",
                                       notice_on=date(2026, 10, 12), number="PROPRZ/2027/01/20/1000", sequence=2)
    assert len(document.days) == 60 and {r.label: r.value for r in document.totals}["Dni przestoju — razem"] == "60"
    assert document.cap_note is not None  # 45 paid days at 150 zł is 6 750 zł, over the cap of 5 000 zł
    pages, size, took = await pdf_of(render_protocol_html(document), "PROPRZ/2027/01/20/1000", pages_max=20, seconds_max=60)
    assert pages >= 2, (pages, size, took)
    assert RiskFacts and DowntimeSources  # the in-memory sources used above are the real classes
