"""UX walk B6: the list of the walls says how many high / critical risks of the inspections of each wall are active ("⚠ N")."""
import uuid

from app.domain.services.surface_service import SurfaceService
from app.models.risk import Risk, RiskSeverity
from app.models.surface import SurfaceType
from tests.test_work_recommendation_accept import _make_inspection, _make_project, _make_room, _make_surface, _make_template, _make_user


def _risk(room_id, inspection_id, severity: RiskSeverity, *, active: bool = True) -> Risk:
    code = uuid.uuid4().hex[:12]
    return Risk(
        room_id=room_id, inspection_id=inspection_id, risk_code=code, rule_code=code, rule_version=1, severity=severity,
        title_key="t", explanation_key="e", consequence_key="c", mitigation_key="m", communication_key="k",
        warranty_exclusion_candidate=False, blocks_finishing=False, source_signature=uuid.uuid4().hex, is_active=active,
    )


async def test_the_wall_list_counts_the_active_high_and_critical_risks_of_each_wall(db_session):
    user = await _make_user(db_session, 1306001)
    project = await _make_project(db_session, user.id)
    room = await _make_room(db_session, project.id)
    wall = await _make_surface(db_session, room.id, SurfaceType.WALL)
    other = await _make_surface(db_session, room.id, SurfaceType.WALL)
    template = await _make_template(db_session)
    inspection = await _make_inspection(db_session, room.id, template.id)
    inspection.surface_id = wall.id
    archived = await _make_inspection(db_session, room.id, template.id)
    archived.surface_id = wall.id
    archived.is_archived = True
    db_session.add_all([
        _risk(room.id, inspection.id, RiskSeverity.HIGH),
        _risk(room.id, inspection.id, RiskSeverity.CRITICAL),
        _risk(room.id, inspection.id, RiskSeverity.MEDIUM),  # not high
        _risk(room.id, inspection.id, RiskSeverity.HIGH, active=False),  # resolved
        _risk(room.id, archived.id, RiskSeverity.HIGH),  # an archived inspection
    ])
    await db_session.commit()

    items, _ = await SurfaceService(db_session).list_surfaces(project.id, room.id, user.id)
    counts = {item.id: item.high_risk_count for item in items}
    assert counts[wall.id] == 2 and counts[other.id] == 0


async def test_the_summary_of_the_object_lists_the_high_risks_by_room(db_session):
    # owner 2026-10-31: "Dodatkowo" of the summary of the object shows where the open high risks are
    from app.domain.services.room_service import RoomService

    user = await _make_user(db_session, 1306002)
    project = await _make_project(db_session, user.id)
    room = await _make_room(db_session, project.id)
    calm = await _make_room(db_session, project.id)
    template = await _make_template(db_session)
    inspection = await _make_inspection(db_session, room.id, template.id)
    db_session.add_all([_risk(room.id, inspection.id, RiskSeverity.CRITICAL), _risk(room.id, inspection.id, RiskSeverity.LOW)])
    await db_session.commit()
    summary = await RoomService(db_session).get_project_summary(project.id, user.id)
    assert [(r.room_id, r.count) for r in summary.high_risks] == [(room.id, 1)]
    assert calm.id not in {r.room_id for r in summary.high_risks}
