"""Integration tests for the communication engine API (Stage 8B)."""

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.data.communication_phrases import (
    build_baseline_communication_phrases,
    risk_phrase_key,
)
from app.domain.data.risk_rules import build_baseline_risk_rules
from app.domain.rules.risk_rules import compute_source_signature
from app.models.communication import (
    CommunicationApplication,
    CommunicationCategory,
    CommunicationPhrase,
)
from tests.conftest import make_telegram_init_data

VALID_USER = {
    "id": 900555666,
    "username": "comm_contractor",
    "first_name": "Comm",
    "last_name": "Contractor",
    "language_code": "pl",
}
OTHER_USER = {
    "id": 900777888,
    "username": "other_comm_contractor",
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
            "name": "Projekt Komunikacji",
            "address": "ul. Rozmowna 1",
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


def communications_url(project_id: str, room_id: str, inspection_id: str) -> str:
    return (
        f"/api/projects/{project_id}/rooms/{room_id}/inspections/"
        f"{inspection_id}/communications"
    )


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
    quality_target: str | None = None,
    token: str | None = None,
    project: dict | None = None,
    room: dict | None = None,
) -> tuple[str, dict, dict, dict, dict]:
    if token is None or project is None or room is None:
        token, project, room = await _scaffold(async_client)
    template = await full_template(async_client, token, substrate)
    payload = {
        "template_id": template["id"],
        "substrate": substrate,
        "plane": plane,
    }
    if quality_target is not None:
        payload["quality_target"] = quality_target
    response = await async_client.post(
        inspections_url(project["id"], room["id"]),
        json=payload,
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


async def _evaluate_risks(
    async_client: AsyncClient,
    token: str,
    project: dict,
    room: dict,
    inspection: dict,
) -> dict:
    response = await async_client.post(
        f"{risks_url(project['id'], room['id'])}/evaluate",
        json={"inspection_id": inspection["id"]},
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _evaluate_communications(
    async_client: AsyncClient,
    token: str,
    project: dict,
    room: dict,
    inspection: dict,
):
    return await async_client.post(
        f"{communications_url(project['id'], room['id'], inspection['id'])}/evaluate",
        headers=auth_header(token),
    )


async def _comm_items(
    async_client: AsyncClient,
    token: str,
    project: dict,
    room: dict,
    inspection: dict,
    **params,
) -> list[dict]:
    response = await async_client.get(
        communications_url(project["id"], room["id"], inspection["id"]),
        params=params,
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


class TestCommunicationReferenceData:
    async def test_baseline_phrases_bootstrapped(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, project, room, inspection, _ = await _scaffold_inspection(async_client)
        await _complete(async_client, token, project, room, inspection)
        await _evaluate_communications(async_client, token, project, room, inspection)

        rows = list(
            (
                await db_session.execute(select(CommunicationPhrase))
            ).scalars().all()
        )
        assert len(rows) == len(build_baseline_communication_phrases())
        codes = {row.code for row in rows}
        assert len(codes) == len(rows), "phrase codes must be unique"
        assert all(row.version == 1 for row in rows)

    async def test_bootstrap_is_idempotent(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, project, room, inspection, _ = await _scaffold_inspection(async_client)
        await _complete(async_client, token, project, room, inspection)
        await _evaluate_communications(async_client, token, project, room, inspection)
        # A second, concurrent-style evaluation must not create phrase rows again.
        await _evaluate_communications(async_client, token, project, room, inspection)
        rows = list(
            (
                await db_session.execute(select(CommunicationPhrase))
            ).scalars().all()
        )
        assert len(rows) == len(build_baseline_communication_phrases())

    async def test_phrase_version_pair_is_unique(
        self, db_session: AsyncSession
    ) -> None:
        base = build_baseline_communication_phrases()[0]
        db_session.add(
            CommunicationPhrase(
                code=base.code,
                version=base.version,
                active=True,
                category=base.category,
                priority=base.priority,
                phrase_key=base.phrase_key,
            )
        )
        await db_session.flush()
        db_session.add(
            CommunicationPhrase(
                code=base.code,
                version=base.version,
                active=True,
                category=base.category,
                priority=base.priority,
                phrase_key=base.phrase_key,
            )
        )
        try:
            await db_session.flush()
            raise AssertionError("duplicate (code, version) must be rejected")
        except IntegrityError:
            await db_session.rollback()

    async def test_every_baseline_risk_rule_has_a_seed_phrase(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, project, room, inspection, _ = await _scaffold_inspection(async_client)
        await _complete(async_client, token, project, room, inspection)
        await _evaluate_communications(async_client, token, project, room, inspection)

        rules = [rule for rule in build_baseline_risk_rules() if rule.version == 1]
        assert len(rules) == 15
        for rule in rules:
            expected_key = risk_phrase_key(rule.code)
            phrase = (
                await db_session.execute(
                    select(CommunicationPhrase).where(
                        CommunicationPhrase.risk_code == rule.code,
                        CommunicationPhrase.seed_key == expected_key,
                    )
                )
            ).scalar_one_or_none()
            assert phrase is not None, (
                f"missing seed phrase for risk {rule.code} "
                f"(expected seed {expected_key})"
            )
            assert phrase.phrase_key == expected_key


class TestRiskDerivedPhrases:
    async def test_risk_phrases_materialize_with_seed_keys(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client
        )
        await _put_answers(
            async_client, token, project, room, inspection, template, CONCRETE_FULL
        )
        await _complete(async_client, token, project, room, inspection)
        await _evaluate_risks(async_client, token, project, room, inspection)
        response = await _evaluate_communications(
            async_client, token, project, room, inspection
        )
        assert response.status_code == 200, response.text
        body = response.json()
        codes = {item["phrase_code"] for item in body["items"]}
        assert codes == {
            "COMM_RISK_CRACK_RECURRENCE",
            "COMM_RISK_UNEVENNESS_PREP_INCREASED",
            "COMM_RISK_LOOSE_SUBSTRATE_REMOVAL",
            "COMM_RISK_DELAMINATION_REPAIR",
            "COMM_RISK_MOLD_TREATMENT_BEFORE_FINISH",
        }
        assert body["total"] == 5
        for item in body["items"]:
            assert item["source_kind"] == "RISK"
            assert item["seed_key"] == risk_phrase_key(
                item["phrase_code"].removeprefix("COMM_RISK_")
            )
            assert item["phrase_key"] == item["seed_key"]
            assert item["is_active"] is True

    async def test_risk_phrases_link_the_materialized_risk(
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
        risks = await _evaluate_risks(async_client, token, project, room, inspection)
        assert risks["total"] == 1
        risk_id = risks["items"][0]["id"]
        response = await _evaluate_communications(
            async_client, token, project, room, inspection
        )
        item = response.json()["items"][0]
        assert item["phrase_code"] == "COMM_RISK_MOISTURE_BLOCK_FINISHING"
        assert item["category"] == "REQUIRE_CLIENT_DECISION"

    async def test_no_risk_phrases_until_risks_are_evaluated(
        self, async_client: AsyncClient
    ) -> None:
        # A CRACK finding would produce CRACK_RECURRENCE under Stage 7, but the
        # communication engine must never fabricate risk-derived phrases from
        # raw findings — it consumes materialized risk rows only.
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
        response = await _evaluate_communications(
            async_client, token, project, room, inspection
        )
        assert response.status_code == 200
        codes = {item["phrase_code"] for item in response.json()["items"]}
        assert "COMM_RISK_CRACK_RECURRENCE" not in codes
        assert all(item["source_kind"] != "RISK" for item in response.json()["items"])

    async def test_finding_phrase_still_generates_without_risk_evaluation(
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
            {
                "cracks_present": {"value_bool": True},
                "unevenness_mm": {"value_number": "1.000"},
            },
        )
        await _complete(async_client, token, project, room, inspection)
        response = await _evaluate_communications(
            async_client, token, project, room, inspection
        )
        codes = {item["phrase_code"] for item in response.json()["items"]}
        assert codes == {"COMM_FIND_UNEVENNESS"}


class TestFindingOnlyPhrases:
    async def test_below_threshold_unevenness_emits_finding_phrase(
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
            {"unevenness_mm": {"value_number": "1.000"}},
        )
        await _complete(async_client, token, project, room, inspection)
        response = await _evaluate_communications(
            async_client, token, project, room, inspection
        )
        items = response.json()["items"]
        assert len(items) == 1
        item = items[0]
        assert item["phrase_code"] == "COMM_FIND_UNEVENNESS"
        assert item["source_kind"] == "FINDING"
        assert item["seed_key"] is None
        assert item["phrase_key"] == "communication.comm_find_unevenness.phrase"
        assert item["why_key"] == "communication.comm_find_unevenness.why"

    async def test_specificity_full_wins_over_generic_and_partial(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client,
            substrate="GYPSUM_PLASTER",
            quality_target="S3",
        )
        await _put_answers(
            async_client,
            token,
            project,
            room,
            inspection,
            template,
            {"unevenness_mm": {"value_number": "1.000"}},
        )
        await _complete(async_client, token, project, room, inspection)
        response = await _evaluate_communications(
            async_client, token, project, room, inspection
        )
        codes = {item["phrase_code"] for item in response.json()["items"]}
        assert codes == {
            "COMM_FIND_UNEVENNESS_GYPSUM_PLASTER_S3",
            "COMM_QUALITY_GYPSUM_PLASTER_S3",
        }

    async def test_specificity_substrate_wins_without_quality(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client, substrate="GYPSUM_PLASTER"
        )
        await _put_answers(
            async_client,
            token,
            project,
            room,
            inspection,
            template,
            {"unevenness_mm": {"value_number": "1.000"}},
        )
        await _complete(async_client, token, project, room, inspection)
        response = await _evaluate_communications(
            async_client, token, project, room, inspection
        )
        codes = {item["phrase_code"] for item in response.json()["items"]}
        assert codes == {"COMM_FIND_UNEVENNESS_GYPSUM_PLASTER"}

    async def test_covered_finding_does_not_double_emit(
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
            {"unevenness_mm": {"value_number": "3.500"}},
        )
        await _complete(async_client, token, project, room, inspection)
        await _evaluate_risks(async_client, token, project, room, inspection)
        response = await _evaluate_communications(
            async_client, token, project, room, inspection
        )
        codes = {item["phrase_code"] for item in response.json()["items"]}
        # The risk fires (>= 3 mm); the finding is explained by the risk, so the
        # finding-only phrase must not also be emitted.
        assert codes == {"COMM_RISK_UNEVENNESS_PREP_INCREASED"}
        assert not any(code.startswith("COMM_FIND_") for code in codes)

    async def test_below_threshold_joint_gap_emits_finding_phrase(
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
            {"joint_gap_mm": {"value_number": "1.500"}},
        )
        await _complete(async_client, token, project, room, inspection)
        await _evaluate_risks(async_client, token, project, room, inspection)
        response = await _evaluate_communications(
            async_client, token, project, room, inspection
        )
        codes = {item["phrase_code"] for item in response.json()["items"]}
        assert codes == {"COMM_FIND_JOINT_GAP"}

    async def test_isolated_board_movement_keeps_its_distinct_purpose(
        self, async_client: AsyncClient
    ) -> None:
        # BOARD_MOVEMENT alone never fires the compounded Stage 7 rule (that
        # one needs CRACK too), so suppression must NOT remove the finding-only
        # phrase for a distinct isolated purpose.
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
        await _evaluate_risks(async_client, token, project, room, inspection)
        response = await _evaluate_communications(
            async_client, token, project, room, inspection
        )
        codes = {item["phrase_code"] for item in response.json()["items"]}
        assert codes == {"COMM_FIND_BOARD_MOVEMENT"}

    async def test_compounded_risk_suppresses_duplicate_finding_echo(
        self, async_client: AsyncClient
    ) -> None:
        # CRACK + BOARD_MOVEMENT fires BOARD_MOVEMENT_CRACK, which already
        # explains the movement; the covered finding's finding-only echo must
        # be dropped so the client is not shown two messages about the same
        # condition.
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
        await _evaluate_risks(async_client, token, project, room, inspection)
        response = await _evaluate_communications(
            async_client, token, project, room, inspection
        )
        codes = {item["phrase_code"] for item in response.json()["items"]}
        assert codes == {
            "COMM_RISK_CRACK_RECURRENCE",
            "COMM_RISK_BOARD_MOVEMENT_CRACK",
        }
        assert "COMM_FIND_BOARD_MOVEMENT" not in codes


class TestQualityPhrases:
    async def test_quality_phrase_exact_match(self, async_client: AsyncClient) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client, substrate="GYPSUM_BOARD", quality_target="Q2"
        )
        await _put_answers(
            async_client,
            token,
            project,
            room,
            inspection,
            template,
            {"moisture_high": {"value_bool": False}},
        )
        await _complete(async_client, token, project, room, inspection)
        response = await _evaluate_communications(
            async_client, token, project, room, inspection
        )
        items = response.json()["items"]
        assert len(items) == 1
        item = items[0]
        assert item["phrase_code"] == "COMM_QUALITY_GYPSUM_BOARD_Q2"
        assert item["category"] == "QUALITY_EXPECTATION"
        assert item["source_kind"] == "QUALITY"
        # Context-only phrases share one constant identity signature.
        assert item["source_signature"] == compute_source_signature([])

    async def test_quality_absent_without_target(self, async_client: AsyncClient) -> None:
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
            {"moisture_high": {"value_bool": False}},
        )
        await _complete(async_client, token, project, room, inspection)
        response = await _evaluate_communications(
            async_client, token, project, room, inspection
        )
        assert response.json()["items"] == []

    async def test_no_automatic_generic_quality_fallback(
        self, async_client: AsyncClient
    ) -> None:
        # CONCRETE S4 exists in the catalog, but S3 does not — the engine must
        # stay silent rather than invent a generic expectation phrase.
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client, substrate="CONCRETE", quality_target="S3"
        )
        await _put_answers(
            async_client,
            token,
            project,
            room,
            inspection,
            template,
            {"moisture_high": {"value_bool": False}},
        )
        await _complete(async_client, token, project, room, inspection)
        response = await _evaluate_communications(
            async_client, token, project, room, inspection
        )
        codes = {item["phrase_code"] for item in response.json()["items"]}
        assert "COMM_QUALITY_CONCRETE_S3" not in codes
        assert not any(item["source_kind"] == "QUALITY" for item in response.json()["items"])

    async def test_quality_coexists_with_risk_and_finding_phrases(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client, substrate="GYPSUM_BOARD", quality_target="Q2"
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
        await _evaluate_risks(async_client, token, project, room, inspection)
        response = await _evaluate_communications(
            async_client, token, project, room, inspection
        )
        codes = {item["phrase_code"] for item in response.json()["items"]}
        assert codes == {
            "COMM_RISK_JOINT_TAPE_MISSING_REWORK",
            "COMM_QUALITY_GYPSUM_BOARD_Q2",
        }


class TestIdentityReconciliation:
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
        await _evaluate_risks(async_client, token, project, room, inspection)

        first = (await _evaluate_communications(
            async_client, token, project, room, inspection
        )).json()
        second = (await _evaluate_communications(
            async_client, token, project, room, inspection
        )).json()
        assert first["total"] == second["total"] == 5
        assert {item["id"] for item in first["items"]} == {
            item["id"] for item in second["items"]
        }
        # No duplicate applications after two evaluations.
        assert len(await _comm_items(
            async_client, token, project, room, inspection, status="all"
        )) == 5

    async def test_reopen_recomplete_reuses_and_resolves(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client
        )
        await _put_answers(
            async_client, token, project, room, inspection, template, CONCRETE_FULL
        )
        await _complete(async_client, token, project, room, inspection)
        await _evaluate_risks(async_client, token, project, room, inspection)
        first = (await _evaluate_communications(
            async_client, token, project, room, inspection
        )).json()
        by_code = {item["phrase_code"]: item for item in first["items"]}
        crack_app_id = by_code["COMM_RISK_CRACK_RECURRENCE"]["id"]

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
                "unevenness_mm": {"value_number": "1.000"},
            },
        )
        await _complete(async_client, token, project, room, inspection)
        await _evaluate_risks(async_client, token, project, room, inspection)
        second = (await _evaluate_communications(
            async_client, token, project, room, inspection
        )).json()
        active = {item["phrase_code"]: item for item in second["items"]}
        assert set(active) == {
            "COMM_RISK_CRACK_RECURRENCE",
            "COMM_FIND_UNEVENNESS",
        }
        assert active["COMM_RISK_CRACK_RECURRENCE"]["id"] == crack_app_id

        all_rows = await _comm_items(
            async_client, token, project, room, inspection, status="all"
        )
        resolved = [item for item in all_rows if not item["is_active"]]
        assert {item["phrase_code"] for item in resolved} == {
            "COMM_RISK_UNEVENNESS_PREP_INCREASED",
            "COMM_RISK_LOOSE_SUBSTRATE_REMOVAL",
            "COMM_RISK_DELAMINATION_REPAIR",
            "COMM_RISK_MOLD_TREATMENT_BEFORE_FINISH",
        }
        assert all(item["resolved_at"] is not None for item in resolved)

    async def test_later_phrase_version_keeps_application_immutable(
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
        await _evaluate_risks(async_client, token, project, room, inspection)
        first = (await _evaluate_communications(
            async_client, token, project, room, inspection
        )).json()
        app = first["items"][0]
        assert (app["phrase_version"], app["category"]) == (1, "EXPLAIN_CONDITION")

        # A future catalog version ships for the SAME phrase code.
        db_session.add(
            CommunicationPhrase(
                code="COMM_RISK_CRACK_RECURRENCE",
                version=2,
                active=True,
                category=CommunicationCategory.REQUIRE_CLIENT_DECISION,
                priority=0,
                risk_code="CRACK_RECURRENCE",
                phrase_key="risk.crack_recurrence.communication",
                seed_key="risk.crack_recurrence.communication",
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
        second = (await _evaluate_communications(
            async_client, token, project, room, inspection
        )).json()
        same = second["items"][0]
        assert same["id"] == app["id"]
        assert same["phrase_version"] == 1
        assert same["category"] == "EXPLAIN_CONDITION"
        assert len(await _comm_items(
            async_client, token, project, room, inspection, status="all"
        )) == 1

        # A fresh inspection being evaluated now picks up the newest version.
        _token, _project, _room, fresh, _template = await _scaffold_inspection(
            async_client,
            token=token,
            project=project,
            room=room,
        )
        await _put_answers(
            async_client,
            token,
            project,
            room,
            fresh,
            _template,
            {"cracks_present": {"value_bool": True}},
        )
        await _complete(async_client, token, project, room, fresh)
        await _evaluate_risks(async_client, token, project, room, fresh)
        fresh_app = (await _evaluate_communications(
            async_client, token, project, room, fresh
        )).json()["items"][0]
        assert fresh_app["phrase_version"] == 2
        assert fresh_app["category"] == "REQUIRE_CLIENT_DECISION"

    async def test_identity_keyed_on_signature_not_version(
        self, async_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        # Two applications of the SAME phrase at the SAME version are legally
        # distinct when their factual source signatures differ — the reason the
        # identity law is (phrase_code, source_signature), not phrase_version.
        _, project, room, inspection, _ = await _scaffold_inspection(async_client)
        inspection_id = uuid.UUID(inspection["id"])
        for signature in ("a" * 64, "b" * 64):
            db_session.add(
                CommunicationApplication(
                    inspection_id=inspection_id,
                    phrase_code="COMM_RISK_TEST",
                    phrase_version=1,
                    category=CommunicationCategory.GENERAL,
                    priority=0,
                    phrase_key="risk.test.communication",
                    source_kind="RISK",
                    source_signature=signature,
                )
            )
            await db_session.flush()

        db_session.add(
            CommunicationApplication(
                inspection_id=inspection_id,
                phrase_code="COMM_RISK_TEST",
                phrase_version=1,
                category=CommunicationCategory.GENERAL,
                priority=0,
                phrase_key="risk.test.communication",
                source_kind="RISK",
                source_signature="a" * 64,
            )
        )
        try:
            await db_session.flush()
            raise AssertionError("duplicate identity must be rejected")
        except IntegrityError:
            await db_session.rollback()


class TestLifecycleAndFilters:
    async def test_evaluate_on_draft_inspection_is_rejected(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, _ = await _scaffold_inspection(async_client)
        response = await _evaluate_communications(
            async_client, token, project, room, inspection
        )
        assert response.status_code == 409

    async def test_evaluate_unknown_inspection_is_rejected(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room = await _scaffold(async_client)
        response = await async_client.post(
            f"{communications_url(project['id'], room['id'], str(uuid.uuid4()))}/evaluate",
            headers=auth_header(token),
        )
        assert response.status_code == 404

    async def test_rejected_draft_evaluate_changes_no_state(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client
        )
        await _put_answers(
            async_client, token, project, room, inspection, template, CONCRETE_FULL
        )
        await _complete(async_client, token, project, room, inspection)
        await _evaluate_risks(async_client, token, project, room, inspection)
        first = (await _evaluate_communications(
            async_client, token, project, room, inspection
        )).json()
        assert first["total"] == 5

        await _reopen(async_client, token, project, room, inspection)
        response = await _evaluate_communications(
            async_client, token, project, room, inspection
        )
        assert response.status_code == 409

        active = await _comm_items(
            async_client, token, project, room, inspection, status="active"
        )
        assert [item["id"] for item in active] == [item["id"] for item in first["items"]]
        assert len(await _comm_items(
            async_client, token, project, room, inspection, status="resolved"
        )) == 0

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
        await _evaluate_risks(async_client, token, project, room, inspection)
        await _evaluate_communications(async_client, token, project, room, inspection)
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
        await _evaluate_risks(async_client, token, project, room, inspection)
        await _evaluate_communications(async_client, token, project, room, inspection)

        active = await _comm_items(
            async_client, token, project, room, inspection, status="active"
        )
        assert [item["phrase_code"] for item in active] == ["COMM_RISK_CRACK_RECURRENCE"]
        resolved = await _comm_items(
            async_client, token, project, room, inspection, status="resolved"
        )
        assert len(resolved) == 4
        assert all(not item["is_active"] for item in resolved)
        assert len(await _comm_items(
            async_client, token, project, room, inspection, status="all"
        )) == 5


class TestTraceability:
    async def test_detail_risk_source_has_risk_context_and_snapshots(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client
        )
        await _put_answers(
            async_client, token, project, room, inspection, template, CONCRETE_FULL
        )
        await _complete(async_client, token, project, room, inspection)
        await _evaluate_risks(async_client, token, project, room, inspection)
        items = (await _evaluate_communications(
            async_client, token, project, room, inspection
        )).json()["items"]
        app = next(
            item for item in items if item["phrase_code"] == "COMM_RISK_DELAMINATION_REPAIR"
        )
        response = await async_client.get(
            f"{communications_url(project['id'], room['id'], inspection['id'])}/{app['id']}",
            headers=auth_header(token),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["source_kind"] == "RISK"
        source = body["source"]
        assert source["kind"] == "RISK"
        assert source["risk_code"] == "DELAMINATION_REPAIR"
        assert source["severity"] == "HIGH"
        assert source["risk_is_active"] is True
        assert source["source_findings"][0]["finding_key_snapshot"] == "DELAMINATION"

    async def test_detail_finding_source_has_label_and_value_snapshots(
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
            {"unevenness_mm": {"value_number": "1.000"}},
        )
        await _complete(async_client, token, project, room, inspection)
        app = (await _evaluate_communications(
            async_client, token, project, room, inspection
        )).json()["items"][0]
        response = await async_client.get(
            f"{communications_url(project['id'], room['id'], inspection['id'])}/{app['id']}",
            headers=auth_header(token),
        )
        assert response.status_code == 200
        source = response.json()["source"]
        assert source["kind"] == "FINDING"
        assert source["finding_key"] == "UNEVENNESS"
        assert len(source["findings"]) == 1
        assert source["findings"][0]["value_snapshot"] is not None

    async def test_detail_quality_source_lists_substrate_and_target(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client, substrate="GYPSUM_BOARD", quality_target="Q2"
        )
        await _put_answers(
            async_client,
            token,
            project,
            room,
            inspection,
            template,
            {"moisture_high": {"value_bool": False}},
        )
        await _complete(async_client, token, project, room, inspection)
        app = (await _evaluate_communications(
            async_client, token, project, room, inspection
        )).json()["items"][0]
        response = await async_client.get(
            f"{communications_url(project['id'], room['id'], inspection['id'])}/{app['id']}",
            headers=auth_header(token),
        )
        assert response.status_code == 200
        source = response.json()["source"]
        assert source["kind"] == "QUALITY"
        assert source["substrate"] == "GYPSUM_BOARD"
        assert source["quality_level"] == "Q2"

    async def test_detail_unknown_application_is_404(self, async_client: AsyncClient) -> None:
        token, project, room, inspection, _ = await _scaffold_inspection(async_client)
        response = await async_client.get(
            f"{communications_url(project['id'], room['id'], inspection['id'])}/{uuid.uuid4()}",
            headers=auth_header(token),
        )
        assert response.status_code == 404


class TestSecurity:
    async def test_other_owner_cannot_access_communications(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client
        )
        await _put_answers(
            async_client, token, project, room, inspection, template, CONCRETE_FULL
        )
        await _complete(async_client, token, project, room, inspection)
        await _evaluate_risks(async_client, token, project, room, inspection)
        await _evaluate_communications(async_client, token, project, room, inspection)
        other_token = await get_token(async_client, OTHER_USER)

        response = await async_client.get(
            communications_url(project["id"], room["id"], inspection["id"]),
            headers=auth_header(other_token),
        )
        assert response.status_code == 404
        response = await async_client.post(
            f"{communications_url(project['id'], room['id'], inspection['id'])}/evaluate",
            headers=auth_header(other_token),
        )
        assert response.status_code == 404

    async def test_unauthorized_requests_are_rejected(self, async_client: AsyncClient) -> None:
        project_id, room_id, inspection_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        response = await async_client.get(
            communications_url(str(project_id), str(room_id), str(inspection_id))
        )
        assert response.status_code == 401
        response = await async_client.post(
            f"{communications_url(str(project_id), str(room_id), str(inspection_id))}/evaluate"
        )
        assert response.status_code == 401


class TestOpenApiRoutes:
    async def test_openapi_pins_communication_route_surface(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]
        list_path = (
            "/api/projects/{project_id}/rooms/{room_id}/inspections/"
            "{inspection_id}/communications"
        )
        evaluate_path = (
            "/api/projects/{project_id}/rooms/{room_id}/inspections/"
            "{inspection_id}/communications/evaluate"
        )
        detail_path = (
            "/api/projects/{project_id}/rooms/{room_id}/inspections/"
            "{inspection_id}/communications/{communication_id}"
        )
        assert set(paths[list_path]) == {"get"}
        assert set(paths[evaluate_path]) == {"post"}
        assert set(paths[detail_path]) == {"get"}
        # No generic CRUD routes (create/update/delete) may exist on the family.
        for path, methods in paths.items():
            if "/communications" not in path:
                continue
            assert not ({"post", "patch", "put", "delete"} & set(methods) - {"post"}), (
                f"unexpected mutation route {path} methods {set(methods)}"
            )