"""Editable Price Book domain service (Stage 9B).

Stage 9 owns catalog management only — no estimate entities, no Project/room/
inspection coupling. Seed rows are materialized lazily and per-owner: each
owner receives their own editable copies of the (non-market) technical baseline
set, bootstrap is idempotent, and owner-edited rows are never overwritten.
Currency is an ISO 4217-style string (PLN-only for MVP), not a DB enum.
"""
import asyncio
from decimal import Decimal
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.data.price_book_seed import (
    PriceItemSeed,
    build_technical_baseline_price_items,
)
from app.domain.exceptions import PriceBookValidationError, PriceItemNotFoundError
from app.models.checklist import QualityLevel
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit

# Serializes concurrent first-call materializations within the process; the
# (owner_id, code) unique constraint guarantees correctness even without it.
_bootstrap_lock = asyncio.Lock()

# MVP currency contract: a future currency widens this set, not the schema.
_ALLOWED_CURRENCIES = frozenset({"PLN"})

# Distinguishes "field omitted" from an explicit clear-to-null in a PATCH.
_UNSET = object()


def validate_price(value: Decimal) -> Decimal:
    """Return the validated price; reject negatives and >2-decimal values.

    Input is never rounded or truncated: a value with more than two decimal
    places is rejected so the user's typing is preserved until corrected.
    """
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    if not value.is_finite():
        raise PriceBookValidationError("price must be a finite decimal number")
    if value < 0:
        raise PriceBookValidationError("price must be greater than or equal to 0")
    if value.as_tuple().exponent < -2:
        raise PriceBookValidationError(
            "price may have at most 2 decimal places (no silent rounding)"
        )
    return value


def validate_currency(code: str) -> None:
    if code not in _ALLOWED_CURRENCIES:
        raise PriceBookValidationError("only PLN is supported for the MVP")


def validate_custom_name(display_name: str | None) -> str:
    name = (display_name or "").strip()
    if not name:
        raise PriceBookValidationError("custom price items require a display_name")
    return name


class PriceBookService:
    """Owner-scoped operations over the editable Price Book."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ensure_owner_catalog(self, owner_id: uuid.UUID) -> list[PriceItem]:
        """Materialize every missing baseline seed code for one owner.

        Idempotent: only codes not already present for this owner are inserted,
        and existing owner rows (including user edits) are never overwritten.
        """
        async with _bootstrap_lock:
            existing_codes = set(
                (
                    await self.db.execute(
                        select(PriceItem.code).where(PriceItem.owner_id == owner_id)
                    )
                ).scalars()
            )
            missing = [
                seed
                for seed in build_technical_baseline_price_items()
                if seed.code not in existing_codes
            ]
            created: list[PriceItem] = []
            for seed in missing:
                created.append(self._materialize_seed(owner_id, seed))
            if created:
                await self.db.commit()
            return created

    def _materialize_seed(self, owner_id: uuid.UUID, seed: PriceItemSeed) -> PriceItem:
        item = PriceItem(
            owner_id=owner_id,
            code=seed.code,
            name_key=seed.name_key,
            category=seed.category,
            unit=seed.unit,
            price=Decimal(seed.price),
            price_scope=seed.price_scope,
            currency="PLN",
        )
        self.db.add(item)
        return item

    async def generate_custom_code(self, owner_id: uuid.UUID) -> str:
        """Return a unique, stable CUSTOM_* code for the owner (server-side)."""
        while True:
            code = f"CUSTOM_{uuid.uuid4().hex[:12].upper()}"
            exists = (
                await self.db.execute(
                    select(PriceItem.id).where(
                        PriceItem.owner_id == owner_id,
                        PriceItem.code == code,
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                return code

    async def create_custom_item(
        self,
        owner_id: uuid.UUID,
        *,
        category: PriceCategory,
        unit: PriceUnit,
        price: Decimal,
        display_name: str,
        price_scope: PriceScope = PriceScope.LABOR,
        quality_level: QualityLevel | None = None,
        currency: str = "PLN",
    ) -> PriceItem:
        """Create a user-authored item with a generated, immutable CUSTOM_* code."""
        validate_currency(currency)
        validated_price = validate_price(price)
        name = validate_custom_name(display_name)
        code = await self.generate_custom_code(owner_id)
        item = PriceItem(
            owner_id=owner_id,
            code=code,
            display_name=name,
            category=category,
            unit=unit,
            price=validated_price,
            currency=currency,
            price_scope=price_scope,
            quality_level=quality_level,
        )
        self.db.add(item)
        await self.db.commit()
        return item

    async def update_item(
        self,
        owner_id: uuid.UUID,
        item_id: uuid.UUID,
        *,
        price: Decimal | None = None,
        display_name: str | None = None,
        category: PriceCategory | None = None,
        unit: PriceUnit | None = None,
        price_scope: PriceScope | None = None,
        quality_level: QualityLevel | None = _UNSET,
        currency: str | None = None,
        is_archived: bool | None = None,
    ) -> PriceItem:
        """Update an owned item; the semantic ``code`` is immutable on this path.

        ``display_name`` blank clears a seeded row's override (reverting to its
        ``name_key`` identity) but is rejected for custom rows, which require a
        name. ``quality_level`` distinguishes omitted (sentinel) from an explicit
        clear-to-null.
        """
        item = (
            await self.db.execute(
                select(PriceItem).where(
                    PriceItem.id == item_id,
                    PriceItem.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        if item is None:
            raise PriceItemNotFoundError(f"Price item {item_id} not found")

        if price is not None:
            item.price = validate_price(price)
        if currency is not None:
            validate_currency(currency)
            item.currency = currency
        if display_name is not None:
            item.display_name = self._resolve_display_name(item, display_name)
        if category is not None:
            item.category = category
        if unit is not None:
            item.unit = unit
        if price_scope is not None:
            item.price_scope = price_scope
        if quality_level is not _UNSET:
            item.quality_level = quality_level
        if is_archived is not None:
            item.is_archived = is_archived
        await self.db.commit()
        return item

    def _resolve_display_name(
        self, item: PriceItem, display_name: str | None
    ) -> str | None:
        name = (display_name or "").strip()
        if not name:
            if item.name_key is not None:
                # Seeded identity: clearing the override reverts to name_key.
                return None
            raise PriceBookValidationError("custom price items require a display_name")
        return name

    async def archive_item(self, owner_id: uuid.UUID, item_id: uuid.UUID) -> PriceItem:
        """Soft-archive an owned item (idempotent); never a hard delete."""
        item = await self.get_owned_item(owner_id, item_id)
        item.is_archived = True
        await self.db.commit()
        return item

    async def restore_item(self, owner_id: uuid.UUID, item_id: uuid.UUID) -> PriceItem:
        """Restore an archived owned item (idempotent)."""
        item = await self.get_owned_item(owner_id, item_id)
        item.is_archived = False
        await self.db.commit()
        return item

    async def list_owner_items(
        self,
        owner_id: uuid.UUID,
        *,
        archived: str = "active",
        category: PriceCategory | None = None,
        unit: PriceUnit | None = None,
        price_scope: PriceScope | None = None,
        quality_level: QualityLevel | None = None,
        search: str | None = None,
    ) -> list[PriceItem]:
        """Return the owner's catalog with filters; ``archived`` is one of
        ``"active"`` (default) / ``"archived"`` / ``"all"``.

        Search matches the stable identity fields (code / name_key /
        display_name); localized labels are resolved client-side in 9D. The
        catalog has no pagination, so the full filtered set is returned with
        stable ordering: is_archived, category, display identity, code.
        """
        stmt = select(PriceItem).where(PriceItem.owner_id == owner_id)
        if archived == "active":
            stmt = stmt.where(PriceItem.is_archived.is_(False))
        elif archived == "archived":
            stmt = stmt.where(PriceItem.is_archived.is_(True))

        if category is not None:
            stmt = stmt.where(PriceItem.category == category)
        if unit is not None:
            stmt = stmt.where(PriceItem.unit == unit)
        if price_scope is not None:
            stmt = stmt.where(PriceItem.price_scope == price_scope)
        if quality_level is not None:
            stmt = stmt.where(PriceItem.quality_level == quality_level)
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    PriceItem.code.ilike(pattern),
                    PriceItem.name_key.ilike(pattern),
                    PriceItem.display_name.ilike(pattern),
                )
            )

        sort_label = func.coalesce(PriceItem.display_name, PriceItem.name_key)
        stmt = stmt.order_by(
            PriceItem.is_archived,
            PriceItem.category,
            sort_label,
            PriceItem.code,
        )
        return list((await self.db.execute(stmt)).scalars())

    async def get_owned_item(
        self,
        owner_id: uuid.UUID,
        item_id: uuid.UUID,
    ) -> PriceItem:
        item = (
            await self.db.execute(
                select(PriceItem).where(
                    PriceItem.id == item_id,
                    PriceItem.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        if item is None:
            raise PriceItemNotFoundError(f"Price item {item_id} not found")
        return item