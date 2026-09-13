"""Stage 8 (8D) integration contract: the full Stage 6->7->8 chain.

One canonical COMPLETED inspection drives:

    InspectionFinding (Stage 6) -> Risk (Stage 7) -> CommunicationApplication (Stage 8)

and is then exercised through two reopen / edit / recomplete cycles to prove
joint lifecycle consistency across all three layers: obsolete rows resolve,
new rows materialize, same factual context reuses the same UUIDs, filters
return the right historical slices without physical deletion, and traceability
details still explain every source kind without any layer recomputing another
layer's responsibility.

The Stage 8 communication engine only consumes materialized risk/finding rows
and the inspection context; the no-risk-before-evaluation assertion below locks
that a communication risk phrase can never exist before Stage 7 risk evaluation.
"""

import uuid

from httpx import AsyncClient

from tests.test_communications import (
    auth_header,
    communications_url,
    get_token,
    risks_url,
    _comm_items,
    _complete,
    _evaluate_communications,
    _evaluate_risks,
    _put_answers,
    _reopen,
    _scaffold_inspection,
)
from tests.test_inspections import _findings
from tests.test_risks import _risk_items

VALID_USER = {
    "id": 900444555,
    "username": "integration_contractor",
    "first_name": "Integration",
    "last_name": "Contractor",
    "language_code": "pl",
}
OTHER_USER = {
    "id": 900666777,
    "username": "integration_other",
    "first_name": "Other",
    "last_name": "Contractor",
    "language_code": "pl",
}

# Canonical GYPSUM_BOARD finished-work scenario: exercises a BOOLEAN-driven
# finding (CRACK / BOARD_MOVEMENT), a NUMBER-driven finding (UNEVENNESS below
# the 3 mm risk threshold, JOINT_GAP below the 2 mm threshold), a MULTI_CHOICE
# finding (BLOW_HOLES), two Stage 7 risks from Boolean findings plus one LOW
# risk from the MULTI_CHOICE finding, and the Q2 quality expectation.
CANONICAL = {
    "cracks_present": {"value_bool": True},
    "board_movement": {"value_bool": True},
    "unevenness_mm": {"value_number": "1.500"},
    "present_defects": {"option_keys": ["BLOW_HOLES"]},
    "joint_gap_mm": {"value_number": "1.500"},
    "substrate_condition": {"option_key": "SOLID"},
    "moisture_high": {"value_bool": False},
    "adhesion_weak": {"value_bool": False},
}

# Cycle 1: drop board movement (resolves BOARD_MOVEMENT finding and the
# compounded BOARD_MOVEMENT_CRACK risk), raise unevenness past the 3 mm
# threshold (fires UNEVENNESS_PREP_INCREASED and covers the UNEVENNESS finding),
# and swap the MULTI_CHOICE defect from BLOW_HOLES to DELAMINATION.
CYCLE_1 = {
    "cracks_present": {"value_bool": True},
    "board_movement": {"value_bool": False},
    "unevenness_mm": {"value_number": "4.500"},
    "present_defects": {"option_keys": ["DELAMINATION"]},
    "joint_gap_mm": {"value_number": "1.500"},
    "substrate_condition": {"option_key": "SOLID"},
    "moisture_high": {"value_bool": False},
    "adhesion_weak": {"value_bool": False},
}

# Cycle 2: clear the crack (resolves CRACK / CRACK_RECURRENCE and its risk
# phrase) and switch the substrate condition to LOOSE (new LOOSE_SUBSTRATE
# finding + LOOSE_SUBSTRATE_REMOVAL risk and phrase).
CYCLE_2 = {
    "cracks_present": {"value_bool": False},
    "board_movement": {"value_bool": False},
    "unevenness_mm": {"value_number": "4.500"},
    "present_defects": {"option_keys": ["DELAMINATION"]},
    "joint_gap_mm": {"value_number": "1.500"},
    "substrate_condition": {"option_key": "LOOSE"},
    "moisture_high": {"value_bool": False},
    "adhesion_weak": {"value_bool": False},
}

PASS1_FINDINGS = {
    "CRACK",
    "BOARD_MOVEMENT",
    "UNEVENNESS",
    "BLOW_HOLES",
    "JOINT_GAP",
}
PASS1_RISKS = {"CRACK_RECURRENCE", "BOARD_MOVEMENT_CRACK", "BLOW_HOLES_FILLING"}
PASS1_COMMS = {
    "COMM_RISK_CRACK_RECURRENCE",
    "COMM_RISK_BOARD_MOVEMENT_CRACK",
    "COMM_RISK_BLOW_HOLES_FILLING",
    "COMM_FIND_JOINT_GAP",
    "COMM_FIND_UNEVENNESS",
    "COMM_QUALITY_GYPSUM_BOARD_Q2",
}

CYCLE1_RISKS = {"CRACK_RECURRENCE", "UNEVENNESS_PREP_INCREASED", "DELAMINATION_REPAIR"}
CYCLE1_COMMS = {
    "COMM_RISK_CRACK_RECURRENCE",
    "COMM_RISK_UNEVENNESS_PREP_INCREASED",
    "COMM_RISK_DELAMINATION_REPAIR",
    "COMM_FIND_JOINT_GAP",
    "COMM_QUALITY_GYPSUM_BOARD_Q2",
}

FINAL_RISKS = {
    "UNEVENNESS_PREP_INCREASED",
    "DELAMINATION_REPAIR",
    "LOOSE_SUBSTRATE_REMOVAL",
}
FINAL_COMMS = {
    "COMM_RISK_UNEVENNESS_PREP_INCREASED",
    "COMM_RISK_DELAMINATION_REPAIR",
    "COMM_RISK_LOOSE_SUBSTRATE_REMOVAL",
    "COMM_FIND_JOINT_GAP",
    "COMM_QUALITY_GYPSUM_BOARD_Q2",
}

FINAL_RESOLVED_COMMS = {
    "COMM_RISK_CRACK_RECURRENCE",
    "COMM_RISK_BOARD_MOVEMENT_CRACK",
    "COMM_RISK_BLOW_HOLES_FILLING",
    "COMM_FIND_UNEVENNESS",
}
FINAL_RESOLVED_RISKS = {
    "CRACK_RECURRENCE",
    "BOARD_MOVEMENT_CRACK",
    "BLOW_HOLES_FILLING",
}


async def _comm_detail(async_client, token, project, room, inspection, app_id):
    response = await async_client.get(
        f"{communications_url(project['id'], room['id'], inspection['id'])}/{app_id}",
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _comm_items_status(async_client, token, project, room, inspection, *, status):
    return await _comm_items(
        async_client, token, project, room, inspection, status=status
    )


class TestCanonicalChain:
    async def test_canonical_chain_findings_risks_communications(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client, substrate="GYPSUM_BOARD", quality_target="Q2"
        )
        await _put_answers(
            async_client, token, project, room, inspection, template, CANONICAL
        )
        await _complete(async_client, token, project, room, inspection)

        # Stage 6: exactly the materialized active findings.
        findings = await _findings(async_client, token, project, room, inspection)
        assert {f["finding_key"] for f in findings} == PASS1_FINDINGS
        assert all(f["is_active"] for f in findings)

        # Stage 8 BEFORE Stage 7: no risk-derived phrase may exist yet. The
        # finding-only BOARD_MOVEMENT phrase is present here precisely because no
        # Stage 7 risk covers it yet; once BOARD_MOVEMENT_CRACK materializes it
        # is suppressed (asserted below), proving the engine consumes risk rows.
        early = (await _evaluate_communications(
            async_client, token, project, room, inspection
        )).json()["items"]
        assert "RISK" not in {item["source_kind"] for item in early}
        assert {item["phrase_code"] for item in early} == {
            "COMM_FIND_BOARD_MOVEMENT",
            "COMM_FIND_JOINT_GAP",
            "COMM_FIND_UNEVENNESS",
            "COMM_QUALITY_GYPSUM_BOARD_Q2",
        }

        # Stage 7: deterministic risks from the materialized facts.
        risks = (await _evaluate_risks(
            async_client, token, project, room, inspection
        ))["items"]
        assert {r["risk_code"] for r in risks} == PASS1_RISKS
        assert all(r["is_active"] for r in risks)

        # Stage 8 after Stage 7: risk-derived phrases now appear alongside the
        # already-materialized finding-only and quality phrases.
        comms = (await _evaluate_communications(
            async_client, token, project, room, inspection
        )).json()["items"]
        assert {c["phrase_code"] for c in comms} == PASS1_COMMS
        assert len(comms) == len(PASS1_COMMS)


class TestLifecycleCycles:
    async def test_two_reopen_edit_recomplete_cycles_keep_layers_in_sync(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client, substrate="GYPSUM_BOARD", quality_target="Q2"
        )
        await _put_answers(
            async_client, token, project, room, inspection, template, CANONICAL
        )
        await _complete(async_client, token, project, room, inspection)
        await _evaluate_risks(async_client, token, project, room, inspection)
        pass1 = (await _evaluate_communications(
            async_client, token, project, room, inspection
        )).json()["items"]
        pass1_comm_by_code = {c["phrase_code"]: c for c in pass1}

        # ---- Cycle 1 -----------------------------------------------------
        await _reopen(async_client, token, project, room, inspection)
        await _put_answers(
            async_client, token, project, room, inspection, template, CYCLE_1
        )
        response = await _complete(async_client, token, project, room, inspection)
        assert response.status_code == 200, response.text
        await _evaluate_risks(async_client, token, project, room, inspection)
        cycle1 = (await _evaluate_communications(
            async_client, token, project, room, inspection
        )).json()["items"]
        cycle1_comm_by_code = {c["phrase_code"]: c for c in cycle1}
        assert set(cycle1_comm_by_code) == CYCLE1_COMMS
        assert len(cycle1) == len(set(cycle1_comm_by_code))

        # Same factual context (CRACK still present) reuses the application UUID.
        assert (
            cycle1_comm_by_code["COMM_RISK_CRACK_RECURRENCE"]["id"]
            == pass1_comm_by_code["COMM_RISK_CRACK_RECURRENCE"]["id"]
        )
        # Quality expectation is context-only: reuses its constant signature.
        assert (
            cycle1_comm_by_code["COMM_QUALITY_GYPSUM_BOARD_Q2"]["id"]
            == pass1_comm_by_code["COMM_QUALITY_GYPSUM_BOARD_Q2"]["id"]
        )

        # Findings: obsolete resolved, new active.
        findings = await _findings(async_client, token, project, room, inspection)
        assert {f["finding_key"] for f in findings if f["is_active"]} == {
            "CRACK",
            "UNEVENNESS",
            "DELAMINATION",
            "JOINT_GAP",
        }
        all_findings = await _findings(
            async_client, token, project, room, inspection, include_inactive=True
        )
        assert {f["finding_key"] for f in all_findings if not f["is_active"]} == {
            "BOARD_MOVEMENT",
            "BLOW_HOLES",
        }

        # Risk layer in sync.
        active_risks = await _risk_items(
            async_client, token, project, room, status="active"
        )
        assert {r["risk_code"] for r in active_risks} == CYCLE1_RISKS

        # ---- Cycle 2 -----------------------------------------------------
        await _reopen(async_client, token, project, room, inspection)
        await _put_answers(
            async_client, token, project, room, inspection, template, CYCLE_2
        )
        response = await _complete(async_client, token, project, room, inspection)
        assert response.status_code == 200, response.text
        await _evaluate_risks(async_client, token, project, room, inspection)
        final = (await _evaluate_communications(
            async_client, token, project, room, inspection
        )).json()["items"]
        final_comm_by_code = {c["phrase_code"]: c for c in final}
        assert set(final_comm_by_code) == FINAL_COMMS

        # Every surviving context keeps its original application UUID.
        for code in FINAL_COMMS & CYCLE1_COMMS:
            assert (
                final_comm_by_code[code]["id"] == cycle1_comm_by_code[code]["id"]
            )
        # The CRACK_RECURRENCE phrase resolved in cycle 2 but its historical row
        # keeps the original UUID from pass 1 (identity keyed on signature).
        resolved = await _comm_items_status(
            async_client, token, project, room, inspection, status="resolved"
        )
        resolved_by_code = {c["phrase_code"]: c for c in resolved}
        assert resolved_by_code["COMM_RISK_CRACK_RECURRENCE"]["id"] == (
            pass1_comm_by_code["COMM_RISK_CRACK_RECURRENCE"]["id"]
        )
        assert all(not c["is_active"] for c in resolved)
        assert all(c["resolved_at"] is not None for c in resolved)

        # Risk layer: obsolete resolved, new active.
        active_risks = await _risk_items(
            async_client, token, project, room, status="active"
        )
        assert {r["risk_code"] for r in active_risks} == FINAL_RISKS
        resolved_risks = await _risk_items(
            async_client, token, project, room, status="resolved"
        )
        assert {r["risk_code"] for r in resolved_risks} == FINAL_RESOLVED_RISKS
        assert all(not r["is_active"] for r in resolved_risks)

        # Final findings slice.
        findings = await _findings(async_client, token, project, room, inspection)
        assert {f["finding_key"] for f in findings if f["is_active"]} == {
            "UNEVENNESS",
            "DELAMINATION",
            "JOINT_GAP",
            "LOOSE_SUBSTRATE",
        }


class TestFiltersAndHistory:
    async def test_filters_active_resolved_all_across_layers(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client, substrate="GYPSUM_BOARD", quality_target="Q2"
        )
        for answers in (CANONICAL, CYCLE_1, CYCLE_2):
            if inspection["status"] != "DRAFT":
                _ = await _reopen(async_client, token, project, room, inspection)
            await _put_answers(
                async_client, token, project, room, inspection, template, answers
            )
            assert (await _complete(
                async_client, token, project, room, inspection
            )).status_code == 200
            await _evaluate_risks(async_client, token, project, room, inspection)
            await _evaluate_communications(
                async_client, token, project, room, inspection
            )
            inspection = (await async_client.get(
                f"/api/projects/{project['id']}/rooms/{room['id']}/"
                f"inspections/{inspection['id']}",
                headers=auth_header(token),
            )).json()

        active = await _comm_items_status(
            async_client, token, project, room, inspection, status="active"
        )
        assert {c["phrase_code"] for c in active} == FINAL_COMMS
        assert all(c["is_active"] for c in active)

        resolved = await _comm_items_status(
            async_client, token, project, room, inspection, status="resolved"
        )
        assert {c["phrase_code"] for c in resolved} == FINAL_RESOLVED_COMMS
        assert all(not c["is_active"] for c in resolved)

        everything = await _comm_items_status(
            async_client, token, project, room, inspection, status="all"
        )
        # Historical rows are never physically deleted: all == active + resolved.
        assert len(everything) == len(active) + len(resolved)
        assert {c["phrase_code"] for c in everything} == (
            {c["phrase_code"] for c in active} | {c["phrase_code"] for c in resolved}
        )

        active_risks = await _risk_items(
            async_client, token, project, room, status="active"
        )
        assert {r["risk_code"] for r in active_risks} == FINAL_RISKS
        resolved_risks = await _risk_items(
            async_client, token, project, room, status="resolved"
        )
        assert {r["risk_code"] for r in resolved_risks} == FINAL_RESOLVED_RISKS
        all_risks = await _risk_items(
            async_client, token, project, room, status="all"
        )
        assert len(all_risks) == len(active_risks) + len(resolved_risks)

        # Every resolver page reuses active cards, so no duplicated active card.
        assert len({c["id"] for c in active}) == len(active)

    async def test_traceability_detail_explains_every_source_kind(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client, substrate="GYPSUM_BOARD", quality_target="Q2"
        )
        await _put_answers(
            async_client, token, project, room, inspection, template, CYCLE_2
        )
        assert (await _complete(
            async_client, token, project, room, inspection
        )).status_code == 200
        await _evaluate_risks(async_client, token, project, room, inspection)
        comms = (await _evaluate_communications(
            async_client, token, project, room, inspection
        )).json()["items"]
        by_code = {c["phrase_code"]: c for c in comms}

        # RISK source: risk context + Stage 7 source-finding snapshots.
        detail = await _comm_detail(
            async_client, token, project, room, inspection,
            by_code["COMM_RISK_UNEVENNESS_PREP_INCREASED"]["id"],
        )
        source = detail["source"]
        assert source["kind"] == "RISK"
        assert source["risk_code"] == "UNEVENNESS_PREP_INCREASED"
        assert source["severity"] == "MEDIUM"
        assert source["risk_is_active"] is True
        assert len(source["source_findings"]) >= 1
        assert source["source_findings"][0]["finding_key_snapshot"] == "UNEVENNESS"
        assert source["source_findings"][0]["value_snapshot"] is not None

        # FINDING source: finding label/value snapshot.
        detail = await _comm_detail(
            async_client, token, project, room, inspection,
            by_code["COMM_FIND_JOINT_GAP"]["id"],
        )
        source = detail["source"]
        assert source["kind"] == "FINDING"
        assert source["finding_key"] == "JOINT_GAP"
        assert len(source["findings"]) == 1
        assert source["findings"][0]["value_snapshot"] is not None
        assert source["findings"][0]["is_active"] is True

        # QUALITY source: substrate + quality target.
        detail = await _comm_detail(
            async_client, token, project, room, inspection,
            by_code["COMM_QUALITY_GYPSUM_BOARD_Q2"]["id"],
        )
        source = detail["source"]
        assert source["kind"] == "QUALITY"
        assert source["substrate"] == "GYPSUM_BOARD"
        assert source["quality_level"] == "Q2"


class TestOwnershipAndAuth:
    async def test_unauthenticated_is_401_across_all_layers(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client, substrate="GYPSUM_BOARD"
        )
        await _put_answers(
            async_client, token, project, room, inspection, template, CANONICAL
        )
        await _complete(async_client, token, project, room, inspection)
        inspection_id = inspection["id"]

        for method, url in (
            (
                "GET",
                f"/api/projects/{project['id']}/rooms/{room['id']}/"
                f"inspections/{inspection_id}/findings",
            ),
            (
                "POST",
                f"{risks_url(project['id'], room['id'])}/evaluate",
            ),
            (
                "POST",
                f"{communications_url(project['id'], room['id'], inspection_id)}/evaluate",
            ),
            (
                "GET",
                communications_url(project["id"], room["id"], inspection_id),
            ),
        ):
            kwargs = {"headers": {}}
            if method == "POST" and "risks" in url:
                kwargs["json"] = {"inspection_id": str(inspection_id)}
            response = await async_client.request(method, url, **kwargs)
            assert response.status_code == 401, (method, url, response.text)

    async def test_foreign_owner_is_404_across_all_layers(
        self, async_client: AsyncClient
    ) -> None:
        token, project, room, inspection, template = await _scaffold_inspection(
            async_client, substrate="GYPSUM_BOARD", quality_target="Q2"
        )
        await _put_answers(
            async_client, token, project, room, inspection, template, CANONICAL
        )
        await _complete(async_client, token, project, room, inspection)
        await _evaluate_risks(async_client, token, project, room, inspection)
        await _evaluate_communications(async_client, token, project, room, inspection)
        app_id = (await _comm_items_status(
            async_client, token, project, room, inspection, status="active"
        ))[0]["id"]
        other_token = await get_token(async_client, OTHER_USER)

        inspection_id = inspection["id"]
        for method, url in (
            (
                "GET",
                f"/api/projects/{project['id']}/rooms/{room['id']}/"
                f"inspections/{inspection_id}/findings",
            ),
            ("GET", risks_url(project["id"], room["id"])),
            (
                "POST",
                f"{risks_url(project['id'], room['id'])}/evaluate",
            ),
            (
                "GET",
                communications_url(project["id"], room["id"], inspection_id),
            ),
            (
                "POST",
                f"{communications_url(project['id'], room['id'], inspection_id)}/evaluate",
            ),
            (
                "GET",
                f"{communications_url(project['id'], room['id'], inspection_id)}/{app_id}",
            ),
        ):
            kwargs: dict = {"headers": auth_header(other_token)}
            if method == "POST" and "risks" in url:
                kwargs["json"] = {"inspection_id": str(inspection_id)}
            response = await async_client.request(method, url, **kwargs)
            assert response.status_code == 404, (method, url, response.text)