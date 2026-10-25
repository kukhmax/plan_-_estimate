"""The typical items of the trades that work in points and routes (V2-10): an extra to the approved catalog, made in the owner's price book on request.

The approved 49-row catalog (`price_book_seed.py`) is not touched. These twelve rows are made as the owner's own items (a generated `CUSTOM_*` code, no price: "Do ustalenia"),
named in Polish because the names reach the estimate and its documents, which are Polish for the client; the owner renames them freely.
"""
from dataclasses import dataclass

from app.models.price_item import PriceCategory, PriceUnit


@dataclass(frozen=True)
class PackItem:
    display_name: str
    category: PriceCategory
    unit: PriceUnit


POINTS_PACK: tuple[PackItem, ...] = (
    PackItem("Punkt elektryczny - gniazdko / włącznik", PriceCategory.ELECTRICAL, PriceUnit.PCS),
    PackItem("Punkt oświetleniowy", PriceCategory.ELECTRICAL, PriceUnit.PCS),
    PackItem("Bruzda pod przewód", PriceCategory.ELECTRICAL, PriceUnit.LM),
    PackItem("Ułożenie przewodu elektrycznego", PriceCategory.ELECTRICAL, PriceUnit.LM),
    PackItem("Punkt wodny", PriceCategory.PLUMBING, PriceUnit.PCS),
    PackItem("Punkt kanalizacyjny", PriceCategory.PLUMBING, PriceUnit.PCS),
    PackItem("Trasa rurowa", PriceCategory.PLUMBING, PriceUnit.LM),
    PackItem("Układanie płytek", PriceCategory.TILE, PriceUnit.M2),
    PackItem("Fugowanie", PriceCategory.TILE, PriceUnit.M2),
    PackItem("Hydroizolacja pod płytki", PriceCategory.TILE, PriceUnit.M2),
    PackItem("Punkt", PriceCategory.POINTS_ROUTES, PriceUnit.PCS),
    PackItem("Trasa", PriceCategory.POINTS_ROUTES, PriceUnit.LM),
)
