"""V2-12a -- the hidden utilities in the PDFs: the colour of a marker and of its contour follow the type, the legend says what it is and where it lies
(docs/V2_12A_PLAN_RU.md). The geometry itself is the one of Stage 15E."""
import uuid

from app.domain.documents.photo_report_document import (
    DEFAULT_MARKER_COLOR,
    UTILITY_COLORS,
    legend_entries,
    marker_color,
    marker_shapes,
    outline_shapes,
)
from app.domain.services.photo_report_read_model import ReportMarker

LOOP = ((0.1, 0.1), (0.4, 0.2), (0.6, 0.5))


def mark(label=None, utility=None, depth=None, floor=None, corner=None, outline=None, position=0):
    return ReportMarker(uuid.uuid4(), 0.5, 0.5, label, position, outline, utility, depth, floor, corner)


def test_the_palette_has_a_colour_for_every_type_and_the_screen_uses_the_same_ones():
    from app.models.photo_annotation import UTILITY_VALUES

    assert set(UTILITY_COLORS) == set(UTILITY_VALUES)
    assert len(set(UTILITY_COLORS.values())) == len(UTILITY_VALUES)
    import re
    from pathlib import Path

    screen = (Path(__file__).resolve().parents[2] / "frontend/src/utils/photoUtilities.ts").read_text(encoding="utf-8")
    for kind, color in UTILITY_COLORS.items():
        assert re.search(rf"{kind}: '{color}'", screen), kind


def test_a_marker_and_its_contour_take_the_colour_of_their_type_an_ordinary_one_stays_red():
    markers = (mark(utility="WATER_COLD", outline=LOOP), mark(utility="CABLE", outline=LOOP), mark(outline=LOOP), mark(utility="nope"))
    assert [m.fill for m in marker_shapes(markers, 1000, 750)] == [UTILITY_COLORS["WATER_COLD"], UTILITY_COLORS["CABLE"], DEFAULT_MARKER_COLOR, DEFAULT_MARKER_COLOR]
    assert [o.color for o in outline_shapes(markers, 1000, 750)] == [UTILITY_COLORS["WATER_COLD"], UTILITY_COLORS["CABLE"], DEFAULT_MARKER_COLOR]
    assert marker_color(mark(utility="GAS")) == UTILITY_COLORS["GAS"]


def test_the_legend_says_the_type_the_label_and_where_in_polish():
    entries = legend_entries((
        mark("do gniazda", "CABLE", depth=3, floor=30, corner=12.5),
        mark(utility="WATER_HOT", floor=40),
        mark("rysa"),
        mark(),
        mark(utility="SEWER", depth=2.5),
    ))
    assert entries == (
        (1, "przewód elektryczny · do gniazda · od podłogi 30 cm · od narożnika 12,5 cm · głębokość 3 cm"),
        (2, "woda ciepła · od podłogi 40 cm"),
        (3, "rysa"),
        (4, None),
        (5, "kanalizacja · głębokość 2,5 cm"),
    )
    for kind, word in (("WATER_COLD", "woda zimna"), ("HEATING", "ogrzewanie"), ("GAS", "gaz")):
        assert legend_entries((mark(utility=kind),)) == ((1, word),)
