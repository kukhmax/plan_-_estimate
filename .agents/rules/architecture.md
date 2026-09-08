# Architecture Rules & System Design

## 1. Core Paradigm & Philosophy
- **Clean Layered Architecture**:
  1. **Presentation / Interface Layer**: FastAPI routers (thin controllers) and Telegram Bot handlers (`aiogram 3.x`).
  2. **Service / Domain Layer**: Pure business logic, workflow orchestrators, calculation and estimation engines, technical validation, and rule engines.
  3. **Data Access / Persistence Layer**: SQLAlchemy 2.x async models, Alembic migrations, PostgreSQL repository/query functions.
- **Independence of Core Logic**: Business decisions, validation formulas, risk analysis, and unit price calculations must NEVER depend on web frameworks (FastAPI/HTTP) or UI components.
- **Small Coherent Changes**: Build iteratively, one logical stage at a time. Never implement future features prematurely. Preserve working functionality from earlier stages.

## 2. Central Entity: OBIEKT (Project / Site)
- In the Polish finishing and renovation domain, the central aggregate root is the **OBIEKT** (Project / Work Site).
- Every domain sub-entity (rooms, walls, ceilings, substrate inspections, measurements, risk logs, estimates, contracts, technical acceptance protocols) strictly anchors back to an `Obiekt` (`project_id`).
- Hierarchical structure:
  `Client -> Obiekt (Project) -> Room (Pomieszczenie) -> Surface (Ściana / Sufit / Wnęka) -> Inspection (Badanie podłoża) & Measurements (Pomiary) -> Estimate Items (Pozycje kosztorysowe) -> Work Execution (Realizacja) -> Technical Protocol (Protokół odbioru)`.

## 3. User Model & Tenancy Architecture
- **MVP Model**: Single-owner user initially (the finishing contractor / master craftsman).
- **Multi-Tenant Readiness**:
  - Every root entity (`Client`, `Obiekt`, `PriceBook`, `ContractTemplate`) must include an `owner_id` (foreign key pointing to `User.id`).
  - Queries and mutations must always filter by `owner_id`.
  - Architecture and database constraints must allow easy extension to multi-tenant teams, subcontractors, and role-based access control (RBAC) without destructive schema rewrites.

## 4. Entity & Database Standards
- **Primary Keys**: UUIDv4 (`uuid_generate_v4()` or application-generated `uuid.uuid4()`) for all entities to avoid enumeration attacks, enable offline draft UUID generation, and simplify distributed sync.
- **Timestamps**: All timestamps must be stored in UTC (`created_at`, `updated_at`, `deleted_at` if soft-deleting). Format: ISO 8601 UTC.
- **Schema Evolution**:
  - Direct DDL on the database is strictly forbidden.
  - Every schema change must be accompanied by an Alembic migration script.
  - Migrations must be reversible (`upgrade` and `downgrade` implemented).
  - Schema naming conventions: snake_case for tables and columns, singular or consistent plural table names.

## 5. API Contracts & Boundary Integrity
- **Thin Controllers**: FastAPI route functions must only:
  1. Authenticate and extract caller context (`User`, `initData`).
  2. Validate incoming requests using Pydantic v2 schemas.
  3. Delegate business operations to the appropriate Domain Service.
  4. Return typed response schemas or handle domain exceptions into standard HTTP error responses.
- **No Leaky Abstractions**: SQLAlchemy ORM models must never be returned directly by API endpoints. Always serialize through explicit Pydantic DTOs/schemas.
- **Typed Error Envelopes**: Structured error responses with clear machine-readable error codes and human-readable messages. Never silently swallow exceptions.

## 6. Deterministic Technical Risk Engine
- Risk decisions (substrate incompatibility, moisture danger, cracking hazards, surface preparation requirements, warranty limitations) must be **100% deterministic and rule-driven**.
- **No AI / LLM evaluation** for technical risk decisions in MVP.
- All rules must stem from established Polish and European construction standards (PN-B, ITB, DIN / Eurofins, manufacturer technical cards).
