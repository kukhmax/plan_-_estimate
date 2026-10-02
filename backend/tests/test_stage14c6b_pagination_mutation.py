"""Stage 14C.6B — pins the ACCEPTED v1 pagination consistency model
(contract §11d.5, F5): "Each page reflects current state. Pagination across
multiple requests is not snapshot-isolated." These tests document observed
behaviour; they are not defects."""

from datetime import UTC, datetime, timedelta

from tests import test_stage14c5_photos_api as c5
from tests.test_stage14c4_photos_api import path_for
from tests.test_stage14c5_followup import add_photo, ids

api, http = c5.api, c5.http
T = datetime(2026, 5, 1, tzinfo=UTC)


async def seed(a, n: int, position: int = 0) -> list[str]:
    return [str((await add_photo(a, position=position, uploaded_at=T + timedelta(minutes=i)))[1].id)
            for i in range(n)]


async def page(http, a, cursor=None, limit=2):
    params = {"limit": limit, **({"cursor": cursor} if cursor else {})}
    r = await http.get(path_for(a.project), params=params)
    return ids(r), r.json()["next_cursor"]


async def test_insert_after_the_cursor_appears_on_a_later_page(api, http):
    base = await seed(api, 4)
    first, cursor = await page(http, api)
    _, late = await add_photo(api, uploaded_at=T + timedelta(hours=1))  # sorts after everything
    rest = []
    while cursor:
        more, cursor = await page(http, api, cursor)
        rest += more
    assert first == base[:2] and rest == base[2:] + [str(late.id)]


async def test_insert_before_the_cursor_is_not_seen_by_later_pages(api, http):
    base = await seed(api, 4)
    first, cursor = await page(http, api)
    assert first == base[:2]
    _, early = await add_photo(api, uploaded_at=T - timedelta(hours=1))  # sorts before the cursor
    rest = []
    while cursor:
        more, cursor = await page(http, api, cursor)
        rest += more
    assert str(early.id) not in first + rest  # missed by this traversal (accepted)
    assert str(early.id) in ids(await http.get(path_for(api.project), params={"limit": 100}))  # fresh read sees it


async def test_moving_position_across_the_cursor_can_revisit_or_skip(api, http):
    base = await seed(api, 4, position=1)  # room on both sides of the cursor
    first, cursor = await page(http, api)
    assert first == base[:2]
    # revisit: an item already seen moves after the cursor
    r = await http.patch(f"/api/projects/{api.project}/photo-attachments/{first[0]}", json={"position": 9})
    assert r.status_code == 200
    # skip: an unseen item moves before the cursor
    r = await http.patch(f"/api/projects/{api.project}/photo-attachments/{base[2]}", json={"position": 0})
    assert r.status_code == 200
    rest = []
    while cursor:
        more, cursor = await page(http, api, cursor)
        rest += more
    traversal = first + rest
    assert traversal.count(first[0]) == 2  # revisited (moved after the cursor)
    assert base[2] not in traversal  # skipped (moved before the cursor)


async def test_archive_between_pages_removes_the_row_from_that_view(api, http):
    base = await seed(api, 4)
    first, cursor = await page(http, api)
    r = await http.post(f"/api/projects/{api.project}/photo-attachments/{base[2]}/archive")
    assert r.status_code == 200
    rest = []
    while cursor:
        more, cursor = await page(http, api, cursor)
        rest += more
    assert base[2] not in rest and rest == [base[3]]
    archive_view = ids(await http.get(path_for(api.project), params={"archived": "true"}))
    assert archive_view == [base[2]]
