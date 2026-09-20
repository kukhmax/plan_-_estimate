"""Focused Stage 11B.2 tests: work-recommendation command/list HTTP API.

Covers dismiss/reconsider lifecycle commands, ownership/cross-project
guards, and list-time PriceItem read-resolution (S-AE from the canonical
Stage 11B.2 task spec). Materialization/reconciliation service-level tests
live in test_work_recommendation_evaluation.py.

Recommendation rows are seeded directly via the ORM (no evaluate-endpoint
dependency needed for command/list-API testing), exactly like
test_surface_work_plan_api.py seeds SurfaceWorkPlan rows directly.
"""
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.checklist import ChecklistTemplate, Substrate
from app.models.inspection import Inspection, InspectionStatus
from app.models.market_evidence import PriceMarketReference
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.user import User
from app.models.work_plan import SurfaceWorkPlan
from app.models.work_recommendation import (
    WorkRecommendation,
    WorkRecommendationRule,
    WorkRecommendationStatus,
    WorkRecommendationTargetKind,
    WorkRecommendationTriggerType,
)
from tests.conftest import make_telegram_init_data

VALID_USER = {
    "id": 311111111,
    "username": "rec_owner",
    "first_name": "Rec",
    "last_name": "Owner",
    "language_code": "pl",
}
OTHER_USER = {
    "id": 322222222,
    "username": "rec_other",
    "first_name": "Rec",
    "last_name": "Other",
    "language_code": "pl",
}


async def get_token(async_client: AsyncClient, user_dict: dict) -> str:
    resp = await async_client.post(
        "/api/auth/telegram", json={"init_data": make_telegram_init_data(user_dict)}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _owner(db, user_dict: dict) -> User:
    return (
        await db.execute(select(User).where(User.telegram_user_id == user_dict["id"]))
    ).scalar_one()


async def _make_project(db, owner_id: uuid.UUID) -> Project:
    project = Project(
        owner_id=owner_id, name="Obiekt testowy", address="ul. Kwiatowa 1",
        city="Kraków", postal_code="30-001",
    )
    db.add(project)
    await db.commit()
    return project


async def _make_room(db, project_id: uuid.UUID) -> Room:
    room = Room(project_id=project_id, name="Salon")
    db.add(room)
    await db.commit()
    return room


async def _make_template(db) -> ChecklistTemplate:
    template = ChecklistTemplate(
        code="TPL_CONCRETE", version=1, substrate=Substrate.CONCRETE,
        title_key="checklist.concrete.title",
    )
    db.add(template)
    await db.commit()
    return template


async def _make_inspection(db, room_id: uuid.UUID, template_id: uuid.UUID) -> Inspection:
    inspection = Inspection(
        room_id=room_id, template_id=template_id, substrate=Substrate.CONCRETE,
        status=InspectionStatus.COMPLETED, completed_at=datetime.now(timezone.utc),
    )
    db.add(inspection)
    await db.commit()
    return inspection


async def _make_price_item(
    db, owner_id: uuid.UUID, *, code: str, price: str | None = "35.00", is_archived: bool = False,
) -> PriceItem:
    item = PriceItem(
        owner_id=owner_id, code=code, category=PriceCategory.SKIM_COAT, unit=PriceUnit.M2,
        price=Decimal(price) if price is not None else None,
        price_scope=PriceScope.LABOR, is_archived=is_archived,
    )
    db.add(item)
    await db.commit()
    return item


async def _make_recommendation(
    db, room: Room, inspection: Inspection, *,
    recommended_work_code: str = "SKIM_Q3_M2",
    status: WorkRecommendationStatus = WorkRecommendationStatus.PENDING,
    is_active: bool = True,
    trigger_code: str = "old_paint_present",
) -> WorkRecommendation:
    rec = WorkRecommendation(
        trigger_type=WorkRecommendationTriggerType.FINDING,
        trigger_code=trigger_code,
        source_signature=uuid.uuid4().hex,
        inspection_id=inspection.id,
        room_id=room.id,
        surface_id=None,
        target_kind=WorkRecommendationTargetKind.ROOM,
        recommended_work_code=recommended_work_code,
        status=status,
        is_active=is_active,
    )
    db.add(rec)
    await db.commit()
    return rec


async def _make_surface(db, room_id: uuid.UUID) -> Surface:
    surface = Surface(room_id=room_id, name="Ściana 1", surface_type=SurfaceType.WALL)
    db.add(surface)
    await db.commit()
    return surface


async def _make_plan(db, project_id, room_id, surface_id, owner_id) -> SurfaceWorkPlan:
    service = SurfaceWorkPlanService(db)
    return await service.set_plan(
        project_id, room_id, surface_id, owner_id,
        substrate=Substrate.GYPSUM_PLASTER, planned_works=[],
    )


async def _make_actionable_recommendation(
    db, room: Room, inspection: Inspection, surface: Surface, *,
    recommended_work_code: str = "SKIM_Q3_M2",
) -> WorkRecommendation:
    rec = WorkRecommendation(
        trigger_type=WorkRecommendationTriggerType.FINDING,
        trigger_code="old_paint_present",
        source_signature=uuid.uuid4().hex,
        inspection_id=inspection.id,
        room_id=room.id,
        surface_id=surface.id,
        target_kind=WorkRecommendationTargetKind.WALL,
        recommended_work_code=recommended_work_code,
        status=WorkRecommendationStatus.PENDING,
        is_active=True,
    )
    db.add(rec)
    await db.commit()
    return rec


def _accept_url(project_id, recommendation_id) -> str:
    return f"/api/projects/{project_id}/work-recommendations/{recommendation_id}/accept"


def _list_url(project_id, room_id) -> str:
    return f"/api/projects/{project_id}/rooms/{room_id}/work-recommendations"


def _dismiss_url(project_id, recommendation_id) -> str:
    return f"/api/projects/{project_id}/work-recommendations/{recommendation_id}/dismiss"


def _reconsider_url(project_id, recommendation_id) -> str:
    return f"/api/projects/{project_id}/work-recommendations/{recommendation_id}/reconsider"


class TestS_DismissPending:
    async def test_dismiss_pending_becomes_dismissed(self, async_client: AsyncClient, db_session):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rec = await _make_recommendation(db_session, room, inspection)

        resp = await async_client.post(_dismiss_url(project.id, rec.id), headers=auth_header(token))

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "DISMISSED"
        assert data["dismissed_at"] is not None
        assert data["is_active"] is True


class TestT_DismissIdempotent:
    async def test_dismiss_already_dismissed_is_idempotent(self, async_client: AsyncClient, db_session):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rec = await _make_recommendation(
            db_session, room, inspection, status=WorkRecommendationStatus.DISMISSED,
        )

        resp1 = await async_client.post(_dismiss_url(project.id, rec.id), headers=auth_header(token))
        resp2 = await async_client.post(_dismiss_url(project.id, rec.id), headers=auth_header(token))

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "DISMISSED"


class TestU_DismissAcceptedRejected:
    async def test_dismiss_accepted_is_rejected(self, async_client: AsyncClient, db_session):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rec = await _make_recommendation(
            db_session, room, inspection, status=WorkRecommendationStatus.ACCEPTED,
        )

        resp = await async_client.post(_dismiss_url(project.id, rec.id), headers=auth_header(token))

        assert resp.status_code == 409, resp.text


class TestV_ReconsiderDismissed:
    async def test_reconsider_dismissed_becomes_pending(self, async_client: AsyncClient, db_session):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rec = await _make_recommendation(
            db_session, room, inspection, status=WorkRecommendationStatus.DISMISSED,
        )

        resp = await async_client.post(_reconsider_url(project.id, rec.id), headers=auth_header(token))

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "PENDING"
        assert data["dismissed_at"] is None


class TestW_ReconsiderPendingIdempotent:
    async def test_reconsider_pending_is_idempotent(self, async_client: AsyncClient, db_session):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rec = await _make_recommendation(db_session, room, inspection)

        resp = await async_client.post(_reconsider_url(project.id, rec.id), headers=auth_header(token))

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "PENDING"


class TestX_ReconsiderAcceptedRejected:
    async def test_reconsider_accepted_is_rejected(self, async_client: AsyncClient, db_session):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rec = await _make_recommendation(
            db_session, room, inspection, status=WorkRecommendationStatus.ACCEPTED,
        )

        resp = await async_client.post(_reconsider_url(project.id, rec.id), headers=auth_header(token))

        assert resp.status_code == 409, resp.text


class TestY_ReconsiderInactiveDoesNotReactivate:
    async def test_reconsider_inactive_recommendation_keeps_is_active_false(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rec = await _make_recommendation(
            db_session, room, inspection,
            status=WorkRecommendationStatus.DISMISSED, is_active=False,
        )

        resp = await async_client.post(_reconsider_url(project.id, rec.id), headers=auth_header(token))

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "PENDING"
        assert data["is_active"] is False


class TestZ_CrossProjectRejected:
    async def test_dismiss_from_a_different_owner_is_rejected(
        self, async_client: AsyncClient, db_session
    ):
        owner_token = await get_token(async_client, VALID_USER)
        other_token = await get_token(async_client, OTHER_USER)
        owner = await _owner(db_session, VALID_USER)
        other_owner = await _owner(db_session, OTHER_USER)
        project = await _make_project(db_session, owner.id)
        other_project = await _make_project(db_session, other_owner.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rec = await _make_recommendation(db_session, room, inspection)

        # Using the OTHER owner's project_id (not the recommendation's own
        # project) must not resolve the recommendation, regardless of token.
        resp = await async_client.post(
            _dismiss_url(other_project.id, rec.id), headers=auth_header(other_token)
        )
        assert resp.status_code == 404, resp.text

        # The real owner's project_id but the OTHER owner's token must also
        # fail (ownership resolves through owner_id, never project_id alone).
        resp2 = await async_client.post(
            _dismiss_url(project.id, rec.id), headers=auth_header(other_token)
        )
        assert resp2.status_code == 404, resp2.text

        # Sanity: the real owner can dismiss it.
        resp3 = await async_client.post(
            _dismiss_url(project.id, rec.id), headers=auth_header(owner_token)
        )
        assert resp3.status_code == 200, resp3.text

    async def test_cross_project_list_is_rejected(self, async_client: AsyncClient, db_session):
        owner_token = await get_token(async_client, VALID_USER)
        other_token = await get_token(async_client, OTHER_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)

        resp = await async_client.get(_list_url(project.id, room.id), headers=auth_header(other_token))
        assert resp.status_code == 404, resp.text


class TestAA_ListReadOnly:
    async def test_list_does_not_materialize_or_mutate(self, async_client: AsyncClient, db_session):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rec = await _make_recommendation(db_session, room, inspection)
        updated_at_before = rec.updated_at

        resp = await async_client.get(_list_url(project.id, room.id), headers=auth_header(token))

        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] == 1

        refreshed = (
            await db_session.execute(
                select(WorkRecommendation).where(WorkRecommendation.room_id == room.id)
            )
        ).scalars().all()
        assert len(refreshed) == 1
        assert refreshed[0].updated_at == updated_at_before


class TestAB_NullPricePreserved:
    async def test_list_preserves_null_owner_price(self, async_client: AsyncClient, db_session):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_price_item(db_session, owner.id, code="UNRESOLVED_ITEM", price=None)
        await _make_recommendation(
            db_session, room, inspection, recommended_work_code="UNRESOLVED_ITEM",
        )

        resp = await async_client.get(_list_url(project.id, room.id), headers=auth_header(token))

        assert resp.status_code == 200, resp.text
        item = resp.json()["items"][0]
        assert item["current_price_item"]["price"] is None


class TestAC_ZeroDistinctFromNull:
    async def test_list_distinguishes_explicit_zero_from_null(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_price_item(db_session, owner.id, code="ZERO_ITEM", price="0.00")
        await _make_recommendation(
            db_session, room, inspection, recommended_work_code="ZERO_ITEM",
        )

        resp = await async_client.get(_list_url(project.id, room.id), headers=auth_header(token))

        item = resp.json()["items"][0]
        assert item["current_price_item"]["price"] == "0.00"
        assert item["current_price_item"]["price"] is not None


class TestAD_ArchivedVisibleNoSubstitution:
    async def test_archived_price_item_is_visible_not_substituted(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_price_item(db_session, owner.id, code="ARCHIVED_ITEM", price="20.00", is_archived=True)
        await _make_recommendation(
            db_session, room, inspection, recommended_work_code="ARCHIVED_ITEM",
        )

        resp = await async_client.get(_list_url(project.id, room.id), headers=auth_header(token))

        item = resp.json()["items"][0]
        assert item["current_price_item"]["is_archived"] is True
        assert item["current_price_item"]["code"] == "ARCHIVED_ITEM"


class TestAE_NoMarketSubstitution:
    async def test_market_reference_price_never_substitutes_owner_price(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        item = await _make_price_item(db_session, owner.id, code="EVIDENCED_ITEM", price="35.00")
        db_session.add(
            PriceMarketReference(
                price_item_id=item.id, region="Kraków", unit=PriceUnit.M2,
                market_min=Decimal("50.00"), market_max=Decimal("70.00"),
                reference_price=Decimal("60.00"),
                checked_at=datetime.now(timezone.utc),
            )
        )
        await db_session.commit()
        await _make_recommendation(
            db_session, room, inspection, recommended_work_code="EVIDENCED_ITEM",
        )

        resp = await async_client.get(_list_url(project.id, room.id), headers=auth_header(token))

        item_data = resp.json()["items"][0]["current_price_item"]
        assert item_data["price"] == "35.00"


def _evaluate_url(project_id, room_id) -> str:
    return f"{_list_url(project_id, room_id)}/evaluate"


class TestEvaluateEndpoint:
    """HTTP-level wiring for the explicit evaluation endpoint itself (route,
    dependency injection, schema serialization). The underlying reconciliation
    algorithm is exhaustively covered at the service level in
    test_work_recommendation_evaluation.py.
    """

    async def test_evaluate_via_http_creates_and_returns_recommendation(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        from app.models.inspection import InspectionFinding
        finding = InspectionFinding(
            inspection_id=inspection.id, finding_key="old_paint_present", is_active=True,
        )
        db_session.add(finding)
        db_session.add(
            WorkRecommendationRule(
                trigger_type=WorkRecommendationTriggerType.FINDING,
                trigger_code="old_paint_present",
                recommended_work_code="MECHANICAL_SCRATCH",
            )
        )
        await db_session.commit()

        resp = await async_client.post(
            _evaluate_url(project.id, room.id), headers=auth_header(token)
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["created"] == 1
        assert data["reactivated"] == 0
        assert data["unchanged"] == 0
        assert data["resolved"] == 0
        assert data["total"] == 1
        assert data["items"][0]["recommended_work_code"] == "MECHANICAL_SCRATCH"
        assert data["items"][0]["status"] == "PENDING"

    async def test_evaluate_route_rejects_get(self, async_client: AsyncClient, db_session):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)

        resp = await async_client.get(
            _evaluate_url(project.id, room.id), headers=auth_header(token)
        )

        assert resp.status_code == 405, resp.text

    async def test_repeat_evaluate_via_http_is_idempotent(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        from app.models.inspection import InspectionFinding
        finding = InspectionFinding(
            inspection_id=inspection.id, finding_key="old_paint_present", is_active=True,
        )
        db_session.add(finding)
        db_session.add(
            WorkRecommendationRule(
                trigger_type=WorkRecommendationTriggerType.FINDING,
                trigger_code="old_paint_present",
                recommended_work_code="MECHANICAL_SCRATCH",
            )
        )
        await db_session.commit()

        first = await async_client.post(_evaluate_url(project.id, room.id), headers=auth_header(token))
        second = await async_client.post(_evaluate_url(project.id, room.id), headers=auth_header(token))

        assert first.json()["created"] == 1
        assert second.json()["created"] == 0
        assert second.json()["unchanged"] == 1
        assert second.json()["total"] == 1


class TestCrossOwnerPriceItemIsolation:
    async def test_listing_never_resolves_another_owners_priceitem_with_same_code(
        self, async_client: AsyncClient, db_session
    ):
        owner_token = await get_token(async_client, VALID_USER)
        await get_token(async_client, OTHER_USER)
        owner = await _owner(db_session, VALID_USER)
        other_owner = await _owner(db_session, OTHER_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)

        # Owner A has NO PriceItem with this code; Owner B does.
        await _make_price_item(db_session, other_owner.id, code="SHARED_CODE", price="99.00")
        await _make_recommendation(
            db_session, room, inspection, recommended_work_code="SHARED_CODE",
        )

        resp = await async_client.get(_list_url(project.id, room.id), headers=auth_header(owner_token))

        assert resp.status_code == 200, resp.text
        item = resp.json()["items"][0]
        assert item["current_price_item"] is None


class TestAcceptEndpointWiring:
    async def test_accept_via_http_success(self, async_client: AsyncClient, db_session):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_plan(db_session, project.id, room.id, wall.id, owner.id)
        await _make_price_item(db_session, owner.id, code="SKIM_Q3_M2")
        rec = await _make_actionable_recommendation(db_session, room, inspection, wall)

        resp = await async_client.post(_accept_url(project.id, rec.id), headers=auth_header(token))

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "ACCEPTED"
        assert data["accepted_at"] is not None
        assert data["current_price_item"]["code"] == "SKIM_Q3_M2"

    async def test_accept_with_manual_price_item_id_body(self, async_client: AsyncClient, db_session):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_plan(db_session, project.id, room.id, wall.id, owner.id)
        fallback = await _make_price_item(db_session, owner.id, code="MANUAL_FALLBACK")
        rec = await _make_actionable_recommendation(
            db_session, room, inspection, wall, recommended_work_code="NO_SEMANTIC_MATCH",
        )

        resp = await async_client.post(
            _accept_url(project.id, rec.id),
            headers=auth_header(token),
            json={"price_item_id": str(fallback.id)},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["current_price_item"]["code"] == "MANUAL_FALLBACK"

    async def test_accept_without_body_is_accepted(self, async_client: AsyncClient, db_session):
        """Optional request body -- accept must work with no JSON body sent."""
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_plan(db_session, project.id, room.id, wall.id, owner.id)
        await _make_price_item(db_session, owner.id, code="SKIM_Q3_M2")
        rec = await _make_actionable_recommendation(db_session, room, inspection, wall)

        resp = await async_client.post(_accept_url(project.id, rec.id), headers=auth_header(token))
        assert resp.status_code == 200, resp.text

    async def test_accept_with_empty_json_object_body_resolves_semantically(
        self, async_client: AsyncClient, db_session
    ):
        """An explicit `{}` body (distinct from truly no body) must still
        trigger semantic-code resolution, not be rejected as a malformed
        payload -- FastAPI body declarations can accidentally make the
        whole body required even when its one field is optional.
        """
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_plan(db_session, project.id, room.id, wall.id, owner.id)
        item = await _make_price_item(db_session, owner.id, code="SKIM_Q3_M2")
        rec = await _make_actionable_recommendation(db_session, room, inspection, wall)

        resp = await async_client.post(
            _accept_url(project.id, rec.id), headers=auth_header(token), json={},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["current_price_item"]["id"] == str(item.id)

    async def test_accept_with_explicit_null_price_item_id_resolves_semantically(
        self, async_client: AsyncClient, db_session
    ):
        """`{"price_item_id": null}` must behave identically to omitting the
        field or omitting the body entirely -- semantic resolution, not an
        attempt to resolve a literal null id.
        """
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_plan(db_session, project.id, room.id, wall.id, owner.id)
        item = await _make_price_item(db_session, owner.id, code="SKIM_Q3_M2")
        rec = await _make_actionable_recommendation(db_session, room, inspection, wall)

        resp = await async_client.post(
            _accept_url(project.id, rec.id),
            headers=auth_header(token),
            json={"price_item_id": None},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["current_price_item"]["id"] == str(item.id)

    async def test_accept_dismissed_returns_409(self, async_client: AsyncClient, db_session):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_plan(db_session, project.id, room.id, wall.id, owner.id)
        await _make_price_item(db_session, owner.id, code="SKIM_Q3_M2")
        rec = await _make_actionable_recommendation(db_session, room, inspection, wall)
        rec.status = WorkRecommendationStatus.DISMISSED
        await db_session.commit()

        resp = await async_client.post(_accept_url(project.id, rec.id), headers=auth_header(token))
        assert resp.status_code == 409, resp.text

    async def test_accept_room_advisory_returns_422(self, async_client: AsyncClient, db_session):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rec = await _make_recommendation(db_session, room, inspection)  # ROOM target by default

        resp = await async_client.post(_accept_url(project.id, rec.id), headers=auth_header(token))
        assert resp.status_code == 422, resp.text

    async def test_accept_missing_workplan_returns_404(self, async_client: AsyncClient, db_session):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_price_item(db_session, owner.id, code="SKIM_Q3_M2")
        rec = await _make_actionable_recommendation(db_session, room, inspection, wall)

        resp = await async_client.post(_accept_url(project.id, rec.id), headers=auth_header(token))
        assert resp.status_code == 404, resp.text

    async def test_accept_reveal_category_returns_422(self, async_client: AsyncClient, db_session):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_plan(db_session, project.id, room.id, wall.id, owner.id)
        item = PriceItem(
            owner_id=owner.id, code="REVEAL_ITEM", category=PriceCategory.REVEAL,
            unit=PriceUnit.LM, price=Decimal("10.00"), price_scope=PriceScope.LABOR,
        )
        db_session.add(item)
        await db_session.commit()
        rec = await _make_actionable_recommendation(
            db_session, room, inspection, wall, recommended_work_code="REVEAL_ITEM",
        )

        resp = await async_client.post(_accept_url(project.id, rec.id), headers=auth_header(token))
        assert resp.status_code == 422, resp.text


class TestAcceptOwnershipChain:
    async def test_recommendation_from_another_project_rejected(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        other_project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_plan(db_session, project.id, room.id, wall.id, owner.id)
        await _make_price_item(db_session, owner.id, code="SKIM_Q3_M2")
        rec = await _make_actionable_recommendation(db_session, room, inspection, wall)

        # rec belongs to `project`, not `other_project`.
        resp = await async_client.post(
            _accept_url(other_project.id, rec.id), headers=auth_header(token)
        )
        assert resp.status_code == 404, resp.text

    async def test_recommendation_owned_by_another_owner_rejected(
        self, async_client: AsyncClient, db_session
    ):
        owner_token = await get_token(async_client, VALID_USER)
        other_token = await get_token(async_client, OTHER_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_plan(db_session, project.id, room.id, wall.id, owner.id)
        await _make_price_item(db_session, owner.id, code="SKIM_Q3_M2")
        rec = await _make_actionable_recommendation(db_session, room, inspection, wall)

        resp = await async_client.post(
            _accept_url(project.id, rec.id), headers=auth_header(other_token)
        )
        assert resp.status_code == 404, resp.text

        # Sanity: the real owner succeeds.
        resp2 = await async_client.post(
            _accept_url(project.id, rec.id), headers=auth_header(owner_token)
        )
        assert resp2.status_code == 200, resp2.text

    async def test_manual_priceitem_from_another_owner_rejected(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        await get_token(async_client, OTHER_USER)
        owner = await _owner(db_session, VALID_USER)
        other_owner = await _owner(db_session, OTHER_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_plan(db_session, project.id, room.id, wall.id, owner.id)
        foreign_item = await _make_price_item(db_session, other_owner.id, code="FOREIGN")
        rec = await _make_actionable_recommendation(db_session, room, inspection, wall)

        resp = await async_client.post(
            _accept_url(project.id, rec.id),
            headers=auth_header(token),
            json={"price_item_id": str(foreign_item.id)},
        )
        assert resp.status_code == 404, resp.text

    async def test_valid_project_recommendation_priceitem_chain_succeeds(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        owner = await _owner(db_session, VALID_USER)
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_plan(db_session, project.id, room.id, wall.id, owner.id)
        await _make_price_item(db_session, owner.id, code="SKIM_Q3_M2")
        rec = await _make_actionable_recommendation(db_session, room, inspection, wall)

        resp = await async_client.post(_accept_url(project.id, rec.id), headers=auth_header(token))
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "ACCEPTED"
