"""Fill the empty answers of a draft from what is already known (UX walk B2): never an invented number.

Two sources, both deterministic:

* **facts of this object** -- the day (today in Poland), the place (the city of the object), the VAT rate of its current estimate
  (8 or 23; "zw." and an unset VAT leave the question empty), a private client is a consumer, and the customer in person, when he
  may accept the work, accepts it;
* **the owner's own terms** -- the answers of his latest contract of another object (issued first, else a draft): the warranty,
  the advance, the payment, the penalties, the downtime, the acceptance and the premises are the same for every order, so they are
  carried over exactly as he answered them there.

Only an answer the draft does not have yet is filled; the owner sees every field and changes what he wants before the issue.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

# the answers that describe the owner's way of working, not one object (the same for every order)
STANDARD_TERM_KEYS: tuple[str, ...] = (
    "conclusion_mode",
    "work_hours",
    "price_validity_days",
    "advance_percent",
    "payment_mode",
    "payment_due_days",
    "payment_account",
    "materials_supplier",
    "contractor_representative",
    "insurance_sum",
    "insurance_policy",
    "warranty_months",
    "penalty_mode",
    "penalty_rate_per_day",
    "penalty_cap_percent",
    "downtime_rate_per_day",
    "downtime_cap_percent",
    "downtime_days_limit",
    "customer_appearance_days",
    "partial_acceptance",
    "reinspection_limit",
    "premises_acceptance_notice_days",
    "premises_requirement_values",
)


@dataclass(frozen=True, slots=True)
class PrefillFacts:
    today: date
    place: str | None
    vat_rate_percent: int | None  # the rate of the current estimate (8 / 23), None when it has none
    private_client: bool
    customer_ids: tuple[str, ...]  # active persons of the customer's side in person who may accept the work and sign


def _empty(value: Any) -> bool:
    return value in (None, "", [], {})


def prefill_changes(stored: dict[str, Any], facts: PrefillFacts, terms: dict[str, Any]) -> dict[str, Any]:
    """The answers to add: only the keys the draft has not answered (`stored`, the answers without the catalogue's defaults)."""
    proposed: dict[str, Any] = {
        "contract_date": facts.today.isoformat(),
        "contract_place": facts.place,
        "vat_rate_percent": facts.vat_rate_percent,
        "client_status": "CONSUMER" if facts.private_client else None,
        "who_accepts": list(facts.customer_ids) or None,
    }
    for key in STANDARD_TERM_KEYS:
        proposed[key] = terms.get(key)
    return {key: value for key, value in proposed.items() if not _empty(value) and _empty(stored.get(key))}
