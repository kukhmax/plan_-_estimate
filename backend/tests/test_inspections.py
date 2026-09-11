"""Integration tests for the inspection checklist engine API (Stage 6)."""

import uuid
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.checklist import AnswerType, ChecklistQuestion
from tests.conftest import make_telegram_init_data

VALID_USER = {
    "id": 900111222,
    "username": "inspection_contractor",
    "first_name": "Inspection",
    "last_name": "Contractor",
    "language_code": "pl",
}
OTHER_USER = {
    "id": 900333444,
    "username": "other_inspection_contractor",
    "first_name": "Other",
    "last_name": "Contractor",
    "language_code": "pl",
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
            "name": "Projekt Inspekcji",
            "address": "ul. Inspekcyjna 1",
            "city": "Warszawa",
            "postal_code": "00-001",
        },
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_room(async_client: AsyncClient, token: str, project_id: str) -> dict:
    response = await async_client.post(
        f"/api/projects/{project_id}/rooms",
        json={"name": "Salon"},
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_surface(
    async_client: AsyncClient,
    token: str,
    project_id: str,
    room_id: str,
    *,
    surface_type: str = "WALL",
) -> dict:
    response = await async_client.post(
        f"/api/projects/{project_id}/rooms/{room_id}/surfaces",
        json={
            "name": "Ściana 1",
            "surface_type": surface_type,
        },
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def get_template_for(
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
    return items[0]


def question_by_key(template: dict, key: str) -> dict:
    for section in template["sections"]:
        for question in section["questions"]:
            if question["key"] == key:
                return question
    raise AssertionError(f"question key {key} not found in template")


def template_url(template_id: str) -> str:
    return f"/api/checklist-templates/{template_id}"


def inspections_url(project_id: str, room_id: str) -> str:
    return f"/api/projects/{project_id}/rooms/{room_id}/inspections"


def inspection_url(project_id: str, room_id: str, inspection_id: str) -> str:
    return f"{inspections_url(project_id, room_id)}/{inspection_id}"


def action_url(project_id: str, room_id: str, inspection_id: str, action: str) -> str:
    return f"{inspection_url(project_id, room_id, inspection_id)}/{action}"


async def full_template(
    async_client: AsyncClient,
    token: str,
    template_id: str,
) -> dict:
    response = await async_client.get(
        template_url(template_id),
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    return response.json()


class TestTemplateCatalog:
    async def test_bootstrap_lists_one_active_template_per_substrate(
        self, async_client: AsyncClient
    ) -> None:
        token = await get_token(async_client, VALID_USER)
        response = await async_client.get(
            "/api/checklist-templates",
            headers=auth_header(token),
        )
        assert response.status_code == 200
        body = response.json()
        templates = body["items"]
        assert body["total"] == 6
        substrates = {item["substrate"] for item in templates}
        assert substrates == {
            "CONCRETE",
            "GYPSUM_PLASTER",
            "CEMENT_LIME_PLASTER",
            "GYPSUM_BOARD",
            "PAINTED",
            "OTHER",
        }
        assert all(item["version"] == 1 for item in templates)
        assert all(item["active"] is True for item in templates)

    async def test_bootstrap_is_idempotent(self, async_client: AsyncClient) -> None:
        token = await get_token(async_client, VALID_USER)
        for _ in range(2):
            response = await async_client.get(
                "/api/checklist-templates",
                headers=auth_header(token),
            )
            assert response.json()["total"] == 6

    async def test_gypsum_board_template_carries_drywall_section(
        self, async_client: AsyncClient
    ) -> None:
        token = await get_token(async_client, VALID_USER)
        template = await template_by_substrate(async_client, token, "GYPSUM_BOARD")
        full = await full_template(async_client, token, template["id"])
        section_keys = [s["key"] for s in full["sections"]]
        assert section_keys == ["general_conditions", "drywall_joints"]
        questions = {
            q["key"]: q
            for section in full["sections"]
            for q in section["questions"]
        }
        assert questions["joint_tape_missing"]["answer_type"] == "BOOLEAN"
        assert questions["joint_tape_missing"]["finding_key"] == "JOINT_TAPE_MISSING"
        assert questions["joint_gap_mm"]["answer_type"] == "NUMBER"
        assert questions["notes"]["answer_type"] == "TEXT"
        assert questions["notes"]["finding_key"] is None

    async def test_template_detail_requires_auth(self, async_client: AsyncClient) -> None:
        response = await async_client.get("/api/checklist-templates")
        assert response.status_code == 401


async def template_by_substrate(
    async_client: AsyncClient,
    token: str,
    substrate: str,
) -> dict:
    return await get_template_for(async_client, token, substrate)


class TestInspectionCreation:
    async def test_create_plane_inspection(self, async_client: AsyncClient) -> None:
        token, project, room = await _scaffold(async_client)
        template = await template_by_substrate(async_client, token, "CONCRETE")
        response = await async_client.post(
            inspections_url(project["id"], room["id"]),
            json={
                "template_id": template["id"],
                "substrate": "CONCRETE",
                "quality_target": "S2",
                "plane": "CEILING",
            },
            headers=auth_header(token),
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["plane"] == "CEILING"
        assert body["surface_id"] is None
        assert body["substrate"] == "CONCRETE"
        assert body["quality_target"] == "S2"
        assert body["status"] == "DRAFT"
        assert body["is_archived"] is False

    async def test_create_surface_inspection(self, async_client: AsyncClient) -> None:
        token, project, room = await _scaffold(async_client)
        wall = await create_surface(async_client, token, project["id"], room["id"])
        template = await template_by_substrate(async_client, token, "GYPSUM_BOARD")
        response = await async_client.post(
            inspections_url(project["id"], room["id"]),
            json={
                "template_id": template["id"],
                "substrate": "GYPSUM_BOARD",
                "quality_target": "Q3",
                "surface_id": wall["id"],
            },
            headers=auth_header(token),
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["surface_id"] == wall["id"]
        assert body["plane"] is None

    async def test_targeting_both_surface_and_plane_is_rejected(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room = await _scaffold(async_client)
        wall = await create_surface(async_client, token, project["id"], room["id"])
        template = await template_by_substrate(async_client, token, "CONCRETE")
        response = await async_client.post(
            inspections_url(project["id"], room["id"]),
            json={
                "template_id": template["id"],
                "substrate": "CONCRETE",
                "surface_id": wall["id"],
                "plane": "FLOOR",
            },
            headers=auth_header(token),
        )
        assert response.status_code == 422

    async def test_create_room_level_inspection(self, async_client: AsyncClient) -> None:
        token, project, room = await _scaffold(async_client)
        template = await template_by_substrate(async_client, token, "CONCRETE")
        response = await async_client.post(
            inspections_url(project["id"], room["id"]),
            json={
                "template_id": template["id"],
                "substrate": "CONCRETE",
            },
            headers=auth_header(token),
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["surface_id"] is None
        assert body["plane"] is None

    async def test_create_floor_inspection(self, async_client: AsyncClient) -> None:
        token, project, room = await _scaffold(async_client)
        template = await template_by_substrate(async_client, token, "CONCRETE")
        response = await async_client.post(
            inspections_url(project["id"], room["id"]),
            json={
                "template_id": template["id"],
                "substrate": "CONCRETE",
                "plane": "FLOOR",
            },
            headers=auth_header(token),
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["plane"] == "FLOOR"
        assert body["surface_id"] is None

    async def test_non_wall_surface_target_is_rejected(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room = await _scaffold(async_client)
        ceiling = await create_surface(
            async_client,
            token,
            project["id"],
            room["id"],
            surface_type="CEILING",
        )
        template = await template_by_substrate(async_client, token, "CONCRETE")
        response = await async_client.post(
            inspections_url(project["id"], room["id"]),
            json={
                "template_id": template["id"],
                "substrate": "CONCRETE",
                "surface_id": ceiling["id"],
            },
            headers=auth_header(token),
        )
        assert response.status_code == 422

    async def test_surface_target_from_another_room_is_rejected(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room = await _scaffold(async_client)
        other_room = await create_room(async_client, token, project["id"])
        wall = await create_surface(async_client, token, project["id"], other_room["id"])
        template = await template_by_substrate(async_client, token, "CONCRETE")
        response = await async_client.post(
            inspections_url(project["id"], room["id"]),
            json={
                "template_id": template["id"],
                "substrate": "CONCRETE",
                "surface_id": wall["id"],
            },
            headers=auth_header(token),
        )
        assert response.status_code == 404

    async def test_unknown_template_is_rejected(self, async_client: AsyncClient) -> None:
        token, project, room = await _scaffold(async_client)
        response = await async_client.post(
            inspections_url(project["id"], room["id"]),
            json={
                "template_id": str(uuid.uuid4()),
                "substrate": "CONCRETE",
                "plane": "FLOOR",
            },
            headers=auth_header(token),
        )
        assert response.status_code == 404

    async def test_template_substrate_mismatch_is_rejected(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room = await _scaffold(async_client)
        concrete_template = await template_by_substrate(async_client, token, "CONCRETE")
        response = await async_client.post(
            inspections_url(project["id"], room["id"]),
            json={
                "template_id": concrete_template["id"],
                "substrate": "GYPSUM_BOARD",
                "plane": "CEILING",
            },
            headers=auth_header(token),
        )
        assert response.status_code == 422


class TestQualityScale:
    async def test_wrong_scale_is_rejected(self, async_client: AsyncClient) -> None:
        token, project, room = await _scaffold(async_client)
        concrete_template = await template_by_substrate(async_client, token, "CONCRETE")
        response = await async_client.post(
            inspections_url(project["id"], room["id"]),
            json={
                "template_id": concrete_template["id"],
                "substrate": "CONCRETE",
                "quality_target": "Q1",
                "plane": "CEILING",
            },
            headers=auth_header(token),
        )
        assert response.status_code == 422

    async def test_gypsum_board_requires_q_scale(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room = await _scaffold(async_client)
        board_template = await template_by_substrate(async_client, token, "GYPSUM_BOARD")
        response = await async_client.post(
            inspections_url(project["id"], room["id"]),
            json={
                "template_id": board_template["id"],
                "substrate": "GYPSUM_BOARD",
                "quality_target": "S4",
                "plane": "CEILING",
            },
            headers=auth_header(token),
        )
        assert response.status_code == 422

    async def test_quality_target_can_be_deferred(self, async_client: AsyncClient) -> None:
        token, project, room = await _scaffold(async_client)
        template = await template_by_substrate(async_client, token, "CONCRETE")
        response = await async_client.post(
            inspections_url(project["id"], room["id"]),
            json={
                "template_id": template["id"],
                "substrate": "CONCRETE",
                "plane": "FLOOR",
            },
            headers=auth_header(token),
        )
        assert response.status_code == 201
        assert response.json()["quality_target"] is None


class TestInspectionAnswers:
    async def test_replace_answers_round_trip(self, async_client: AsyncClient) -> None:
        token, project, room, inspection = await _scaffold_inspection(async_client)
        template = await full_template(async_client, token, inspection["template_id"])
        payload = _answer_payload(template, cracks=True, unevenness="3.5")
        response = await async_client.put(
            action_url(project["id"], room["id"], inspection["id"], "answers"),
            json={"answers": payload},
            headers=auth_header(token),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == 2
        answers = {a["question_id"]: a for a in body["items"]}
        assert answers[payload[0]["question_id"]]["value_bool"] is True
        assert Decimal(answers[payload[1]["question_id"]]["value_number"]) == Decimal(
            "3.5"
        )

    async def test_replace_set_is_atomic(self, async_client: AsyncClient) -> None:
        token, project, room, inspection = await _scaffold_inspection(async_client)
        template = await full_template(async_client, token, inspection["template_id"])
        first = _answer_payload(template, cracks=True)
        response = await async_client.put(
            action_url(project["id"], room["id"], inspection["id"], "answers"),
            json={"answers": first},
            headers=auth_header(token),
        )
        assert response.status_code == 200
        # A second replace overwrites the previous set completely.
        second = _answer_payload(template, cracks=False)
        response = await async_client.put(
            action_url(project["id"], room["id"], inspection["id"], "answers"),
            json={"answers": second},
            headers=auth_header(token),
        )
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["items"][0]["value_bool"] is False

    async def test_answer_type_mismatch_is_rejected(self, async_client: AsyncClient) -> None:
        token, project, room, inspection = await _scaffold_inspection(async_client)
        template = await full_template(async_client, token, inspection["template_id"])
        cracks = question_by_key(template, "cracks_present")
        response = await async_client.put(
            action_url(project["id"], room["id"], inspection["id"], "answers"),
            json={"answers": [{"question_id": cracks["id"], "value_number": "1.0"}]},
            headers=auth_header(token),
        )
        assert response.status_code == 422

    async def test_unknown_question_is_rejected(self, async_client: AsyncClient) -> None:
        token, project, room, inspection = await _scaffold_inspection(async_client)
        response = await async_client.put(
            action_url(project["id"], room["id"], inspection["id"], "answers"),
            json={"answers": [{"question_id": str(uuid.uuid4()), "value_bool": True}]},
            headers=auth_header(token),
        )
        assert response.status_code == 422

    async def test_invalid_single_choice_option_is_rejected(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection = await _scaffold_inspection(async_client)
        template = await full_template(async_client, token, inspection["template_id"])
        condition = question_by_key(template, "substrate_condition")
        response = await async_client.put(
            action_url(project["id"], room["id"], inspection["id"], "answers"),
            json={"answers": [{"question_id": condition["id"], "option_key": "NOPE"}]},
            headers=auth_header(token),
        )
        assert response.status_code == 422

    async def test_completed_inspection_cannot_edit_answers(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection = await _scaffold_inspection(async_client)
        template = await full_template(async_client, token, inspection["template_id"])
        await _put_answers(
            async_client, token, project, room, inspection, template, cracks=True
        )
        await _complete(async_client, token, project, room, inspection)
        response = await async_client.put(
            action_url(project["id"], room["id"], inspection["id"], "answers"),
            json={"answers": []},
            headers=auth_header(token),
        )
        assert response.status_code == 409


class TestInspectionLifecycle:
    async def test_list_inspections_for_room(self, async_client: AsyncClient) -> None:
        token, project, room, inspection = await _scaffold_inspection(async_client)
        response = await async_client.get(
            inspections_url(project["id"], room["id"]),
            headers=auth_header(token),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == inspection["id"]

    async def test_complete_materializes_findings(self, async_client: AsyncClient) -> None:
        token, project, room, inspection = await _scaffold_inspection(async_client)
        template = await full_template(async_client, token, inspection["template_id"])
        await _put_full_answers(async_client, token, project, room, inspection, template)
        response = await _complete(async_client, token, project, room, inspection)
        assert response.status_code == 200
        assert response.json()["status"] == "COMPLETED"
        assert response.json()["completed_at"] is not None

        findings = await _findings(async_client, token, project, room, inspection)
        keys = {f["finding_key"] for f in findings}
        assert keys == {
            "CRACK",
            "UNEVENNESS",
            "LOOSE_SUBSTRATE",
            "DELAMINATION",
            "MOLD",
        }
        # notes is a TEXT question without a finding_key -> no finding
        assert "NOTES" not in keys
        unevenness = next(f for f in findings if f["finding_key"] == "UNEVENNESS")
        assert unevenness["value_snapshot"] == {"number": "3.500"}
        assert unevenness["is_active"] is True

    async def test_reopen_allows_rework(self, async_client: AsyncClient) -> None:
        token, project, room, inspection = await _scaffold_inspection(async_client)
        template = await full_template(async_client, token, inspection["template_id"])
        await _put_answers(async_client, token, project, room, inspection, template, cracks=True)
        await _complete(async_client, token, project, room, inspection)

        response = await async_client.post(
            action_url(project["id"], room["id"], inspection["id"], "reopen"),
            headers=auth_header(token),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "DRAFT"
        assert body["completed_at"] is None

        # Answers are editable again after reopen.
        response = await async_client.put(
            action_url(project["id"], room["id"], inspection["id"], "answers"),
            json={"answers": _answer_payload(template, cracks=False)},
            headers=auth_header(token),
        )
        assert response.status_code == 200

    async def test_complete_reconciles_findings_and_keeps_stable_ids(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection = await _scaffold_inspection(async_client)
        template = await full_template(async_client, token, inspection["template_id"])
        await _put_full_answers(
            async_client, token, project, room, inspection, template
        )
        await _complete(async_client, token, project, room, inspection)
        first = await _findings(async_client, token, project, room, inspection)
        unevenness_id = next(
            f["id"] for f in first if f["finding_key"] == "UNEVENNESS"
        )

        # Rework: only unevenness remains; everything else resolves.
        response = await async_client.post(
            action_url(project["id"], room["id"], inspection["id"], "reopen"),
            headers=auth_header(token),
        )
        assert response.status_code == 200
        await _put_answers(
            async_client,
            token,
            project,
            room,
            inspection,
            template,
            cracks=False,
            unevenness="1.0",
        )
        await _complete(async_client, token, project, room, inspection)

        second = await _findings(async_client, token, project, room, inspection)
        active = {f["finding_key"]: f for f in second}
        assert set(active) == {"UNEVENNESS"}
        # The reused finding keeps its UUID for downstream photo linking.
        assert active["UNEVENNESS"]["id"] == unevenness_id
        assert active["UNEVENNESS"]["resolved_at"] is None

        resolved = await _findings(
            async_client,
            token,
            project,
            room,
            inspection,
            include_inactive=True,
        )
        inactive = {f["finding_key"]: f for f in resolved if not f["is_active"]}
        assert inactive["CRACK"]["resolved_at"] is not None
        assert inactive["DELAMINATION"]["resolved_at"] is not None
        # Resolved findings are never deleted.
        assert len(resolved) == 5

    async def test_complete_twice_is_rejected(self, async_client: AsyncClient) -> None:
        token, project, room, inspection = await _scaffold_inspection(async_client)
        template = await full_template(async_client, token, inspection["template_id"])
        await _put_answers(async_client, token, project, room, inspection, template, cracks=True)
        await _complete(async_client, token, project, room, inspection)
        response = await async_client.post(
            action_url(project["id"], room["id"], inspection["id"], "complete"),
            headers=auth_header(token),
        )
        assert response.status_code == 409

    async def test_archive_and_restore(self, async_client: AsyncClient) -> None:
        token, project, room, inspection = await _scaffold_inspection(async_client)
        response = await async_client.post(
            action_url(project["id"], room["id"], inspection["id"], "archive"),
            headers=auth_header(token),
        )
        assert response.status_code == 200
        assert response.json()["is_archived"] is True
        # Hidden from the default list.
        response = await async_client.get(
            inspections_url(project["id"], room["id"]),
            headers=auth_header(token),
        )
        assert response.json()["total"] == 0
        # Visible with include_archived.
        response = await async_client.get(
            inspections_url(project["id"], room["id"]),
            params={"include_archived": "true"},
            headers=auth_header(token),
        )
        assert response.json()["total"] == 1

        response = await async_client.post(
            action_url(project["id"], room["id"], inspection["id"], "restore"),
            headers=auth_header(token),
        )
        assert response.status_code == 200
        assert response.json()["is_archived"] is False

    async def test_reopen_draft_is_rejected(self, async_client: AsyncClient) -> None:
        token, project, room, inspection = await _scaffold_inspection(async_client)
        response = await async_client.post(
            action_url(project["id"], room["id"], inspection["id"], "reopen"),
            headers=auth_header(token),
        )
        assert response.status_code == 409

    async def test_update_quality_target_on_draft(self, async_client: AsyncClient) -> None:
        token, project, room, inspection = await _scaffold_inspection(
            async_client, substrate="CONCRETE", plane="FLOOR"
        )
        response = await async_client.patch(
            inspection_url(project["id"], room["id"], inspection["id"]),
            json={"quality_target": "S3", "notes": "po ponownym pomiarze"},
            headers=auth_header(token),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["quality_target"] == "S3"
        assert body["notes"] == "po ponownym pomiarze"

    async def test_update_wrong_scale_is_rejected(self, async_client: AsyncClient) -> None:
        token, project, room, inspection = await _scaffold_inspection(
            async_client, substrate="CONCRETE", plane="FLOOR"
        )
        response = await async_client.patch(
            inspection_url(project["id"], room["id"], inspection["id"]),
            json={"quality_target": "Q2"},
            headers=auth_header(token),
        )
        assert response.status_code == 422

    async def test_update_completed_is_rejected(self, async_client: AsyncClient) -> None:
        token, project, room, inspection = await _scaffold_inspection(async_client)
        template = await full_template(async_client, token, inspection["template_id"])
        await _put_answers(async_client, token, project, room, inspection, template, cracks=True)
        await _complete(async_client, token, project, room, inspection)
        response = await async_client.patch(
            inspection_url(project["id"], room["id"], inspection["id"]),
            json={"notes": "zmiana"},
            headers=auth_header(token),
        )
        assert response.status_code == 409


async def test_other_owner_cannot_see_room_level_inspections(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    other_token = await get_token(async_client, OTHER_USER)
    project, room = await _scaffold_project_room(async_client, token)
    template = await template_by_substrate(async_client, token, "CONCRETE")

    response = await async_client.post(
        inspections_url(project["id"], room["id"]),
        json={"template_id": template["id"], "substrate": "CONCRETE"},
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    inspection_id = response.json()["id"]

    # The other owner must not be able to list, read, or complete the
    # room-level inspection of a foreign project.
    response = await async_client.get(
        inspections_url(project["id"], room["id"]),
        headers=auth_header(other_token),
    )
    assert response.status_code == 404
    response = await async_client.get(
        inspection_url(project["id"], room["id"], inspection_id),
        headers=auth_header(other_token),
    )
    assert response.status_code == 404
    response = await async_client.post(
        action_url(project["id"], room["id"], inspection_id, "complete"),
        headers=auth_header(other_token),
    )
    assert response.status_code == 404


async def test_other_owner_cannot_see_room_inspections(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    other_token = await get_token(async_client, OTHER_USER)
    project, room = await _scaffold_project_room(async_client, token)
    other_project = await create_project(async_client, other_token)
    other_room = await create_room(async_client, other_token, other_project["id"])

    response = await async_client.get(
        inspections_url(project["id"], room["id"]),
        headers=auth_header(other_token),
    )
    assert response.status_code == 404
    response = await async_client.get(
        inspections_url(other_project["id"], other_room["id"]),
        headers=auth_header(token),
    )
    assert response.status_code == 404


async def test_duplicate_finding_key_sources_stay_distinct(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Two distinct questions sharing one semantic finding_key stay separate.

    The reconciliation identity is (question_id, finding_key); a second question
    that produces the same finding_key must neither be conflated with nor
    overwrite the finding of the first source.
    """
    token, project, room, inspection = await _scaffold_inspection(async_client)
    template = await full_template(async_client, token, inspection["template_id"])
    original = question_by_key(template, "cracks_present")

    original_row = await db_session.get(ChecklistQuestion, uuid.UUID(original["id"]))
    alt = ChecklistQuestion(
        template_id=original_row.template_id,
        section_id=original_row.section_id,
        position=99,
        key="cracks_present_alt",
        text_key="checklist.question.cracks_present_alt",
        answer_type=AnswerType.BOOLEAN,
        finding_key=original_row.finding_key,
    )
    db_session.add(alt)
    await db_session.commit()
    await db_session.refresh(alt)
    alt_id = str(alt.id)

    # Both sources confirmed at once -> two distinct CRACK findings.
    response = await async_client.put(
        action_url(project["id"], room["id"], inspection["id"], "answers"),
        json={
            "answers": [
                {"question_id": original["id"], "value_bool": True},
                {"question_id": alt_id, "value_bool": True},
            ]
        },
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    await _complete(async_client, token, project, room, inspection)

    findings = await _findings(async_client, token, project, room, inspection)
    cracks = [f for f in findings if f["finding_key"] == "CRACK"]
    assert len(cracks) == 2
    assert len({f["id"] for f in cracks}) == 2
    assert len({f["question_id"] for f in cracks}) == 2
    kept = next(f for f in cracks if f["question_id"] == alt_id)
    dropped = next(f for f in cracks if f["question_id"] == original["id"])

    # Only the alternative source stays confirmed: its UUID must be reused and
    # the original source's finding resolved (never deleted).
    await async_client.post(
        action_url(project["id"], room["id"], inspection["id"], "reopen"),
        headers=auth_header(token),
    )
    response = await async_client.put(
        action_url(project["id"], room["id"], inspection["id"], "answers"),
        json={"answers": [{"question_id": alt_id, "value_bool": True}]},
        headers=auth_header(token),
    )
    assert response.status_code == 200
    await _complete(async_client, token, project, room, inspection)

    active = await _findings(async_client, token, project, room, inspection)
    assert len(active) == 1
    assert active[0]["id"] == kept["id"]
    assert active[0]["question_id"] == alt_id

    resolved = await _findings(
        async_client,
        token,
        project,
        room,
        inspection,
        include_inactive=True,
    )
    inactive = [f for f in resolved if not f["is_active"]]
    assert len(inactive) == 1
    assert inactive[0]["question_id"] == original["id"]
    assert inactive[0]["resolved_at"] is not None


async def test_unauthorized_requests_are_rejected(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/checklist-templates")
    assert response.status_code == 401
    response = await async_client.get(
        f"/api/projects/{uuid.uuid4()}/rooms/{uuid.uuid4()}/inspections"
    )
    assert response.status_code == 401


async def _scaffold(
    async_client: AsyncClient,
    user_dict: dict | None = None,
) -> tuple[str, dict, dict]:
    token = await get_token(async_client, user_dict or VALID_USER)
    project, room = await _scaffold_project_room(async_client, token)
    return token, project, room


async def _scaffold_project_room(
    async_client: AsyncClient,
    token: str,
) -> tuple[dict, dict]:
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    return project, room


async def _scaffold_inspection(
    async_client: AsyncClient,
    *,
    substrate: str = "CONCRETE",
    plane: str = "CEILING",
) -> tuple[str, dict, dict, dict]:
    token, project, room = await _scaffold(async_client)
    template = await template_by_substrate(async_client, token, substrate)
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
    return token, project, room, response.json()


def _answer_payload(template: dict, *, cracks: bool, unevenness: str | None = None) -> list[dict]:
    questions = {
        q["key"]: q for section in template["sections"] for q in section["questions"]
    }
    payload = [{"question_id": questions["cracks_present"]["id"], "value_bool": cracks}]
    if unevenness is not None:
        payload.append(
            {"question_id": questions["unevenness_mm"]["id"], "value_number": unevenness}
        )
    return payload


async def _put_answers(
    async_client: AsyncClient,
    token: str,
    project: dict,
    room: dict,
    inspection: dict,
    template: dict,
    *,
    cracks: bool,
    unevenness: str | None = None,
) -> None:
    response = await async_client.put(
        action_url(project["id"], room["id"], inspection["id"], "answers"),
        json={
            "answers": _answer_payload(template, cracks=cracks, unevenness=unevenness)
        },
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text


async def _put_full_answers(
    async_client: AsyncClient,
    token: str,
    project: dict,
    room: dict,
    inspection: dict,
    template: dict,
) -> None:
    questions = {
        q["key"]: q for section in template["sections"] for q in section["questions"]
    }
    payload = [
        {"question_id": questions["cracks_present"]["id"], "value_bool": True},
        {"question_id": questions["unevenness_mm"]["id"], "value_number": "3.500"},
        {"question_id": questions["substrate_condition"]["id"], "option_key": "LOOSE"},
        {
            "question_id": questions["present_defects"]["id"],
            "option_keys": ["DELAMINATION", "MOLD"],
        },
        {"question_id": questions["notes"]["id"], "value_text": "uwagi ogólne"},
    ]
    response = await async_client.put(
        action_url(project["id"], room["id"], inspection["id"], "answers"),
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
        action_url(project["id"], room["id"], inspection["id"], "complete"),
        headers=auth_header(token),
    )


async def _findings(
    async_client: AsyncClient,
    token: str,
    project: dict,
    room: dict,
    inspection: dict,
    *,
    include_inactive: bool = False,
):
    params = {"include_inactive": "true"} if include_inactive else {}
    response = await async_client.get(
        action_url(project["id"], room["id"], inspection["id"], "findings"),
        params=params,
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]