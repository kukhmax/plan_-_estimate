"""Stage 13F-PRE — room / surface / object corrections (backend read models
and FLOOR recommendation compatibility).

- B: RoomRead.opening_groups — active openings on active surfaces grouped by
  type + exact Decimal width/height, quantities summed.
- E: GET /projects/{id}/summary — Decimal sums of the rooms' canonical
  calculations over ACTIVE rooms + openings grouped across rooms.
- D: a recommended work is produced only for inspection targets it is
  explicitly compatible with; the baseline wall/ceiling works never reach FLOOR.
"""
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.domain.data.work_recommendation_rules import (
    RECOMMENDED_WORK_TARGET_KINDS,
    build_baseline_work_recommendation_rules,
    recommended_work_allows_target,
)
from app.domain.exceptions import WorkRecommendationTargetError
from app.domain.rules.opening_summary import group_openings
from app.domain.rules.risk_rules import compute_source_signature
from app.domain.services.canonical_planes import ensure_canonical_plane_surfaces
from app.domain.services.work_recommendation_service import WorkRecommendationService
from app.models.area_segment import AreaPlane
from app.models.opening import OpeningType
from app.models.surface import SurfaceType
from app.models.work_recommendation import (
    WorkRecommendation,
    WorkRecommendationTargetKind,
    WorkRecommendationTriggerType,
)
from tests.test_openings import (
    OTHER_USER,
    VALID_USER,
    auth_header,
    create_project,
    create_room,
    create_surface,
    get_token,
    openings_url,
)
from tests.test_work_recommendation_evaluation import (
    _make_finding,
    _make_inspection,
    _make_project,
    _make_risk,
    _make_room,
    _make_rule,
    _make_surface,
    _make_template,
    _make_user,
)

K = WorkRecommendationTargetKind


# ---------------------------------------------------------------------------
# Opening grouping (pure)
# ---------------------------------------------------------------------------


class TestGroupOpenings:
    def test_exact_decimal_grouping_quantities_and_order(self):
        groups = group_openings([
            ("WINDOW", Decimal("1.7"), Decimal("1.65"), 2),
            (OpeningType.WINDOW, Decimal("1.700"), Decimal("1.650"), 3),   # same as above
            ("WINDOW", Decimal("2.43"), Decimal("1.65"), 1),
            ("DOOR", "0.90", "2.07", 2),
            ("DOOR", Decimal("0.800"), Decimal("2.070"), 3),
            ("OTHER", Decimal("1.200"), Decimal("2.000"), 1),
            ("DOOR", Decimal("1.700"), Decimal("1.650"), 1),  # same size as a window: never merged
        ])
        assert [(g.opening_type, str(g.width), str(g.height), g.quantity) for g in groups] == [
            (OpeningType.DOOR, "0.800", "2.070", 3),
            (OpeningType.DOOR, "0.900", "2.070", 2),
            (OpeningType.DOOR, "1.700", "1.650", 1),
            (OpeningType.WINDOW, "1.700", "1.650", 5),
            (OpeningType.WINDOW, "2.430", "1.650", 1),
            (OpeningType.OTHER, "1.200", "2.000", 1),
        ]

    def test_close_but_different_dimensions_stay_separate(self):
        groups = group_openings([
            ("WINDOW", Decimal("1.700"), Decimal("1.650"), 1),
            ("WINDOW", Decimal("1.701"), Decimal("1.650"), 1),
        ])
        assert [(str(g.width), g.quantity) for g in groups] == [("1.700", 1), ("1.701", 1)]

    def test_empty(self):
        assert group_openings([]) == []


# ---------------------------------------------------------------------------
# Room opening groups + object summary (API)
# ---------------------------------------------------------------------------


async def _opening(client, token, p, r, s, otype, width, height, qty=1, **extra) -> dict:
    resp = await client.post(
        openings_url(p, r, s),
        json={"opening_type": otype, "width": width, "height": height, "quantity": qty, **extra},
        headers=auth_header(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _archive(client, token, url):
    resp = await client.post(f"{url}/archive", headers=auth_header(token))
    assert resp.status_code == 200, resp.text


REVEAL = {"reveal_enabled": True, "reveal_depth": "0.200", "reveal_left": True,
          "reveal_right": True, "reveal_top": True, "reveal_bottom": False}


async def _object(client) -> dict:
    """Two active rooms, one archived room, plus an archived opening and an
    archived wall (with its own opening) that must not count anywhere."""
    token = await get_token(client, VALID_USER)
    project = await create_project(client, token)
    p = project["id"]
    a = await create_room(client, token, p, name="Sypialnia", length="4.000", width="3.000", height="2.500")
    wall_a = await create_surface(client, token, p, a["id"], width="4.000", height="2.500")
    await _opening(client, token, p, a["id"], wall_a["id"], "WINDOW", "1.700", "1.650", 2, **REVEAL)
    await _opening(client, token, p, a["id"], wall_a["id"], "DOOR", "0.900", "2.070")

    b = await create_room(client, token, p, name="Salon", length="5.000", width="4.000", height="2.700")
    wall_b = await create_surface(client, token, p, b["id"], width="5.000", height="2.700")
    await _opening(client, token, p, b["id"], wall_b["id"], "WINDOW", "1.7", "1.65", 3)
    await _opening(client, token, p, b["id"], wall_b["id"], "DOOR", "0.90", "2.07")
    gone = await _opening(client, token, p, b["id"], wall_b["id"], "OTHER", "1.200", "2.000")
    await _archive(client, token, f"{openings_url(p, b['id'], wall_b['id'])}/{gone['id']}")
    old_wall = await create_surface(client, token, p, b["id"], name="Stara", width="3.000", height="2.700")
    await _opening(client, token, p, b["id"], old_wall["id"], "DOOR", "0.800", "2.070")
    await _archive(client, token, f"/api/projects/{p}/rooms/{b['id']}/surfaces/{old_wall['id']}")

    c = await create_room(client, token, p, name="Pokój (archiwum)", length="3.000", width="3.000", height="2.500")
    wall_c = await create_surface(client, token, p, c["id"], width="3.000", height="2.500")
    await _opening(client, token, p, c["id"], wall_c["id"], "WINDOW", "1.700", "1.650")
    await _archive(client, token, f"/api/projects/{p}/rooms/{c['id']}")
    return {"token": token, "p": p, "a": a["id"], "b": b["id"], "c": c["id"]}


def _groups(payload: list[dict]) -> list[tuple]:
    return [(g["opening_type"], g["width"], g["height"], g["quantity"]) for g in payload]


class TestRoomOpeningGroups:
    async def test_room_read_and_list_expose_grouped_active_openings(self, async_client: AsyncClient):
        o = await _object(async_client)
        h = auth_header(o["token"])
        room_b = (await async_client.get(f"/api/projects/{o['p']}/rooms/{o['b']}", headers=h)).json()
        # archived opening (OTHER) and the archived wall's door are excluded
        assert _groups(room_b["opening_groups"]) == [("DOOR", "0.900", "2.070", 1), ("WINDOW", "1.700", "1.650", 3)]
        listed = {r["id"]: r for r in (await async_client.get(f"/api/projects/{o['p']}/rooms", headers=h)).json()["items"]}
        assert listed[o["b"]]["opening_groups"] == room_b["opening_groups"]
        assert _groups(listed[o["a"]]["opening_groups"]) == [("DOOR", "0.900", "2.070", 1), ("WINDOW", "1.700", "1.650", 2)]
        assert o["c"] not in listed

    async def test_identical_dimensions_on_different_walls_aggregate(self, async_client: AsyncClient):
        token = await get_token(async_client, VALID_USER)
        p = (await create_project(async_client, token))["id"]
        r = (await create_room(async_client, token, p))["id"]
        w1 = await create_surface(async_client, token, p, r, name="Ściana 1")
        w2 = await create_surface(async_client, token, p, r, name="Ściana 2")
        await _opening(async_client, token, p, r, w1["id"], "WINDOW", "1.200", "1.500", 2)
        await _opening(async_client, token, p, r, w2["id"], "WINDOW", "1.2", "1.5", 1)
        await _opening(async_client, token, p, r, w2["id"], "WINDOW", "1.200", "1.400", 1)
        room = (await async_client.get(f"/api/projects/{p}/rooms/{r}", headers=auth_header(token))).json()
        assert _groups(room["opening_groups"]) == [("WINDOW", "1.200", "1.400", 1), ("WINDOW", "1.200", "1.500", 3)]


class TestProjectSummary:
    async def test_object_totals_over_active_rooms_only(self, async_client: AsyncClient):
        o = await _object(async_client)
        h = auth_header(o["token"])
        resp = await async_client.get(f"/api/projects/{o['p']}/summary", headers=h)
        assert resp.status_code == 200, resp.text
        s = resp.json()
        assert s["room_count"] == 2
        assert (s["floor_area"], s["ceiling_area"]) == ("32.000", "32.000")          # 12 + 20
        assert s["total_wall_area"] == "23.500"                                         # 10.000 + 13.500
        assert s["total_deduction_area"] == "17.751"                                    # 7.473 + 10.278
        assert s["net_wall_area"] == "5.749"
        assert Decimal(s["total_wall_area"]) - Decimal(s["total_deduction_area"]) == Decimal(s["net_wall_area"])
        assert (s["reveal_total_length"], s["reveal_total_area"]) == ("10.000", "2.000")  # 2 x (1.65+1.65+1.70), x0.2
        assert _groups(s["opening_groups"]) == [("DOOR", "0.900", "2.070", 2), ("WINDOW", "1.700", "1.650", 5)]

    async def test_summary_equals_sum_of_canonical_room_calculations(self, async_client: AsyncClient):
        o = await _object(async_client)
        h = auth_header(o["token"])
        rooms = (await async_client.get(f"/api/projects/{o['p']}/rooms", headers=h)).json()["items"]
        s = (await async_client.get(f"/api/projects/{o['p']}/summary", headers=h)).json()
        for field in ("floor_area", "ceiling_area", "total_wall_area", "total_deduction_area",
                      "net_wall_area", "reveal_total_length", "reveal_total_area"):
            expected = sum((Decimal(r["calculations"][field]) for r in rooms
                            if r["calculations"] and r["calculations"][field] is not None), Decimal("0"))
            assert Decimal(s[field]) == expected, field

    async def test_empty_object_and_metrics_without_data_are_null(self, async_client: AsyncClient):
        token = await get_token(async_client, VALID_USER)
        p = (await create_project(async_client, token))["id"]
        s = (await async_client.get(f"/api/projects/{p}/summary", headers=auth_header(token))).json()
        assert s == {"room_count": 0, "floor_area": None, "ceiling_area": None, "total_wall_area": None,
                     "total_deduction_area": None, "net_wall_area": None, "reveal_total_length": None,
                     "reveal_total_area": None, "opening_groups": []}
        await create_room(async_client, token, p)  # 5 x 4 x 2.7, no walls, no reveals
        s = (await async_client.get(f"/api/projects/{p}/summary", headers=auth_header(token))).json()
        assert (s["room_count"], s["floor_area"], s["reveal_total_length"]) == (1, "20.000", None)

    async def test_foreign_or_missing_project_is_404(self, async_client: AsyncClient):
        o = await _object(async_client)
        other = await get_token(async_client, OTHER_USER)
        assert (await async_client.get(f"/api/projects/{o['p']}/summary", headers=auth_header(other))).status_code == 404
        missing = "00000000-0000-4000-8000-000000000000"
        assert (await async_client.get(f"/api/projects/{missing}/summary", headers=auth_header(o["token"]))).status_code == 404

    async def test_summary_is_read_only(self, async_client: AsyncClient):
        o = await _object(async_client)
        h = auth_header(o["token"])
        before = (await async_client.get(f"/api/projects/{o['p']}/rooms?include_archived=true", headers=h)).json()
        await async_client.get(f"/api/projects/{o['p']}/summary", headers=h)
        after = (await async_client.get(f"/api/projects/{o['p']}/rooms?include_archived=true", headers=h)).json()
        assert after == before


# ---------------------------------------------------------------------------
# FLOOR recommendation compatibility
# ---------------------------------------------------------------------------


class TestRecommendationTargetCompatibility:
    def test_every_baseline_work_is_declared_and_none_is_a_floor_work(self):
        for rule in build_baseline_work_recommendation_rules():
            allowed = RECOMMENDED_WORK_TARGET_KINDS[rule.recommended_work_code]
            assert {K.WALL, K.CEILING} <= allowed and K.FLOOR not in allowed

    def test_undeclared_code_never_reaches_floor(self):
        assert recommended_work_allows_target("SOMETHING_NEW", K.WALL)
        assert not recommended_work_allows_target("SOMETHING_NEW", K.FLOOR)

    async def _room_with_planes(self, db, tid):
        user = await _make_user(db, tid)
        project = await _make_project(db, user.id)
        room = await _make_room(db, project.id)
        floor, ceiling = await ensure_canonical_plane_surfaces(db, room.id)
        await db.commit()
        return user, project, room, floor, ceiling

    async def test_baseline_wall_work_is_not_recommended_for_floor_but_still_for_wall_and_ceiling(self, db_session):
        user, project, room, floor, ceiling = await self._room_with_planes(db_session, 213501)
        wall = await _make_surface(db_session, room.id, SurfaceType.WALL)
        template = await _make_template(db_session)
        for kwargs in ({"plane": AreaPlane.FLOOR}, {"plane": AreaPlane.CEILING}, {"surface_id": wall.id}):
            inspection = await _make_inspection(db_session, room.id, template.id, **kwargs)
            await _make_risk(db_session, room.id, inspection.id, rule_code="UNEVENNESS_PREP_INCREASED",
                             source_signature=compute_source_signature([inspection.id]))
        result = await WorkRecommendationService(db_session).evaluate_recommendations(project.id, room.id, user.id)
        got = sorted((r.target_kind.value, r.recommended_work_code) for r in result.recommendations)
        assert got == [("CEILING", "CENNIK_SKIM_LOCAL-01"), ("WALL", "CENNIK_SKIM_LOCAL-01")]

    async def test_ceiling_only_and_wall_only_works_never_leak_to_floor(self, db_session, monkeypatch):
        monkeypatch.setitem(RECOMMENDED_WORK_TARGET_KINDS, "CEIL_ONLY", frozenset({K.CEILING}))
        monkeypatch.setitem(RECOMMENDED_WORK_TARGET_KINDS, "WALL_ONLY", frozenset({K.WALL}))
        user, project, room, floor, ceiling = await self._room_with_planes(db_session, 213502)
        template = await _make_template(db_session)
        for plane in (AreaPlane.FLOOR, AreaPlane.CEILING):
            inspection = await _make_inspection(db_session, room.id, template.id, plane=plane)
            await _make_finding(db_session, inspection.id, finding_key="k13fpre")
        for code in ("CEIL_ONLY", "WALL_ONLY"):
            await _make_rule(db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
                             trigger_code="k13fpre", recommended_work_code=code)
        result = await WorkRecommendationService(db_session).evaluate_recommendations(project.id, room.id, user.id)
        assert [(r.target_kind, r.recommended_work_code) for r in result.recommendations] == [(K.CEILING, "CEIL_ONLY")]

    async def test_explicit_floor_work_is_still_recommended(self, db_session, monkeypatch):
        monkeypatch.setitem(RECOMMENDED_WORK_TARGET_KINDS, "FLOOR_PRIMER_TEST", frozenset({K.FLOOR}))
        user, project, room, floor, _ = await self._room_with_planes(db_session, 213503)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id, plane=AreaPlane.FLOOR)
        await _make_finding(db_session, inspection.id, finding_key="floor_dust")
        await _make_rule(db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
                         trigger_code="floor_dust", recommended_work_code="FLOOR_PRIMER_TEST")
        result = await WorkRecommendationService(db_session).evaluate_recommendations(project.id, room.id, user.id)
        assert [(r.target_kind, r.surface_id, r.recommended_work_code) for r in result.recommendations] == [
            (K.FLOOR, floor.id, "FLOOR_PRIMER_TEST")
        ]

    async def test_pre_existing_floor_row_is_resolved_and_cannot_auto_accept(self, db_session):
        """A wall/ceiling recommendation materialized on FLOOR before 13F-PRE
        becomes inactive on the next evaluation and never auto-resolves into
        the incompatible work."""
        user, project, room, floor, _ = await self._room_with_planes(db_session, 213504)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id, plane=AreaPlane.FLOOR)
        risk = await _make_risk(db_session, room.id, inspection.id, rule_code="UNEVENNESS_PREP_INCREASED",
                                source_signature=compute_source_signature([inspection.id]))
        legacy = WorkRecommendation(
            trigger_type=WorkRecommendationTriggerType.RISK_RULE, trigger_code="UNEVENNESS_PREP_INCREASED",
            source_signature=risk.source_signature, inspection_id=inspection.id, risk_id=risk.id,
            room_id=room.id, surface_id=floor.id, target_kind=K.FLOOR,
            recommended_work_code="CENNIK_SKIM_LOCAL-01",
        )
        db_session.add(legacy)
        await db_session.commit()
        service = WorkRecommendationService(db_session)
        with pytest.raises(WorkRecommendationTargetError):
            await service.accept_recommendation(project.id, legacy.id, user.id)
        result = await service.evaluate_recommendations(project.id, room.id, user.id)
        assert result.recommendations == [] and result.resolved == 1
        await db_session.refresh(legacy)
        assert legacy.is_active is False and legacy.status.value == "PENDING"  # owner decision untouched
