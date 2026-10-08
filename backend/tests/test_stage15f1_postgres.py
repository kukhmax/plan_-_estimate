"""Stage 15F.1 on PostgreSQL (opt-in: TEST_PG_URL pointing to a pe_scratch_test database).

SQLite cannot prove the numbering race: here many issues of one object start at the same moment and every one must get its
own running number and its own time number, with no gap, no duplicate and no error; the same document asked for twice at the
same moment must be one row."""

import asyncio
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.domain.services.issued_document_service import IssuedDocumentService
from app.models.issued_document import IssuedDocument, IssuedDocumentKind
from app.models.project import Project
from app.models.user import User
from tests.pg_scratch_guard import scratch_url

URL = scratch_url()
pytestmark = pytest.mark.skipif(URL is None, reason="opt-in: set TEST_PG_URL to a pe_scratch_test database")

BACKEND = Path(__file__).resolve().parents[1]
ROUNDS = int(os.environ.get("PG_RACE_ROUNDS", "10"))
WRITERS = 10
NOW = datetime(2026, 10, 8, 17, 53, 10, tzinfo=UTC)


@pytest.fixture(scope="module", autouse=True)
def migrated_schema():
    env = dict(os.environ, DATABASE_URL=URL.render_as_string(hide_password=False))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True, capture_output=True)


@pytest.fixture
async def pg():
    engine = create_async_engine(URL, poolclass=NullPool, hide_parameters=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    owners: list[uuid.UUID] = []
    yield sessions, owners
    async with sessions() as s:
        await s.execute(delete(IssuedDocument).where(IssuedDocument.owner_id.in_(owners)))
        await s.execute(delete(Project).where(Project.owner_id.in_(owners)))
        await s.execute(delete(User).where(User.id.in_(owners)))
        await s.commit()
    await engine.dispose()


async def new_project(sessions, owners) -> tuple[uuid.UUID, uuid.UUID]:
    async with sessions() as s:
        user = User(telegram_user_id=uuid.uuid4().int % 10**12, username="pg15f")
        s.add(user)
        await s.flush()
        project = Project(owner_id=user.id, name="p", address="a", city="c", postal_code="00-001")
        s.add(project)
        await s.commit()
        owners.append(user.id)
        return user.id, project.id


async def reserve(sessions, owner, project, kind=IssuedDocumentKind.ESTIMATE, source=None):
    async with sessions() as s:
        return await IssuedDocumentService(s, clock=lambda: NOW).reserve(
            owner, project, kind, title="t", template_version="1", source_id=source)


async def test_simultaneous_issues_get_distinct_numbers_without_gaps(pg):
    sessions, owners = pg
    for _ in range(ROUNDS):
        owner, project = await new_project(sessions, owners)
        kinds = [IssuedDocumentKind.ESTIMATE, IssuedDocumentKind.PHOTO_REPORT]
        results = await asyncio.gather(
            *(reserve(sessions, owner, project, kinds[i % 2], source=uuid.uuid4()) for i in range(WRITERS)), return_exceptions=True)
        failures = [r for r in results if isinstance(r, BaseException)]
        assert not failures, failures
        docs = [r.document for r in results]
        assert sorted(d.project_seq for d in docs) == list(range(1, WRITERS + 1))
        assert len({d.number for d in docs}) == WRITERS
        by_kind = {}
        for d in docs:
            by_kind.setdefault(d.kind, []).append(d.number)
        for kind, numbers in by_kind.items():
            base = {"ESTIMATE": "KOSZ", "PHOTO_REPORT": "FOTO"}[kind] + "/2026/10/08/1953"
            assert min(numbers, key=lambda n: (len(n), n)) == base and all(n == base or n.startswith(base + "-") for n in numbers)


async def test_the_same_document_asked_for_at_once_is_one_row(pg):
    sessions, owners = pg
    for _ in range(ROUNDS):
        owner, project = await new_project(sessions, owners)
        source = uuid.uuid4()
        results = await asyncio.gather(*(reserve(sessions, owner, project, source=source) for _ in range(WRITERS)), return_exceptions=True)
        assert not [r for r in results if isinstance(r, BaseException)]
        assert sum(1 for r in results if not r.reused) == 1
        assert len({r.document.id for r in results}) == 1
        async with sessions() as s:
            rows = (await s.execute(select(IssuedDocument).where(IssuedDocument.project_id == project))).scalars().all()
        assert len(rows) == 1 and rows[0].project_seq == 1


async def test_two_objects_number_independently_under_load(pg):
    sessions, owners = pg
    owner, first = await new_project(sessions, owners)
    async with sessions() as s:
        second = Project(owner_id=owner, name="q", address="a", city="c", postal_code="00-002")
        s.add(second)
        await s.commit()
        second_id = second.id
    results = await asyncio.gather(*(reserve(sessions, owner, p, source=uuid.uuid4()) for p in (first, second_id) for _ in range(5)))
    for project in (first, second_id):
        assert sorted(r.document.project_seq for r in results if r.document.project_id == project) == [1, 2, 3, 4, 5]
    assert len({r.document.number for r in results}) == 10
