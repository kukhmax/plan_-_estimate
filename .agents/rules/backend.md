# Backend Engineering Rules

## 1. Technology Stack
- **Language**: Python 3.11+ (modern typing, union operators `|`, `asyncio` native performance).
- **Framework**: FastAPI (async routes, dependency injection, automatic OpenAPI spec generation).
- **ORM**: SQLAlchemy 2.x (strict declarative base with `Mapped` and `mapped_column`, async engine, `AsyncSession`).
- **Migrations**: Alembic (async env, automated migration generation, verified reversible migrations).
- **Data Validation**: Pydantic v2 (`BaseModel`, `Field`, `model_validator`, `field_validator`, ConfigDict).
- **Bot Framework**: `aiogram 3.x` (Telegram Bot integration, async routers, middleware, deep-linking into Mini App).
- **Testing**: `pytest`, `pytest-asyncio`, `httpx` (AsyncClient).

## 2. Directory & Package Conventions
```
backend/
├── app/
│   ├── api/                  # FastAPI routers (thin controllers)
│   │   ├── v1/
│   │   │   ├── routers/
│   │   │   └── deps.py       # Dependency injection (Auth, DB session, Current User)
│   ├── core/                 # App configuration, security, database engine
│   │   ├── config.py         # Pydantic Settings
│   │   ├── database.py       # Async SQLAlchemy sessionmaker
│   │   └── security.py       # Telegram initData validation & token parsing
│   ├── domain/               # Pure domain logic, risk engine, calculations
│   │   ├── models/           # Domain entity definitions
│   │   ├── services/         # Business services (estimates, risk rules, protocols)
│   │   └── rules/            # Deterministic construction rules & tables
│   ├── models/               # SQLAlchemy 2.x declarative DB models
│   ├── schemas/              # Pydantic v2 request/response schemas (DTOs)
│   └── bot/                  # aiogram 3.x bot handlers and menus
├── alembic/                  # Alembic migration scripts
├── tests/                    # Unit, integration, and contract tests
│   ├── conftest.py
│   ├── unit/
│   └── integration/
├── alembic.ini
└── pyproject.toml
```

## 3. SQLAlchemy 2.x & Database Rules
- Always use the 2.0 style syntax:
  ```python
  stmt = select(Obiekt).where(Obiekt.id == obiekt_id, Obiekt.owner_id == user.id)
  result = await session.execute(stmt)
  obiekt = result.scalar_one_or_none()
  ```
- Use `Mapped[...]` and `mapped_column(...)` type annotations on all models.
- All primary keys must be `UUID`:
  ```python
  id: Mapped[uuid.UUID] = mapped_column(
      UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
  )
  ```
- UTC Timestamps:
  ```python
  created_at: Mapped[datetime] = mapped_column(
      DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
  )
  updated_at: Mapped[datetime] = mapped_column(
      DateTime(timezone=True),
      default=lambda: datetime.now(timezone.utc),
      onupdate=lambda: datetime.now(timezone.utc)
  )
  ```
- Session management: Always inject `AsyncSession` using FastAPI `Depends(get_db)`. Do not manage sessions manually in controllers.

## 4. Telegram Mini App Authentication
- Mini App transmits `initData` query string on launch from Telegram.
- Validation algorithm:
  1. Parse query string into key-value pairs.
  2. Extract `hash`.
  3. Sort remaining keys alphabetically and build data check string `key=value\n...`.
  4. Compute HMAC-SHA256 signature using secret key derived from `HMAC-SHA256("WebAppData", bot_token)`.
  5. Compare calculated hash with received hash using constant-time comparison (`hmac.compare_digest`).
  6. Check `auth_date` freshness to prevent replay attacks.
- Store Telegram `user_id`, `username`, `first_name`, `language_code` in `User` entity.

## 5. MVP Constraints
- **No Redis**: Do not introduce Redis or any external cache server for MVP. Use PostgreSQL or in-memory LRU cache where caching is strictly needed.
- **No AI / LLMs**: Do not introduce OpenAI, Claude, LangChain, or other LLM integrations for MVP. Construction estimations, quality classifications, and risk warnings must be deterministic, transparent, and reproducible.
- **Secrets Management**: Read all secrets (bot token, DB URL, JWT secrets) via environment variables or `.env` using `pydantic-settings`. Never commit `.env`.

## 6. Error Handling & Testing
- Custom domain exceptions (e.g. `ObiektNotFoundException`, `InvalidSubstrateTransitionException`, `PriceItemMissingException`) defined in domain layer.
- Global FastAPI exception handlers convert domain exceptions to RFC 7807 problem details or clean JSON error structures:
  `{"error": {"code": "OBIEKT_NOT_FOUND", "message": "..."}}`.
- Never silently catch exceptions (`except Exception: pass` is strictly forbidden).
- Every backend stage must include `pytest` tests:
  - Unit tests for domain services, calculation logic, and risk rules.
  - Integration tests for API endpoints verifying status codes, response schemas, and database persistence.
