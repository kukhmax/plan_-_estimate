"""The knowledge base (Stage 17B), read only and the same for every owner: sources, entries, search, situations, and the
entries the application links to a risk, a clause, a phrase or a document. Nothing here is written by a request."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user
from app.domain.contracts.clauses import load_clause_catalog
from app.domain.knowledge.catalog import (
    Entry,
    KnowledgeCatalog,
    KnowledgeCatalogError,
    Situation,
    load_knowledge_catalog,
)
from app.domain.knowledge.search import Filters, search
from app.models.user import User
from app.schemas.knowledge import (
    KnowledgeEntryList,
    KnowledgeEntryListItem,
    KnowledgeEntryRead,
    KnowledgeLinkIndex,
    KnowledgeLinkRead,
    KnowledgeMetaRead,
    KnowledgePlaceRead,
    KnowledgeSituationList,
    KnowledgeSituationListItem,
)

router = APIRouter(prefix="/knowledge")

SourceKind = Literal["STATUTE", "NORM", "ITB", "OTHER"]
Status = Literal["DRAFT", "APPROVED"]
Target = Literal["RISK", "CLAUSE", "PHRASE", "DOCUMENT"]


def _error(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"code": code, "message": message})


def _catalog() -> KnowledgeCatalog:
    try:
        return load_knowledge_catalog()
    except KnowledgeCatalogError as exc:
        raise _error("KNOWLEDGE_UNAVAILABLE", "The knowledge base is not available", status.HTTP_500_INTERNAL_SERVER_ERROR) from exc


def _item(catalog: KnowledgeCatalog, entry: Entry) -> KnowledgeEntryListItem:
    source = catalog.source(entry.source)
    assert source is not None  # checked when the catalogue was read
    return KnowledgeEntryListItem(
        code=entry.code, kind=source.kind, source=source.code, source_designation=source.designation, locator=entry.locator,
        title_pl=entry.title_pl, title_ru=entry.title_ru, status=entry.status, tags=list(entry.tags),
        substrates=list(entry.substrates), qualities=list(entry.qualities),
    )


def _place(target_kind: Target, target: str) -> KnowledgePlaceRead:
    """A clause is shown as "§ 10 ust. 5 — <title of the section>", in the numbering of the printed contract."""
    if target_kind != "CLAUSE":
        return KnowledgePlaceRead(target_kind=target_kind, target=target)
    key, _, number = target.rpartition(".")
    for index, section in enumerate(load_clause_catalog().sections, start=1):
        if section.key == key:
            return KnowledgePlaceRead(
                target_kind=target_kind, target=target, section_number=index, clause_number=int(number), section_title_pl=section.title_pl,
            )
    return KnowledgePlaceRead(target_kind=target_kind, target=target)


@router.get("/meta", response_model=KnowledgeMetaRead, summary="Version, date and disclaimer of the knowledge base")
async def read_meta(current_user: User = Depends(get_current_user)) -> KnowledgeMetaRead:
    catalog = _catalog()
    meta = catalog.meta
    return KnowledgeMetaRead(
        version=meta.version, updated_on=meta.updated_on, disclaimer_pl=meta.disclaimer_pl, disclaimer_ru=meta.disclaimer_ru,
        disclaimer_status=meta.disclaimer_status, sources=len(catalog.sources), entries=len(catalog.entries),
        situations=len(catalog.situations),
    )


@router.get("/entries", response_model=KnowledgeEntryList, summary="Entries: the list of titles, a search, filters")
async def list_entries(
    q: str = Query("", max_length=100),
    kind: SourceKind | None = None,
    source: str | None = Query(None, max_length=41),
    tag: str | None = Query(None, max_length=31),
    work: str | None = Query(None, max_length=40),
    substrate: str | None = Query(None, max_length=40),
    quality: str | None = Query(None, max_length=4),
    entry_status: Status | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
) -> KnowledgeEntryList:
    catalog = _catalog()
    found = search(catalog, q, Filters(kind=kind, source=source, tag=tag, work=work, substrate=substrate, quality=quality, status=entry_status))
    return KnowledgeEntryList(items=[_item(catalog, entry) for entry in found[offset:offset + limit]], total=len(found))


@router.get("/entries/{code}", response_model=KnowledgeEntryRead, summary="One entry with its source and where it is linked from")
async def read_entry(code: str, current_user: User = Depends(get_current_user)) -> KnowledgeEntryRead:
    catalog = _catalog()
    entry = catalog.entry(code)
    if entry is None:
        raise _error("KNOWLEDGE_ENTRY_NOT_FOUND", "No such entry", status.HTTP_404_NOT_FOUND)
    source = catalog.source(entry.source)
    assert source is not None
    links = catalog.links_to(entry.code)
    return KnowledgeEntryRead(entry=entry, source=source, linked_from=links, places=[_place(link.target_kind, link.target) for link in links])


@router.get("/situations", response_model=KnowledgeSituationList, summary="The situations to choose from")
async def list_situations(current_user: User = Depends(get_current_user)) -> KnowledgeSituationList:
    catalog = _catalog()
    return KnowledgeSituationList(items=[
        KnowledgeSituationListItem(code=s.code, title_pl=s.title_pl, title_ru=s.title_ru, status=s.status) for s in catalog.situations
    ])


@router.get("/situations/{code}", response_model=Situation, summary="One situation: its questions, answers and outcomes")
async def read_situation(code: str, current_user: User = Depends(get_current_user)) -> Situation:
    situation = _catalog().situation(code)
    if situation is None:
        raise _error("KNOWLEDGE_SITUATION_NOT_FOUND", "No such situation", status.HTTP_404_NOT_FOUND)
    return situation


@router.get("/links", response_model=KnowledgeLinkRead, summary="The entries the application links to one risk, clause, phrase or document")
async def read_links(
    target_kind: Target,
    target: str = Query(min_length=1, max_length=80),
    current_user: User = Depends(get_current_user),
) -> KnowledgeLinkRead:
    catalog = _catalog()
    link = next((l for l in catalog.links if l.target_kind == target_kind and l.target == target), None)
    entries = [catalog.entry(code) for code in link.entries] if link else []
    return KnowledgeLinkRead(target_kind=target_kind, target=target, entries=[_item(catalog, e) for e in entries if e is not None])


@router.get("/links/index", response_model=KnowledgeLinkIndex, summary="Every link of the application to the knowledge base at once")
async def read_link_index(current_user: User = Depends(get_current_user)) -> KnowledgeLinkIndex:
    catalog = _catalog()
    items = []
    for link in catalog.links:
        entries = [catalog.entry(code) for code in link.entries]
        items.append(KnowledgeLinkRead(
            target_kind=link.target_kind, target=link.target, entries=[_item(catalog, e) for e in entries if e is not None],
        ))
    return KnowledgeLinkIndex(items=items)
