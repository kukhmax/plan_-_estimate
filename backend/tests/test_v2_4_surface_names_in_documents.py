"""V2-4 correction -- the language-neutral names of the surfaces ("Wall 1", "Floor", "Ceiling") are Polish in the documents of the client."""
import pytest

from app.domain.documents.surface_names import surface_title, surface_title_or_none
from tests.test_stage15d_estimate_document import (
    STANDARD,
    build,
    estimate,
    html_of,
    line,
)


@pytest.mark.parametrize(
    "stored,shown",
    [
        ("Wall 1", "Ściana 1"),
        ("Wall 12", "Ściana 12"),
        ("Floor", "Podłoga"),
        ("Ceiling", "Sufit"),
        ("Ściana północna", "Ściana północna"),  # the owner's own name stays
        ("Wall A", "Wall A"),  # not a generated name
        ("wall 1", "wall 1"),
        ("Ceiling 2", "Ceiling 2"),
    ],
)
def test_the_canonical_names_are_translated_and_the_owners_names_are_kept(stored, shown):
    assert surface_title(stored) == shown


def test_a_missing_name_stays_missing():
    assert surface_title_or_none(None) is None
    assert surface_title_or_none("Wall 3") == "Ściana 3"


def test_the_estimate_document_shows_polish_names_of_generated_surfaces():
    lines = [
        line(1, "Gładź gipsowa dwuwarstwowa", "Salon", "Wall 1", "15.12", "20.00"),
        line(2, "Gładź gipsowa dwuwarstwowa", "Salon", "Ceiling", "18.72", "20.00"),
        line(3, "Gładź gipsowa dwuwarstwowa", "Salon", "Wall 2", "10.26", "20.00", opening="Okno 1"),
        line(4, "Gładź gipsowa dwuwarstwowa", "Salon", "Ściana własna", "9.00", "20.00"),
    ]
    doc = build(estimate(lines))
    details = [row.detail for group in doc.groups for row in group.lines]
    assert details == ["Ściana 1", "Sufit", "Ściana 2 · Okno 1", "Ściana własna"]
    html = html_of(doc)
    assert "Wall 1" not in html and "Ceiling" not in html


def test_the_existing_standard_estimate_is_unchanged():
    details = [row.detail for group in build(estimate(STANDARD)).groups for row in group.lines]
    assert details[:2] == ["Ściana A", "Sufit"]
