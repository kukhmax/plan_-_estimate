"""Stage 10F hardening tests for Estimate domain and HTTP API.

Covers correctness gaps not exercised by Stages 10D/10E tests:

F01 - Snapshot immutability (additional triggers)
F02 - Regeneration override preservation (exact spec scenarios)
F03 - NULL/Zero price lifecycle (Case D: finalize after reset-to-null)
F04 - Version sequencing (v1→FINAL immutable after v2, v3, list order, ACCEPTED/ARCHIVED)
F05 - State machine (ACCEPTED / ARCHIVED block all mutations)
F06 - Manual line provenance (all provenance fields NULL)
F07 - Surface provenance (plan_id / planned_work_id / surface_id / room_id / opening_id=NULL)
F08 - Reveal provenance (plan_id=NULL / per-opening independence)
F09 - Reveal quantity sources (exact 1.50×1.40 geometry)
F10 - Duplicates / Order (regen does not collapse duplicates)
F11 - Regeneration: disable reveal removes reveal lines
F12 - Archived PriceItem in generation and reset_price_override
F13 - Transaction atomicity (no partial commit on failure)
F14 - Concurrency / version uniqueness (SELECT FOR UPDATE on Project row; correction applied)
F15 - Decimal / rounding (adversarial cases)
F16 - Ownership isolation (systematic cross-owner)
F17 - HTTP contract fields for Stage 10G readiness
"""
from decimal import Decimal
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    EstimateDraftExistsError,
    EstimateStateError,
    EstimateValidationError,
)
from app.domain.services.estimate_service import EstimateService
from app.domain.services.opening_reveal_work_service import OpeningRevealWorkService
from app.models.checklist import QualityLevel, Substrate
from app.models.estimate import (
    Estimate,
    EstimateLine,
    EstimateStatus,
    LineOrigin,
    QuantitySource,
)
from app.models.opening import Opening, OpeningType
from app.models.opening_reveal_planned_work import OpeningRevealPlannedWork
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.user import User
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan
from tests.conftest import make_telegram_init_data

# ---------------------------------------------------------------------------
# Telegram IDs reserved for this file: 4000001 – 4001000
# ---------------------------------------------------------------------------

VALID_USER = {
    "id": 4000900,
    "username": "howner",
    "first_name": "Hardening",
    "language_code": "pl",
}
OTHER_USER = {
    "id": 4000901,
    "username": "hother",
    "first_name": "Other",
    "language_code": "pl",
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _make_user(db, telegram_id: int) -> User:
    user = User(telegram_user_id=telegram_id, username=f"u{telegram_id}")
    db.add(user)
    await db.commit()
    return user


async def _make_project(db, owner_id: uuid.UUID, *, name: str = "Projekt") -> Project:
    p = Project(
        owner_id=owner_id,
        name=name,
        address="ul. Testowa 1",
        city="Kraków",
        postal_code="30-001",
    )
    db.add(p)
    await db.commit()
    return p


async def _make_room(db, project_id: uuid.UUID) -> Room:
    r = Room(project_id=project_id, name="Salon")
    db.add(r)
    await db.commit()
    return r


async def _make_surface(
    db,
    room_id: uuid.UUID,
    *,
    width: str = "4.000",
    height: str = "2.500",
    position: int = 0,
) -> Surface:
    s = Surface(
        room_id=room_id,
        name="Ściana",
        surface_type=SurfaceType.WALL,
        width=Decimal(width),
        height=Decimal(height),
        position=position,
    )
    db.add(s)
    await db.commit()
    return s


async def _make_opening(
    db,
    surface_id: uuid.UUID,
    *,
    width: str = "1.200",
    height: str = "1.400",
    quantity: int = 1,
    reveal_enabled: bool = True,
    reveal_depth: str | None = "0.250",
    reveal_left: bool = True,
    reveal_right: bool = True,
    reveal_top: bool = True,
    reveal_bottom: bool = False,
) -> Opening:
    opening = Opening(
        surface_id=surface_id,
        opening_type=OpeningType.WINDOW,
        width=Decimal(width),
        height=Decimal(height),
        quantity=quantity,
        reveal_enabled=reveal_enabled,
        reveal_depth=Decimal(reveal_depth) if reveal_depth else None,
        reveal_left=reveal_left,
        reveal_right=reveal_right,
        reveal_top=reveal_top,
        reveal_bottom=reveal_bottom,
    )
    db.add(opening)
    await db.commit()
    return opening


async def _make_price_item(
    db,
    owner_id: uuid.UUID,
    *,
    code: str | None = None,
    category: PriceCategory = PriceCategory.PAINTING,
    unit: PriceUnit = PriceUnit.M2,
    price: str | None = "12.50",
    price_scope: PriceScope = PriceScope.LABOR,
    is_archived: bool = False,
) -> PriceItem:
    item = PriceItem(
        owner_id=owner_id,
        code=code or f"ITEM_{uuid.uuid4().hex[:8].upper()}",
        category=category,
        unit=unit,
        price=Decimal(price) if price is not None else None,
        price_scope=price_scope,
        is_archived=is_archived,
    )
    db.add(item)
    await db.commit()
    return item


async def _make_reveal_item(
    db,
    owner_id: uuid.UUID,
    *,
    unit: PriceUnit = PriceUnit.LM,
    price: str | None = "15.00",
    is_archived: bool = False,
) -> PriceItem:
    return await _make_price_item(
        db,
        owner_id,
        category=PriceCategory.REVEAL,
        unit=unit,
        price=price,
        is_archived=is_archived,
    )


async def _make_work_plan(
    db,
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    owner_id: uuid.UUID,
    price_items: list[PriceItem],
) -> SurfaceWorkPlan:
    from app.domain.services.work_plan_service import SurfaceWorkPlanService
    from app.schemas.work_plan import OrderedPriceItemSelection

    return await SurfaceWorkPlanService(db).set_plan(
        project_id,
        room_id,
        surface_id,
        owner_id,
        substrate=Substrate.GYPSUM_PLASTER,
        planned_works=[
            OrderedPriceItemSelection(price_item_id=item.id) for item in price_items
        ],
    )


async def get_token(client: AsyncClient, user_dict: dict) -> str:
    resp = await client.post(
        "/api/auth/telegram",
        json={"init_data": make_telegram_init_data(user_dict)},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# F01 — Snapshot immutability (additional triggers)
# ===========================================================================


class TestF01_SnapshotImmutabilityAdditional:
    async def test_item_description_change_no_effect_on_snapshot(self, db_session):
        """Changing display_name after generation does not mutate snapshot description."""
        user = await _make_user(db_session, 4000001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="10.00")
        item.display_name = "Original description"
        await db_session.commit()
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        assert line.description == "Original description"

        item.display_name = "Changed description"
        await db_session.commit()

        refreshed = (
            await db_session.execute(
                select(EstimateLine).where(EstimateLine.id == line.id)
            )
        ).scalar_one()
        assert refreshed.description == "Original description"

    async def test_item_archive_no_effect_on_snapshot(self, db_session):
        """Archiving the PriceItem after generation does not mutate snapshot unit_price."""
        user = await _make_user(db_session, 4000002)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="20.00")
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        assert line.unit_price == Decimal("20.00")

        item.is_archived = True
        await db_session.commit()

        refreshed = (
            await db_session.execute(
                select(EstimateLine).where(EstimateLine.id == line.id)
            )
        ).scalar_one()
        assert refreshed.unit_price == Decimal("20.00")
        assert refreshed.item_code == line.item_code

    async def test_opening_geometry_change_no_effect_on_reveal_snapshot(self, db_session):
        """Changing opening width after generation does not update reveal source_quantity."""
        user = await _make_user(db_session, 4000003)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(
            db_session, surface.id, width="1.200", height="1.400", reveal_depth="0.250"
        )
        item = await _make_reveal_item(db_session, user.id, unit=PriceUnit.LM)
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [item.id])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        original_qty = line.source_quantity  # left+right+top = 1.4+1.4+1.2 = 4.0

        opening.width = Decimal("2.000")
        await db_session.commit()

        refreshed = (
            await db_session.execute(
                select(EstimateLine).where(EstimateLine.id == line.id)
            )
        ).scalar_one()
        assert refreshed.source_quantity == original_qty

    async def test_reveal_depth_change_no_effect_on_snapshot(self, db_session):
        """Changing reveal_depth does not mutate reveal area snapshot."""
        user = await _make_user(db_session, 4000004)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id, reveal_depth="0.250")
        item = await _make_reveal_item(db_session, user.id, unit=PriceUnit.M2)
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [item.id])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        original_qty = line.source_quantity

        opening.reveal_depth = Decimal("0.500")
        await db_session.commit()

        refreshed = (
            await db_session.execute(
                select(EstimateLine).where(EstimateLine.id == line.id)
            )
        ).scalar_one()
        assert refreshed.source_quantity == original_qty

    async def test_replace_surface_workplan_no_effect_on_existing_snapshot(
        self, db_session
    ):
        """Replacing the SurfaceWorkPlan after generation leaves existing lines unchanged."""
        user = await _make_user(db_session, 4000005)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item_a = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="10.00")
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item_a])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        original_desc = line.description
        original_price = line.unit_price

        item_b = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="99.00")
        item_b.display_name = "New item"
        await db_session.commit()
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item_b])

        refreshed = (
            await db_session.execute(
                select(EstimateLine).where(EstimateLine.id == line.id)
            )
        ).scalar_one()
        assert refreshed.description == original_desc
        assert refreshed.unit_price == original_price

    async def test_edit_reveal_planned_work_no_effect_on_snapshot(self, db_session):
        """Replacing the OpeningRevealPlannedWork list does not update existing lines."""
        user = await _make_user(db_session, 4000006)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id, reveal_depth="0.250")
        item_a = await _make_reveal_item(db_session, user.id, unit=PriceUnit.LM)
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [item_a.id])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        original_pwid = line.planned_work_id

        item_b = await _make_reveal_item(db_session, user.id, unit=PriceUnit.LM)
        await reveal_svc.set_works(opening.id, user.id, [item_b.id])

        refreshed = (
            await db_session.execute(
                select(EstimateLine).where(EstimateLine.id == line.id)
            )
        ).scalar_one()
        assert refreshed.planned_work_id == original_pwid


# ===========================================================================
# F02 — Regeneration override preservation (exact spec scenarios)
# ===========================================================================


class TestF02_RegenerationOverridePreservation:
    async def test_qty_override_preserved_source_updated(self, db_session):
        """qty_overridden=True: after geometry change regeneration updates source_quantity
        but preserves the owner-set quantity."""
        user = await _make_user(db_session, 4000010)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        # Initial: 4×2.5 = 10 m²
        surface = await _make_surface(db_session, room.id, width="4.000", height="2.500")
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="10.00")
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        assert line.source_quantity == Decimal("10.000")

        # Owner overrides qty to 11
        line.quantity = Decimal("11.000")
        line.quantity_overridden = True
        await db_session.commit()

        # Geometry changes to 12 m²
        surface.width = Decimal("4.800")  # 4.8 × 2.5 = 12.0
        await db_session.commit()

        result = await svc.regenerate_draft(estimate.id, user.id)

        refreshed = (
            await db_session.execute(
                select(EstimateLine).where(EstimateLine.id == line.id)
            )
        ).scalar_one()
        assert refreshed.source_quantity == Decimal("12.000")
        assert refreshed.quantity == Decimal("11.000")
        assert refreshed.quantity_overridden is True

    async def test_qty_override_shows_in_preview_diff(self, db_session):
        """Preview: old_source=10, new_source=12 when geometry changes, override preserved."""
        user = await _make_user(db_session, 4000011)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id, width="4.000", height="2.500")
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="10.00")
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        line.quantity = Decimal("11.000")
        line.quantity_overridden = True
        await db_session.commit()

        surface.width = Decimal("4.800")  # 12 m²
        await db_session.commit()

        result = await svc.preview_regeneration(project.id, estimate.id, user.id)
        assert result.updated == 1
        assert len(result.changes) == 1
        entry = result.changes[0]
        assert entry.change_type == "UPDATED"
        assert entry.old_source_quantity == Decimal("10.000")
        assert entry.new_source_quantity == Decimal("12.000")
        assert entry.quantity_overridden is True

    async def test_price_override_preserved_when_pricebook_changes(self, db_session):
        """price_override=True: regeneration preserves override even if PriceBook changes."""
        user = await _make_user(db_session, 4000012)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="30.00")
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        assert line.unit_price == Decimal("30.00")

        # Owner overrides price to 35
        line.unit_price = Decimal("35.00")
        line.price_override = True
        await db_session.commit()

        # PriceBook changes to 40
        item.price = Decimal("40.00")
        await db_session.commit()

        await svc.regenerate_draft(estimate.id, user.id)

        refreshed = (
            await db_session.execute(
                select(EstimateLine).where(EstimateLine.id == line.id)
            )
        ).scalar_one()
        assert refreshed.unit_price == Decimal("35.00")
        assert refreshed.price_override is True

    async def test_reset_price_override_restores_current_pricebook(self, db_session):
        """reset_price_override after PriceBook change: gets new price 40, flag cleared."""
        user = await _make_user(db_session, 4000013)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="30.00")
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        line.unit_price = Decimal("35.00")
        line.price_override = True
        await db_session.commit()

        item.price = Decimal("40.00")
        await db_session.commit()

        updated = await svc.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields=set(),
            reset_price_override=True,
        )
        assert updated.unit_price == Decimal("40.00")
        assert updated.price_override is False

    async def test_preview_shows_price_override_flag_in_updated_entry(self, db_session):
        """Preview shows price_override=True for lines with an active price override."""
        user = await _make_user(db_session, 4000014)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id, width="4.000", height="2.500")
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="30.00")
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        line.unit_price = Decimal("35.00")
        line.price_override = True
        await db_session.commit()

        # Change geometry to force UPDATED diff entry
        surface.width = Decimal("5.000")  # 5×2.5=12.5
        await db_session.commit()

        result = await svc.preview_regeneration(project.id, estimate.id, user.id)
        assert result.updated == 1
        entry = result.changes[0]
        assert entry.price_override is True
        # new_unit_price reflects the override (kept at 35)
        assert entry.new_unit_price == Decimal("35.00")


# ===========================================================================
# F03 — NULL/Zero lifecycle: Case D finalize
# ===========================================================================


class TestF03_NullZeroLifecycle:
    async def test_case_d_reset_to_null_price_then_finalize_blocked(self, db_session):
        """Case D: reset_price_override when PriceBook price=NULL → unit_price=NULL → FINAL rejected."""
        user = await _make_user(db_session, 4000020)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="10.00")
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]

        # Owner sets price override
        line.unit_price = Decimal("25.00")
        line.price_override = True
        await db_session.commit()

        # PriceBook price becomes NULL
        item.price = None
        await db_session.commit()

        # Reset override → unit_price=NULL restored from PriceBook
        updated = await svc.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields=set(),
            reset_price_override=True,
        )
        assert updated.unit_price is None
        assert updated.price_override is False

        # Finalize must be rejected
        with pytest.raises(EstimateValidationError):
            await svc.finalize(estimate.id, user.id, project_id=project.id)

    async def test_zero_price_finalizes_successfully(self, db_session):
        """Case B: PriceItem.price=0.00 → DRAFT unit_price=0.00 → FINAL allowed."""
        user = await _make_user(db_session, 4000021)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="0.00")
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        assert line.unit_price == Decimal("0.00")
        assert line.amount == Decimal("0.00")

        finalized = await svc.finalize(estimate.id, user.id, project_id=project.id)
        assert finalized.status == EstimateStatus.FINAL

    async def test_case_c_override_to_null_finalize_blocked(self, db_session):
        """Case C: owner sets unit_price=NULL explicitly → FINAL rejected."""
        user = await _make_user(db_session, 4000022)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="10.00")
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]

        updated = await svc.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields={"unit_price"},
            unit_price=None,
        )
        assert updated.unit_price is None
        assert updated.price_override is True

        with pytest.raises(EstimateValidationError):
            await svc.finalize(estimate.id, user.id, project_id=project.id)


# ===========================================================================
# F04 — Version sequencing
# ===========================================================================


class TestF04_VersionSequencing:
    async def test_final_v1_lines_unchanged_after_v2_generated(self, db_session):
        """FINAL v1 snapshot is immutable even after DRAFT v2 is created."""
        user = await _make_user(db_session, 4000030)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="10.00")
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)

        draft_v1 = await svc.generate_estimate(project.id, user.id)
        v1_line_id = draft_v1.lines[0].id
        v1_price = draft_v1.lines[0].unit_price

        final_v1 = await svc.finalize(draft_v1.id, user.id, project_id=project.id)
        assert final_v1.version == 1

        item.price = Decimal("99.00")
        await db_session.commit()
        draft_v2 = await svc.generate_estimate(project.id, user.id)
        assert draft_v2.version == 2

        v1_line = (
            await db_session.execute(
                select(EstimateLine).where(EstimateLine.id == v1_line_id)
            )
        ).scalar_one()
        assert v1_line.unit_price == v1_price

    async def test_version_three_after_two_finals(self, db_session):
        """v1→FINAL, v2 DRAFT→FINAL, generate → v3 DRAFT."""
        user = await _make_user(db_session, 4000031)
        project = await _make_project(db_session, user.id)
        svc = EstimateService(db_session)

        v1 = await svc.generate_estimate(project.id, user.id)
        await svc.finalize(v1.id, user.id, project_id=project.id)

        v2 = await svc.generate_estimate(project.id, user.id)
        assert v2.version == 2
        await svc.finalize(v2.id, user.id, project_id=project.id)

        v3 = await svc.generate_estimate(project.id, user.id)
        assert v3.version == 3
        assert v3.status == EstimateStatus.DRAFT

    async def test_list_ordered_newest_first(self, db_session):
        """list_estimates returns estimates in descending version order."""
        user = await _make_user(db_session, 4000032)
        project = await _make_project(db_session, user.id)
        svc = EstimateService(db_session)

        v1 = await svc.generate_estimate(project.id, user.id)
        await svc.finalize(v1.id, user.id, project_id=project.id)
        v2 = await svc.generate_estimate(project.id, user.id)
        await svc.finalize(v2.id, user.id, project_id=project.id)
        await svc.generate_estimate(project.id, user.id)

        estimates = await svc.list_estimates(project.id, user.id)
        versions = [e.version for e in estimates]
        assert versions == sorted(versions, reverse=True)
        assert versions[0] == 3

    async def test_versions_strictly_increasing(self, db_session):
        """Each successive DRAFT has version = previous max + 1."""
        user = await _make_user(db_session, 4000033)
        project = await _make_project(db_session, user.id)
        svc = EstimateService(db_session)

        versions_seen = []
        for _ in range(3):
            draft = await svc.generate_estimate(project.id, user.id)
            versions_seen.append(draft.version)
            await svc.finalize(draft.id, user.id, project_id=project.id)

        assert versions_seen == [1, 2, 3]

    async def test_generate_after_accepted_creates_new_draft(self, db_session):
        """generate after ACCEPTED status creates the next DRAFT version."""
        user = await _make_user(db_session, 4000034)
        project = await _make_project(db_session, user.id)
        svc = EstimateService(db_session)

        v1 = await svc.generate_estimate(project.id, user.id)
        v1.status = EstimateStatus.ACCEPTED
        await db_session.commit()

        v2 = await svc.generate_estimate(project.id, user.id)
        assert v2.version == 2
        assert v2.status == EstimateStatus.DRAFT

    async def test_generate_after_archived_creates_new_draft(self, db_session):
        """generate after ARCHIVED status creates the next DRAFT version."""
        user = await _make_user(db_session, 4000035)
        project = await _make_project(db_session, user.id)
        svc = EstimateService(db_session)

        v1 = await svc.generate_estimate(project.id, user.id)
        v1.status = EstimateStatus.ARCHIVED
        await db_session.commit()

        v2 = await svc.generate_estimate(project.id, user.id)
        assert v2.version == 2
        assert v2.status == EstimateStatus.DRAFT

    async def test_no_duplicate_versions_for_project(self, db_session):
        """Each (project_id, version) pair is unique across all estimates."""
        user = await _make_user(db_session, 4000036)
        project = await _make_project(db_session, user.id)
        svc = EstimateService(db_session)

        v1 = await svc.generate_estimate(project.id, user.id)
        await svc.finalize(v1.id, user.id, project_id=project.id)
        v2 = await svc.generate_estimate(project.id, user.id)
        await svc.finalize(v2.id, user.id, project_id=project.id)
        v3 = await svc.generate_estimate(project.id, user.id)

        all_estimates = (
            await db_session.execute(
                select(Estimate).where(Estimate.project_id == project.id)
            )
        ).scalars().all()
        all_versions = [e.version for e in all_estimates]
        assert len(all_versions) == len(set(all_versions)), "Duplicate versions found"


# ===========================================================================
# F05 — State machine: ACCEPTED / ARCHIVED mutations blocked
# ===========================================================================


class TestF05_StateMachineAcceptedArchived:
    async def _make_draft_with_line(self, db_session, telegram_id: int):
        user = await _make_user(db_session, telegram_id)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="10.00")
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        return user, project, estimate, svc

    async def test_regenerate_accepted_rejected(self, db_session):
        user, project, estimate, svc = await self._make_draft_with_line(db_session, 4000040)
        estimate.status = EstimateStatus.ACCEPTED
        await db_session.commit()
        with pytest.raises(EstimateStateError):
            await svc.regenerate_draft(estimate.id, user.id)

    async def test_regenerate_archived_rejected(self, db_session):
        user, project, estimate, svc = await self._make_draft_with_line(db_session, 4000041)
        estimate.status = EstimateStatus.ARCHIVED
        await db_session.commit()
        with pytest.raises(EstimateStateError):
            await svc.regenerate_draft(estimate.id, user.id)

    async def test_add_manual_line_accepted_rejected(self, db_session):
        user, project, estimate, svc = await self._make_draft_with_line(db_session, 4000042)
        estimate.status = EstimateStatus.ACCEPTED
        await db_session.commit()
        with pytest.raises(EstimateStateError):
            await svc.add_manual_line(
                estimate.id, user.id,
                description="X",
                scope=PriceScope.LABOR,
                unit=PriceUnit.FLAT,
                quantity=Decimal("1.000"),
                unit_price=Decimal("10.00"),
                project_id=project.id,
            )

    async def test_add_manual_line_archived_rejected(self, db_session):
        user, project, estimate, svc = await self._make_draft_with_line(db_session, 4000043)
        estimate.status = EstimateStatus.ARCHIVED
        await db_session.commit()
        with pytest.raises(EstimateStateError):
            await svc.add_manual_line(
                estimate.id, user.id,
                description="X",
                scope=PriceScope.LABOR,
                unit=PriceUnit.FLAT,
                quantity=Decimal("1.000"),
                unit_price=Decimal("10.00"),
                project_id=project.id,
            )

    async def test_patch_line_accepted_rejected(self, db_session):
        user, project, estimate, svc = await self._make_draft_with_line(db_session, 4000044)
        line_id = estimate.lines[0].id
        estimate.status = EstimateStatus.ACCEPTED
        await db_session.commit()
        with pytest.raises(EstimateStateError):
            await svc.patch_line(
                project.id, estimate.id, user.id, line_id,
                provided_fields={"quantity"},
                quantity=Decimal("5.000"),
            )

    async def test_patch_line_archived_rejected(self, db_session):
        user, project, estimate, svc = await self._make_draft_with_line(db_session, 4000045)
        line_id = estimate.lines[0].id
        estimate.status = EstimateStatus.ARCHIVED
        await db_session.commit()
        with pytest.raises(EstimateStateError):
            await svc.patch_line(
                project.id, estimate.id, user.id, line_id,
                provided_fields={"quantity"},
                quantity=Decimal("5.000"),
            )

    async def test_finalize_accepted_rejected(self, db_session):
        user, project, estimate, svc = await self._make_draft_with_line(db_session, 4000046)
        estimate.status = EstimateStatus.ACCEPTED
        await db_session.commit()
        with pytest.raises(EstimateStateError):
            await svc.finalize(estimate.id, user.id, project_id=project.id)

    async def test_finalize_archived_rejected(self, db_session):
        user, project, estimate, svc = await self._make_draft_with_line(db_session, 4000047)
        estimate.status = EstimateStatus.ARCHIVED
        await db_session.commit()
        with pytest.raises(EstimateStateError):
            await svc.finalize(estimate.id, user.id, project_id=project.id)

    async def test_finalize_already_final_rejected(self, db_session):
        user, project, estimate, svc = await self._make_draft_with_line(db_session, 4000048)
        # Set a price so finalize succeeds once
        line = estimate.lines[0]
        line.unit_price = Decimal("10.00")
        await db_session.commit()
        await svc.finalize(estimate.id, user.id, project_id=project.id)
        with pytest.raises(EstimateStateError):
            await svc.finalize(estimate.id, user.id, project_id=project.id)

    async def test_preview_accepted_rejected(self, db_session):
        user, project, estimate, svc = await self._make_draft_with_line(db_session, 4000049)
        estimate.status = EstimateStatus.ACCEPTED
        await db_session.commit()
        with pytest.raises(EstimateStateError):
            await svc.preview_regeneration(project.id, estimate.id, user.id)


# ===========================================================================
# F06 — Manual line provenance (all fields must be NULL)
# ===========================================================================


class TestF06_ManualLineProvenance:
    async def test_manual_line_provenance_all_null(self, db_session):
        """MANUAL lines must not carry any provenance references."""
        user = await _make_user(db_session, 4000050)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2)
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        line = await svc.add_manual_line(
            estimate.id, user.id,
            description="Manual item",
            scope=PriceScope.LABOR,
            unit=PriceUnit.FLAT,
            quantity=Decimal("1.000"),
            unit_price=Decimal("100.00"),
            project_id=project.id,
        )
        assert line.price_item_id is None
        assert line.plan_id is None
        assert line.planned_work_id is None
        assert line.surface_id is None
        assert line.room_id is None
        assert line.opening_id is None
        assert line.item_code is None
        assert line.origin == LineOrigin.MANUAL

    async def test_manual_line_currency_matches_estimate(self, db_session):
        """Manual lines inherit the estimate currency; mismatched currency is rejected."""
        user = await _make_user(db_session, 4000051)
        project = await _make_project(db_session, user.id)
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        assert estimate.currency == "PLN"

        with pytest.raises(EstimateValidationError):
            await svc.add_manual_line(
                estimate.id, user.id,
                description="EUR line",
                scope=PriceScope.LABOR,
                unit=PriceUnit.FLAT,
                quantity=Decimal("1.000"),
                unit_price=Decimal("10.00"),
                currency="EUR",
                project_id=project.id,
            )

    async def test_manual_line_price_override_always_true(self, db_session):
        """price_override on MANUAL lines is always True (owner controls price)."""
        user = await _make_user(db_session, 4000052)
        project = await _make_project(db_session, user.id)
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        line = await svc.add_manual_line(
            estimate.id, user.id,
            description="Manual",
            scope=PriceScope.MATERIAL,
            unit=PriceUnit.PCS,
            quantity=Decimal("3.000"),
            unit_price=Decimal("50.00"),
            project_id=project.id,
        )
        assert line.price_override is True

    async def test_manual_line_survives_regeneration_unchanged(self, db_session):
        """MANUAL line provenance fields remain NULL after regeneration."""
        user = await _make_user(db_session, 4000053)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2)
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        manual = await svc.add_manual_line(
            estimate.id, user.id,
            description="Stays",
            scope=PriceScope.LABOR,
            unit=PriceUnit.FLAT,
            quantity=Decimal("1.000"),
            unit_price=Decimal("200.00"),
            project_id=project.id,
        )
        await svc.regenerate_draft(estimate.id, user.id)

        refreshed = (
            await db_session.execute(
                select(EstimateLine).where(EstimateLine.id == manual.id)
            )
        ).scalar_one()
        assert refreshed.price_item_id is None
        assert refreshed.plan_id is None
        assert refreshed.planned_work_id is None
        assert refreshed.surface_id is None
        assert refreshed.opening_id is None


# ===========================================================================
# F07 — Surface provenance correctness
# ===========================================================================


class TestF07_SurfaceProvenance:
    async def test_surface_line_provenance_fields(self, db_session):
        """Generated PLANNED_WORK surface line: plan_id, planned_work_id, surface_id,
        room_id all set; opening_id=NULL."""
        user = await _make_user(db_session, 4000060)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="10.00")
        work_plan = await _make_work_plan(
            db_session, project.id, room.id, surface.id, user.id, [item]
        )
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        line = estimate.lines[0]
        assert line.origin == LineOrigin.PLANNED_WORK
        assert line.plan_id == work_plan.id
        assert line.surface_id == surface.id
        assert line.room_id == room.id
        assert line.opening_id is None
        assert line.planned_work_id is not None
        # planned_work_id must be one of the SurfacePlannedWork IDs under this plan
        pw_ids = {pw.id for pw in work_plan.planned_works}
        assert line.planned_work_id in pw_ids

    async def test_cross_project_provenance_not_possible(self, db_session):
        """Lines from project A cannot appear in an estimate for project B."""
        user = await _make_user(db_session, 4000061)
        project_a = await _make_project(db_session, user.id, name="A")
        project_b = await _make_project(db_session, user.id, name="B")
        room_b = await _make_room(db_session, project_b.id)
        surface_b = await _make_surface(db_session, room_b.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2)
        await _make_work_plan(
            db_session, project_b.id, room_b.id, surface_b.id, user.id, [item]
        )
        svc = EstimateService(db_session)
        estimate_a = await svc.generate_estimate(project_a.id, user.id)
        # Project A has no planned works → no lines
        assert estimate_a.lines == []


# ===========================================================================
# F08 — Reveal provenance and per-opening independence
# ===========================================================================


class TestF08_RevealProvenance:
    async def test_reveal_line_provenance_fields(self, db_session):
        """Reveal line: plan_id=None, opening_id set, planned_work_id set, surface_id/room_id set."""
        user = await _make_user(db_session, 4000070)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id, reveal_depth="0.250")
        item = await _make_reveal_item(db_session, user.id, unit=PriceUnit.LM)
        reveal_svc = OpeningRevealWorkService(db_session)
        reveal_works = await reveal_svc.set_works(opening.id, user.id, [item.id])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        line = estimate.lines[0]
        assert line.origin == LineOrigin.PLANNED_WORK
        assert line.plan_id is None
        assert line.opening_id == opening.id
        assert line.surface_id == surface.id
        assert line.room_id == room.id
        assert line.planned_work_id == reveal_works[0].id

    async def test_different_openings_independent_lines(self, db_session):
        """Three openings on same wall each produce independent reveal lines."""
        user = await _make_user(db_session, 4000071)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)

        # Window A: primer, skim, paint (3 items)
        opening_a = await _make_opening(db_session, surface.id, reveal_depth="0.250")
        item_primer = await _make_reveal_item(db_session, user.id, unit=PriceUnit.LM, price="5.00")
        item_skim = await _make_reveal_item(db_session, user.id, unit=PriceUnit.LM, price="8.00")
        item_paint = await _make_reveal_item(db_session, user.id, unit=PriceUnit.LM, price="3.00")

        # Window B: primer, paint (2 items)
        opening_b = await _make_opening(db_session, surface.id, reveal_depth="0.200")

        # Door C: skim, paint (2 items)
        opening_c = await _make_opening(db_session, surface.id, reveal_depth="0.100")

        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(
            opening_a.id, user.id, [item_primer.id, item_skim.id, item_paint.id]
        )
        await reveal_svc.set_works(
            opening_b.id, user.id, [item_primer.id, item_paint.id]
        )
        await reveal_svc.set_works(
            opening_c.id, user.id, [item_skim.id, item_paint.id]
        )
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        assert len(estimate.lines) == 7  # 3 + 2 + 2
        opening_ids = {l.opening_id for l in estimate.lines}
        assert opening_ids == {opening_a.id, opening_b.id, opening_c.id}

        # Each opening retains its independent line count
        a_lines = [l for l in estimate.lines if l.opening_id == opening_a.id]
        b_lines = [l for l in estimate.lines if l.opening_id == opening_b.id]
        c_lines = [l for l in estimate.lines if l.opening_id == opening_c.id]
        assert len(a_lines) == 3
        assert len(b_lines) == 2
        assert len(c_lines) == 2

    async def test_same_price_item_on_different_openings_no_merge(self, db_session):
        """Same PriceItem on two openings creates two independent lines (no merge)."""
        user = await _make_user(db_session, 4000072)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_reveal_item(db_session, user.id, unit=PriceUnit.LM)

        opening_a = await _make_opening(
            db_session, surface.id, width="1.200", height="1.400", reveal_depth="0.250"
        )
        opening_b = await _make_opening(
            db_session, surface.id, width="0.900", height="2.000", reveal_depth="0.300"
        )
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening_a.id, user.id, [item.id])
        await reveal_svc.set_works(opening_b.id, user.id, [item.id])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        assert len(estimate.lines) == 2
        assert estimate.lines[0].opening_id != estimate.lines[1].opening_id
        # Different source quantities (different opening geometries)
        assert estimate.lines[0].source_quantity != estimate.lines[1].source_quantity


# ===========================================================================
# F09 — Reveal quantity sources (exact 1.50×1.40 geometry)
# ===========================================================================


class TestF09_RevealQuantitySources:
    async def test_exact_reveal_lm_geometry(self, db_session):
        """1.50×1.40, depth=0.30, left/right/top=True, bottom=False →
        length=4.300 for LM item."""
        user = await _make_user(db_session, 4000080)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(
            db_session, surface.id,
            width="1.500", height="1.400",
            reveal_depth="0.300",
            reveal_left=True, reveal_right=True, reveal_top=True, reveal_bottom=False,
            quantity=1,
        )
        item = await _make_reveal_item(db_session, user.id, unit=PriceUnit.LM, price="20.00")
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [item.id])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        line = estimate.lines[0]
        assert line.quantity_source == QuantitySource.REVEAL_LENGTH
        # left=1.40 + right=1.40 + top=1.50 = 4.30
        assert line.source_quantity == Decimal("4.300")
        assert line.quantity == Decimal("4.300")

    async def test_exact_reveal_m2_geometry(self, db_session):
        """1.50×1.40, depth=0.30, left/right/top=True, bottom=False →
        area=1.290 for M2 item."""
        user = await _make_user(db_session, 4000081)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(
            db_session, surface.id,
            width="1.500", height="1.400",
            reveal_depth="0.300",
            reveal_left=True, reveal_right=True, reveal_top=True, reveal_bottom=False,
            quantity=1,
        )
        item = await _make_reveal_item(
            db_session, user.id, unit=PriceUnit.M2, price="25.00"
        )
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [item.id])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        line = estimate.lines[0]
        assert line.quantity_source == QuantitySource.REVEAL_AREA
        # 4.30 × 0.30 = 1.290
        assert line.source_quantity == Decimal("1.290")
        assert line.quantity == Decimal("1.290")

    async def test_reveal_area_not_added_to_surface_net_area(self, db_session):
        """Reveal area appears as separate quantity; never summed with wall net area."""
        user = await _make_user(db_session, 4000082)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id, width="5.000", height="2.700")
        opening = await _make_opening(
            db_session, surface.id,
            width="1.500", height="1.400",
            reveal_depth="0.300",
            reveal_left=True, reveal_right=True, reveal_top=True, reveal_bottom=False,
        )
        wall_item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="10.00"
        )
        reveal_item = await _make_reveal_item(
            db_session, user.id, unit=PriceUnit.M2, price="25.00"
        )
        await _make_work_plan(
            db_session, project.id, room.id, surface.id, user.id, [wall_item]
        )
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [reveal_item.id])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        wall_line = next(l for l in estimate.lines if l.price_item_id == wall_item.id)
        reveal_line = next(l for l in estimate.lines if l.price_item_id == reveal_item.id)
        # wall net = 5×2.7 - 1.5×1.4 = 13.5 - 2.1 = 11.400
        assert wall_line.quantity == Decimal("11.400")
        # reveal area = 1.290 (independent)
        assert reveal_line.quantity == Decimal("1.290")
        assert reveal_line.quantity != wall_line.quantity


# ===========================================================================
# F10 — Duplicates / Order
# ===========================================================================


class TestF10_DuplicatesOrder:
    async def test_duplicate_surface_items_create_two_lines(self, db_session):
        """Same PriceItem twice in SurfaceWorkPlan → two independent EstimateLines."""
        user = await _make_user(db_session, 4000090)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="10.00")
        # Two rows of the same item
        await _make_work_plan(
            db_session, project.id, room.id, surface.id, user.id, [item, item]
        )
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        assert len(estimate.lines) == 2
        assert estimate.lines[0].planned_work_id != estimate.lines[1].planned_work_id

    async def test_regen_does_not_collapse_duplicate_surface_lines(self, db_session):
        """Regeneration preserves duplicate rows; does not merge them."""
        user = await _make_user(db_session, 4000091)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="10.00")
        await _make_work_plan(
            db_session, project.id, room.id, surface.id, user.id, [item, item]
        )
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        assert len(estimate.lines) == 2

        result = await svc.regenerate_draft(estimate.id, user.id)
        assert len(result.lines) == 2

    async def test_duplicate_reveal_items_create_two_lines(self, db_session):
        """Same reveal PriceItem twice on same opening → two independent lines."""
        user = await _make_user(db_session, 4000092)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id, reveal_depth="0.250")
        item = await _make_reveal_item(db_session, user.id, unit=PriceUnit.LM)
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [item.id, item.id])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        assert len(estimate.lines) == 2

    async def test_regen_does_not_collapse_duplicate_reveal_lines(self, db_session):
        """Regeneration preserves two-coat reveal rows."""
        user = await _make_user(db_session, 4000093)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id, reveal_depth="0.250")
        item = await _make_reveal_item(db_session, user.id, unit=PriceUnit.LM)
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [item.id, item.id])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        result = await svc.regenerate_draft(estimate.id, user.id)
        assert len(result.lines) == 2

    async def test_line_positions_deterministic(self, db_session):
        """After regeneration, positions are 0..N-1 with no gaps."""
        user = await _make_user(db_session, 4000094)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item_a = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="5.00")
        item_b = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="8.00")
        await _make_work_plan(
            db_session, project.id, room.id, surface.id, user.id, [item_a, item_b]
        )
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        result = await svc.regenerate_draft(estimate.id, user.id)
        positions = sorted(l.position for l in result.lines)
        assert positions == list(range(len(result.lines)))


# ===========================================================================
# F11 — Regeneration: disable reveal removes reveal lines
# ===========================================================================


class TestF11_RegenerationRevealDisable:
    async def test_disable_reveal_removes_lines_on_regen(self, db_session):
        """Disabling reveal_enabled then regenerating removes all reveal lines for that opening."""
        user = await _make_user(db_session, 4000100)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id, reveal_depth="0.250")
        item = await _make_reveal_item(db_session, user.id, unit=PriceUnit.LM)
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [item.id])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        assert len(estimate.lines) == 1

        opening.reveal_enabled = False
        await db_session.commit()

        result = await svc.regenerate_draft(estimate.id, user.id)
        assert result.removed == 1
        assert result.added == 0
        reveal_lines = [l for l in result.lines if l.opening_id is not None]
        assert reveal_lines == []

    async def test_preview_disable_reveal_shows_removed(self, db_session):
        """Preview classifies reveal lines as REMOVED after reveal is disabled."""
        user = await _make_user(db_session, 4000101)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id, reveal_depth="0.250")
        item = await _make_reveal_item(db_session, user.id, unit=PriceUnit.LM)
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [item.id])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        opening.reveal_enabled = False
        await db_session.commit()

        result = await svc.preview_regeneration(project.id, estimate.id, user.id)
        assert result.removed == 1
        assert len(result.changes) == 1
        assert result.changes[0].change_type == "REMOVED"

    async def test_regen_add_reveal_then_remove_reveal(self, db_session):
        """Full cycle: generate→add reveal work→regen ADDED→remove reveal→regen REMOVED."""
        user = await _make_user(db_session, 4000102)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="10.00")
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        assert len(estimate.lines) == 1

        # Add reveal on a new opening
        opening = await _make_opening(db_session, surface.id, reveal_depth="0.250")
        reveal_item = await _make_reveal_item(db_session, user.id, unit=PriceUnit.LM)
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [reveal_item.id])

        result = await svc.regenerate_draft(estimate.id, user.id)
        assert result.added >= 1
        reveal_in_lines = [l for l in result.lines if l.opening_id == opening.id]
        assert len(reveal_in_lines) == 1

        # Remove reveal
        opening.reveal_enabled = False
        await db_session.commit()
        result2 = await svc.regenerate_draft(estimate.id, user.id)
        assert result2.removed >= 1
        reveal_after = [l for l in result2.lines if l.opening_id == opening.id]
        assert reveal_after == []


# ===========================================================================
# F12 — Archived PriceItem behavior
# ===========================================================================


class TestF12_ArchivedPriceItemBehavior:
    async def test_archived_item_in_surface_plan_generates_line(self, db_session):
        """An archived item that was in the plan before archiving still generates a line."""
        user = await _make_user(db_session, 4000110)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="10.00")
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])

        # Archive item AFTER adding to plan
        item.is_archived = True
        await db_session.commit()

        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        assert len(estimate.lines) == 1
        line = estimate.lines[0]
        assert line.unit_price == Decimal("10.00")
        assert line.price_item_id == item.id

    async def test_reset_price_override_archived_item_restores_archived_price(
        self, db_session
    ):
        """reset_price_override on a line whose PriceItem is archived restores archived price."""
        user = await _make_user(db_session, 4000111)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="10.00")
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]

        # Owner overrides price
        line.unit_price = Decimal("99.00")
        line.price_override = True
        await db_session.commit()

        # Item archived (price stays 10.00 in catalog)
        item.is_archived = True
        await db_session.commit()

        # reset_price_override → restores 10.00 from archived item
        updated = await svc.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields=set(),
            reset_price_override=True,
        )
        assert updated.unit_price == Decimal("10.00")
        assert updated.price_override is False

    async def test_regen_with_archived_item_in_plan_preserves_snapshot(
        self, db_session
    ):
        """Regeneration with an archived item in the plan updates the snapshot correctly."""
        user = await _make_user(db_session, 4000112)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="10.00")
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        item.is_archived = True
        await db_session.commit()

        # Change geometry so regen UPDATES the source_quantity
        surface.width = Decimal("6.000")  # was 4.000
        await db_session.commit()

        result = await svc.regenerate_draft(estimate.id, user.id)
        assert len(result.lines) == 1
        # source_quantity updated despite archived item
        assert result.lines[0].source_quantity == Decimal("15.000")  # 6×2.5


# ===========================================================================
# F13 — Transaction atomicity
# ===========================================================================


class TestF13_TransactionAtomicity:
    async def test_invalid_manual_currency_no_partial_commit(self, db_session):
        """Failed currency check: no EstimateLine row is committed."""
        user = await _make_user(db_session, 4000120)
        project = await _make_project(db_session, user.id)
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        before_count = len(
            (
                await db_session.execute(
                    select(EstimateLine).where(EstimateLine.estimate_id == estimate.id)
                )
            ).scalars().all()
        )
        with pytest.raises(EstimateValidationError):
            await svc.add_manual_line(
                estimate.id, user.id,
                description="Bad",
                scope=PriceScope.LABOR,
                unit=PriceUnit.FLAT,
                quantity=Decimal("1.000"),
                unit_price=Decimal("10.00"),
                currency="EUR",
                project_id=project.id,
            )

        after_count = len(
            (
                await db_session.execute(
                    select(EstimateLine).where(EstimateLine.estimate_id == estimate.id)
                )
            ).scalars().all()
        )
        assert after_count == before_count

    async def test_finalize_null_price_status_unchanged(self, db_session):
        """Failed finalize (NULL price): estimate remains DRAFT."""
        user = await _make_user(db_session, 4000121)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price=None)
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        with pytest.raises(EstimateValidationError):
            await svc.finalize(estimate.id, user.id, project_id=project.id)

        refreshed = (
            await db_session.execute(
                select(Estimate).where(Estimate.id == estimate.id)
            )
        ).scalar_one()
        assert refreshed.status == EstimateStatus.DRAFT

    async def test_reveal_put_partial_invalid_item_atomically_rejected(
        self, db_session
    ):
        """reveal PUT with one valid and one invalid item: entire list unchanged."""
        user = await _make_user(db_session, 4000122)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id, reveal_depth="0.250")
        item_ok = await _make_reveal_item(db_session, user.id)
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [item_ok.id])

        bad_id = uuid.uuid4()
        from app.domain.exceptions import PriceItemNotFoundError
        with pytest.raises(PriceItemNotFoundError):
            await reveal_svc.set_works(opening.id, user.id, [item_ok.id, bad_id])

        # List is unchanged (still just item_ok)
        works = await reveal_svc.get_works(opening.id, user.id)
        assert len(works) == 1
        assert works[0].price_item_id == item_ok.id

    async def test_state_guard_no_partial_write_on_add_line(self, db_session):
        """Adding line to FINAL estimate: no line written, status unchanged."""
        user = await _make_user(db_session, 4000123)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="10.00")
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        await svc.finalize(estimate.id, user.id, project_id=project.id)

        line_count_before = len(
            (
                await db_session.execute(
                    select(EstimateLine).where(EstimateLine.estimate_id == estimate.id)
                )
            ).scalars().all()
        )
        with pytest.raises(EstimateStateError):
            await svc.add_manual_line(
                estimate.id, user.id,
                description="X",
                scope=PriceScope.LABOR,
                unit=PriceUnit.FLAT,
                quantity=Decimal("1.000"),
                unit_price=Decimal("10.00"),
                project_id=project.id,
            )
        line_count_after = len(
            (
                await db_session.execute(
                    select(EstimateLine).where(EstimateLine.estimate_id == estimate.id)
                )
            ).scalars().all()
        )
        assert line_count_after == line_count_before


# ===========================================================================
# F14 — Concurrency / version uniqueness
# ===========================================================================


class TestF14_ConcurrencyVersionUniqueness:
    """Concurrency correction tests (Stage 10F owner decision: Option A).

    generate_estimate now acquires SELECT ... FOR UPDATE on the Project row
    before checking for existing DRAFTs or computing the next version.  The
    lock serialises concurrent generation for the SAME project; different
    projects use independent row locks.

    The test backend uses SQLite (aiosqlite) which accepts .with_for_update()
    in the compiled SQL but does not enforce real row-level locking at the
    database level.  Real PostgreSQL concurrency proof would require a live
    PostgreSQL session pair and is outside the in-memory test environment.

    Verification strategy used here:
      1. Structural: inspect source code to confirm _lock_project is called
         from generate_estimate and that _lock_project uses with_for_update().
      2. Structural: _lock_project raises ProjectNotFoundError for unknown project.
      3. Structural: _lock_project returns the Project row for a known project.
      4. Behavioral: sequential second-generation (same project) still returns
         EstimateDraftExistsError — the guard runs inside the locked region.
      5. DB constraint: uq_estimates_project_version remains the final DB-level net.
    """

    def test_generate_estimate_calls_lock_project(self):
        """Structural: generate_estimate must call _lock_project, not _assert_project_owned."""
        import inspect
        source = inspect.getsource(EstimateService.generate_estimate)
        assert "_lock_project" in source, (
            "generate_estimate must call _lock_project for concurrency safety"
        )
        assert "_assert_project_owned" not in source, (
            "generate_estimate must not bypass locking via _assert_project_owned"
        )

    def test_lock_project_uses_with_for_update(self):
        """Structural: _lock_project must use .with_for_update() on the SELECT."""
        import inspect
        source = inspect.getsource(EstimateService._lock_project)
        assert "with_for_update" in source, (
            "_lock_project must call .with_for_update() to acquire the row lock"
        )

    async def test_lock_project_raises_for_unknown_project(self, db_session):
        """_lock_project raises ProjectNotFoundError when project is absent."""
        from app.domain.exceptions import ProjectNotFoundError
        user = await _make_user(db_session, 4000141)
        service = EstimateService(db_session)
        with pytest.raises(ProjectNotFoundError):
            await service._lock_project(uuid.uuid4(), user.id)

    async def test_lock_project_returns_project_row(self, db_session):
        """_lock_project returns the matching Project row (executes without error)."""
        user = await _make_user(db_session, 4000142)
        project = await _make_project(db_session, user.id)
        service = EstimateService(db_session)
        locked = await service._lock_project(project.id, user.id)
        assert locked.id == project.id

    async def test_duplicate_draft_detected_inside_locked_region(self, db_session):
        """Behavioral: second generate call raises EstimateDraftExistsError.

        In real PostgreSQL this guard runs while holding the row lock, ensuring
        that a concurrent request waiting on the lock will see the DRAFT created
        by the first request and raise 409 instead of creating a second DRAFT.
        """
        user = await _make_user(db_session, 4000143)
        project = await _make_project(db_session, user.id)
        service = EstimateService(db_session)

        await service.generate_estimate(project.id, user.id)
        with pytest.raises(EstimateDraftExistsError):
            await service.generate_estimate(project.id, user.id)

        stmt = select(Estimate).where(Estimate.project_id == project.id)
        drafts = (await db_session.execute(stmt)).scalars().all()
        assert len(drafts) == 1

    def test_unique_constraint_project_version_exists(self):
        """DB-level constraint prevents duplicate (project_id, version) pairs."""
        constraint_names = {c.name for c in Estimate.__table__.constraints}
        assert "uq_estimates_project_version" in constraint_names

    def test_different_project_locks_are_independent(self):
        """Structural: _lock_project filters by Project.id — different projects
        use different row locks and do not block each other."""
        import inspect
        source = inspect.getsource(EstimateService._lock_project)
        assert "Project.id == project_id" in source or "Project.id ==" in source


# ===========================================================================
# F15 — Decimal / rounding
# ===========================================================================


class TestF15_DecimalRounding:
    async def test_amount_1_290_times_30_10_rounds_half_up(self, db_session):
        """1.290 × 30.10 = 38.829 → ROUND_HALF_UP → 38.83."""
        user = await _make_user(db_session, 4000130)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        # Surface with exact net area 1.290 m²: e.g. 1.290 × 1.000
        surface = await _make_surface(db_session, room.id, width="1.290", height="1.000")
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="30.10"
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        assert line.quantity == Decimal("1.290")
        assert line.unit_price == Decimal("30.10")
        assert line.amount == Decimal("38.83")

    async def test_amount_4_300_times_12_35_rounds_half_up(self, db_session):
        """4.300 × 12.35 = 53.105 → ROUND_HALF_UP → 53.11."""
        user = await _make_user(db_session, 4000131)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id, width="4.300", height="1.000")
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="12.35"
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        assert line.quantity == Decimal("4.300")
        assert line.amount == Decimal("53.11")

    async def test_amount_zero_quantity_times_price(self, db_session):
        """0.000 × any price = 0.00 (not NULL)."""
        user = await _make_user(db_session, 4000132)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        # PCS item → source_quantity=None, quantity defaults to 0.000
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.PCS, price="15.00"
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        assert line.quantity == Decimal("0.000")
        assert line.amount == Decimal("0.00")

    async def test_amount_null_price_is_null(self, db_session):
        """quantity × NULL price = NULL (not zero)."""
        user = await _make_user(db_session, 4000133)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price=None
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        assert line.unit_price is None
        assert line.amount is None

    async def test_total_null_excluded_priced_included(self, db_session):
        """Total = sum of non-NULL amounts; NULL lines excluded; zero included."""
        user = await _make_user(db_session, 4000134)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id, width="2.000", height="1.000")
        # item_a: price=10.00, M2 → qty=2.000, amount=20.00
        item_a = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="10.00"
        )
        # item_b: price=NULL → amount=NULL
        item_b = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price=None
        )
        # item_c: PCS, price=0.00 → qty=0.000, amount=0.00
        item_c = await _make_price_item(
            db_session, user.id, unit=PriceUnit.PCS, price="0.00"
        )
        await _make_work_plan(
            db_session, project.id, room.id, surface.id, user.id,
            [item_a, item_b, item_c]
        )
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        lines_by_item = {l.price_item_id: l for l in estimate.lines}
        assert lines_by_item[item_a.id].amount == Decimal("20.00")
        assert lines_by_item[item_b.id].amount is None
        assert lines_by_item[item_c.id].amount == Decimal("0.00")
        # total = 20.00 + 0.00 = 20.00 (NULL excluded)
        assert estimate.total == Decimal("20.00")

    async def test_rounding_multi_line_total(self, db_session):
        """Each line amount is independently rounded; total = sum of rounded amounts."""
        user = await _make_user(db_session, 4000135)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        # Line 1: 1.290 × 30.10 = 38.829 → 38.83
        surface1 = await _make_surface(
            db_session, room.id, width="1.290", height="1.000", position=0
        )
        item1 = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="30.10"
        )
        await _make_work_plan(
            db_session, project.id, room.id, surface1.id, user.id, [item1]
        )
        # Line 2: 4.300 × 12.35 = 53.105 → 53.11
        surface2 = await _make_surface(
            db_session, room.id, width="4.300", height="1.000", position=1
        )
        item2 = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="12.35"
        )
        await _make_work_plan(
            db_session, project.id, room.id, surface2.id, user.id, [item2]
        )
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        amounts = {l.price_item_id: l.amount for l in estimate.lines}
        assert amounts[item1.id] == Decimal("38.83")
        assert amounts[item2.id] == Decimal("53.11")
        assert estimate.total == Decimal("91.94")

    async def test_no_float_in_decimal_computation(self, db_session):
        """amount is computed as Decimal, not float."""
        user = await _make_user(db_session, 4000136)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id, width="3.333", height="1.000")
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="10.00"
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        # Verify types — Decimal not float
        assert isinstance(line.quantity, Decimal)
        assert isinstance(line.unit_price, Decimal)
        assert isinstance(line.amount, Decimal)
        assert isinstance(estimate.total, Decimal)


# ===========================================================================
# F16 — Ownership isolation (HTTP)
# ===========================================================================


class TestF16_OwnershipIsolation:
    async def _setup(self, db_session, async_client):
        """Create owner + other, get tokens, create owned project + estimate."""
        tok_owner = await get_token(async_client, VALID_USER)
        tok_other = await get_token(async_client, OTHER_USER)

        user = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()

        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, unit=PriceUnit.M2, price="10.00")
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        return tok_owner, tok_other, project, estimate

    async def test_other_user_cannot_list_estimates(
        self, async_client: AsyncClient, db_session
    ):
        _, tok_other, project, _ = await self._setup(db_session, async_client)
        resp = await async_client.get(
            f"/api/projects/{project.id}/estimates",
            headers=auth(tok_other),
        )
        assert resp.status_code == 404

    async def test_other_user_cannot_get_estimate_detail(
        self, async_client: AsyncClient, db_session
    ):
        _, tok_other, project, estimate = await self._setup(db_session, async_client)
        resp = await async_client.get(
            f"/api/projects/{project.id}/estimates/{estimate.id}",
            headers=auth(tok_other),
        )
        assert resp.status_code == 404

    async def test_other_user_cannot_generate_estimate(
        self, async_client: AsyncClient, db_session
    ):
        _, tok_other, project, _ = await self._setup(db_session, async_client)
        resp = await async_client.post(
            f"/api/projects/{project.id}/estimates/generate",
            headers=auth(tok_other),
        )
        assert resp.status_code == 404

    async def test_other_user_cannot_regen_preview(
        self, async_client: AsyncClient, db_session
    ):
        _, tok_other, project, estimate = await self._setup(db_session, async_client)
        resp = await async_client.post(
            f"/api/projects/{project.id}/estimates/{estimate.id}/regenerate-preview",
            headers=auth(tok_other),
        )
        assert resp.status_code == 404

    async def test_other_user_cannot_regen_confirm(
        self, async_client: AsyncClient, db_session
    ):
        _, tok_other, project, estimate = await self._setup(db_session, async_client)
        resp = await async_client.post(
            f"/api/projects/{project.id}/estimates/{estimate.id}/regenerate",
            headers=auth(tok_other),
        )
        assert resp.status_code == 404

    async def test_other_user_cannot_add_manual_line(
        self, async_client: AsyncClient, db_session
    ):
        _, tok_other, project, estimate = await self._setup(db_session, async_client)
        resp = await async_client.post(
            f"/api/projects/{project.id}/estimates/{estimate.id}/lines",
            headers=auth(tok_other),
            json={
                "description": "X", "scope": "LABOR", "unit": "FLAT",
                "quantity": "1.000", "unit_price": "10.00",
            },
        )
        assert resp.status_code == 404

    async def test_other_user_cannot_patch_line(
        self, async_client: AsyncClient, db_session
    ):
        tok_owner, tok_other, project, estimate = await self._setup(db_session, async_client)
        line_id = estimate.lines[0].id
        resp = await async_client.patch(
            f"/api/projects/{project.id}/estimates/{estimate.id}/lines/{line_id}",
            headers=auth(tok_other),
            json={"quantity": "5.000"},
        )
        assert resp.status_code == 404

    async def test_other_user_cannot_finalize(
        self, async_client: AsyncClient, db_session
    ):
        _, tok_other, project, estimate = await self._setup(db_session, async_client)
        resp = await async_client.post(
            f"/api/projects/{project.id}/estimates/{estimate.id}/finalize",
            headers=auth(tok_other),
        )
        assert resp.status_code == 404


# ===========================================================================
# F17 — HTTP contract stability for Stage 10G
# ===========================================================================


class TestF17_HttpContractStability:
    async def test_estimate_summary_all_required_fields(
        self, async_client: AsyncClient, db_session
    ):
        """EstimateSummaryRead must have id, project_id, version, status, name,
        total, currency, created_at, updated_at."""
        tok = await get_token(async_client, VALID_USER)
        user = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, user.id)
        svc = EstimateService(db_session)
        await svc.generate_estimate(project.id, user.id)

        resp = await async_client.get(
            f"/api/projects/{project.id}/estimates", headers=auth(tok)
        )
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        for field in ("id", "project_id", "version", "status", "currency",
                      "created_at", "updated_at"):
            assert field in item, f"Missing field: {field}"
        assert "total" in item  # may be null
        assert "name" in item   # may be null

    async def test_estimate_detail_all_required_fields(
        self, async_client: AsyncClient, db_session
    ):
        """EstimateRead must have id, version, status, name, total, currency, lines,
        created_at, updated_at."""
        tok = await get_token(async_client, VALID_USER)
        user = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="10.00"
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        resp = await async_client.get(
            f"/api/projects/{project.id}/estimates/{estimate.id}",
            headers=auth(tok),
        )
        assert resp.status_code == 200
        data = resp.json()
        for field in ("id", "project_id", "version", "status", "currency",
                      "lines", "created_at", "updated_at"):
            assert field in data, f"Missing field: {field}"

    async def test_estimate_line_all_provenance_fields(
        self, async_client: AsyncClient, db_session
    ):
        """EstimateLineRead must include all provenance + override fields."""
        tok = await get_token(async_client, VALID_USER)
        user = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(
            db_session, user.id, unit=PriceUnit.M2, price="10.00"
        )
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [item])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        resp = await async_client.get(
            f"/api/projects/{project.id}/estimates/{estimate.id}",
            headers=auth(tok),
        )
        line = resp.json()["lines"][0]
        required = (
            "id", "estimate_id", "origin", "position",
            "description", "item_code", "unit", "scope", "currency",
            "source_quantity", "quantity", "quantity_source",
            "quantity_overridden", "unit_price", "price_override", "amount",
            "price_item_id", "plan_id", "planned_work_id",
            "surface_id", "room_id", "opening_id",
        )
        for field in required:
            assert field in line, f"Missing EstimateLineRead field: {field}"

    async def test_preview_response_has_changes_field(
        self, async_client: AsyncClient, db_session
    ):
        """RegenerationPreviewResponse must include 'changes' list (C6)."""
        tok = await get_token(async_client, VALID_USER)
        user = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, user.id)
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)

        resp = await async_client.post(
            f"/api/projects/{project.id}/estimates/{estimate.id}/regenerate-preview",
            headers=auth(tok),
        )
        assert resp.status_code == 200
        data = resp.json()
        for field in ("added", "removed", "updated", "preserved_manual", "changes"):
            assert field in data, f"Missing preview field: {field}"

    async def test_reveal_work_item_has_price_item_display_info(
        self, async_client: AsyncClient, db_session
    ):
        """RevealWorkItemRead must expose price_item display information for Stage 10G."""
        tok = await get_token(async_client, VALID_USER)
        user = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id, reveal_depth="0.250")
        item = await _make_reveal_item(db_session, user.id)
        reveal_svc = OpeningRevealWorkService(db_session)
        await reveal_svc.set_works(opening.id, user.id, [item.id])

        resp = await async_client.get(
            f"/api/projects/{project.id}/rooms/{room.id}"
            f"/surfaces/{surface.id}/openings/{opening.id}/reveal-works",
            headers=auth(tok),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "opening_id" in data
        assert len(data["items"]) == 1
        item_data = data["items"][0]
        assert "id" in item_data
        assert "position" in item_data
        assert "price_item_id" in item_data
        assert "price_item" in item_data
