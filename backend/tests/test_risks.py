"""Integration tests for the risk rules engine API (Stage 7B)."""

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk import (
    RiskConditionOperator,
    RiskRule,
    RiskRuleCondition,
    RiskSeverity,
)
from tests.conftest import make_telegram_init_data

VALID_USER = {
    "id": 900555666,
    "username": "risk_contractor",
    "first_name": "Risk",
    "last_name": "Contractor",
    "language_code": "pl",
}
OTHER_USER = {
    "id": 900777888,
    "username": "other_risk_contractor",
    "first_name": "Other",
    "last_name": "Contractor",
    "language_code": "pl",
}

CONCRETE_FULL = {
    "cracks_present": {"value_bool": True},
    "unevenness_mm": {"value_number": "3.500"},
    "substrate_condition": {"option_key": "LOOSE"},
    "present_defects": {"option_keys": ["DELAMINATION", "MOLD"]},
    "moisture_high": {"value_bool": False},
    "adhesion_weak": {"value_bool": False},
}


async def get_token(async_client: AsyncClient, user_dict: dict) -> str:
    response = await async_client.post(
        "/api/auth/telegram",
        json={"init_data": make_telegram_init_data(user_dict)},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_project(async_client: AsyncClient, token: str) -> dict:
    response = await async_client.post(
        "/api/projects",
        json={
            "name": "Projekt Ryzyka",
            "address": "ul. Ryzykowna 1",
            "city": "Kraków",
            "postal_code": "30-001",
        },
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_room(async_client: AsyncClient, token: str, project_id: str) -> dict:
    response = await async_client.post(
        f"/api/projects/{project_id}/rooms",
        json={"name": "Sypialnia"},
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def full_template(
    async_client: AsyncClient,
    token: str,
    substrate: str,
) -> dict:
    response = await async_client.get(
        "/api/checklist-templates",
        params={"substrate": substrate},
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    template_id = items[0]["id"]
    detail = await async_client.get(
        f"/api/checklist-templates/{template_id}",
        headers=auth_header(token),
    )
    assert detail.status_code == 200
    return detail.json()


def question_by_key(template: dict, key: str) -> dict:
    for section in template["sections"]:
        for question in section["questions"]:
            if question["key"] == key:
                return question
    raise AssertionError(f"question key {key} not found in template")


def inspections_url(project_id: str, room_id: str) -> str:
    return f"/api/projects/{project_id}/rooms/{room_id}/inspections"


def inspection_url(project_id: str, room_id: str, inspection_id: str) -> str:
    return f"{inspections_url(project_id, room_id)}/{inspection_id}"


def risks_url(project_id: str, room_id: str) -> str:
    return f"/api/projects/{project_id}/rooms/{room_id}/risks"


async def _scaffold(
    async_client: AsyncClient,
    user_dict: dict | None = None,
) -> tuple[str, dict, dict]:
    token = await get_token(async_client, user_dict or VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    return token, project, room


async def _scaffold_inspection(
    async_client: AsyncClient,
    *,
    substrate: str = "CONCRETE",
    plane: str = "CEILING",
    token: str | None = None,
    project: dict | None = None,
    room: dict | None = None,
) -> tuple[str, dict, dict, dict, dict]:
    if token is None or project is None or room is None:
        token, project, room = await _scaffold(async_client)
    template = await full_template(async_client, token, substrate)
    response = await async_client.post(
        inspections_url(project["id"], room["id"]),
        json={
            "template_id": template["id"],
            "substrate": substrate,
            "plane": plane,
        },
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return token, project, room, response.json(), template


async def _put_answers(
    async_client: AsyncClient,
    token: str,
    project: dict,
    room: dict,
    inspection: dict,
    template: dict,
    answers: dict[str, dict],
) -> None:
    payload = [
        {"question_id": question_by_key(template, key)["id"], **value}
        for key, value in answers.items()
    ]
    response = await async_client.put(
        f"{inspection_url(project['id'], room['id'], inspection['id'])}/answers",
        json={"answers": payload},
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text


async def _complete(
    async_client: AsyncClient,
    token: str,
    project: dict,
    room: dict,
    inspection: dict,
):
    return await async_client.post(
        f"{inspection_url(project['id'], room['id'], inspection['id'])}/complete",
        headers=auth_header(token),
    )


async def _reopen(
    async_client: AsyncClient,
    token: str,
    project: dict,
    room: dict,
    inspection: dict,
):
    return await async_client.post(
        f"{inspection_url(project['id'], room['id'], inspection['id'])}/reopen",
        headers=auth_header(token),
    )


async def _evaluate(
    async_client: AsyncClient,
    token: str,
    project: dict,
    room: dict,
    inspection: dict,
):
    return await async_client.post(
        f"{risks_url(project['id'], room['id'])}/evaluate",
        json={"inspection_id": inspection["id"]},
        headers=auth_header(token),
    )


async def _risk_items(
    async_client: AsyncClient,
    token: str,
    project: dict,
    room: dict,
    **params,
) -> list[dict]:
    response = await async_client.get(
        risks_url(project["id"], room["id"]),
        params=params,
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


class TestRiskEvaluation:
    async def test_evaluate_materializes_expected_risks(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client
        )
        await _put_answers(
            async_client, token, project, room, inspection, template, CONCRETE_FULL
        )
        await _complete(async_client, token, project, room, inspection)

        response = await _evaluate(async_client, token, project, room, inspection)
        assert response.status_code == 200, response.text
        body = response.json()
        codes = {item["risk_code"] for item in body["items"]}
        assert codes == {
            "CRACK_RECURRENCE",
            "UNEVENNESS_PREP_INCREASED",
            "LOOSE_SUBSTRATE_REMOVAL",
            "DELAMINATION_REPAIR",
            "MOLD_TREATMENT_BEFORE_FINISH",
        }
        assert body["total"] == 5
        assert all(item["is_active"] for item in body["items"])
        assert all(len(item["source_findings"]) >= 1 for item in body["items"])

    async def test_unevenness_below_threshold_produces_no_risk(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client
        )
        answers = dict(CONCRETE_FULL)
        answers["unevenness_mm"] = {"value_number": "1.000"}
        await _put_answers(async_client, token, project, room, inspection, template, answers)
        await _complete(async_client, token, project, room, inspection)
        response = await _evaluate(async_client, token, project, room, inspection)
        codes = {item["risk_code"] for item in response.json()["items"]}
        assert "UNEVENNESS_PREP_INCREASED" not in codes

    async def test_critical_moisture_blocks_finishing(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client
        )
        await _put_answers(
            async_client,
            token,
            project,
            room,
            inspection,
            template,
            {"moisture_high": {"value_bool": True}},
        )
        await _complete(async_client, token, project, room, inspection)
        response = await _evaluate(async_client, token, project, room, inspection)
        body = response.json()
        assert body["total"] == 1
        risk = body["items"][0]
        assert risk["risk_code"] == "MOISTURE_BLOCK_FINISHING"
        assert risk["severity"] == "CRITICAL"
        assert risk["blocks_finishing"] is True
        assert risk["warranty_exclusion_candidate"] is True
        assert risk["source_findings"][0]["finding_key_snapshot"] == "HIGH_MOISTURE"

    async def test_drywall_joint_tape_rule_fires_on_gypsum_board(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client, substrate="GYPSUM_BOARD"
        )
        await _put_answers(
            async_client,
            token,
            project,
            room,
            inspection,
            template,
            {"joint_tape_missing": {"value_bool": True}},
        )
        await _complete(async_client, token, project, room, inspection)
        response = await _evaluate(async_client, token, project, room, inspection)
        codes = {item["risk_code"] for item in response.json()["items"]}
        assert codes == {"JOINT_TAPE_MISSING_REWORK"}

    async def test_compound_crack_plus_board_movement_yields_both_risks(
        self, async_client: AsyncClient
    ) -> None:
        # Check C (Stage 7D.2): a GYPSUM_BOARD inspection with CRACK + BOARD_MOVEMENT
        # findings must fire BOTH the single CRACK rule and the compounded
        # BOARD_MOVEMENT_CRACK rule (which requires both findings present).
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client, substrate="GYPSUM_BOARD"
        )
        await _put_answers(
            async_client,
            token,
            project,
            room,
            inspection,
            template,
            {
                "cracks_present": {"value_bool": True},
                "board_movement": {"value_bool": True},
            },
        )
        await _complete(async_client, token, project, room, inspection)
        response = await _evaluate(async_client, token, project, room, inspection)
        assert response.status_code == 200, response.text
        items = response.json()["items"]
        codes = {item["risk_code"] for item in items}
        assert codes == {"CRACK_RECURRENCE", "BOARD_MOVEMENT_CRACK"}
        compound = next(item for item in items if item["risk_code"] == "BOARD_MOVEMENT_CRACK")
        assert compound["severity"] == "HIGH"
        assert compound["blocks_finishing"] is True
        assert compound["warranty_exclusion_candidate"] is True
        source_keys = {
            finding["finding_key_snapshot"] for finding in compound["source_findings"]
        }
        assert source_keys == {"CRACK", "BOARD_MOVEMENT"}

    async def test_board_movement_alone_produces_no_compound_risk(
        self, async_client: AsyncClient
    ) -> None:
        # Check C (Stage 7D.2): BOARD_MOVEMENT alone must NOT fire the compounded rule —
        # it requires BOTH findings — and CRACK_RECURRENCE stays silent without CRACK.
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client, substrate="GYPSUM_BOARD"
        )
        await _put_answers(
            async_client,
            token,
            project,
            room,
            inspection,
            template,
            {"board_movement": {"value_bool": True}},
        )
        await _complete(async_client, token, project, room, inspection)
        response = await _evaluate(async_client, token, project, room, inspection)
        assert response.status_code == 200, response.text
        assert response.json()["items"] == []

    async def test_evaluate_on_draft_inspection_is_rejected(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, _ = await _scaffold_inspection(async_client)
        response = await _evaluate(async_client, token, project, room, inspection)
        assert response.status_code == 409

    async def test_evaluate_unknown_inspection_is_rejected(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room = await _scaffold(async_client)
        response = await async_client.post(
            f"{risks_url(project['id'], room['id'])}/evaluate",
            json={"inspection_id": str(uuid.uuid4())},
            headers=auth_header(token),
        )
        assert response.status_code == 404

    async def test_rejected_draft_evaluate_changes_no_risk_state(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client
        )
        await _put_answers(
            async_client, token, project, room, inspection, template, CONCRETE_FULL
        )
        await _complete(async_client, token, project, room, inspection)
        first = (await _evaluate(async_client, token, project, room, inspection)).json()
        assert first["total"] == 5

        await _reopen(async_client, token, project, room, inspection)
        response = await _evaluate(async_client, token, project, room, inspection)
        assert response.status_code == 409

        # Rejected DRAFT evaluation created nothing and mutated no risk row.
        active = await _risk_items(async_client, token, project, room, status="active")
        assert [item["id"] for item in active] == [item["id"] for item in first["items"]]
        assert all(item["is_active"] for item in active)
        assert await _risk_items(async_client, token, project, room, status="resolved") == []


class TestRiskReconciliation:
    async def test_evaluate_is_idempotent_with_stable_uuids(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client
        )
        await _put_answers(
            async_client, token, project, room, inspection, template, CONCRETE_FULL
        )
        await _complete(async_client, token, project, room, inspection)

        first = (await _evaluate(async_client, token, project, room, inspection)).json()
        second = (await _evaluate(async_client, token, project, room, inspection)).json()
        assert first["total"] == second["total"] == 5
        assert {item["id"] for item in first["items"]} == {
            item["id"] for item in second["items"]
        }
        assert {
            item["source_signature"] for item in first["items"]
        } == {
            item["source_signature"] for item in second["items"]
        }
        # Still exactly five risk rows after two evaluations (no duplicates).
        assert len(await _risk_items(async_client, token, project, room, status="all")) == 5

    async def test_reopen_recomplete_reuses_stable_uuids_and_resolves(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client
        )
        await _put_answers(
            async_client, token, project, room, inspection, template, CONCRETE_FULL
        )
        await _complete(async_client, token, project, room, inspection)
        first = (await _evaluate(async_client, token, project, room, inspection)).json()
        by_code = {item["risk_code"]: item for item in first["items"]}
        unevenness_id = by_code["UNEVENNESS_PREP_INCREASED"]["id"]
        crack_id = by_code["CRACK_RECURRENCE"]["id"]

        # Rework keeps CRACK and a still-above-threshold UNEVENNESS, drops the rest.
        await _reopen(async_client, token, project, room, inspection)
        await _put_answers(
            async_client,
            token,
            project,
            room,
            inspection,
            template,
            {
                "cracks_present": {"value_bool": True},
                "unevenness_mm": {"value_number": "4.000"},
            },
        )
        await _complete(async_client, token, project, room, inspection)
        second = (await _evaluate(async_client, token, project, room, inspection)).json()
        active = {item["risk_code"]: item for item in second["items"]}
        assert set(active) == {"CRACK_RECURRENCE", "UNEVENNESS_PREP_INCREASED"}
        # The reused risks keep their UUIDs for downstream reference.
        assert active["UNEVENNESS_PREP_INCREASED"]["id"] == unevenness_id
        assert active["CRACK_RECURRENCE"]["id"] == crack_id

        # The three dropped risks are resolved, never deleted.
        all_rows = await _risk_items(async_client, token, project, room, status="all")
        resolved = [r for r in all_rows if not r["is_active"]]
        assert {r["risk_code"] for r in resolved} == {
            "LOOSE_SUBSTRATE_REMOVAL",
            "DELAMINATION_REPAIR",
            "MOLD_TREATMENT_BEFORE_FINISH",
        }
        assert all(r["resolved_at"] is not None for r in resolved)

    async def test_later_rule_version_keeps_materialized_risk_immutable(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client
        )
        await _put_answers(
            async_client,
            token,
            project,
            room,
            inspection,
            template,
            {"cracks_present": {"value_bool": True}},
        )
        await _complete(async_client, token, project, room, inspection)
        first = (await _evaluate(async_client, token, project, room, inspection)).json()
        assert len(first["items"]) == 1
        risk = first["items"][0]
        assert (risk["rule_version"], risk["severity"]) == (1, "MEDIUM")

        # A future rule version ships; materialized historical risks must keep
        # their original version/severity snapshot (no silent mutation).
        v1 = (
            await db_session.execute(
                select(RiskRule).where(
                    RiskRule.code == "CRACK_RECURRENCE",
                    RiskRule.version == 1,
                )
            )
        ).scalar_one()
        db_session.add(
            RiskRule(
                code="CRACK_RECURRENCE",
                version=2,
                active=True,
                severity=RiskSeverity.CRITICAL,
                blocks_finishing=True,
                title_key=v1.title_key,
                explanation_key=v1.explanation_key,
                consequence_key=v1.consequence_key,
                mitigation_key=v1.mitigation_key,
                communication_key=v1.communication_key,
            )
        )
        await db_session.flush()
        v2 = (
            await db_session.execute(select(RiskRule).where(RiskRule.version == 2))
        ).scalar_one()
        db_session.add(
            RiskRuleCondition(
                rule_id=v2.id,
                position=0,
                operator=RiskConditionOperator.FINDING_PRESENT,
                finding_key="CRACK",
            )
        )
        await db_session.commit()

        await _reopen(async_client, token, project, room, inspection)
        await _put_answers(
            async_client,
            token,
            project,
            room,
            inspection,
            template,
            {"cracks_present": {"value_bool": True}},
        )
        await _complete(async_client, token, project, room, inspection)
        second = (await _evaluate(async_client, token, project, room, inspection)).json()
        active = second["items"]
        assert len(active) == 1
        assert active[0]["id"] == risk["id"]
        assert active[0]["rule_version"] == 1
        assert active[0]["severity"] == "MEDIUM"
        # Same historical row -- reused, never duplicated.
        assert len(await _risk_items(async_client, token, project, room, status="all")) == 1

    async def test_list_filters_active_resolved_all(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client
        )
        await _put_answers(
            async_client, token, project, room, inspection, template, CONCRETE_FULL
        )
        await _complete(async_client, token, project, room, inspection)
        await _evaluate(async_client, token, project, room, inspection)
        await _reopen(async_client, token, project, room, inspection)
        await _put_answers(
            async_client,
            token,
            project,
            room,
            inspection,
            template,
            {"cracks_present": {"value_bool": True}},
        )
        await _complete(async_client, token, project, room, inspection)
        await _evaluate(async_client, token, project, room, inspection)

        active = await _risk_items(async_client, token, project, room, status="active")
        assert [r["risk_code"] for r in active] == ["CRACK_RECURRENCE"]
        resolved = await _risk_items(async_client, token, project, room, status="resolved")
        assert len(resolved) == 4
        assert all(not r["is_active"] for r in resolved)
        assert len(await _risk_items(async_client, token, project, room, status="all")) == 5

    async def test_risk_detail_has_traceable_sources(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client
        )
        await _put_answers(
            async_client, token, project, room, inspection, template, CONCRETE_FULL
        )
        await _complete(async_client, token, project, room, inspection)
        evaluated = (await _evaluate(async_client, token, project, room, inspection)).json()
        risk = next(
            item for item in evaluated["items"] if item["risk_code"] == "DELAMINATION_REPAIR"
        )
        detail = await async_client.get(
            f"{risks_url(project['id'], room['id'])}/{risk['id']}",
            headers=auth_header(token),
        )
        assert detail.status_code == 200
        body = detail.json()
        assert body["id"] == risk["id"]
        assert body["rule_version"] == 1
        assert body["title_key"] == "risk.delamination_repair.title"
        assert body["source_findings"][0]["finding_key_snapshot"] == "DELAMINATION"
        assert body["source_findings"][0]["value_snapshot"] == {"option": "DELAMINATION"}


class TestRiskSecurity:
    async def test_other_owner_cannot_access_risks(self, async_client: AsyncClient) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client
        )
        await _put_answers(
            async_client, token, project, room, inspection, template, CONCRETE_FULL
        )
        await _complete(async_client, token, project, room, inspection)
        await _evaluate(async_client, token, project, room, inspection)
        other_token = await get_token(async_client, OTHER_USER)

        response = await async_client.get(
            risks_url(project["id"], room["id"]),
            headers=auth_header(other_token),
        )
        assert response.status_code == 404
        response = await async_client.post(
            f"{risks_url(project['id'], room['id'])}/evaluate",
            json={"inspection_id": inspection["id"]},
            headers=auth_header(other_token),
        )
        assert response.status_code == 404

    async def test_unauthorized_requests_are_rejected(self, async_client: AsyncClient) -> None:
        response = await async_client.get(
            f"/api/projects/{uuid.uuid4()}/rooms/{uuid.uuid4()}/risks"
        )
        assert response.status_code == 401
        response = await async_client.post(
            f"/api/projects/{uuid.uuid4()}/rooms/{uuid.uuid4()}/risks/evaluate",
            json={"inspection_id": str(uuid.uuid4())},
        )
        assert response.status_code == 401
