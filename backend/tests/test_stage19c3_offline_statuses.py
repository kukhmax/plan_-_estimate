"""Stage 19C.3 -- what the phone sends after a stretch without a signal: an inspection started under its own id (safely repeatable)
and a work status carrying the moment of the tap (`recorded_at`), believed only when plausible."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.domain.rules.work_execution_rules import RECORDED_AT_FUTURE_SKEW, RECORDED_AT_MAX_AGE, resolve_moment
from tests.test_inspections import (
    auth_header,
    inspections_url,
    template_by_substrate,
    _scaffold,
    _scaffold_project_room,
)
from tests.test_stage13h_execution_api import _ctx, _dt, _patch, _url, _works

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


# --- the rule: which moment is recorded ----------------------------------------------------------------------------------------------

class TestResolveMoment:
    def test_nothing_sent_the_server_time_is_used(self) -> None:
        assert resolve_moment(None, NOW, None) == NOW

    def test_a_plausible_moment_from_the_phone_is_used(self) -> None:
        moment = NOW - timedelta(hours=4)
        assert resolve_moment(moment, NOW, None) == moment

    def test_a_moment_in_another_time_zone_is_converted_to_utc(self) -> None:
        local = datetime(2026, 10, 16, 12, 30, tzinfo=timezone(timedelta(hours=2)))  # 10:30 UTC
        assert resolve_moment(local, NOW, None) == datetime(2026, 10, 16, 10, 30, tzinfo=timezone.utc)

    def test_without_a_time_zone_it_is_not_believed(self) -> None:
        assert resolve_moment(datetime(2026, 10, 16, 8, 0), NOW, None) == NOW

    def test_the_future_is_not_believed_but_a_little_clock_skew_is_clamped_to_now(self) -> None:
        assert resolve_moment(NOW + timedelta(hours=1), NOW, None) == NOW
        assert resolve_moment(NOW + RECORDED_AT_FUTURE_SKEW, NOW, None) == NOW  # within the skew: clamped, not trusted beyond now
        assert resolve_moment(NOW + RECORDED_AT_FUTURE_SKEW + timedelta(seconds=1), NOW, None) == NOW

    def test_older_than_two_weeks_is_not_believed(self) -> None:
        assert resolve_moment(NOW - RECORDED_AT_MAX_AGE, NOW, None) == NOW - RECORDED_AT_MAX_AGE
        assert resolve_moment(NOW - RECORDED_AT_MAX_AGE - timedelta(seconds=1), NOW, None) == NOW

    def test_before_what_is_already_recorded_for_the_work_is_not_believed(self) -> None:
        recorded = NOW - timedelta(hours=3)
        assert resolve_moment(NOW - timedelta(hours=4), NOW, recorded) == NOW
        assert resolve_moment(NOW - timedelta(hours=2), NOW, recorded) == NOW - timedelta(hours=2)

    def test_a_stored_time_without_a_zone_is_read_as_utc(self) -> None:
        recorded = datetime(2026, 10, 16, 9, 0)  # SQLite hands back naive datetimes
        assert resolve_moment(NOW - timedelta(hours=1), NOW, recorded) == NOW - timedelta(hours=1)
        assert resolve_moment(NOW - timedelta(hours=5), NOW, recorded) == NOW


# --- the API -------------------------------------------------------------------------------------------------------------------------

def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


async def _transition(client, c, key, status, expected, recorded_at=None):
    body = {"status": status, "expected_status": expected}
    if recorded_at is not None:
        body["recorded_at"] = _iso(recorded_at)
    return await client.patch(_url(c, key), headers=c.headers, json=body)


class TestRecordedAt:
    async def test_the_moment_of_the_tap_is_recorded_not_the_moment_of_sending(self, async_client: AsyncClient, db_session) -> None:
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        tapped = datetime.now(timezone.utc) - timedelta(hours=5)

        response = await _transition(async_client, c, key, "IN_PROGRESS", "NOT_STARTED", tapped)

        assert response.status_code == 200, response.text
        assert abs(_dt(response.json()["started_at"]) - tapped) < timedelta(seconds=1)

    async def test_finishing_without_a_signal_counts_the_break_from_the_real_moment(self, async_client: AsyncClient, db_session) -> None:
        c = await _ctx(async_client, db_session)  # the first work has a 6 h break
        key = (await _works(async_client, c))[0]["occurrence_key"]
        began = datetime.now(timezone.utc) - timedelta(hours=9)
        finished = datetime.now(timezone.utc) - timedelta(hours=8)
        assert (await _transition(async_client, c, key, "IN_PROGRESS", "NOT_STARTED", began)).status_code == 200

        done = (await _transition(async_client, c, key, "COMPLETED", "IN_PROGRESS", finished)).json()

        assert abs(_dt(done["completed_at"]) - finished) < timedelta(seconds=1)
        assert _dt(done["ready_after"]) - _dt(done["completed_at"]) == timedelta(hours=6)
        assert abs(_dt(done["started_at"]) - began) < timedelta(seconds=1)  # the start is kept

    async def test_not_started_straight_to_completed_records_the_one_moment_for_both(self, async_client: AsyncClient, db_session) -> None:
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        tapped = datetime.now(timezone.utc) - timedelta(hours=2)

        done = (await _transition(async_client, c, key, "COMPLETED", "NOT_STARTED", tapped)).json()

        assert abs(_dt(done["started_at"]) - tapped) < timedelta(seconds=1)
        assert done["started_at"] == done["completed_at"]

    @pytest.mark.parametrize("offset", [timedelta(hours=1), timedelta(days=30)])
    async def test_an_implausible_moment_is_replaced_by_the_server_time(self, async_client: AsyncClient, db_session, offset) -> None:
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        now = datetime.now(timezone.utc)
        sent = now + offset if offset < timedelta(days=2) else now - offset  # one in the future, one far in the past

        response = await _transition(async_client, c, key, "IN_PROGRESS", "NOT_STARTED", sent)

        assert response.status_code == 200
        assert abs(_dt(response.json()["started_at"]) - now) < timedelta(seconds=30)

    async def test_a_moment_before_the_start_does_not_move_the_finish_before_it(self, async_client: AsyncClient, db_session) -> None:
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        began = datetime.now(timezone.utc) - timedelta(hours=1)
        await _transition(async_client, c, key, "IN_PROGRESS", "NOT_STARTED", began)

        done = (await _transition(async_client, c, key, "COMPLETED", "IN_PROGRESS", began - timedelta(hours=3))).json()

        assert _dt(done["completed_at"]) >= began  # a clock that is wrong on the phone cannot finish a work before it began

    async def test_the_same_status_sent_again_changes_nothing(self, async_client: AsyncClient, db_session) -> None:
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        tapped = datetime.now(timezone.utc) - timedelta(hours=5)
        first = (await _transition(async_client, c, key, "IN_PROGRESS", "NOT_STARTED", tapped)).json()

        again = await _transition(async_client, c, key, "IN_PROGRESS", "NOT_STARTED", datetime.now(timezone.utc) - timedelta(hours=1))

        assert again.status_code == 200  # the answer of the first one was lost and the phone sent it again
        assert _dt(again.json()["started_at"]) == _dt(first["started_at"])

    async def test_a_status_changed_elsewhere_is_still_a_conflict(self, async_client: AsyncClient, db_session) -> None:
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        await _patch(async_client, c, key, "IN_PROGRESS", "NOT_STARTED")

        late = await _transition(async_client, c, key, "COMPLETED", "NOT_STARTED", datetime.now(timezone.utc) - timedelta(hours=1))

        assert late.status_code == 409 and late.json()["detail"]["code"] == "WORK_EXECUTION_CONFLICT"

    async def test_the_timestamps_themselves_still_cannot_be_sent(self, async_client: AsyncClient, db_session) -> None:
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        response = await async_client.patch(
            _url(c, key), headers=c.headers,
            json={"status": "IN_PROGRESS", "expected_status": "NOT_STARTED", "started_at": "2020-01-01T00:00:00Z"},
        )
        assert response.status_code == 422

    async def test_a_moment_that_is_not_a_time_is_refused(self, async_client: AsyncClient, db_session) -> None:
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        response = await async_client.patch(
            _url(c, key), headers=c.headers,
            json={"status": "IN_PROGRESS", "expected_status": "NOT_STARTED", "recorded_at": "yesterday"},
        )
        assert response.status_code == 422


# --- starting an inspection under the id of the phone --------------------------------------------------------------------------------

def _body(template: dict, **over) -> dict:
    return {"template_id": template["id"], "substrate": "CONCRETE", "plane": "CEILING", **over}


class TestInspectionClientId:
    async def test_an_inspection_is_started_under_the_id_of_the_phone(self, async_client: AsyncClient) -> None:
        token, project, room = await _scaffold(async_client)
        template = await template_by_substrate(async_client, token, "CONCRETE")
        inspection_id = str(uuid.uuid4())

        response = await async_client.post(inspections_url(project["id"], room["id"]), json=_body(template, id=inspection_id), headers=auth_header(token))

        assert response.status_code == 201, response.text
        assert response.json()["id"] == inspection_id

    async def test_sending_it_again_gives_back_the_same_inspection_not_a_second(self, async_client: AsyncClient) -> None:
        token, project, room = await _scaffold(async_client)
        template = await template_by_substrate(async_client, token, "CONCRETE")
        inspection_id = str(uuid.uuid4())
        url = inspections_url(project["id"], room["id"])

        first = await async_client.post(url, json=_body(template, id=inspection_id), headers=auth_header(token))
        again = await async_client.post(url, json=_body(template, id=inspection_id), headers=auth_header(token))

        assert first.status_code == 201 and again.status_code == 201
        assert again.json()["id"] == first.json()["id"]
        listed = await async_client.get(url, headers=auth_header(token))
        assert listed.json()["total"] == 1

    async def test_the_id_taken_by_other_content_is_a_conflict(self, async_client: AsyncClient) -> None:
        token, project, room = await _scaffold(async_client)
        template = await template_by_substrate(async_client, token, "CONCRETE")
        inspection_id = str(uuid.uuid4())
        url = inspections_url(project["id"], room["id"])
        await async_client.post(url, json=_body(template, id=inspection_id), headers=auth_header(token))

        other = await async_client.post(url, json=_body(template, id=inspection_id, plane="FLOOR"), headers=auth_header(token))

        assert other.status_code == 409
        assert other.json()["detail"]["code"] == "CLIENT_ID_CONFLICT"

    async def test_the_id_taken_in_another_room_is_a_conflict(self, async_client: AsyncClient) -> None:
        token, project, room = await _scaffold(async_client)
        second_room = (await async_client.post(
            f"/api/projects/{project['id']}/rooms", json={"name": "Kuchnia", "length": "3.000", "width": "3.000", "height": "2.600"}, headers=auth_header(token),
        )).json()
        template = await template_by_substrate(async_client, token, "CONCRETE")
        inspection_id = str(uuid.uuid4())
        await async_client.post(inspections_url(project["id"], room["id"]), json=_body(template, id=inspection_id), headers=auth_header(token))

        other = await async_client.post(inspections_url(project["id"], second_room["id"]), json=_body(template, id=inspection_id), headers=auth_header(token))

        assert other.status_code == 409 and other.json()["detail"]["code"] == "CLIENT_ID_CONFLICT"

    @pytest.mark.parametrize("bad", ["not-a-uuid", "00000000-0000-0000-0000-000000000000", str(uuid.uuid1())])
    async def test_an_id_that_is_not_a_random_uuid_is_refused(self, async_client: AsyncClient, bad: str) -> None:
        token, project, room = await _scaffold(async_client)
        template = await template_by_substrate(async_client, token, "CONCRETE")
        response = await async_client.post(inspections_url(project["id"], room["id"]), json=_body(template, id=bad), headers=auth_header(token))
        assert response.status_code == 422

    async def test_a_refused_request_leaves_its_id_free(self, async_client: AsyncClient) -> None:
        token, project, room = await _scaffold(async_client)
        template = await template_by_substrate(async_client, token, "CONCRETE")
        inspection_id = str(uuid.uuid4())
        url = inspections_url(project["id"], room["id"])

        refused = await async_client.post(url, json=_body(template, id=inspection_id, substrate="GYPSUM_PLASTER"), headers=auth_header(token))
        assert refused.status_code == 422  # the template serves another substrate

        retried = await async_client.post(url, json=_body(template, id=inspection_id), headers=auth_header(token))
        assert retried.status_code == 201 and retried.json()["id"] == inspection_id

    async def test_without_an_id_the_server_still_chooses_one(self, async_client: AsyncClient) -> None:
        token, project, room = await _scaffold(async_client)
        template = await template_by_substrate(async_client, token, "CONCRETE")
        response = await async_client.post(inspections_url(project["id"], room["id"]), json=_body(template), headers=auth_header(token))
        assert response.status_code == 201 and uuid.UUID(response.json()["id"]).version == 4
