"""Stage 17F — the guards of the knowledge base: what must never happen, however the content grows.

A draft entry is for the owner's eyes only (Q7): it never goes into a document for a client. The documents are built by
`domain/documents`, the contract and the protocols by their own catalogues; none of them may read the knowledge base. If one
ever must (a basis printed in a document), that is a new decision of the owner and this list changes with it, on purpose.
"""

import re
from pathlib import Path

from app.main import app

APP = Path(__file__).resolve().parent.parent / "app"
IMPORTS_KNOWLEDGE = re.compile(r"^\s*(?:from|import)\s+app\.(?:domain\.knowledge|schemas\.knowledge|api\.v1\.endpoints\.knowledge)\b", re.MULTILINE)

# the only modules that know the knowledge base: the application's start (it checks the files), its read-only API and the
# envelopes of that API
ALLOWED = {
    "main.py",
    "api/v1/endpoints/knowledge.py",
    "schemas/knowledge.py",
}


def test_only_the_start_and_the_read_only_api_know_the_knowledge_base():
    importers = {
        str(path.relative_to(APP))
        for path in APP.rglob("*.py")
        if "knowledge" not in path.parts and IMPORTS_KNOWLEDGE.search(path.read_text(encoding="utf-8"))
    }
    assert importers == ALLOWED


def test_every_route_of_the_knowledge_base_only_reads_and_is_behind_the_login():
    paths = {path: item for path, item in app.openapi()["paths"].items() if path.startswith("/api/knowledge")}
    assert len(paths) == 7  # meta, entries, entry, situations, situation, links, link index
    for path, item in paths.items():
        assert set(item) == {"get"}, path
        assert item["get"].get("security"), path  # the bearer token of the owner is required


async def test_the_real_catalogue_is_served_as_it_is_in_the_files(async_client):
    """The files that go to production, over HTTP: nothing monkeypatched."""
    from tests.test_clients import VALID_USER, auth_header, get_token

    headers = auth_header(await get_token(async_client, VALID_USER))
    meta = (await async_client.get("/api/knowledge/meta", headers=headers)).json()
    assert meta["entries"] == 24 and meta["sources"] == 3
    entries = (await async_client.get("/api/knowledge/entries", params={"limit": 200}, headers=headers)).json()
    assert entries["total"] == 24 and all(item["status"] == "DRAFT" for item in entries["items"])
    found = (await async_client.get("/api/knowledge/entries", params={"q": "rekoj"}, headers=headers)).json()
    assert {"KC.556", "KC.558", "KC.638"} <= {item["code"] for item in found["items"]}  # letters without marks, the start of a word
    card = (await async_client.get("/api/knowledge/entries/KC.640", headers=headers)).json()
    assert card["entry"]["summary_pl"] and card["source"]["url"].startswith("https://")
    index = (await async_client.get("/api/knowledge/links/index", headers=headers)).json()["items"]
    assert len(index) == 51 and all(row["entries"] for row in index)
