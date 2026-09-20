"""Editable Price Book domain service (Stage 9B).

Stage 9 owns catalog management only — no estimate entities, no Project/room/
inspection coupling. Seed rows are materialized lazily and per-owner: each
owner receives their own editable copies of the (non-market) technical baseline
set, bootstrap is idempotent, and owner-edited rows are never overwritten.
Currency is an ISO 4217-style string (PLN-only for MVP), not a DB enum.
"""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.data.price_book_seed import (
    LEGACY_GENERIC_CODES,
    MarketReferenceSeed,
    PriceItemSeed,
    PriceSourceSeed,
    build_approved_market_references,
    build_approved_price_book_items,
)
from app.domain.exceptions import (
    MarketReferenceNotFoundError,
    PriceBookValidationError,
    PriceItemNotFoundError,
)
from app.models.checklist import QualityLevel
from app.models.market_evidence import (
    PriceMarketReference,
    PriceSource,
    SourceType,
)
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit

# Serializes concurrent first-call materializations within the process; the
# (owner_id, code) unique constraint guarantees correctness even without it.
_bootstrap_lock = asyncio.Lock()

# MVP currency contract: a future currency widens this set, not the schema.
_ALLOWED_CURRENCIES = frozenset({"PLN"})

# Distinguishes "field omitted" from an explicit clear-to-null in a PATCH.
_UNSET = object()


def _as_decimal(value: str | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _money(value: Decimal) -> Decimal:
    """Quantize a money value to the Numeric(12, 2) scale for content-key equality.

    The money contract bounds inputs to two decimals, so quantization never
    rounds; it only aligns DB-rounded values (Decimal("12.00")) with seed
    literals (Decimal("12")) for idempotent evidence reconciliation.
    """
    return value.quantize(Decimal("0.01"))


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


# MVP region contract (9E.1): the researched area is one of three exact labels.
_ALLOWED_REGIONS = frozenset({"Kraków", "Małopolskie", "Kraków / Małopolskie"})


def validate_amount(value: Decimal, *, label: str) -> Decimal:
    """Like validate_price but label-aware for market-evidence fields.

    Market amounts obey the same money contract as the owner price: finite,
    >= 0, at most 2 decimal places, never silently rounded or truncated.
    """
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    if not value.is_finite():
        raise PriceBookValidationError(f"{label} must be a finite decimal number")
    if value < 0:
        raise PriceBookValidationError(f"{label} must be greater than or equal to 0")
    if value.as_tuple().exponent < -2:
        raise PriceBookValidationError(
            f"{label} may have at most 2 decimal places (no silent rounding)"
        )
    return value


def validate_region(region: str) -> str:
    label = (region or "").strip()
    if label not in _ALLOWED_REGIONS:
        raise PriceBookValidationError(
            "region must be one of: Kraków, Małopolskie, Kraków / Małopolskie"
        )
    return label


def validate_optional_label(value: str | None) -> str | None:
    """Controlled free text that may differ from the reference region."""
    if value is None:
        return None
    label = value.strip()
    if not label:
        raise PriceBookValidationError("label must be non-blank when provided")
    return label


def normalize_checked_at(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise PriceBookValidationError("checked_at is required")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _coerce_source_type(value: object) -> SourceType:
    if isinstance(value, SourceType):
        return value
    try:
        return SourceType(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise PriceBookValidationError(
            "source_type must be a valid source type"
        ) from None


def _coerce_quoted_unit(value: object) -> PriceUnit | None:
    if value is None:
        return None
    if isinstance(value, PriceUnit):
        return value
    try:
        return PriceUnit(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise PriceBookValidationError(
            "quoted_unit must be a valid price unit"
        ) from None


def validate_source_payload(source: dict) -> dict:
    """Validate one evidence source and derive its quoting mode.

    Exactly one of SINGLE / RANGE / QUALITATIVE is allowed:
    - SINGLE: quoted_price_single set, quoted_price_min/max null
    - RANGE: quoted_price_min and quoted_price_max both set, min <= max
    - QUALITATIVE: all numeric quotes null, note carries the evidence
    """
    if not isinstance(source, dict):
        raise PriceBookValidationError("each source must be a mapping")

    source_name = (source.get("source_name") or "").strip()
    if not source_name:
        raise PriceBookValidationError("sources require a non-blank source_name")
    source_type = _coerce_source_type(source.get("source_type"))
    source_url = source.get("source_url") or None
    source_region = validate_optional_label(source.get("source_region"))
    quoted_unit = _coerce_quoted_unit(source.get("quoted_unit"))
    checked_at = normalize_checked_at(source.get("checked_at"))

    raw_min = source.get("quoted_price_min")
    raw_max = source.get("quoted_price_max")
    raw_single = source.get("quoted_price_single")
    note = (source.get("note") or "").strip() or None

    quoted_price_min: Decimal | None = None
    quoted_price_max: Decimal | None = None
    quoted_price_single: Decimal | None = None

    if raw_single is not None:
        quoted_price_single = validate_amount(raw_single, label="quoted_price_single")
        if raw_min is not None or raw_max is not None:
            raise PriceBookValidationError(
                "a source supports exactly one quoting mode: SINGLE or RANGE"
            )
    elif raw_min is not None or raw_max is not None:
        if raw_min is None or raw_max is None:
            raise PriceBookValidationError(
                "a RANGE source requires both quoted_price_min and quoted_price_max"
            )
        quoted_price_min = validate_amount(raw_min, label="quoted_price_min")
        quoted_price_max = validate_amount(raw_max, label="quoted_price_max")
        if quoted_price_min > quoted_price_max:
            raise PriceBookValidationError(
                "quoted_price_min must not exceed quoted_price_max"
            )
    elif not note:
        raise PriceBookValidationError(
            "a QUALITATIVE source requires a non-blank note"
        )

    return {
        "source_name": source_name,
        "source_type": source_type,
        "source_url": source_url,
        "source_region": source_region,
        "quoted_price_min": quoted_price_min,
        "quoted_price_max": quoted_price_max,
        "quoted_price_single": quoted_price_single,
        "quoted_unit": quoted_unit,
        "note": note,
        "checked_at": checked_at,
    }


def market_source_is_comparable(reference_unit: PriceUnit, source: dict) -> bool:
    """Whether a source's numeric quotes may feed the reference range.

    No automatic unit conversion exists: a source quoting a different unit
    keeps its numbers untouched but contributes qualitative context only.
    """
    quoted = source.get("quoted_unit")
    return quoted is None or quoted == reference_unit


class PriceBookService:
    """Owner-scoped operations over the editable Price Book."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ensure_owner_catalog(self, owner_id: uuid.UUID) -> list[PriceItem]:
        """Materialize the owner's catalog and market evidence (idempotent).

        Adds every missing 9E.5 canonical seed (``price=None``), retires the
        Stage 9B GENERIC placeholders once (soft-archive, never delete), and
        reconciles the approved evidence: a reference (or any missing source) is
        created only when its content key is absent, so repeated bootstraps do
        not duplicate rows and existing owner rows (including user edits and the
        owner's own research) are never overwritten. Commits only when something
        actually changed.
        """
        async with _bootstrap_lock:
            existing = (
                await self.db.execute(
                    select(PriceItem).where(PriceItem.owner_id == owner_id)
                )
            ).scalars().all()
            by_code = {row.code: row for row in existing}

            created: list[PriceItem] = []
            for seed in build_approved_price_book_items():
                if seed.code not in by_code:
                    item = self._materialize_seed(owner_id, seed)
                    created.append(item)
                    by_code[item.code] = item
            changed = bool(created)
            if created:
                # New ids are required before evidence can link to their items.
                await self.db.flush()

            for code in LEGACY_GENERIC_CODES:
                row = by_code.get(code)
                if row is not None and not row.is_archived:
                    row.is_archived = True
                    changed = True

            if await self._reconcile_evidence(owner_id, by_code):
                changed = True

            if changed:
                await self.db.commit()
            return created

    def _materialize_seed(self, owner_id: uuid.UUID, seed: PriceItemSeed) -> PriceItem:
        item = PriceItem(
            owner_id=owner_id,
            code=seed.code,
            name_key=seed.name_key,
            category=seed.category,
            unit=seed.unit,
            price=Decimal(seed.price) if seed.price is not None else None,
            price_scope=seed.price_scope,
            quality_level=seed.quality_level,
            currency="PLN",
        )
        self.db.add(item)
        return item

    async def _reconcile_evidence(
        self,
        owner_id: uuid.UUID,
        by_code: dict[str, PriceItem],
    ) -> bool:
        """Create missing approved references/sources; True if anything was added.

        References are matched by content key (region + unit + market bounds +
        reference price + checked_at + methodology_note + currency), sources by
        their full content tuple, so repeated bootstraps never duplicate rows and
        a user's own research is preserved as long as it differs in any field.
        """
        item_ids = [item.id for item in by_code.values()]
        if not item_ids:
            return False
        refs = (
            await self.db.execute(
                select(PriceMarketReference)
                .where(PriceMarketReference.price_item_id.in_(item_ids))
                .options(selectinload(PriceMarketReference.sources))
            )
        ).scalars().all()

        changed = False
        for code, seed in build_approved_market_references().items():
            item = by_code.get(code)
            if item is None:
                continue
            matching = [
                reference
                for reference in refs
                if reference.price_item_id == item.id
                and self._reference_matches(reference, seed)
            ]
            if not matching:
                reference = self._materialize_reference(item, seed)
                self.db.add(reference)
                refs.append(reference)
                changed = True
                continue
            existing = matching[0]
            present_keys = {
                self._source_content_key(source, source.checked_at)
                for source in existing.sources
            }
            for src_seed in seed.sources:
                key = self._source_content_key(src_seed, seed.checked_at)
                if key not in present_keys:
                    existing.sources.append(
                        PriceSource(**self._source_payload(src_seed, seed.checked_at))
                    )
                    present_keys.add(key)
                    changed = True
        return changed

    def _materialize_reference(
        self,
        item: PriceItem,
        seed: MarketReferenceSeed,
    ) -> PriceMarketReference:
        reference = PriceMarketReference(
            price_item_id=item.id,
            region=seed.region,
            unit=seed.unit,
            currency="PLN",
            market_min=_as_decimal(seed.market_min),
            market_max=_as_decimal(seed.market_max),
            reference_price=_as_decimal(seed.reference_price),
            methodology_note=seed.methodology_note,
            checked_at=normalize_checked_at(seed.checked_at),
        )
        for src_seed in seed.sources:
            reference.sources.append(
                PriceSource(**self._source_payload(src_seed, seed.checked_at))
            )
        return reference

    @staticmethod
    def _source_payload(src_seed: PriceSourceSeed, checked_at: datetime) -> dict:
        return {
            "source_name": src_seed.source_name,
            "source_type": src_seed.source_type,
            "source_url": src_seed.source_url,
            "source_region": None,
            "quoted_price_min": _as_decimal(src_seed.quoted_price_min),
            "quoted_price_max": _as_decimal(src_seed.quoted_price_max),
            "quoted_price_single": _as_decimal(src_seed.quoted_price_single),
            "quoted_unit": src_seed.quoted_unit,
            "note": src_seed.note,
            "checked_at": checked_at,
        }

    @staticmethod
    def _reference_matches(
        reference: PriceMarketReference,
        seed: MarketReferenceSeed,
    ) -> bool:
        return (
            reference.region == seed.region
            and reference.unit == seed.unit
            and reference.currency == "PLN"
            and _money(reference.market_min) == _money(_as_decimal(seed.market_min))
            and _money(reference.market_max) == _money(_as_decimal(seed.market_max))
            and (
                (reference.reference_price is None and seed.reference_price is None)
                or (
                    reference.reference_price is not None
                    and seed.reference_price is not None
                    and _money(reference.reference_price)
                    == _money(_as_decimal(seed.reference_price))
                )
            )
            and reference.methodology_note == seed.methodology_note
            and normalize_checked_at(reference.checked_at)
            == normalize_checked_at(seed.checked_at)
        )

    @staticmethod
    def _source_content_key(
        source,
        checked_at: datetime | None,
    ) -> tuple:
        """Canonical content key for one source (works for PriceSource and seed)."""
        return (
            source.source_name,
            source.source_type,
            source.source_url,
            _money(_as_decimal(source.quoted_price_min))
            if source.quoted_price_min is not None
            else None,
            _money(_as_decimal(source.quoted_price_max))
            if source.quoted_price_max is not None
            else None,
            _money(_as_decimal(source.quoted_price_single))
            if source.quoted_price_single is not None
            else None,
            source.quoted_unit,
            source.note,
            normalize_checked_at(checked_at) if checked_at is not None else None,
        )

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
        price: Decimal | None,
        display_name: str,
        price_scope: PriceScope = PriceScope.LABOR,
        quality_level: QualityLevel | None = None,
        currency: str = "PLN",
    ) -> PriceItem:
        """Create a user-authored item with a generated, immutable CUSTOM_* code.

        ``price=None`` is a fully valid "Do ustalenia / Цена уточняется" row,
        identical in meaning to a seeded row that has not yet been priced
        (Stage 10G.4). It is never coerced to ``0.00``, a distinct explicit price.
        """
        validate_currency(currency)
        validated_price = validate_price(price) if price is not None else None
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
        price: Decimal | None = _UNSET,
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
        name. ``price`` and ``quality_level`` both distinguish omitted (sentinel,
        left unchanged) from an explicit clear-to-null (Stage 10G.4 correction
        for ``price``: an explicit ``price=None`` now actually clears an existing
        price back to "Do ustalenia", rather than being a silent no-op).
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

        if price is not _UNSET:
            item.price = validate_price(price) if price is not None else None
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

    async def create_market_reference_with_sources(
        self,
        owner_id: uuid.UUID,
        price_item_id: uuid.UUID,
        *,
        region: str,
        unit: PriceUnit,
        market_min: Decimal,
        market_max: Decimal,
        reference_price: Decimal | None = None,
        currency: str = "PLN",
        methodology_note: str | None = None,
        checked_at: datetime | None = None,
        sources: list[dict],
    ) -> PriceMarketReference:
        """Create one market reference (with its sources) for an owned item.

        The reference range is expressed in the linked item's own unit and
        currency; neither may deviate, and the item's working ``price`` stays
        untouched on this path (evidence is application-maintained).
        """
        item = await self.get_owned_item(owner_id, price_item_id)
        if unit != item.unit:
            raise PriceBookValidationError(
                "market reference unit must match the price item unit"
            )
        validate_currency(currency)
        if currency != item.currency:
            raise PriceBookValidationError(
                "market reference currency must match the price item currency"
            )
        region_label = validate_region(region)
        min_value = validate_amount(market_min, label="market_min")
        max_value = validate_amount(market_max, label="market_max")
        if min_value > max_value:
            raise PriceBookValidationError("market_min must not exceed market_max")
        reference_value = (
            validate_amount(reference_price, label="reference_price")
            if reference_price is not None
            else None
        )
        checked = normalize_checked_at(checked_at)
        if not sources:
            raise PriceBookValidationError(
                "a market reference requires at least one source"
            )

        reference = PriceMarketReference(
            price_item_id=item.id,
            region=region_label,
            unit=item.unit,
            currency=currency,
            market_min=min_value,
            market_max=max_value,
            reference_price=reference_value,
            methodology_note=methodology_note,
            checked_at=checked,
        )
        for payload in sources:
            reference.sources.append(PriceSource(**validate_source_payload(payload)))
        self.db.add(reference)
        await self.db.commit()
        return reference

    async def get_market_references(
        self,
        owner_id: uuid.UUID,
        price_item_id: uuid.UUID,
    ) -> list[PriceMarketReference]:
        """Return the item's references (newest research first) with sources.

        Ownership is enforced through the parent PriceItem, so foreign ids
        raise the same uniform 404 as the price-item endpoints.
        """
        await self.get_owned_item(owner_id, price_item_id)
        stmt = (
            select(PriceMarketReference)
            .where(PriceMarketReference.price_item_id == price_item_id)
            .options(selectinload(PriceMarketReference.sources))
            .order_by(
                PriceMarketReference.checked_at.desc(),
                PriceMarketReference.created_at.desc(),
            )
        )
        return list((await self.db.execute(stmt)).scalars())

    async def update_market_reference(
        self,
        owner_id: uuid.UUID,
        reference_id: uuid.UUID,
        *,
        market_min: Decimal,
        market_max: Decimal,
        reference_price: Decimal | None = None,
        methodology_note: str | None = None,
        checked_at: datetime,
        sources: list[dict] | None = None,
    ) -> PriceMarketReference:
        """Re-check a reference in place (9E.1 policy); never touches item price.

        ``sources`` replaces the full source set when provided; otherwise the
        existing evidence is preserved.
        """
        reference = (
            await self.db.execute(
                select(PriceMarketReference)
                .join(PriceItem, PriceItem.id == PriceMarketReference.price_item_id)
                .where(
                    PriceMarketReference.id == reference_id,
                    PriceItem.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        if reference is None:
            raise MarketReferenceNotFoundError(
                f"Market reference {reference_id} not found"
            )
        min_value = validate_amount(market_min, label="market_min")
        max_value = validate_amount(market_max, label="market_max")
        if min_value > max_value:
            raise PriceBookValidationError("market_min must not exceed market_max")
        reference.market_min = min_value
        reference.market_max = max_value
        if reference_price is not None:
            reference.reference_price = validate_amount(
                reference_price, label="reference_price"
            )
        if methodology_note is not None:
            reference.methodology_note = methodology_note
        reference.checked_at = normalize_checked_at(checked_at)
        if sources is not None:
            if not sources:
                raise PriceBookValidationError(
                    "a market reference requires at least one source"
                )
            validated = [PriceSource(**validate_source_payload(p)) for p in sources]
            reference.sources.clear()
            reference.sources.extend(validated)
        await self.db.commit()
        return reference