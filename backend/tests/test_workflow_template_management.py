"""Stage 13F.2 — template management backend hardening.

- D-F1: derived read-only `is_default` (canonical Stage 13D code set, never
  stored); defaults stay owner-editable; a default's custom display_name can
  be cleared so its localized name_key applies again; an owner-created
  template can never become nameless; duplication uses the existing create.
- D-F2: optimistic `expected_step_ids` precondition on step replacement
  (exact ordered match or 409, nothing changes); omitted = unchanged
  backwards-compatible behaviour.
"""
import json
from pathlib import Path

from httpx import AsyncClient

from app.domain.data.workflow_templates import (
    CANONICAL_STEP_NOTE_KEYS,
    DEFAULT_TEMPLATE_DESCRIPTIONS,
    DEFAULT_WORKFLOW_TEMPLATE_CODES,
    build_default_workflow_templates,
    canonical_description_key,
    canonical_step_note_key,
)
import uuid

from tests.test_planned_work_coefficient_assignments import _make_price_item, _wp
from tests.test_workflow_templates_api import OTHER_USER, T, _create, _history_count, _owner, _surface

S2 = "TECH_BETON_S2-01"


async def _all(client, headers) -> dict[str, dict]:
    resp = await client.get(T, headers=headers, params={"archived": "all"})
    assert resp.status_code == 200, resp.text
    return {i["code"]: i for i in resp.json()["items"]}


async def _get(client, headers, template_id) -> dict:
    resp = await client.get(f"{T}/{template_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _write(steps: list[dict]) -> list[dict]:
    return [
        {"price_item_id": s["price_item_id"], "is_optional": s["is_optional"],
         "note": s["note"], "wait_after_hours": s["wait_after_hours"]}
        for s in steps
    ]


class TestIsDefault:
    def test_code_set_is_the_canonical_13d_recipe_list(self):
        codes = [t.code for t in build_default_workflow_templates()]
        assert DEFAULT_WORKFLOW_TEMPLATE_CODES == frozenset(codes)
        assert len(DEFAULT_WORKFLOW_TEMPLATE_CODES) == len(codes) == 16

    async def test_seeded_true_custom_false_and_read_only(self, async_client: AsyncClient, db_session):
        headers, _, prime, _ = await _owner(async_client, db_session)
        custom = await _create(async_client, headers, steps=[{"price_item_id": str(prime.id)}])
        assert custom["is_default"] is False and custom["code"].startswith("CUSTOM_")
        items = await _all(async_client, headers)
        assert {c for c, i in items.items() if i["is_default"]} == DEFAULT_WORKFLOW_TEMPLATE_CODES
        assert (await _get(async_client, headers, items[S2]["id"]))["is_default"] is True
        # Not writable: unknown fields are rejected on create and update.
        bad = await async_client.post(T, headers=headers, json={"display_name": "X", "is_default": True})
        assert bad.status_code == 422
        patch = await async_client.patch(f"{T}/{custom['id']}", headers=headers, json={"is_default": True})
        assert patch.status_code == 422
        assert (await _get(async_client, headers, custom["id"]))["is_default"] is False

    async def test_default_stays_default_after_owner_edits_and_archive(self, async_client: AsyncClient, db_session):
        headers, *_ = await _owner(async_client, db_session)
        tid = (await _all(async_client, headers))[S2]["id"]
        await async_client.patch(f"{T}/{tid}", headers=headers, json={"display_name": "Mój beton"})
        await async_client.post(f"{T}/{tid}/archive", headers=headers)
        got = await _get(async_client, headers, tid)
        assert (got["is_default"], got["is_archived"], got["display_name"]) == (True, True, "Mój beton")

    async def test_duplicate_via_create_is_custom_and_keeps_steps(self, async_client: AsyncClient, db_session):
        """Duplication needs no new endpoint: the client re-creates the read
        template. NULL-price items and repeated PriceItems stay valid, independent steps."""
        headers, *_ = await _owner(async_client, db_session)
        source = (await _all(async_client, headers))["TECH_BETON_S3-01"]
        assert any(s["price_item"]["price"] is None for s in source["steps"])  # NULL price allowed
        steps = _write(source["steps"]) + _write(source["steps"][:1])  # repeat one PriceItem
        copy = await _create(
            async_client, headers, display_name="Kopia — Beton S3", description=source["description"],
            applies_to_substrates=source["applies_to_substrates"], applies_to_quality=source["applies_to_quality"],
            applies_to_surface_types=source["applies_to_surface_types"], steps=steps,
        )
        assert copy["is_default"] is False and copy["code"] != source["code"]
        assert [s["price_item_id"] for s in copy["steps"]] == [s["price_item_id"] for s in steps]
        assert len({s["id"] for s in copy["steps"]}) == len(steps)
        assert {s["id"] for s in copy["steps"]}.isdisjoint({s["id"] for s in source["steps"]})
        assert _write((await _get(async_client, headers, source["id"]))["steps"]) == _write(source["steps"])


class TestDisplayNameSemantics:
    async def test_omitted_leaves_name_unchanged(self, async_client: AsyncClient, db_session):
        headers, *_ = await _owner(async_client, db_session)
        custom = await _create(async_client, headers, display_name="Mój proces")
        resp = await async_client.patch(f"{T}/{custom['id']}", headers=headers, json={"description": "Opis"})
        assert resp.status_code == 200
        assert (resp.json()["display_name"], resp.json()["description"]) == ("Mój proces", "Opis")

    async def test_set_name_on_default_and_custom(self, async_client: AsyncClient, db_session):
        headers, *_ = await _owner(async_client, db_session)
        tid = (await _all(async_client, headers))[S2]["id"]
        resp = await async_client.patch(f"{T}/{tid}", headers=headers, json={"display_name": "Mój beton S2"})
        assert resp.status_code == 200
        assert (resp.json()["display_name"], resp.json()["name_key"]) == ("Mój beton S2", "workflow_templates.seed.tech_beton_s2")
        custom = await _create(async_client, headers, display_name="A")
        resp = await async_client.patch(f"{T}/{custom['id']}", headers=headers, json={"display_name": "B"})
        assert resp.json()["display_name"] == "B"

    async def test_clear_restores_localized_default_name_and_touches_nothing_else(self, async_client: AsyncClient, db_session):
        headers, *_ = await _owner(async_client, db_session)
        before = (await _all(async_client, headers))[S2]
        tid = before["id"]
        await async_client.patch(f"{T}/{tid}", headers=headers, json={"display_name": "Mój beton S2"})
        resp = await async_client.patch(f"{T}/{tid}", headers=headers, json={"display_name": None})
        assert resp.status_code == 200, resp.text
        after = resp.json()
        assert after["display_name"] is None and after["name_key"] == before["name_key"]
        for field in ("code", "description", "applies_to_substrates", "applies_to_quality",
                      "applies_to_surface_types", "position", "is_archived", "is_default"):
            assert after[field] == before[field], field
        assert [s["id"] for s in after["steps"]] == [s["id"] for s in before["steps"]]

    async def test_clearing_a_custom_name_is_rejected(self, async_client: AsyncClient, db_session):
        headers, *_ = await _owner(async_client, db_session)
        custom = await _create(async_client, headers, display_name="Mój proces")
        for value in (None, "   "):
            resp = await async_client.patch(f"{T}/{custom['id']}", headers=headers, json={"display_name": value})
            assert resp.status_code == 422, (value, resp.text)
        empty = await async_client.patch(f"{T}/{custom['id']}", headers=headers, json={"display_name": ""})
        assert empty.status_code == 422  # schema min_length
        assert (await _get(async_client, headers, custom["id"]))["display_name"] == "Mój proces"


class TestStepReplacementPrecondition:
    async def _two_step(self, client, db):
        headers, user, prime, skim = await _owner(client, db)
        tpl = await _create(client, headers, steps=[{"price_item_id": str(prime.id)}, {"price_item_id": str(skim.id)}])
        return headers, user, prime, skim, tpl

    async def _put(self, client, headers, tid, steps, expected=None):
        body = {"steps": steps}
        if expected is not None:
            body["expected_step_ids"] = expected
        return await client.put(f"{T}/{tid}/steps", headers=headers, json=body)

    async def test_exact_ordered_match_succeeds(self, async_client: AsyncClient, db_session):
        headers, _, prime, skim, tpl = await self._two_step(async_client, db_session)
        ids = [s["id"] for s in tpl["steps"]]
        resp = await self._put(async_client, headers, tpl["id"],
                               [{"price_item_id": str(skim.id), "wait_after_hours": 12}], expected=ids)
        assert resp.status_code == 200, resp.text
        assert [(s["price_item_id"], s["wait_after_hours"]) for s in resp.json()["steps"]] == [(str(skim.id), 12)]

    async def test_mismatches_are_409_and_change_nothing(self, async_client: AsyncClient, db_session):
        headers, _, prime, skim, tpl = await self._two_step(async_client, db_session)
        ids = [s["id"] for s in tpl["steps"]]
        new = [{"price_item_id": str(prime.id)}]
        for expected in (
            ids[:1],                          # a current id missing
            ids + [ids[0]],                   # extra id
            [ids[0], "00000000-0000-4000-8000-000000000000"],  # stale / unknown id
            list(reversed(ids)),              # same ids, different order
            [],                               # claims an empty template
        ):
            resp = await self._put(async_client, headers, tpl["id"], new, expected=expected)
            assert resp.status_code == 409, (expected, resp.text)
            assert "changed since" in resp.json()["detail"]
        assert (await _get(async_client, headers, tpl["id"]))["steps"] == tpl["steps"]

    async def test_stale_second_editor_loses_explicitly(self, async_client: AsyncClient, db_session):
        headers, _, prime, skim, tpl = await self._two_step(async_client, db_session)
        read_a = await _get(async_client, headers, tpl["id"])
        read_b = await _get(async_client, headers, tpl["id"])
        a = await self._put(async_client, headers, tpl["id"], [{"price_item_id": str(skim.id), "note": "A"}],
                            expected=[s["id"] for s in read_a["steps"]])
        assert a.status_code == 200
        b = await self._put(async_client, headers, tpl["id"], [{"price_item_id": str(prime.id), "note": "B"}],
                            expected=[s["id"] for s in read_b["steps"]])
        assert b.status_code == 409
        current = await _get(async_client, headers, tpl["id"])
        assert [s["note"] for s in current["steps"]] == ["A"]  # no silent last-write-wins
        # B reloads and retries with the fresh ids.
        retry = await self._put(async_client, headers, tpl["id"], [{"price_item_id": str(prime.id), "note": "B"}],
                                expected=[s["id"] for s in current["steps"]])
        assert retry.status_code == 200 and [s["note"] for s in retry.json()["steps"]] == ["B"]

    async def test_omitted_precondition_keeps_backwards_compatible_replace(self, async_client: AsyncClient, db_session):
        headers, _, prime, skim, tpl = await self._two_step(async_client, db_session)
        await self._put(async_client, headers, tpl["id"], [{"price_item_id": str(skim.id)}])
        resp = await self._put(async_client, headers, tpl["id"], [{"price_item_id": str(prime.id)}])  # no precondition
        assert resp.status_code == 200
        assert [s["price_item_id"] for s in resp.json()["steps"]] == [str(prime.id)]

    async def test_duplicate_price_item_steps_stay_independent(self, async_client: AsyncClient, db_session):
        headers, _, prime, skim, tpl = await self._two_step(async_client, db_session)
        steps = [{"price_item_id": str(prime.id), "note": "1"}, {"price_item_id": str(prime.id), "wait_after_hours": 24},
                 {"price_item_id": str(skim.id)}, {"price_item_id": str(prime.id), "is_optional": True}]
        resp = await self._put(async_client, headers, tpl["id"], steps, expected=[s["id"] for s in tpl["steps"]])
        assert resp.status_code == 200, resp.text
        got = resp.json()["steps"]
        assert [(s["price_item_id"], s["position"], s["note"], s["wait_after_hours"], s["is_optional"]) for s in got] == [
            (str(prime.id), 0, "1", None, False), (str(prime.id), 1, None, 24, False),
            (str(skim.id), 2, None, None, False), (str(prime.id), 3, None, None, True),
        ]
        assert len({s["id"] for s in got}) == 4
        # The precondition compares ids, so the next edit must name all four.
        stale = await self._put(async_client, headers, tpl["id"], steps[:1], expected=[s["id"] for s in got[:3]])
        assert stale.status_code == 409

    async def test_precondition_does_not_bypass_validation_or_ownership(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim, tpl = await self._two_step(async_client, db_session)
        ids = [s["id"] for s in tpl["steps"]]
        bad_wait = await self._put(async_client, headers, tpl["id"], [{"price_item_id": str(prime.id), "wait_after_hours": 0}], expected=ids)
        assert bad_wait.status_code == 422
        assert [s["id"] for s in (await _get(async_client, headers, tpl["id"]))["steps"]] == ids
        other_headers, *_ = await _owner(async_client, db_session, OTHER_USER)
        foreign = await self._put(async_client, other_headers, tpl["id"], [{"price_item_id": str(prime.id)}], expected=ids)
        assert foreign.status_code == 404


# ---------------------------------------------------------------------------
# Stage 13F.3 FIX.1 — canonical built-in description localization key
# ---------------------------------------------------------------------------


_LOCALES = Path(__file__).resolve().parents[2] / "frontend" / "src" / "locales"


class TestDescriptionKey:
    def test_every_default_has_a_key_and_one_text_per_key(self):
        assert set(DEFAULT_TEMPLATE_DESCRIPTIONS) == DEFAULT_WORKFLOW_TEMPLATE_CODES
        texts_by_key: dict[str, set[str]] = {}
        for text, key in DEFAULT_TEMPLATE_DESCRIPTIONS.values():
            assert key.startswith("workflow_templates.description.")
            texts_by_key.setdefault(key, set()).add(text)
        assert all(len(texts) == 1 for texts in texts_by_key.values())

    def test_frontend_pl_text_is_the_canonical_text_and_ru_is_complete(self):
        if not _LOCALES.exists():  # backend-only checkout
            return
        pl = json.loads((_LOCALES / "pl.json").read_text(encoding="utf-8"))["workflow_templates"]["description"]
        ru = json.loads((_LOCALES / "ru.json").read_text(encoding="utf-8"))["workflow_templates"]["description"]
        for text, key in DEFAULT_TEMPLATE_DESCRIPTIONS.values():
            leaf = key.rsplit(".", 1)[1]
            assert pl[leaf] == text  # PL UI shows exactly the stored canonical text
            assert ru[leaf] and ru[leaf] != text

    def test_only_exact_canonical_text_gets_a_key(self):
        text, key = DEFAULT_TEMPLATE_DESCRIPTIONS[S2]
        assert canonical_description_key(S2, text) == key
        assert canonical_description_key(S2, text + " ") is None
        assert canonical_description_key(S2, "Moja wersja") is None
        assert canonical_description_key(S2, None) is None
        assert canonical_description_key("CUSTOM_X", text) is None  # never for custom templates

    async def test_api_key_follows_untouched_vs_owner_edited(self, async_client: AsyncClient, db_session):
        headers, _, prime, _ = await _owner(async_client, db_session)
        items = await _all(async_client, headers)
        tid = items[S2]["id"]
        assert items[S2]["description_key"] == "workflow_templates.description.s2"
        assert all(i["description_key"] for c, i in items.items() if c in DEFAULT_WORKFLOW_TEMPLATE_CODES)
        edited = await async_client.patch(f"{T}/{tid}", headers=headers, json={"description": "Moja wersja"})
        assert (edited.json()["description"], edited.json()["description_key"]) == ("Moja wersja", None)
        cleared = await async_client.patch(f"{T}/{tid}", headers=headers, json={"description": None})
        assert (cleared.json()["description"], cleared.json()["description_key"]) == (None, None)
        canonical = DEFAULT_TEMPLATE_DESCRIPTIONS[S2][0]
        back = await async_client.patch(f"{T}/{tid}", headers=headers, json={"description": canonical})
        assert back.json()["description_key"] == "workflow_templates.description.s2"  # identical content
        custom = await _create(async_client, headers, description=canonical, steps=[{"price_item_id": str(prime.id)}])
        assert custom["description_key"] is None


# ---------------------------------------------------------------------------
# Stage 13F.3 FIX.2 — canonical built-in step note localization key
# ---------------------------------------------------------------------------


class TestStepNoteKey:
    def test_every_canonical_note_has_its_own_key(self):
        notes = {s.note for t in build_default_workflow_templates() for s in t.steps if s.note}
        assert set(CANONICAL_STEP_NOTE_KEYS) == notes
        assert len(set(CANONICAL_STEP_NOTE_KEYS.values())) == len(notes)  # distinct texts -> distinct keys
        assert all(n == n.strip() for n in notes)  # survives the service's strip on re-save

    def test_frontend_pl_text_is_canonical_and_ru_complete(self):
        if not _LOCALES.exists():  # backend-only checkout
            return
        pl = json.loads((_LOCALES / "pl.json").read_text(encoding="utf-8"))["workflow_templates"]["step_note"]
        ru = json.loads((_LOCALES / "ru.json").read_text(encoding="utf-8"))["workflow_templates"]["step_note"]
        assert set(pl) == set(ru) == {k.rsplit(".", 1)[1] for k in CANONICAL_STEP_NOTE_KEYS.values()}
        for text, key in CANONICAL_STEP_NOTE_KEYS.items():
            leaf = key.rsplit(".", 1)[1]
            assert pl[leaf] == text
            assert ru[leaf] and ru[leaf] != text

    def test_key_only_for_this_recipes_exact_canonical_notes(self):
        s2 = next(t for t in build_default_workflow_templates() if t.code == S2)
        s4 = next(t for t in build_default_workflow_templates() if t.code == "TECH_BETON_S4-01")
        note = next(st.note for st in s2.steps if st.note)
        assert canonical_step_note_key(S2, note) == CANONICAL_STEP_NOTE_KEYS[note]
        assert canonical_step_note_key(S2, note + " ") is None
        assert canonical_step_note_key(S2, "Moja notatka") is None
        assert canonical_step_note_key(S2, None) is None
        assert canonical_step_note_key("CUSTOM_X", note) is None
        s4_only = next(st.note for st in s4.steps if st.note and st.note not in {x.note for x in s2.steps})
        assert canonical_step_note_key(S2, s4_only) is None  # canonical, but not part of this recipe

    async def test_api_per_step_keys_edit_restore_custom_and_duplicates(self, async_client: AsyncClient, db_session):
        headers, _, prime, _ = await _owner(async_client, db_session)
        tpl = (await _all(async_client, headers))[S2]
        noted = [st for st in tpl["steps"] if st["note"]]
        assert noted and all(st["note_key"] == CANONICAL_STEP_NOTE_KEYS[st["note"]] for st in noted)
        assert all(st["note_key"] is None for st in tpl["steps"] if not st["note"])

        steps = _write(tpl["steps"])
        canonical = steps[0]["note"]
        steps[0]["note"] = "Notatka właściciela"
        steps.append({**_write(tpl["steps"])[0]})           # same PriceItem + canonical note, again
        steps.append({**_write(tpl["steps"])[0], "note": None})
        edited = await async_client.put(f"{T}/{tpl['id']}/steps", headers=headers, json={
            "steps": steps, "expected_step_ids": [st["id"] for st in tpl["steps"]]})
        assert edited.status_code == 200, edited.text
        got = edited.json()["steps"]
        assert (got[0]["note"], got[0]["note_key"]) == ("Notatka właściciela", None)
        assert got[-2]["note_key"] == CANONICAL_STEP_NOTE_KEYS[canonical]   # independent occurrence
        assert got[-1]["note_key"] is None
        assert [s["note_key"] for s in got[1:-2]] == [s["note_key"] for s in tpl["steps"][1:]]

        steps[0]["note"] = canonical
        restored = await async_client.put(f"{T}/{tpl['id']}/steps", headers=headers, json={
            "steps": steps, "expected_step_ids": [st["id"] for st in got]})
        assert restored.json()["steps"][0]["note_key"] == CANONICAL_STEP_NOTE_KEYS[canonical]

        custom = await _create(async_client, headers, steps=[{"price_item_id": str(prime.id), "note": canonical}])
        assert custom["steps"][0]["note_key"] is None


# ---------------------------------------------------------------------------
# Stage 13F.3 FIX.3 — real contract: seeded TECH_BETON_S4-01 through the API
# ---------------------------------------------------------------------------

_REAL_FIXTURE = _LOCALES.parent / "__fixtures__" / "workflowTemplate.TECH_BETON_S4-01.json"


class TestRealContractFixture:
    async def test_seeded_s4_list_and_detail_json_carry_the_localization_keys(self, async_client: AsyncClient, db_session):
        headers, *_ = await _owner(async_client, db_session)
        listed = (await _all(async_client, headers))["TECH_BETON_S4-01"]
        detail = await _get(async_client, headers, listed["id"])
        for payload in (listed, detail):  # the key survives list AND detail serialization
            assert payload["description_key"] == "workflow_templates.description.s4"
            assert [s["note_key"] for s in payload["steps"]] == [
                CANONICAL_STEP_NOTE_KEYS[s["note"]] for s in payload["steps"]
            ]
            assert all(s["note_key"] for s in payload["steps"])
        if not _REAL_FIXTURE.exists():  # backend-only checkout
            return
        captured = json.loads(_REAL_FIXTURE.read_text(encoding="utf-8"))
        assert captured["description_key"] == detail["description_key"]
        assert captured["description"] == detail["description"]
        assert [(s["note"], s["note_key"]) for s in captured["steps"]] == [
            (s["note"], s["note_key"]) for s in detail["steps"]
        ]


# ---------------------------------------------------------------------------
# Stage 13F.5 — step-editor contract (PUT steps as the editor uses it)
# ---------------------------------------------------------------------------


async def _put_steps(client, headers, tpl: dict, steps: list[dict]):
    return await client.put(f"{T}/{tpl['id']}/steps", headers=headers, json={
        "steps": steps, "expected_step_ids": [s["id"] for s in tpl["steps"]]})


class TestStepEditorContract:
    async def test_editor_save_reorder_add_remove_duplicates_optional_note_wait(self, async_client: AsyncClient, db_session):
        headers, _, prime, skim = await _owner(async_client, db_session)
        tpl = await _create(async_client, headers, steps=[
            {"price_item_id": str(prime.id), "note": "A"},
            {"price_item_id": str(skim.id), "wait_after_hours": 24},
            {"price_item_id": str(prime.id), "is_optional": True},
        ])
        # draft: drop step 0, move old step 2 first, add skim twice, edit note/wait/optional
        draft = [
            {"price_item_id": str(prime.id), "is_optional": False, "note": "  Nowa notatka  ", "wait_after_hours": 48},
            {"price_item_id": str(skim.id), "is_optional": True, "note": None, "wait_after_hours": None},
            {"price_item_id": str(skim.id), "is_optional": False, "note": "", "wait_after_hours": 1},
            {"price_item_id": str(skim.id), "is_optional": False, "note": None, "wait_after_hours": None},
        ]
        resp = await _put_steps(async_client, headers, tpl, draft)
        assert resp.status_code == 200, resp.text
        got = resp.json()["steps"]
        assert [(s["price_item_id"], s["position"], s["is_optional"], s["note"], s["wait_after_hours"]) for s in got] == [
            (str(prime.id), 0, False, "Nowa notatka", 48),   # note trimmed
            (str(skim.id), 1, True, None, None),
            (str(skim.id), 2, False, None, 1),                # blank note -> null
            (str(skim.id), 3, False, None, None),
        ]
        assert len({s["id"] for s in got}) == 4
        assert not {s["id"] for s in got} & {s["id"] for s in tpl["steps"]}  # rows recreated: new step ids
        assert (await _get(async_client, headers, tpl["id"]))["steps"] == got

    async def test_null_price_item_and_empty_list_are_valid(self, async_client: AsyncClient, db_session):
        headers, user, prime, _ = await _owner(async_client, db_session)
        unpriced = await _make_price_item(db_session, user.id, price=None)
        tpl = await _create(async_client, headers, steps=[{"price_item_id": str(prime.id)}])
        resp = await _put_steps(async_client, headers, tpl, [{"price_item_id": str(unpriced.id)}])
        assert resp.status_code == 200, resp.text
        assert resp.json()["steps"][0]["price_item"]["price"] is None
        empty = await _put_steps(async_client, headers, resp.json(), [])
        assert empty.status_code == 200 and empty.json()["steps"] == []

    async def test_archived_item_kept_on_reorder_but_never_added_again(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim = await _owner(async_client, db_session)
        tpl = await _create(async_client, headers, steps=[
            {"price_item_id": str(prime.id)}, {"price_item_id": str(skim.id)}])
        skim.is_archived = True
        await db_session.commit()
        moved = await _put_steps(async_client, headers, tpl, [
            {"price_item_id": str(skim.id)}, {"price_item_id": str(prime.id)}])
        assert moved.status_code == 200, moved.text
        assert [s["price_item"]["is_archived"] for s in moved.json()["steps"]] == [True, False]
        extra = await _put_steps(async_client, headers, moved.json(), [
            {"price_item_id": str(skim.id)}, {"price_item_id": str(skim.id)}, {"price_item_id": str(prime.id)}])
        assert extra.status_code == 422 and "Archived price item" in extra.json()["detail"]
        assert (await _get(async_client, headers, tpl["id"]))["steps"] == moved.json()["steps"]

    async def test_invalid_note_wait_or_item_rejected_without_mutation(self, async_client: AsyncClient, db_session):
        headers, _, prime, _ = await _owner(async_client, db_session)
        tpl = await _create(async_client, headers, steps=[{"price_item_id": str(prime.id)}])
        for bad, status in (
            ({"price_item_id": str(prime.id), "wait_after_hours": 0}, 422),
            ({"price_item_id": str(prime.id), "wait_after_hours": 1.5}, 422),
            ({"price_item_id": str(prime.id), "note": "x" * 4001}, 422),
            ({"price_item_id": str(uuid.uuid4())}, 404),
        ):
            resp = await _put_steps(async_client, headers, tpl, [bad])
            assert resp.status_code == status, (bad, resp.text)
        assert (await _get(async_client, headers, tpl["id"]))["steps"] == tpl["steps"]

    async def test_step_edit_never_touches_applied_work_plan_or_history(self, async_client: AsyncClient, db_session):
        headers, user, prime, skim = await _owner(async_client, db_session)
        tpl = await _create(async_client, headers, steps=[
            {"price_item_id": str(prime.id), "wait_after_hours": 24}, {"price_item_id": str(skim.id)}])
        project, room, surface = await _surface(db_session, user.id)
        url = _wp(project.id, room.id, surface.id)
        put = await async_client.put(url, headers=headers, json={"substrate": "CONCRETE", "quality_target": "S2", "planned_works": []})
        assert put.status_code == 200, put.text
        applied = await async_client.post(f"{url}/apply-template", headers=headers, json={
            "application_id": str(uuid.uuid4()), "template_id": tpl["id"], "mode": "APPEND",
            "selected_optional_step_ids": [], "expected_step_ids": [s["id"] for s in tpl["steps"]]})
        assert applied.status_code == 200, applied.text
        plan_before = (await async_client.get(url, headers=headers)).json()
        history_before = await _history_count(db_session)

        edited = await _put_steps(async_client, headers, tpl, [{"price_item_id": str(skim.id), "note": "zmiana"}])
        assert edited.status_code == 200
        assert (await async_client.get(url, headers=headers)).json() == plan_before  # occurrences, keys, waits unchanged
        assert await _history_count(db_session) == history_before
