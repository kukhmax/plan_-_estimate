from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

def create_app_engine(url: str) -> AsyncEngine:
    """Application engine. hide_parameters=True (14C.6A F1): bound parameter
    values (sha256, storage keys, filenames, captions, ...) never appear in
    SQLAlchemy exception text or SQL logging -- including tracebacks of
    unhandled 500s."""
    return create_async_engine(url, echo=settings.DEBUG, future=True, hide_parameters=True)


engine = create_app_engine(settings.DATABASE_URL)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
