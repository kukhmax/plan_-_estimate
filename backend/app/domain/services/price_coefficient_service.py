"""Price coefficient catalog domain service (Stage 12C/12D).

Catalog persistence (12C) plus `resolve_assignment_options` (12D), the
single shared validation entry point `SurfaceWorkPlanService` and
`OpeningRevealWorkService` both call to validate a proposed coefficient
selection for one planned-work occurrence -- mirrors how Stage 11's
`accept_recommendation` composes `SurfaceWorkPlanService` directly rather
than duplicating its logic. No Estimate calculation/snapshot exists yet
(Stage 12E). See `docs/stage-12-architecture.md` for the full canonical
contract this module implements.

Bootstrap mirrors `WorkRecommendationService._ensure_bootstrapped` verbatim:
lazy, idempotent, no Alembic data seed. The shipped baseline is the Stage 12G
owner-approved v1 default catalog (`app/domain/data/price_coefficients.py`).
"""
import asyncio
from decimal import Decimal
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.data.price_coefficients import build_baseline_price_coefficients
from app.domain.exceptions import (
    CoefficientGroupNotFoundError,
    CoefficientOptionNotFoundError,
    PriceCoefficientValidationError,
)
from app.models.price_coefficient import (
    CoefficientGroup,
    CoefficientOption,
    CoefficientSelectionMode,
)
from app.models.price_item import PriceItem, PriceScope

# Serializes concurrent first-call bootstraps within the process; the
# (owner_id, code) / (group_id, code) unique constraints guarantee
# correctness even without it -- mirrors the Stage 11 precedent exactly.
_bootstrap_lock = asyncio.Lock()

# Distinguishes "field omitted" from an explicit clear-to-null in a PATCH.
_UNSET = object()

_MIN_PERCENTAGE = Decimal("-100")
_MAX_PERCENTAGE = Decimal("500")


def validate_percentage(value: Decimal) -> Decimal:
    """Validate one option's percentage adjustment.

    Exact Decimal only (no float). Strictly greater than -100 (a single
    option can never represent "the price disappears entirely" -- only a
    *sum* of several legitimate discounts may reach exactly -100%, which is
    validated separately at calculation time in Stage 12E, not here). A
    soft upper bound guards against a fat-fingered entry; both bounds are
    documented recommendations in docs/stage-12-architecture.md Sec 10, not
    an immutable business rule.
    """
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    if not value.is_finite():
        raise PriceCoefficientValidationError(
            "percentage must be a finite decimal number"
        )
    if value.as_tuple().exponent < -3:
        raise PriceCoefficientValidationError(
            "percentage may have at most 3 decimal places (no silent rounding)"
        )
    if value <= _MIN_PERCENTAGE:
        raise PriceCoefficientValidationError(
            f"percentage must be greater than {_MIN_PERCENTAGE}%"
        )
    if value > _MAX_PERCENTAGE:
        raise PriceCoefficientValidationError(
            f"percentage must not exceed {_MAX_PERCENTAGE}%"
        )
    return value


def normalize_description(description: str | None) -> str | None:
    """Stage 12G: descriptions are optional free text; blank means "none"."""
    text = (description or "").strip()
    return text or None


def validate_display_name(display_name: str | None) -> str:
    name = (display_name or "").strip()
    if not name:
        raise PriceCoefficientValidationError("display_name is required")
    return name


class PriceCoefficientService:
    """Owner-scoped operations over the price coefficient catalog."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -- Bootstrap (Stage 12C) ------------------------------------------------

    async def ensure_owner_catalog(self, owner_id: uuid.UUID) -> list[CoefficientGroup]:
        """Materialize any missing baseline groups/options for the owner.

        Idempotent and lazy, mirroring the Stage 11 `WorkRecommendationRule`
        bootstrap precedent exactly: inserts only a `(owner_id, code)` group
        (and, within it, a `(group_id, code)` option) that does not already
        exist; never re-inserts, never overwrites an owner edit, never
        reactivates an archived row. Stage 12G ships the owner-approved v1
        default catalog (`app/domain/data/price_coefficients.py`); an
        existing row's name, description, percentage, `is_base` and archive
        state are never touched once it exists.
        """
        async with _bootstrap_lock:
            baseline = build_baseline_price_coefficients()
            if not baseline:
                return []

            existing_groups = (
                await self.db.execute(
                    select(CoefficientGroup)
                    .options(selectinload(CoefficientGroup.options))
                    .execution_options(populate_existing=True)
                    .where(CoefficientGroup.owner_id == owner_id)
                )
            ).scalars().all()
            groups_by_code = {group.code: group for group in existing_groups}

            created: list[CoefficientGroup] = []
            changed = False
            for group_position, group_data in enumerate(baseline):
                group = groups_by_code.get(group_data.code)
                if group is None:
                    # A brand-new group trivially has no options yet -- never
                    # touch `.options` on a just-flushed object directly
                    # (async sessions disallow the implicit lazy load this
                    # would otherwise require; mirrors EstimateService's own
                    # documented precedent for the identical situation).
                    group = CoefficientGroup(
                        owner_id=owner_id,
                        code=group_data.code,
                        name_key=group_data.name_key,
                        display_name=group_data.display_name,
                        description=group_data.description,
                        selection_mode=CoefficientSelectionMode.SINGLE_SELECT,
                        position=group_position,
                    )
                    self.db.add(group)
                    await self.db.flush()
                    groups_by_code[group.code] = group
                    created.append(group)
                    changed = True
                    existing_option_codes: set[str] = set()
                    has_active_base = False
                else:
                    existing_option_codes = {option.code for option in group.options}
                    has_active_base = any(
                        option.is_base and not option.is_archived
                        for option in group.options
                    )

                for position, option_data in enumerate(group_data.options):
                    if option_data.code in existing_option_codes:
                        continue
                    # Never create a second active base: if the owner already
                    # has one in this group (their own choice), a newly
                    # inserted default joins as an ordinary option.
                    is_base = option_data.is_base and not has_active_base
                    has_active_base = has_active_base or is_base
                    self.db.add(
                        CoefficientOption(
                            group_id=group.id,
                            code=option_data.code,
                            name_key=option_data.name_key,
                            display_name=option_data.display_name,
                            description=option_data.description,
                            percentage=Decimal(option_data.percentage),
                            is_base=is_base,
                            position=position,
                        )
                    )
                    changed = True

            if changed:
                await self.db.commit()
            return created

    # -- Ownership -------------------------------------------------------------

    async def get_owned_group(
        self, owner_id: uuid.UUID, group_id: uuid.UUID, *, with_options: bool = False
    ) -> CoefficientGroup:
        stmt = select(CoefficientGroup).where(
            CoefficientGroup.id == group_id,
            CoefficientGroup.owner_id == owner_id,
        )
        if with_options:
            # populate_existing forces a fresh reload of `options` even when
            # `group` is already identity-mapped in this session with a
            # (possibly stale, e.g. pre-dating a just-created sibling option)
            # collection already considered "loaded" -- selectinload alone
            # does not overwrite already-populated relationship state.
            stmt = stmt.options(selectinload(CoefficientGroup.options))
            stmt = stmt.execution_options(populate_existing=True)
        group = (await self.db.execute(stmt)).scalar_one_or_none()
        if group is None:
            raise CoefficientGroupNotFoundError(
                f"Coefficient group {group_id} not found"
            )
        return group

    async def get_owned_option(
        self, owner_id: uuid.UUID, option_id: uuid.UUID
    ) -> CoefficientOption:
        """Resolve an option strictly through its owner's own group -- never
        a bare option_id."""
        stmt = (
            select(CoefficientOption)
            .join(CoefficientGroup, CoefficientOption.group_id == CoefficientGroup.id)
            .where(
                CoefficientOption.id == option_id,
                CoefficientGroup.owner_id == owner_id,
            )
        )
        option = (await self.db.execute(stmt)).scalar_one_or_none()
        if option is None:
            raise CoefficientOptionNotFoundError(
                f"Coefficient option {option_id} not found"
            )
        return option

    # -- Codes -------------------------------------------------------------------

    async def generate_group_code(self, owner_id: uuid.UUID) -> str:
        """Return a unique, stable CUSTOM_* code for the owner (server-side)."""
        while True:
            code = f"CUSTOM_{uuid.uuid4().hex[:12].upper()}"
            exists = (
                await self.db.execute(
                    select(CoefficientGroup.id).where(
                        CoefficientGroup.owner_id == owner_id,
                        CoefficientGroup.code == code,
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                return code

    async def generate_option_code(self, group_id: uuid.UUID) -> str:
        """Return a unique, stable CUSTOM_* code within the group (server-side)."""
        while True:
            code = f"CUSTOM_{uuid.uuid4().hex[:12].upper()}"
            exists = (
                await self.db.execute(
                    select(CoefficientOption.id).where(
                        CoefficientOption.group_id == group_id,
                        CoefficientOption.code == code,
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                return code

    # -- Group CRUD ----------------------------------------------------------

    async def create_group(
        self,
        owner_id: uuid.UUID,
        *,
        display_name: str,
        description: str | None = None,
    ) -> CoefficientGroup:
        """Create an owner-authored group with a generated, immutable code.

        `selection_mode` is always `SINGLE_SELECT` in Stage 12C -- the only
        mode this cut implements (docs/stage-12-architecture.md Sec 4).
        """
        name = validate_display_name(display_name)
        code = await self.generate_group_code(owner_id)
        group = CoefficientGroup(
            owner_id=owner_id,
            code=code,
            display_name=name,
            description=normalize_description(description),
            selection_mode=CoefficientSelectionMode.SINGLE_SELECT,
        )
        self.db.add(group)
        await self.db.commit()
        return group

    async def update_group(
        self,
        owner_id: uuid.UUID,
        group_id: uuid.UUID,
        *,
        display_name: str | None = None,
        description: str | None | object = _UNSET,
        position: int | None = None,
    ) -> CoefficientGroup:
        """Update editable group fields; `code`/`selection_mode` are immutable
        on this path (Stage 12 architecture D6/Sec 4)."""
        group = await self.get_owned_group(owner_id, group_id)
        if display_name is not None:
            group.display_name = self._resolve_display_name(
                group.name_key, display_name
            )
        if description is not _UNSET:
            group.description = normalize_description(description)  # type: ignore[arg-type]
        if position is not None:
            group.position = position
        await self.db.commit()
        return group

    @staticmethod
    def _resolve_display_name(name_key: str | None, display_name: str | None) -> str | None:
        name = (display_name or "").strip()
        if not name:
            if name_key is not None:
                # Seeded identity: clearing the override reverts to name_key.
                return None
            raise PriceCoefficientValidationError(
                "owner-created groups/options require a display_name"
            )
        return name

    async def archive_group(
        self, owner_id: uuid.UUID, group_id: uuid.UUID
    ) -> CoefficientGroup:
        """Soft-archive an owned group (idempotent); never a hard delete.

        Does not cascade to its options' own archive state -- an option's
        `is_archived` flag remains independent and explicit; an archived
        group simply no longer surfaces in the active-groups list, which
        already makes its options moot for new selection without touching
        them (docs/stage-12-architecture.md Sec 8).
        """
        group = await self.get_owned_group(owner_id, group_id)
        group.is_archived = True
        await self.db.commit()
        return group

    async def restore_group(
        self, owner_id: uuid.UUID, group_id: uuid.UUID
    ) -> CoefficientGroup:
        """Restore an archived owned group (idempotent); explicit, never automatic."""
        group = await self.get_owned_group(owner_id, group_id)
        group.is_archived = False
        await self.db.commit()
        return group

    async def list_owner_groups(
        self,
        owner_id: uuid.UUID,
        *,
        archived: str = "active",
    ) -> list[CoefficientGroup]:
        """Return the owner's catalog with eager-loaded options (no N+1).

        `archived` filters GROUPS: `"active"` (default) / `"archived"` /
        `"all"`. Always eager-loads the FULL `options` relationship
        (archived and active) in one extra query -- callers that only want
        active options (the future coefficient-selection modal) filter at
        render/schema time rather than here, since mutating a SQLAlchemy
        `cascade="all, delete-orphan"` relationship collection in place would
        mark the filtered-out rows for deletion on the next flush. A
        catalog-management screen needs the archived options too, to restore
        them (docs/stage-12-architecture.md Sec 13).
        """
        stmt = (
            select(CoefficientGroup)
            .options(selectinload(CoefficientGroup.options))
            .execution_options(populate_existing=True)
            .where(CoefficientGroup.owner_id == owner_id)
        )
        if archived == "active":
            stmt = stmt.where(CoefficientGroup.is_archived.is_(False))
        elif archived == "archived":
            stmt = stmt.where(CoefficientGroup.is_archived.is_(True))
        stmt = stmt.order_by(CoefficientGroup.position, CoefficientGroup.code)

        return list((await self.db.execute(stmt)).scalars())

    # -- Option CRUD ---------------------------------------------------------

    async def create_option(
        self,
        owner_id: uuid.UUID,
        group_id: uuid.UUID,
        *,
        display_name: str,
        percentage: Decimal,
        is_base: bool = False,
        description: str | None = None,
    ) -> CoefficientOption:
        """Create an option within an owned, active group.

        Setting `is_base=True` atomically clears any other non-archived
        `is_base` option already in the group (Stage 12 architecture Sec 6:
        "at most one" is enforced by replacement, not by a two-step
        unset-then-set dance the owner would have to perform manually).
        """
        group = await self.get_owned_group(owner_id, group_id, with_options=True)
        if group.is_archived:
            raise PriceCoefficientValidationError(
                "cannot add an option to an archived group"
            )
        name = validate_display_name(display_name)
        validated_percentage = validate_percentage(percentage)
        code = await self.generate_option_code(group.id)

        if is_base:
            await self._clear_other_base_options(group, exclude_option_id=None)

        next_position = (
            max((option.position for option in group.options), default=-1) + 1
        )
        option = CoefficientOption(
            group_id=group.id,
            code=code,
            display_name=name,
            description=normalize_description(description),
            percentage=validated_percentage,
            is_base=is_base,
            position=next_position,
        )
        self.db.add(option)
        await self.db.commit()
        return option

    async def update_option(
        self,
        owner_id: uuid.UUID,
        option_id: uuid.UUID,
        *,
        display_name: str | None = None,
        description: str | None | object = _UNSET,
        percentage: Decimal | None = None,
        is_base: bool | None = None,
        position: int | None = None,
    ) -> CoefficientOption:
        """Update editable option fields; `code` is immutable on this path.

        Changing a percentage here never touches any already-generated
        Estimate snapshot -- Stage 12C has no Estimate integration at all,
        and Stage 12E's own contract (docs/stage-12-architecture.md Sec 12)
        keeps historical snapshots immutable regardless of later catalog
        edits.
        """
        option = await self.get_owned_option(owner_id, option_id)
        if display_name is not None:
            option.display_name = self._resolve_display_name(
                option.name_key, display_name
            )
        if description is not _UNSET:
            option.description = normalize_description(description)  # type: ignore[arg-type]
        if percentage is not None:
            option.percentage = validate_percentage(percentage)
        if is_base is not None:
            if is_base and not option.is_base:
                group = await self.get_owned_group(
                    owner_id, option.group_id, with_options=True
                )
                await self._clear_other_base_options(
                    group, exclude_option_id=option.id
                )
            option.is_base = is_base
        if position is not None:
            option.position = position
        await self.db.commit()
        return option

    async def _clear_other_base_options(
        self, group: CoefficientGroup, *, exclude_option_id: uuid.UUID | None
    ) -> None:
        """Enforce "at most one active base option per group" by atomic
        replacement: any other non-archived `is_base` option in the group is
        demoted to `is_base=False` in the same transaction. Archived base
        options are left untouched (their historical `is_base` state is not
        retroactively rewritten by a new selection elsewhere)."""
        for option in group.options:
            if option.id == exclude_option_id:
                continue
            if option.is_base and not option.is_archived:
                option.is_base = False

    async def archive_option(
        self, owner_id: uuid.UUID, option_id: uuid.UUID
    ) -> CoefficientOption:
        """Soft-archive an owned option (idempotent); never a hard delete.

        Archiving the current base option does not auto-promote another
        option to base -- the group simply has zero active base options
        until the owner explicitly designates a new one (Stage 12
        architecture: explicit application only, D10).
        """
        option = await self.get_owned_option(owner_id, option_id)
        option.is_archived = True
        await self.db.commit()
        return option

    async def restore_option(
        self, owner_id: uuid.UUID, option_id: uuid.UUID
    ) -> CoefficientOption:
        """Restore an archived owned option (idempotent); explicit, never automatic."""
        option = await self.get_owned_option(owner_id, option_id)
        option.is_archived = False
        await self.db.commit()
        return option

    # -- Planned-work assignment validation (Stage 12D) -----------------------

    async def resolve_assignment_options(
        self,
        owner_id: uuid.UUID,
        price_item: PriceItem,
        coefficient_option_ids: list[uuid.UUID],
    ) -> list[CoefficientOption]:
        """Validate a proposed coefficient selection for ONE planned-work
        occurrence and return the resolved, owner-scoped `CoefficientOption`
        rows (each with `.group` eager-loaded). Called by
        `SurfaceWorkPlanService`/`OpeningRevealWorkService` BEFORE any
        WorkPlan mutation begins -- never after -- so an invalid selection
        never leaves a partially-mutated plan (Stage 12 architecture Sec 14).

        Never persists anything and never commits; this is a pure read/
        validate step. Performs NO arithmetic (no percentage sum, no
        effective price) -- that is Stage 12E's job entirely.

        Raises `PriceCoefficientValidationError` for:
        - a `price_item` whose `price_scope` is not `LABOR` (D3 -- both
          `MATERIAL` and `LABOR_AND_MATERIAL` are rejected in this cut,
          since no reliable labor/material price split exists today); an
          EMPTY `coefficient_option_ids` is always valid regardless of
          scope (only *assigning* a coefficient is scope-gated, never
          planning a MATERIAL/mixed work item as such)
        - a duplicate id in the same selection
        - two options from the same `SINGLE_SELECT` group
        - an archived option, or an option whose group is archived

        Raises `CoefficientOptionNotFoundError` for an id that does not
        resolve to an ACTIVE option owned by `owner_id` -- this uniformly
        covers a nonexistent id, an option belonging to a different owner,
        and (except where explicitly allowed by a caller) any other
        resolution failure, per the project's uniform not-found convention.
        """
        if not coefficient_option_ids:
            return []

        if price_item.price_scope != PriceScope.LABOR:
            raise PriceCoefficientValidationError(
                "coefficient assignment requires a LABOR price item "
                f"(price item {price_item.id} has price_scope="
                f"{price_item.price_scope.value})"
            )

        if len(set(coefficient_option_ids)) != len(coefficient_option_ids):
            raise PriceCoefficientValidationError(
                "duplicate coefficient_option_id in the same planned-work selection"
            )

        stmt = (
            select(CoefficientOption)
            .options(selectinload(CoefficientOption.group))
            .join(CoefficientGroup, CoefficientOption.group_id == CoefficientGroup.id)
            .where(
                CoefficientOption.id.in_(coefficient_option_ids),
                CoefficientGroup.owner_id == owner_id,
            )
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        by_id = {row.id: row for row in rows}

        resolved: list[CoefficientOption] = []
        selected_group_option: dict[uuid.UUID, uuid.UUID] = {}
        for option_id in coefficient_option_ids:
            option = by_id.get(option_id)
            if option is None:
                raise CoefficientOptionNotFoundError(
                    f"Coefficient option {option_id} not found"
                )
            if option.is_archived:
                raise PriceCoefficientValidationError(
                    f"Coefficient option {option_id} is archived and cannot "
                    "be newly assigned"
                )
            if option.group.is_archived:
                raise PriceCoefficientValidationError(
                    f"Coefficient option {option_id}'s group is archived and "
                    "cannot be newly assigned"
                )
            if option.group.selection_mode == CoefficientSelectionMode.SINGLE_SELECT:
                existing = selected_group_option.get(option.group_id)
                if existing is not None and existing != option.id:
                    raise PriceCoefficientValidationError(
                        f"Only one option from group {option.group_id} may be "
                        "selected per planned-work occurrence"
                    )
                selected_group_option[option.group_id] = option.id
            resolved.append(option)
        return resolved
