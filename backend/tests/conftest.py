import base64
import hashlib
import hmac
import json
import os
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.key_ring import OwnerKey, ring, set_owner_key
from app.main import app

# Stage 14D.2D.4: opt-in PostgreSQL 16 proof fixtures (inert unless a test requests them).
pytest_plugins = ["tests.pg16_proof_fixtures"]

# Use isolated in-memory SQLite database for async tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(test_engine.sync_engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    """Mirror Postgres FK enforcement so ON DELETE CASCADE behaves in tests."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

TEST_BOT_TOKEN = "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"


@pytest.fixture(autouse=True)
def setup_test_settings():
    settings.TELEGRAM_BOT_TOKEN = TEST_BOT_TOKEN
    settings.MOCK_TELEGRAM_AUTH = True
    settings.APP_ENV = "development"  # test_auth.py leaves "production" behind; the startup of the application (EN-2a) reads it
    settings.ENVIRONMENT = "development"
    settings.JWT_SECRET_KEY = "test-jwt-secret-key-for-unit-testing"


def fresh_kek() -> SecretStr:
    return SecretStr(base64.b64encode(os.urandom(32)).decode())


@pytest.fixture
def encryption_on():
    """The encryption of the client data switched on (EN-2a): a new key of the server, an empty ring, no owner key in force."""
    settings.DATA_KEK = fresh_kek()
    ring.disable()
    set_owner_key(None)
    yield
    settings.DATA_KEK = SecretStr("")
    ring.disable()
    set_owner_key(None)


@pytest.fixture(autouse=True)
def _whole_suite_encrypted():
    """EN_TEST_ENCRYPTION=1 runs EVERY test with the encryption of the client data on (EN-2b-2): a key of the server, and a fixed key of the owner for the
    writes that tests make straight through the ORM (a request puts the key of its own owner in force). The default run is unchanged."""
    if not os.environ.get("EN_TEST_ENCRYPTION"):
        yield
        return
    dek = os.urandom(32)
    settings.DATA_KEK = fresh_kek()
    ring.disable()
    ring.enable()
    ring.add("suite", dek)
    set_owner_key(OwnerKey("suite", dek))
    yield
    settings.DATA_KEK = SecretStr("")
    ring.disable()
    set_owner_key(None)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


def make_telegram_init_data(
    user_dict: dict,
    bot_token: str = TEST_BOT_TOKEN,
    auth_date: int | None = None,
    tamper_hash: bool = False,
    omit_hash: bool = False,
    omit_auth_date: bool = False,
) -> str:
    """Helper to build cryptographically valid or invalid Telegram initData."""
    if auth_date is None:
        auth_date = int(datetime.now(timezone.utc).timestamp())

    pairs = [
        ("query_id", "AAHdF6IQAAAAAN0XohDhrP_Q"),
        ("user", json.dumps(user_dict, separators=(",", ":"))),
    ]
    if not omit_auth_date:
        pairs.append(("auth_date", str(auth_date)))

    pairs.sort(key=lambda x: x[0])
    data_check_string = "\n".join(f"{k}={v}" for k, v in pairs)

    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if tamper_hash:
        calculated_hash = "deadbeef" + calculated_hash[8:]

    query_parts = [f"{k}={v}" for k, v in pairs]
    if not omit_hash:
        query_parts.append(f"hash={calculated_hash}")

    return "&".join(query_parts)
