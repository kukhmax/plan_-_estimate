from collections.abc import AsyncGenerator
from datetime import datetime, timezone
import hashlib
import hmac
import json
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app

# Use isolated in-memory SQLite database for async tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
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
    settings.ENVIRONMENT = "development"
    settings.JWT_SECRET_KEY = "test-jwt-secret-key-for-unit-testing"


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
