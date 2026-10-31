"""Owner 2026-10-31: "Dlaczego te prace?" of the client's page -- the standard of each room and the reasons the owner accepted from an inspection."""
from datetime import UTC, datetime

from app.domain.services.client_why_service import ClientWhyService
from app.models.work_recommendation import WorkRecommendationStatus
from tests.test_ux_b6_wall_risk_badge import _risk
from tests.test_work_recommendation_accept import _setup_actionable
from app.models.risk import RiskSeverity


async def test_an_accepted_work_shows_its_risk_and_the_room_its_standard_and_nothing_else_is_shown(db_session):
    user, project, room, wall, plan, item, rec, _service = await _setup_actionable(db_session, 1311001)
    inspection_id = rec.inspection_id
    risk = _risk(room.id, inspection_id, RiskSeverity.HIGH)
    db_session.add(risk)
    await db_session.flush()
    # not accepted yet: no reason
    rec.risk_id = risk.id
    await db_session.commit()
    rooms = await ClientWhyService(db_session, None).why(user.id, project.id)
    assert all(not r.reasons for r in rooms)

    rec.status = WorkRecommendationStatus.ACCEPTED
    rec.accepted_at = datetime.now(UTC)
    rec.resolved_price_item_id = item.id
    await db_session.commit()
    [why] = [r for r in await ClientWhyService(db_session, None).why(user.id, project.id) if r.room_id == room.id]
    [reason] = why.reasons
    assert reason.reason_key == risk.title_key and reason.photos == []  # no storage: no photos, the reason stays
    assert reason.work_name == item.display_name and reason.work_name_key == item.name_key
    assert why.quality_target == (plan.quality_target.value if plan.quality_target else None)
