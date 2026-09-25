"""Stage 13D — five new default PriceItems and the sixteen program-default
technological workflows (insert-only, idempotent, owner-scoped bootstrap).

The expected recipes below are an independent literal copy of the binding
owner specification, so any drift in `app/domain/data/workflow_templates.py`
fails here.
"""
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import func, select

from app.domain.data.price_book_seed import build_approved_price_book_items
from app.domain.services.price_book_service import PriceBookService
from app.domain.services.workflow_template_service import (
    WorkflowTemplateService,
    WorkflowTemplateStepSpec,
)
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit
from app.models.user import User
from app.models.workflow_template import WorkflowTemplate, WorkflowTemplateStep
from tests.test_planned_work_coefficient_assignments import (
    VALID_USER,
    auth_header,
    get_token,
)

NEW_ITEMS = {
    "CENNIK_SKIM_ADD-01": (PriceCategory.SKIM_COAT, PriceUnit.M2, "pricebook.seed.skim_add"),
    "CENNIK_GK_JOINT_Q1-01": (PriceCategory.DRYWALL, PriceUnit.LM, "pricebook.seed.gk_joint_q1"),
    "CENNIK_GK_JOINT_Q2-01": (PriceCategory.DRYWALL, PriceUnit.LM, "pricebook.seed.gk_joint_q2"),
    "CENNIK_PREP_CONC-01": (PriceCategory.PREPARATION, PriceUnit.M2, "pricebook.seed.prep_conc"),
    "CENNIK_SKIM_LEVEL-01": (PriceCategory.SKIM_COAT, PriceUnit.M2, "pricebook.seed.skim_level"),
}

R, O = "R", "O"
_BETON_PREP = [(O, "PREP_PROT"), (O, "PREP_CONC"), (R, "PREP_CLEAN"), (O, "PRIM_ADH"),
               (O, "PRIM_STD"), (O, "SKIM_CRACK"), (O, "SKIM_LOCAL")]
_GIPS_PREP = [(O, "PREP_PROT"), (R, "PREP_CLEAN"), (O, "PRIM_STD"), (O, "SKIM_CRACK"), (O, "SKIM_LOCAL")]
_CW_PREP = [(O, "PREP_PROT"), (R, "PREP_CLEAN"), (O, "PRIM_STD"), (O, "PRIM_HIGH"),
            (O, "SKIM_CRACK"), (O, "SKIM_LOCAL")]
_S2_TAIL = [(O, "SKIM_CORNER"), (R, "SKIM_2L"), (R, "SKIM_SAND")]
_S3_TAIL = [(O, "SKIM_CORNER"), (R, "SKIM_2L"), (O, "SKIM_ADD"), (R, "SKIM_SAND")]
_GK_Q1 = [(O, "PREP_PROT"), (R, "GK_JOINT_Q1"), (O, "GK_CORNER")]
_GK_Q2 = _GK_Q1 + [(R, "GK_JOINT_Q2")]

EXPECTED = {
    "TECH_BETON_S1-01": ("CONCRETE", "S1", _BETON_PREP),
    "TECH_BETON_S2-01": ("CONCRETE", "S2", _BETON_PREP + _S2_TAIL),
    "TECH_BETON_S3-01": ("CONCRETE", "S3", _BETON_PREP + _S3_TAIL),
    "TECH_BETON_S4-01": ("CONCRETE", "S4", _BETON_PREP + _S3_TAIL),
    "TECH_TYNK_GIPSOWY_S1-01": ("GYPSUM_PLASTER", "S1", _GIPS_PREP),
    "TECH_TYNK_GIPSOWY_S2-01": ("GYPSUM_PLASTER", "S2", _GIPS_PREP + _S2_TAIL),
    "TECH_TYNK_GIPSOWY_S3-01": ("GYPSUM_PLASTER", "S3", _GIPS_PREP + _S3_TAIL),
    "TECH_TYNK_GIPSOWY_S4-01": ("GYPSUM_PLASTER", "S4", _GIPS_PREP + _S3_TAIL),
    "TECH_TYNK_CW_S1-01": ("CEMENT_LIME_PLASTER", "S1", _CW_PREP),
    "TECH_TYNK_CW_S2-01": ("CEMENT_LIME_PLASTER", "S2", _CW_PREP + _S2_TAIL),
    "TECH_TYNK_CW_S3-01": ("CEMENT_LIME_PLASTER", "S3", _CW_PREP + _S3_TAIL),
    "TECH_TYNK_CW_S4-01": ("CEMENT_LIME_PLASTER", "S4", _CW_PREP + _S3_TAIL),
    "TECH_GK_Q1-01": ("GYPSUM_BOARD", "Q1", _GK_Q1),
    "TECH_GK_Q2-01": ("GYPSUM_BOARD", "Q2", _GK_Q2),
    "TECH_GK_Q3-01": ("GYPSUM_BOARD", "Q3", _GK_Q2 + [(O, "PRIM_STD"), (R, "GK_FULL"), (R, "SKIM_SAND")]),
    "TECH_GK_Q4-01": ("GYPSUM_BOARD", "Q4", _GK_Q2 + [(O, "PRIM_STD"), (R, "GK_Q4"), (R, "SKIM_SAND")]),
}

FORBIDDEN = {
    "CENNIK_GK_JOINT-01", "CENNIK_GK_SCREW-01", "CENNIK_SKIM_SQ-01", "CENNIK_SKIM_LEVEL-01",
    "CENNIK_GF_FLIZ_L-01", "CENNIK_GF_FLIZ_M-01", "CENNIK_GF_MESH-01",
    "CENNIK_PRIM_PAINT-01", "CENNIK_PAINT_MASK-01", "CENNIK_REV_WORK_LM-01",
}


def _short(code: str) -> str:
    return code.removeprefix("CENNIK_").removesuffix("-01")


async def _user(db, telegram_id: int) -> User:
    user = User(telegram_user_id=telegram_id, username=f"user{telegram_id}")
    db.add(user)
    await db.commit()
    return user


async def _items(db, owner_id) -> dict[str, PriceItem]:
    rows = (await db.execute(select(PriceItem).where(PriceItem.owner_id == owner_id))).scalars().all()
    return {row.code: row for row in rows}


async def _templates(db, owner_id) -> dict[str, WorkflowTemplate]:
    service = WorkflowTemplateService(db)
    return {t.code: t for t in await service.list_owner_templates(owner_id, archived="all")}


async def _count(db, model, owner_id=None) -> int:
    stmt = select(func.count()).select_from(model)
    if owner_id is not None:
        stmt = stmt.where(model.owner_id == owner_id)
    return (await db.execute(stmt)).scalar_one()


# ---------------------------------------------------------------------------
# Price Book (1-8)
# ---------------------------------------------------------------------------


class TestPriceBookDefaults:
    async def test_fresh_owner_gets_49_with_five_new_null_price_rows(self, db_session):
        user = await _user(db_session, 1304001)
        await PriceBookService(db_session).ensure_owner_catalog(user.id)
        items = await _items(db_session, user.id)
        assert len(items) == 49
        codes = [s.code for s in build_approved_price_book_items()]
        for code, (category, unit, name_key) in NEW_ITEMS.items():
            assert codes.count(code) == 1
            item = items[code]
            assert (item.category, item.unit, item.price_scope, item.name_key) == (
                category, unit, PriceScope.LABOR, name_key,
            )
            assert item.price is None and item.display_name is None
            assert item.quality_level is None and item.is_archived is False

    async def test_legacy_gk_joint_unchanged(self, db_session):
        user = await _user(db_session, 1304002)
        await PriceBookService(db_session).ensure_owner_catalog(user.id)
        legacy = (await _items(db_session, user.id))["CENNIK_GK_JOINT-01"]
        assert (legacy.category, legacy.unit, legacy.price_scope, legacy.name_key, legacy.quality_level, legacy.is_archived) == (
            PriceCategory.DRYWALL, PriceUnit.LM, PriceScope.LABOR, "pricebook.seed.gk_joint", None, False,
        )

    async def test_existing_44_owner_gains_exactly_five_and_nothing_else_changes(self, db_session, monkeypatch):
        user = await _user(db_session, 1304003)
        uid = user.id  # objects expire on expire_all()
        old_catalog = [s for s in build_approved_price_book_items() if s.code not in NEW_ITEMS]
        assert len(old_catalog) == 44
        monkeypatch.setattr(
            "app.domain.services.price_book_service.build_approved_price_book_items", lambda: old_catalog
        )
        service = PriceBookService(db_session)
        await service.ensure_owner_catalog(uid)
        items = await _items(db_session, uid)
        items["CENNIK_GK_JOINT-01"].price = Decimal("21.00")
        items["CENNIK_GK_JOINT-01"].display_name = "Moje spoiny"
        items["CENNIK_PREP_PROT-01"].is_archived = True
        await db_session.commit()
        before = {c: (i.id, i.price, i.display_name, i.is_archived, i.name_key) for c, i in items.items()}

        monkeypatch.undo()
        created = await service.ensure_owner_catalog(uid)
        assert sorted(i.code for i in created) == sorted(NEW_ITEMS)
        db_session.expire_all()
        after = await _items(db_session, uid)
        assert len(after) == 49
        assert {c: (i.id, i.price, i.display_name, i.is_archived, i.name_key) for c, i in after.items() if c in before} == before

    async def test_repeated_bootstrap_does_not_duplicate_or_overwrite(self, db_session):
        user = await _user(db_session, 1304004)
        uid = user.id  # objects expire on expire_all()
        service = PriceBookService(db_session)
        await service.ensure_owner_catalog(uid)
        items = await _items(db_session, uid)
        items["CENNIK_SKIM_ADD-01"].price = Decimal("12.50")
        items["CENNIK_SKIM_LEVEL-01"].is_archived = True
        await db_session.commit()
        assert await service.ensure_owner_catalog(uid) == []
        assert await service.ensure_owner_catalog(uid) == []
        db_session.expire_all()
        items = await _items(db_session, uid)
        assert len(items) == 49
        assert items["CENNIK_SKIM_ADD-01"].price == Decimal("12.50")
        assert items["CENNIK_SKIM_LEVEL-01"].is_archived is True


# ---------------------------------------------------------------------------
# Workflow defaults (9-32)
# ---------------------------------------------------------------------------


class TestWorkflowDefaults:
    async def _fresh(self, db, telegram_id):
        user = await _user(db, telegram_id)
        created = await WorkflowTemplateService(db).ensure_owner_catalog(user.id)
        return user, created

    async def test_fresh_owner_gets_exactly_the_16_recipes(self, db_session):
        user, created = await self._fresh(db_session, 1304101)
        assert len(created) == 16
        templates = await _templates(db_session, user.id)
        assert sorted(templates) == sorted(EXPECTED)
        assert await _count(db_session, WorkflowTemplate, user.id) == 16
        assert len(await _items(db_session, user.id)) == 49  # Price Book bootstrapped first

    async def test_recipe_content_matches_owner_specification(self, db_session):
        user, _ = await self._fresh(db_session, 1304102)
        templates = await _templates(db_session, user.id)
        items = await _items(db_session, user.id)
        own_ids = {i.id for i in items.values()}
        for code, (substrate, quality, steps) in EXPECTED.items():
            t = templates[code]
            assert t.applies_to_substrates == [substrate], code
            assert t.applies_to_quality == [quality], code
            assert t.applies_to_surface_types == ["WALL", "CEILING", "OTHER"], code
            assert t.name_key == f"workflow_templates.seed.{code[:-3].lower()}"
            assert t.display_name is None and t.is_archived is False
            actual = [(O if s.is_optional else R, _short(s.price_item.code)) for s in t.steps]
            assert actual == steps, code
            assert [s.position for s in t.steps] == list(range(len(steps)))
            assert all(s.wait_after_hours is None for s in t.steps), code
            assert all(s.price_item_id in own_ids for s in t.steps), code

    async def test_forbidden_items_never_used(self, db_session):
        user, _ = await self._fresh(db_session, 1304103)
        for code, t in (await _templates(db_session, user.id)).items():
            used = {s.price_item.code for s in t.steps}
            assert not used & FORBIDDEN, code
            assert not any(s.price_item.category in (PriceCategory.PAINTING, PriceCategory.REVEAL, PriceCategory.GLASS_FIBER) for s in t.steps), code

    async def test_skim_add_only_optional_and_only_in_s3_s4(self, db_session):
        user, _ = await self._fresh(db_session, 1304104)
        for code, t in (await _templates(db_session, user.id)).items():
            adds = [s for s in t.steps if s.price_item.code == "CENNIK_SKIM_ADD-01"]
            if code.endswith(("S3-01", "S4-01")):
                assert len(adds) == 1 and adds[0].is_optional, code
            else:
                assert adds == [], code

    async def test_gk_structure(self, db_session):
        user, _ = await self._fresh(db_session, 1304105)
        t = await _templates(db_session, user.id)
        codes = {c: [s.price_item.code for s in t[c].steps] for c in t if c.startswith("TECH_GK_")}
        assert "CENNIK_GK_JOINT_Q1-01" in codes["TECH_GK_Q1-01"]
        assert "CENNIK_GK_JOINT_Q2-01" not in codes["TECH_GK_Q1-01"]
        assert codes["TECH_GK_Q2-01"] == codes["TECH_GK_Q1-01"] + ["CENNIK_GK_JOINT_Q2-01"]
        assert "CENNIK_GK_FULL-01" in codes["TECH_GK_Q3-01"] and "CENNIK_GK_Q4-01" not in codes["TECH_GK_Q3-01"]
        assert "CENNIK_GK_Q4-01" in codes["TECH_GK_Q4-01"] and "CENNIK_GK_FULL-01" not in codes["TECH_GK_Q4-01"]

    async def test_descriptions_keep_internal_classification_and_no_painting(self, db_session):
        user, _ = await self._fresh(db_session, 1304106)
        for code, t in (await _templates(db_session, user.id)).items():
            assert "Bez malowania" in t.description, code
            if "_GK_" in code:
                assert "Q" in t.description and "Standard Wykończenia Powierzchni" not in t.description
            else:
                assert "Standard Wykończenia Powierzchni" in t.description
                assert "Wewnętrzna klasyfikacja wykonawcy." in t.description
        s1 = (await _templates(db_session, user.id))["TECH_BETON_S1-01"].description
        assert "bez gwarancji szpachlowania całej powierzchni" in s1

    async def test_primer_notes_state_alternatives(self, db_session):
        user, _ = await self._fresh(db_session, 1304107)
        t = await _templates(db_session, user.id)
        for code, primers in (("TECH_BETON_S2-01", ("CENNIK_PRIM_ADH-01", "CENNIK_PRIM_STD-01")),
                              ("TECH_TYNK_CW_S2-01", ("CENNIK_PRIM_STD-01", "CENNIK_PRIM_HIGH-01"))):
            for step in t[code].steps:
                if step.price_item.code in primers:
                    assert step.is_optional and "nie oba" in step.note, (code, step.price_item.code)

    async def test_templates_pass_the_13c_filter(self, db_session):
        user, _ = await self._fresh(db_session, 1304108)
        service = WorkflowTemplateService(db_session)
        from app.models.checklist import QualityLevel, Substrate
        from app.models.surface import SurfaceType

        match = await service.list_owner_templates(
            user.id, substrate=Substrate.CONCRETE, quality_target=QualityLevel.S3, surface_type=SurfaceType.CEILING,
        )
        assert [t.code for t in match] == ["TECH_BETON_S3-01"]
        assert await service.list_owner_templates(user.id, surface_type=SurfaceType.FLOOR) == []


# ---------------------------------------------------------------------------
# Insert-only owner safety (11, 33-36)
# ---------------------------------------------------------------------------


class TestInsertOnly:
    async def test_repeated_bootstrap_creates_nothing(self, db_session):
        user = await _user(db_session, 1304201)
        service = WorkflowTemplateService(db_session)
        await service.ensure_owner_catalog(user.id)
        steps_before = (await db_session.execute(select(func.count()).select_from(WorkflowTemplateStep))).scalar_one()
        assert await service.ensure_owner_catalog(user.id) == []
        assert await service.ensure_owner_catalog(user.id) == []
        assert await _count(db_session, WorkflowTemplate, user.id) == 16
        assert (await db_session.execute(select(func.count()).select_from(WorkflowTemplateStep))).scalar_one() == steps_before

    async def test_owner_edits_and_archive_survive_bootstrap(self, db_session):
        user = await _user(db_session, 1304202)
        uid = user.id  # objects expire on expire_all()
        service = WorkflowTemplateService(db_session)
        await service.ensure_owner_catalog(uid)
        t = await _templates(db_session, uid)
        items = await _items(db_session, uid)
        s2, s3, q1 = t["TECH_BETON_S2-01"], t["TECH_BETON_S3-01"], t["TECH_GK_Q1-01"]
        await service.update_template(uid, s2.id, display_name="Mój beton S2", description="Moja wersja")
        await service.replace_steps(uid, s3.id, [WorkflowTemplateStepSpec(price_item_id=items["CENNIK_SKIM_2L-01"].id, wait_after_hours=24)])
        await service.archive_template(uid, q1.id)

        assert await service.ensure_owner_catalog(uid) == []
        db_session.expire_all()
        t = await _templates(db_session, uid)
        assert (t["TECH_BETON_S2-01"].display_name, t["TECH_BETON_S2-01"].description) == ("Mój beton S2", "Moja wersja")
        assert [(s.price_item.code, s.wait_after_hours) for s in t["TECH_BETON_S3-01"].steps] == [("CENNIK_SKIM_2L-01", 24)]
        assert t["TECH_GK_Q1-01"].is_archived is True
        assert len(t) == 16

    async def test_only_missing_default_is_recreated(self, db_session):
        user = await _user(db_session, 1304203)
        service = WorkflowTemplateService(db_session)
        await service.ensure_owner_catalog(user.id)
        victim = (await _templates(db_session, user.id))["TECH_GK_Q4-01"]
        await db_session.delete(victim)
        await db_session.commit()
        created = await service.ensure_owner_catalog(user.id)
        assert [t.code for t in created] == ["TECH_GK_Q4-01"]
        assert await _count(db_session, WorkflowTemplate, user.id) == 16

    async def test_owner_archived_price_item_is_still_referenced_not_restored(self, db_session):
        user = await _user(db_session, 1304204)
        uid = user.id  # objects expire on expire_all()
        await PriceBookService(db_session).ensure_owner_catalog(uid)
        items = await _items(db_session, uid)
        items["CENNIK_PREP_PROT-01"].is_archived = True
        await db_session.commit()
        await WorkflowTemplateService(db_session).ensure_owner_catalog(uid)
        db_session.expire_all()
        assert (await _items(db_session, uid))["CENNIK_PREP_PROT-01"].is_archived is True
        steps = (await _templates(db_session, uid))["TECH_GK_Q1-01"].steps
        assert steps[0].price_item.code == "CENNIK_PREP_PROT-01" and steps[0].price_item.is_archived

    async def test_second_owner_is_independent(self, db_session):
        a = await _user(db_session, 1304205)
        b = await _user(db_session, 1304206)
        service = WorkflowTemplateService(db_session)
        await service.ensure_owner_catalog(a.id)
        await service.ensure_owner_catalog(b.id)
        a_items = {i.id for i in (await _items(db_session, a.id)).values()}
        b_items = {i.id for i in (await _items(db_session, b.id)).values()}
        ta, tb = await _templates(db_session, a.id), await _templates(db_session, b.id)
        assert sorted(ta) == sorted(tb) == sorted(EXPECTED)
        assert {t.id for t in ta.values()}.isdisjoint({t.id for t in tb.values()})
        assert all(s.price_item_id in a_items for t in ta.values() for s in t.steps)
        assert all(s.price_item_id in b_items for t in tb.values() for s in t.steps)


# ---------------------------------------------------------------------------
# HTTP entry point
# ---------------------------------------------------------------------------


class TestHttpBootstrap:
    async def test_list_bootstraps_defaults_once(self, async_client: AsyncClient, db_session):
        headers = auth_header(await get_token(async_client, VALID_USER))
        first = (await async_client.get("/api/workflow-templates", headers=headers)).json()
        second = (await async_client.get("/api/workflow-templates", headers=headers)).json()
        assert first["total"] == second["total"] == 16
        assert [i["code"] for i in first["items"]] == list(EXPECTED)  # stable display order
        assert first == second
        gk = next(i for i in first["items"] if i["code"] == "TECH_GK_Q2-01")
        assert [s["price_item"]["code"] for s in gk["steps"]] == [
            "CENNIK_PREP_PROT-01", "CENNIK_GK_JOINT_Q1-01", "CENNIK_GK_CORNER-01", "CENNIK_GK_JOINT_Q2-01",
        ]
        assert all(s["wait_after_hours"] is None for i in first["items"] for s in i["steps"])
        filtered = (await async_client.get("/api/workflow-templates", headers=headers, params={
            "substrate": "GYPSUM_BOARD", "quality_target": "Q3", "surface_type": "WALL",
        })).json()
        assert [i["code"] for i in filtered["items"]] == ["TECH_GK_Q3-01"]
