"""Stage 15C — executor profile on PostgreSQL (opt-in: TEST_PG_URL pointing to a pe_scratch_test database).

SQLite cannot prove the first-save race: here several requests of one owner save a profile at the same moment,
and the unique owner row must leave exactly one profile with every request answered.
"""

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.domain.services.executor_profile_service import ExecutorProfileService
from app.models.executor_profile import ExecutorProfile
from app.models.user import User
from app.schemas.executor_profile import ExecutorProfileWrite
from tests.pg_scratch_guard import scratch_url

URL = scratch_url()
pytestmark = pytest.mark.skipif(URL is None, reason="opt-in: set TEST_PG_URL to a pe_scratch_test database")

BACKEND = Path(__file__).resolve().parents[1]
ROUNDS = int(os.environ.get("PG_RACE_ROUNDS", "10"))
WRITERS = 8


@pytest.fixture(scope="module", autouse=True)
def migrated_schema():
    env = dict(os.environ, DATABASE_URL=URL.render_as_string(hide_password=False))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True,
                   capture_output=True)


@pytest.fixture
async def pg():
    engine = create_async_engine(URL, poolclass=NullPool, hide_parameters=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    owners: list[uuid.UUID] = []
    yield sessions, owners
    async with sessions() as s:
        await s.execute(delete(ExecutorProfile).where(ExecutorProfile.owner_id.in_(owners)))
        await s.execute(delete(User).where(User.id.in_(owners)))
        await s.commit()
    await engine.dispose()


async def new_owner(sessions, owners) -> uuid.UUID:
    async with sessions() as s:
        user = User(telegram_user_id=uuid.uuid4().int % 10**12, username="pg15c")
        s.add(user)
        await s.commit()
        owners.append(user.id)
        return user.id


async def test_simultaneous_first_saves_end_with_one_profile_and_no_error(pg):
    sessions, owners = pg
    for round_no in range(ROUNDS):
        owner = await new_owner(sessions, owners)

        async def save(n: int, owner=owner, round_no=round_no):
            async with sessions() as s:
                return await ExecutorProfileService(s).save(owner, ExecutorProfileWrite(name=f"Zapis {round_no}-{n}"))

        results = await asyncio.gather(*(save(n) for n in range(WRITERS)), return_exceptions=True)
        failures = [r for r in results if isinstance(r, BaseException)]
        assert not failures, failures
        async with sessions() as s:
            rows = (await s.execute(select(ExecutorProfile).where(ExecutorProfile.owner_id == owner))).scalars().all()
        assert len(rows) == 1 and rows[0].name.startswith(f"Zapis {round_no}-")


async def test_owners_never_share_a_row_under_load(pg):
    sessions, owners = pg
    ids = [await new_owner(sessions, owners) for _ in range(4)]

    async def save(owner: uuid.UUID, n: int):
        async with sessions() as s:
            return await ExecutorProfileService(s).save(owner, ExecutorProfileWrite(name=f"{owner}-{n}"))

    await asyncio.gather(*(save(o, n) for o in ids for n in range(4)))
    async with sessions() as s:
        count = (await s.execute(select(func.count()).select_from(ExecutorProfile)
                                 .where(ExecutorProfile.owner_id.in_(ids)))).scalar_one()
        rows = (await s.execute(select(ExecutorProfile).where(ExecutorProfile.owner_id.in_(ids)))).scalars().all()
    assert count == 4 and all(r.name.startswith(str(r.owner_id)) for r in rows)
