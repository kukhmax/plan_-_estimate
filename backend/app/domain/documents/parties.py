"""From stored data to the party blocks of a document (Stage 15C)."""

from app.domain.documents.layout import Party
from app.domain.rules.polish_identifiers import format_nip
from app.models.executor_profile import ExecutorProfile


def party_from_executor_profile(profile: ExecutorProfile) -> Party:
    """The executor block: name, `NIP`, address as printed (`ul. Długa 1` / `30-001 Kraków`), phone and e-mail."""
    city_line = " ".join(part for part in (profile.postal_code, profile.city) if part)
    address = tuple(line for line in (profile.street, city_line) if line)
    return Party(
        name=profile.name,
        tax_id=format_nip(profile.nip) if profile.nip else None,
        address_lines=address,
        phone=profile.phone,
        email=profile.email,
    )
