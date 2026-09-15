"""Approved 44-row Price Book catalog + market evidence seeds (Stage 9E.7).

Replaces the Stage 9B technical placeholder set (4 GENERIC rows with
1.11/2.22/3.33/4.44 placeholder prices) with the owner-approved 9E.5 catalog:
28 MARKET_SUPPORTED rows + 16 OWN_PRICE rows, every one seeded with
``price=None`` (owner commercial price not set yet; NULL is the canonical
"do ustalenia" state, 0.00 is a real explicit zero and is never reused as a
sentinel).

The invariant OWNER PRICE != MARKET RANGE != SOURCE QUOTED PRICE is enforced
by the data itself: no seed carries a price, ``reference_price`` in a
``MarketReferenceSeed`` is evidence-only, and each ``PriceSourceSeed`` keeps
the verbatim quote read from the researched page. Every URL below is copied
from ``docs/price-research-batch-{a..e}.md`` / ``docs/price-research-catalog.md``
— none is reconstructed. Source-type labels seen in the research docs map to
the 7-member DB enum (e.g. NATIONAL_PRICE_ARTICLE / CITY_PRICE_TABLE /
INDUSTRY_ARTICLE all become ``SourceType.INDUSTRY_ARTICLE``; MARKETPLACE
variants become ``SourceType.MARKETPLACE``; CONTRACTOR_PRICE_LIST and
MANUFACTURER pass through).
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from app.models.checklist import QualityLevel
from app.models.market_evidence import SourceType
from app.models.price_item import PriceCategory, PriceScope, PriceUnit


@dataclass(frozen=True)
class PriceItemSeed:
    code: str
    category: PriceCategory
    unit: PriceUnit
    name_key: str
    price: str | None = None
    price_scope: PriceScope = PriceScope.LABOR
    quality_level: QualityLevel | None = None


@dataclass(frozen=True)
class PriceSourceSeed:
    source_name: str
    source_type: SourceType
    source_url: str
    quoted_price_min: str | None = None
    quoted_price_max: str | None = None
    quoted_price_single: str | None = None
    quoted_unit: PriceUnit | None = None
    note: str | None = None


@dataclass(frozen=True)
class MarketReferenceSeed:
    """Approved evidence window for one MARKET_SUPPORTED row.

    ``region`` is one of the three canonical labels (Kraków / Małopolskie /
    Kraków / Małopolskie); ``checked_at`` follows the research dates (Batch A
    2026-09-13, Batches B/C/D/E 2026-09-14).
    """

    code: str
    region: str
    unit: PriceUnit
    market_min: str
    market_max: str
    reference_price: str | None = None
    methodology_note: str | None = None
    checked_at: datetime | None = None
    sources: tuple[PriceSourceSeed, ...] = ()


def _d(iso_date: str) -> datetime:
    """UTC datetime helper for the fixed research `checked_at` dates."""
    y, m, d = (int(p) for p in iso_date.split("-"))
    return datetime(y, m, d, tzinfo=timezone.utc)


_BATCH_A = _d("2026-09-13")
_BATCH_BD = _d("2026-09-14")


def _item(
    code: str,
    category: PriceCategory,
    unit: PriceUnit,
    name_key: str,
    *,
    price_scope: PriceScope = PriceScope.LABOR,
    quality_level: QualityLevel | None = None,
) -> PriceItemSeed:
    return PriceItemSeed(
        code=code,
        category=category,
        unit=unit,
        name_key=name_key,
        price=None,
        price_scope=price_scope,
        quality_level=quality_level,
    )


def build_approved_price_book_items() -> list[PriceItemSeed]:
    """Return the owner-approved 44-row catalog (28 MS / 16 OWN_PRICE).

    Every row seeds with ``price=None``; category/unit/scope come from the
    catalog §16.3 as amended by the 9E.5 decisions (§17.1–17.3). Quality is
    seeded only where the catalog records a single unambiguous tier
    (GK_FULL → Q3, GK_Q4 → Q4); dual-tier hints (GK_JOINT Q1/Q2, SKIM_SQ
    S3/S4) stay NULL because the single-value enum cannot represent a range.
    """
    return [
        # ---- PREPARATION (11) ----
        _item("CENNIK_PREP_PROT-01", PriceCategory.PREPARATION, PriceUnit.M2, "pricebook.seed.prep_prot"),
        _item("CENNIK_PREP_WALLP-01", PriceCategory.PREPARATION, PriceUnit.M2, "pricebook.seed.prep_wallp"),
        _item("CENNIK_PREP_SCRAPE-01", PriceCategory.PREPARATION, PriceUnit.M2, "pricebook.seed.prep_scrape"),
        _item("CENNIK_PREP_FLEECE-01", PriceCategory.PREPARATION, PriceUnit.M2, "pricebook.seed.prep_fleece"),
        _item("CENNIK_PREP_DEGR-01", PriceCategory.PREPARATION, PriceUnit.M2, "pricebook.seed.prep_degr"),
        _item(
            "CENNIK_PREP_MOLD-01",
            PriceCategory.PREPARATION,
            PriceUnit.M2,
            "pricebook.seed.prep_mold",
            price_scope=PriceScope.LABOR_AND_MATERIAL,
        ),
        _item("CENNIK_PREP_CLEAN-01", PriceCategory.PREPARATION, PriceUnit.M2, "pricebook.seed.prep_clean"),
        _item(
            "CENNIK_PRIM_STD-01",
            PriceCategory.PREPARATION,
            PriceUnit.M2,
            "pricebook.seed.prim_std",
            price_scope=PriceScope.LABOR_AND_MATERIAL,
        ),
        _item(
            "CENNIK_PRIM_ADH-01",
            PriceCategory.PREPARATION,
            PriceUnit.M2,
            "pricebook.seed.prim_adh",
            price_scope=PriceScope.LABOR_AND_MATERIAL,
        ),
        _item(
            "CENNIK_PRIM_HIGH-01",
            PriceCategory.PREPARATION,
            PriceUnit.M2,
            "pricebook.seed.prim_high",
            price_scope=PriceScope.LABOR_AND_MATERIAL,
        ),
        _item(
            "CENNIK_PRIM_PAINT-01",
            PriceCategory.PREPARATION,
            PriceUnit.M2,
            "pricebook.seed.prim_paint",
            price_scope=PriceScope.LABOR_AND_MATERIAL,
        ),
        # ---- SKIM_COAT (7) ----
        _item("CENNIK_SKIM_1L-01", PriceCategory.SKIM_COAT, PriceUnit.M2, "pricebook.seed.skim_1l"),
        _item("CENNIK_SKIM_2L-01", PriceCategory.SKIM_COAT, PriceUnit.M2, "pricebook.seed.skim_2l"),
        _item("CENNIK_SKIM_SAND-01", PriceCategory.SKIM_COAT, PriceUnit.M2, "pricebook.seed.skim_sand"),
        _item("CENNIK_SKIM_CRACK-01", PriceCategory.SKIM_COAT, PriceUnit.LM, "pricebook.seed.skim_crack"),
        _item("CENNIK_SKIM_CORNER-01", PriceCategory.SKIM_COAT, PriceUnit.LM, "pricebook.seed.skim_corner"),
        _item("CENNIK_SKIM_LOCAL-01", PriceCategory.SKIM_COAT, PriceUnit.M2, "pricebook.seed.skim_local"),
        _item("CENNIK_SKIM_SQ-01", PriceCategory.SKIM_COAT, PriceUnit.M2, "pricebook.seed.skim_sq"),
        # ---- DRYWALL (5) ----
        _item("CENNIK_GK_JOINT-01", PriceCategory.DRYWALL, PriceUnit.LM, "pricebook.seed.gk_joint"),
        _item(
            "CENNIK_GK_FULL-01",
            PriceCategory.DRYWALL,
            PriceUnit.M2,
            "pricebook.seed.gk_full",
            quality_level=QualityLevel.Q3,
        ),
        _item("CENNIK_GK_SCREW-01", PriceCategory.DRYWALL, PriceUnit.M2, "pricebook.seed.gk_screw"),
        _item("CENNIK_GK_CORNER-01", PriceCategory.DRYWALL, PriceUnit.LM, "pricebook.seed.gk_corner"),
        _item(
            "CENNIK_GK_Q4-01",
            PriceCategory.DRYWALL,
            PriceUnit.M2,
            "pricebook.seed.gk_q4",
            quality_level=QualityLevel.Q4,
        ),
        # ---- GLASS_FIBER (3) ----
        _item("CENNIK_GF_FLIZ_L-01", PriceCategory.GLASS_FIBER, PriceUnit.M2, "pricebook.seed.gf_fliz_l"),
        _item(
            "CENNIK_GF_FLIZ_M-01",
            PriceCategory.GLASS_FIBER,
            PriceUnit.M2,
            "pricebook.seed.gf_fliz_m",
            price_scope=PriceScope.LABOR_AND_MATERIAL,
        ),
        _item("CENNIK_GF_MESH-01", PriceCategory.GLASS_FIBER, PriceUnit.M2, "pricebook.seed.gf_mesh"),
        # ---- PAINTING (7) ----
        _item("CENNIK_PAINT_2K-01", PriceCategory.PAINTING, PriceUnit.M2, "pricebook.seed.paint_2k"),
        _item("CENNIK_PAINT_1K-01", PriceCategory.PAINTING, PriceUnit.M2, "pricebook.seed.paint_1k"),
        _item("CENNIK_PAINT_3K-01", PriceCategory.PAINTING, PriceUnit.M2, "pricebook.seed.paint_3k"),
        _item("CENNIK_PAINT_CEIL-01", PriceCategory.PAINTING, PriceUnit.M2, "pricebook.seed.paint_ceil"),
        _item("CENNIK_PAINT_COL-01", PriceCategory.PAINTING, PriceUnit.M2, "pricebook.seed.paint_col"),
        _item("CENNIK_PAINT_MASK-01", PriceCategory.PAINTING, PriceUnit.M2, "pricebook.seed.paint_mask"),
        _item("CENNIK_PAINT_MULTI-01", PriceCategory.PAINTING, PriceUnit.M2, "pricebook.seed.paint_multi"),
        # ---- REVEAL (1) ----
        _item("CENNIK_REV_WORK_LM-01", PriceCategory.REVEAL, PriceUnit.LM, "pricebook.seed.rev_work_lm"),
        # ---- MICROCEMENT (6) ----
        _item("CENNIK_MC_WALL_L-01", PriceCategory.MICROCEMENT, PriceUnit.M2, "pricebook.seed.mc_wall_l"),
        _item(
            "CENNIK_MC_WALL_S-01",
            PriceCategory.MICROCEMENT,
            PriceUnit.M2,
            "pricebook.seed.mc_wall_s",
            price_scope=PriceScope.LABOR_AND_MATERIAL,
        ),
        _item("CENNIK_MC_FLOOR_L-01", PriceCategory.MICROCEMENT, PriceUnit.M2, "pricebook.seed.mc_floor_l"),
        _item(
            "CENNIK_MC_FLOOR_S-01",
            PriceCategory.MICROCEMENT,
            PriceUnit.M2,
            "pricebook.seed.mc_floor_s",
            price_scope=PriceScope.LABOR_AND_MATERIAL,
        ),
        _item(
            "CENNIK_MC_SHOWER-01",
            PriceCategory.MICROCEMENT,
            PriceUnit.M2,
            "pricebook.seed.mc_shower",
            price_scope=PriceScope.LABOR_AND_MATERIAL,
        ),
        _item(
            "CENNIK_MC_STAIRS-01",
            PriceCategory.MICROCEMENT,
            PriceUnit.PCS,
            "pricebook.seed.mc_stairs",
            price_scope=PriceScope.LABOR_AND_MATERIAL,
        ),
        # ---- DECORATIVE (4) ----
        _item("CENNIK_DEC_VEN-01", PriceCategory.DECORATIVE, PriceUnit.M2, "pricebook.seed.dec_ven"),
        _item("CENNIK_DEC_VEN_MAR-01", PriceCategory.DECORATIVE, PriceUnit.M2, "pricebook.seed.dec_ven_mar"),
        _item("CENNIK_DEC_CONC-01", PriceCategory.DECORATIVE, PriceUnit.M2, "pricebook.seed.dec_conc"),
        _item("CENNIK_DEC_GENERIC-01", PriceCategory.DECORATIVE, PriceUnit.M2, "pricebook.seed.dec_generic"),
    ]


def _src(
    name: str,
    type_: SourceType,
    url: str,
    *,
    min_: str | None = None,
    max_: str | None = None,
    single: str | None = None,
    unit: PriceUnit | None = None,
    note: str | None = None,
) -> PriceSourceSeed:
    return PriceSourceSeed(
        source_name=name,
        source_type=type_,
        source_url=url,
        quoted_price_min=min_,
        quoted_price_max=max_,
        quoted_price_single=single,
        quoted_unit=unit,
        note=note,
    )


def _ref(
    code: str,
    region: str,
    unit: PriceUnit,
    market_min: str,
    market_max: str,
    *,
    reference_price: str | None = None,
    methodology_note: str | None = None,
    checked_at: datetime,
    sources: tuple[PriceSourceSeed, ...],
) -> MarketReferenceSeed:
    return MarketReferenceSeed(
        code=code,
        region=region,
        unit=unit,
        market_min=market_min,
        market_max=market_max,
        reference_price=reference_price,
        methodology_note=methodology_note,
        checked_at=checked_at,
        sources=sources,
    )


def build_approved_market_references() -> dict[str, MarketReferenceSeed]:
    """Return the approved evidence per MARKET_SUPPORTED row, keyed by code.

    Only the 28 MARKET_SUPPORTED rows appear; the 16 OWN_PRICE rows get no
    evidence (UI keeps "Brak danych rynkowych"). Reference windows/regions come
    from the approved catalog §16.3/§17.3; every source quote is verbatim.
    """
    refs: list[MarketReferenceSeed] = []

    refs.append(
        _ref(
            "CENNIK_PREP_WALLP-01",
            "Kraków",
            PriceUnit.M2,
            "10",
            "30",
            reference_price="20",
            methodology_note=(
                "Labor per m²; Kraków floor (od 10) + three national portals agree in the 16–30 "
                "band. Multi-layer/fiberglass tiers map to PREP_FLEECE."
            ),
            checked_at=_BATCH_A,
            sources=(
                _src(
                    "Malarz Kraków — cennik",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://malarzkrakow.pl/cennik/",
                    single="10",
                    unit=PriceUnit.M2,
                    note="Zrywanie tapet (jedna warstwa) — od 10 zł/m² (labor, net rate)",
                ),
                _src(
                    "KB.pl — cennik zrywania tapet",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://kb.pl/cenniki/uslugi/cennik-zrywania-tapet-ze-scian-w-czasie-remontu/",
                    min_="18",
                    max_="22",
                    unit=PriceUnit.M2,
                    note="Normalny stopień 18,00–22,00 zł/m²; wyższy stopień 22,00–38,00",
                ),
                _src(
                    "CenaUsług — usuwanie starych tapet",
                    SourceType.MARKETPLACE,
                    "https://cenauslug.pl/budowa-i-remont/usuwanie-starych-tapet",
                    min_="16",
                    max_="24",
                    unit=PriceUnit.M2,
                    note="16–24 zł/m² (średnio 19); cena nie zawiera materiałów",
                ),
                _src(
                    "T-Tapety — zdzieranie tapety cena",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://t-tapety.pl/zdzieranie-tapety-cena",
                    min_="10",
                    max_="15",
                    unit=PriceUnit.M2,
                    note=(
                        "Papierowa luźna 10–15; winylowa 20–30; fiberglassowa/wielowarstwowa "
                        "35–50 → PREP_FLEECE, nie ten wiersz"
                    ),
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_PREP_SCRAPE-01",
            "Kraków",
            PriceUnit.M2,
            "10",
            "35",
            reference_price="18",
            methodology_note=(
                "Manual scraping of old paints/old chalk skim to substrate; oil-paint and "
                "mechanical/chemical tiers excluded per catalog §3 comparability."
            ),
            checked_at=_BATCH_A,
            sources=(
                _src(
                    "Malarz Kraków — cennik",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://malarzkrakow.pl/cennik/",
                    single="10",
                    unit=PriceUnit.M2,
                    note="Skrobanie starych powłok malarskich — od 10 zł/m² (labor)",
                ),
                _src(
                    "KB.pl — cena gruntowania (table)",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://kb.pl/cenniki/uslugi/cena-gruntowania-scian-i-sufitu-przed-malowaniem-za-m2/",
                    min_="12",
                    max_="17",
                    unit=PriceUnit.M2,
                    note="Usuwanie starych powłok malarskich 12,00–17,00 zł/m² (brutto, 8% VAT)",
                ),
                _src(
                    "Mocny Fundament — przygotowanie ścian do malowania",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://mocnyfundament.pl/ile-kosztuje-przygotowanie-scian-i-sufitu-do-malowania-gladzie-gruntowanie-usuwanie-starych-powlok/",
                    min_="10",
                    max_="25",
                    unit=PriceUnit.M2,
                    note="Skrobanie farby (emulsyjna, akrylowa) 10–25 zł/m²; olejna 20–40 (wył.)",
                ),
                _src(
                    "Aikfarby — zdzieranie starej farby cennik",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://aikfarby.pl/zdzieranie-starej-farby-cennik",
                    min_="22",
                    max_="35",
                    unit=PriceUnit.M2,
                    note="Zdzieranie ręczne 22–35 zł/m²; mechaniczne 38–55 (wył.)",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_PREP_MOLD-01",
            "Małopolskie",
            PriceUnit.M2,
            "30",
            "120",
            methodology_note=(
                "Labor + biocide material incl. (LABOR_AND_MATERIAL); area-scaled ladder daart "
                "30–120, NewBridge 50–150 bundled. Labor-only rows kept as context, not merged."
            ),
            checked_at=_BATCH_A,
            sources=(
                _src(
                    "Daart — odgrzybianie cena za m²",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://daart.pl/odgrzybianie-scian-cena-za-m2",
                    min_="30",
                    max_="120",
                    unit=PriceUnit.M2,
                    note=(
                        "Od ok. 30 do 120 zł/m²; area tiers: do 5 m² 30–50; 5–15 m² 50–80; "
                        "15–30 m² 80–100; >30 m² 100–120 (L+M, atestowane środki wliczone)"
                    ),
                ),
                _src(
                    "CenaUsług — odgrzybianie ścian",
                    SourceType.MARKETPLACE,
                    "https://cenauslug.pl/budowa-i-remont/odgrzybianie-scian",
                    min_="52",
                    max_="75",
                    unit=PriceUnit.M2,
                    note="52–75 zł/m², średnia 60 — robocizna, bez materiałów (kontekst LABOR)",
                ),
                _src(
                    "New Bridge — odgrzybianie cena za m²",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://newbridge.com.pl/odgrzybianie-cena-za-m2/",
                    min_="50",
                    max_="150",
                    unit=PriceUnit.M2,
                    note="Średnie ceny od 50 do 150 zł/m²; głębokie (skucie) 200–350 — usługa zbiorcza",
                ),
                _src(
                    "Mocny Fundament — przygotowanie ścian",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://mocnyfundament.pl/ile-kosztuje-przygotowanie-scian-i-sufitu-do-malowania-gladzie-gruntowanie-usuwanie-starych-powlok/",
                    min_="15",
                    max_="30",
                    unit=PriceUnit.M2,
                    note="Usuwanie grzyba lub pleśni 15–30 zł/m² — robocizna, materiał płatny osobno",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_PRIM_STD-01",
            "Kraków",
            PriceUnit.M2,
            "7",
            "15",
            methodology_note=(
                "Labor + penetrating grunt material (LABOR_AND_MATERIAL). Two L+M-explicit "
                "sources (zleca 7–15, NewBridge split ~8–13) anchor the band; the abundant "
                "labor rows stay labor anchors (kb.pl Kraków 7,73 brutto; malarzkrakow od 5)."
            ),
            checked_at=_BATCH_A,
            sources=(
                _src(
                    "KB.pl — gruntowanie ścian przed malowaniem (table by city)",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://kb.pl/cenniki/gruntowanie-scian-przed-malowaniem/",
                    single="7.73",
                    unit=PriceUnit.M2,
                    note="Kraków 7,73 zł/m² brutto (robocizna); małopolskie 6,68–7,73; krajowa 6,95",
                ),
                _src(
                    "KB.pl — cena gruntowania przed malowaniem (article table)",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://kb.pl/cenniki/uslugi/cena-gruntowania-scian-i-sufitu-przed-malowaniem-za-m2/",
                    min_="9",
                    max_="15",
                    unit=PriceUnit.M2,
                    note="Gruntowanie przed malowaniem (jednokrotne) 9,00–15,00 zł/m² (robocizna)",
                ),
                _src(
                    "Malarz Kraków — cennik",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://malarzkrakow.pl/cennik/",
                    single="5",
                    unit=PriceUnit.M2,
                    note="Gruntowanie ścian i sufitów — od 5 zł/m² (Kraków floor, labor)",
                ),
                _src(
                    "Zleca.pl — gruntowanie ściany",
                    SourceType.MARKETPLACE,
                    "https://zleca.pl/cennik/gruntowanie-sciany-cena",
                    min_="7",
                    max_="15",
                    unit=PriceUnit.M2,
                    note="Z materiałem ok. 7–15 zł/m²; sama robocizna 4–10 zł/m²",
                ),
                _src(
                    "New Bridge — gruntowanie cena za m²",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://newbridge.com.pl/gruntowanie-cena-za-m2/",
                    min_="5",
                    max_="8",
                    unit=PriceUnit.M2,
                    note="Jedna warstwa 5–8 zł/m² robocizna + materiał grunt ok. 3–5 zł/m²",
                ),
                _src(
                    "WZBudowa — cennik usług malarskich",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://wzbudowa.pl/cennik-uslug-malarskich/",
                    min_="6",
                    max_="12",
                    unit=PriceUnit.M2,
                    note="Gruntowanie ścian i sufitów ok. 6–12 zł/m²",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_PRIM_PAINT-01",
            "Kraków",
            PriceUnit.M2,
            "3",
            "15",
            methodology_note=(
                "Labor + primer under paint on a smoothed substrate (LABOR_AND_MATERIAL); "
                "two L+M-explicit rows (zleca 7–15, MocnyFundament 3–8). Kraków labor rows "
                "anchor the labor side; kb.pl city row counted once across PRIM_STD/PRIM_PAINT."
            ),
            checked_at=_BATCH_A,
            sources=(
                _src(
                    "KB.pl — gruntowanie ścian przed malowaniem (table by city)",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://kb.pl/cenniki/gruntowanie-scian-przed-malowaniem/",
                    single="7.73",
                    unit=PriceUnit.M2,
                    note="Kraków 7,73 zł/m² brutto (robocizna); liczone razem z PRIM_STD",
                ),
                _src(
                    "TOTALDECOR Kraków — cennik",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://totaldecor.pl/cennik/",
                    single="8",
                    unit=PriceUnit.M2,
                    note="Przygotowanie ścian i gruntowanie — 8 zł/m² (wiersz zbiorczy)",
                ),
                _src(
                    "kubamalarz.pl — cennik",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://kubamalarz.pl/cennik/",
                    single="8",
                    unit=PriceUnit.M2,
                    note="Gruntowanie ścian od 8 zł/m2",
                ),
                _src(
                    "Zleca.pl — gruntowanie ściany",
                    SourceType.MARKETPLACE,
                    "https://zleca.pl/cennik/gruntowanie-sciany-cena",
                    min_="7",
                    max_="15",
                    unit=PriceUnit.M2,
                    note="Z materiałem ok. 7–15 zł/m²; sama robocizna 4–10 zł/m²",
                ),
                _src(
                    "Cennik Remontów — malowanie Kraków 2026",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://cennikremontow.pl/malowanie-krakow-cennik",
                    min_="4",
                    max_="16",
                    unit=PriceUnit.M2,
                    note="Gruntowanie 4–16 zł/m² (niespójne w obrębie strony)",
                ),
                _src(
                    "Mocny Fundament — przygotowanie ścian",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://mocnyfundament.pl/ile-kosztuje-przygotowanie-scian-i-sufitu-do-malowania-gladzie-gruntowanie-usuwanie-starych-powlok/",
                    min_="3",
                    max_="8",
                    unit=PriceUnit.M2,
                    note="FAQ: 3–8 zł/m² wliczając materiał i robociznę (L+M)",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_SKIM_1L-01",
            "Kraków",
            PriceUnit.M2,
            "30",
            "50",
            reference_price="40",
            methodology_note=(
                "One full-surface skim coat, LABOR, no sanding. Kraków table 35–50 anchors; "
                "kb.pl 30–45; idealny-sufit 15–25 kept only as flagged low outlier."
            ),
            checked_at=_BATCH_A,
            sources=(
                _src(
                    "S-Szpachlowanie — cennik szpachlowania Kraków",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://s-szpachlowanie.pl/szpachlowanie-krakow-cennik",
                    min_="35",
                    max_="50",
                    unit=PriceUnit.M2,
                    note="Gładzenie jednokrotne (1 warstwa) 35–50 zł/m², 0,4–0,6 h/m² (bez szlifu)",
                ),
                _src(
                    "KB.pl — cennik gładzi gipsowej i szpachlowania",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://kb.pl/cenniki/uslugi/cennik-gladzi-gipsowej-i-szpachlowania-scian-w-calej-polsce/",
                    min_="30",
                    max_="45",
                    unit=PriceUnit.M2,
                    note="Szpachlowanie 1x 30,00–45,00 zł/m² (robocizna); z materiałem 38–55",
                ),
                _src(
                    "sccot.pl — ile kosztuje szpachlowanie ścian",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://sccot.pl/dobra-robota/ile-kosztuje-szpachlowanie-scian/",
                    min_="40",
                    max_="60",
                    unit=PriceUnit.M2,
                    note="Szpachlowanie 1x 40–60 zł/m² (całkowity koszt — częściowo porównywalny)",
                ),
                _src(
                    "Idealny-Sufit — gładź szpachlowa cena robocizny",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://idealny-sufit.pl/gladz-szpachlowa-cena-robocizny",
                    min_="15",
                    max_="25",
                    unit=PriceUnit.M2,
                    note="Jedna warstwa 15–25 zł/m² — flagowany niski outlier",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_SKIM_2L-01",
            "Kraków",
            PriceUnit.M2,
            "35",
            "75",
            reference_price="55",
            methodology_note=(
                "Two full-surface skim coats, LABOR, without sanding. Kraków 55–75 and "
                "40–70 (CennikiBudowlane Kraków) define the local band; kb.pl 35–54 low edge."
            ),
            checked_at=_BATCH_A,
            sources=(
                _src(
                    "S-Szpachlowanie — cennik szpachlowania Kraków",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://s-szpachlowanie.pl/szpachlowanie-krakow-cennik",
                    min_="55",
                    max_="75",
                    unit=PriceUnit.M2,
                    note="Szpachlowanie dwukrotne (2 warstwy) 55–75 zł/m², 0,8–1,2 h/m²",
                ),
                _src(
                    "KB.pl — cennik gładzi gipsowej",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://kb.pl/cenniki/uslugi/cennik-gladzi-gipsowej-i-szpachlowania-scian-w-calej-polsce/",
                    min_="35",
                    max_="54",
                    unit=PriceUnit.M2,
                    note="Szpachlowanie 2x 35,00–54,00 zł/m² (robocizna); z materiałem 48–70",
                ),
                _src(
                    "CennikiBudowlane — cennik gładzi szpachlowych",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://www.cennikibudowlane.com.pl/cenniki/polozenie-gladzi/",
                    min_="35",
                    max_="60",
                    unit=PriceUnit.M2,
                    note="Standard 35–60 zł/m² (2 warstwy z gruntowaniem) netto; Kraków 40–70",
                ),
                _src(
                    "sccot.pl — ile kosztuje szpachlowanie",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://sccot.pl/dobra-robota/ile-kosztuje-szpachlowanie-scian/",
                    min_="50",
                    max_="70",
                    unit=PriceUnit.M2,
                    note="Szpachlowanie 2x 50–70 zł/m² (całkowity koszt)",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_SKIM_SAND-01",
            "Kraków",
            PriceUnit.M2,
            "10",
            "25",
            reference_price="14",
            methodology_note=(
                "Sanding skim coat with dust extraction, LABOR. Kraków 10–16; kb 12–19; "
                "e-gladz 10–25. Mirror-finish surcharge belongs to SKIM_SQ."
            ),
            checked_at=_BATCH_A,
            sources=(
                _src(
                    "S-Szpachlowanie — cennik szpachlowania Kraków",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://s-szpachlowanie.pl/szpachlowanie-krakow-cennik",
                    min_="10",
                    max_="16",
                    unit=PriceUnit.M2,
                    note="Szlifowanie gładzi 10–16 zł/m², 0,2–0,4 h/m²",
                ),
                _src(
                    "E-Gładź — szlifowanie gładzi cena za m²",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://e-gladz.pl/szlifowanie-gladzi-cena-za-m2",
                    min_="10",
                    max_="25",
                    unit=PriceUnit.M2,
                    note=(
                        "Szlifowanie gładzi 10–25 zł/m²; maszynowe 15–30; bezpyłowe 8 + odpylanie 2"
                    ),
                ),
                _src(
                    "KB.pl — cennik szlifowania gładzi",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://kb.pl/cenniki/uslugi/cennik-gladzi-gipsowej-i-szpachlowania-scian-w-calej-polsce/",
                    min_="12",
                    max_="19",
                    unit=PriceUnit.M2,
                    note="Szlifowanie gładzi 12,00–19,00 zł/m² (bez usługi gładzenia)",
                ),
                _src(
                    "itodesign.pl — ile kosztuje szpachlowanie ścian",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://itodesign.pl/ile-kosztuje-szpachlowanie-scian-cennik-i-od-czego-zalezy/",
                    min_="10",
                    max_="20",
                    unit=PriceUnit.M2,
                    note="Szlifowanie 10–20 zł/m²; na lustro dodatkowe 10–20 zł/m²",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_SKIM_CRACK-01",
            "Małopolskie",
            PriceUnit.LM,
            "62",
            "95",
            methodology_note=(
                "Crack widening + fill, LABOR per mb. Single city-varied source (cenauslug "
                "62–95, W-wa 95 / Radom 62); zleca per-crack unit not cleanly convertible."
            ),
            checked_at=_BATCH_A,
            sources=(
                _src(
                    "CenaUsług — naprawa pęknięć ścian wewnętrznych",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://cenauslug.pl/budowa-i-remont/naprawa-pekniec-scian-wewnetrznych",
                    min_="62",
                    max_="95",
                    unit=PriceUnit.LM,
                    note=(
                        "62–95 zł/mb (śr. 75), Warszawa 95 / Radom 62; materiały osobno 15–30 "
                        "zł/mb; poszerzenie + wypełnienie za mb"
                    ),
                ),
                _src(
                    "Zleca.pl — szpachlowanie pęknięć cena",
                    SourceType.MARKETPLACE,
                    "https://zleca.pl/cennik/szpachlowanie-pekniec-cena",
                    min_="200",
                    max_="350",
                    unit=PriceUnit.PCS,
                    note=(
                        "200–350 zł z pęknięcie 1–2 m (szpachlowanie + przeszlifowanie); jednostka "
                        "per-crack — nieprzeliczalna na mb"
                    ),
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_SKIM_CORNER-01",
            "Kraków",
            PriceUnit.LM,
            "12",
            "22",
            reference_price="16",
            methodology_note=(
                "Corner-bead installation embedded in skim, LABOR per mb (material excluded). "
                "Kraków internal 12–18 / external 15–22; cenauslug 14–22; e-gladz 12."
            ),
            checked_at=_BATCH_A,
            sources=(
                _src(
                    "S-Szpachlowanie — cennik szpachlowania Kraków",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://s-szpachlowanie.pl/szpachlowanie-krakow-cennik",
                    min_="12",
                    max_="22",
                    unit=PriceUnit.LM,
                    note="Obrobienie narożników wewnętrznych 12–18; zewnętrznych 15–22 zł/mb",
                ),
                _src(
                    "CenaUsług — montaż narożników tynkarskich",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://cenauslug.pl/budowa-i-remont/montaz-naroznikow-tynkarskich",
                    min_="14",
                    max_="22",
                    unit=PriceUnit.LM,
                    note="14–22 zł/mb (śr. 18); materiały osobno ok. 5–9 zł/mb",
                ),
                _src(
                    "E-Gładź — gładź cena za m²",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://e-gladz.pl/gladz-cena-za-m2",
                    single="12",
                    unit=PriceUnit.LM,
                    note="Montaż narożników aluminiowych 12 zł/mb",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_SKIM_SQ-01",
            "Małopolskie",
            PriceUnit.M2,
            "60",
            "80",
            methodology_note=(
                "Skimming under strip-light control (lampa smugowa / pod LED). Only sources with "
                "explicit strip-light wording qualify; S3/S4 label stays a dual-tier hint, not "
                "seeded as a quality value."
            ),
            checked_at=_BATCH_A,
            sources=(
                _src(
                    "CennikiBudowlane — położenie gładzi",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://www.cennikibudowlane.com.pl/cenniki/polozenie-gladzi/",
                    min_="60",
                    max_="80",
                    unit=PriceUnit.M2,
                    note=(
                        "Premium 60–80 zł/m² (2 warstwy); Q3 'brak nierówności w świetle padającym' "
                        "— droższa o 30–50%"
                    ),
                ),
                _src(
                    "S-Szpachlowanie — cennik szpachlowania Kraków",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://s-szpachlowanie.pl/szpachlowanie-krakow-cennik",
                    min_="35",
                    max_="55",
                    unit=PriceUnit.M2,
                    note="Gładź gipsowa (1–3 mm) 35–55 zł/m² … pod światło boczne lub lampy LED",
                ),
                _src(
                    "itodesign.pl — ile kosztuje szpachlowanie ścian",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://itodesign.pl/ile-kosztuje-szpachlowanie-scian-cennik-i-od-czego-zalezy/",
                    min_="60",
                    max_="80",
                    unit=PriceUnit.M2,
                    note="3 warstwy 60–80 zł/m² (efekt pod LED)",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_GK_JOINT-01",
            "Kraków",
            PriceUnit.LM,
            "12",
            "24",
            methodology_note=(
                "LM joint-finishing basis per 9E.5 decision 3: market cenniki price joints per "
                "mb (betonizm Q1 12–18; koszt-wykonczen Kraków Q2 24). M2 aggregate 34–46 "
                "report-only; no LM↔M2 conversion."
            ),
            checked_at=_BATCH_BD,
            sources=(
                _src(
                    "Betonizm.pl — szpachlowanie łączeń płyt g-k",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://betonizm.pl/ile-kosztuje-szpachlowanie-laczen-plyt-g-k-sprawdz-aktualny-cennik-i-porady-eksperta/",
                    min_="12",
                    max_="18",
                    unit=PriceUnit.LM,
                    note="Standard Q1 z taśmą 12,00–18,00 zł/mb netto (robocizna)",
                ),
                _src(
                    "Koszt-wykonczen.pl — szpachlowanie płyt gipsowych",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://koszt-wykonczen.pl/ile-kosztuje-szpachlowanie-plyt-gipsowych",
                    single="24",
                    unit=PriceUnit.LM,
                    note="Kraków Q2 24 zł/mb (30–35 zł/m²) — regionalny anchor za mb",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_GK_FULL-01",
            "Kraków",
            PriceUnit.M2,
            "28",
            "45",
            reference_price="40",
            methodology_note=(
                "Full-surface board skim (Q3). Two explicit-Q3 national sources (betonizm 30–45, "
                "koszt-wykonczen 28–35) + local totaldecor 40 (unlabeled corroborator)."
            ),
            checked_at=_BATCH_BD,
            sources=(
                _src(
                    "Totaldecor Kraków — cennik",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://totaldecor.pl/cennik/",
                    single="40",
                    unit=PriceUnit.M2,
                    note="Wykonanie gładzi gipsowych — 40 zł/m² (bez etykiety Q)",
                ),
                _src(
                    "Betonizm.pl — szpachlowanie łączeń / pełne szpachlowanie",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://betonizm.pl/ile-kosztuje-szpachlowanie-laczen-plyt-g-k-sprawdz-aktualny-cennik-i-porady-eksperta/",
                    min_="30",
                    max_="45",
                    unit=PriceUnit.M2,
                    note="Pełne szpachlowanie powierzchniowe (standard Q3) 30,00–45,00 zł/m²",
                ),
                _src(
                    "Koszt-wykonczen.pl — szpachlowanie płyt gipsowych",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://koszt-wykonczen.pl/ile-kosztuje-szpachlowanie-plyt-gipsowych",
                    min_="28",
                    max_="35",
                    unit=PriceUnit.M2,
                    note=(
                        "Wykonawcy kwotują Q3 na poziomie 28–35 zł/m² całej ściany (2–3 warstwy, "
                        "gradacja 180–220)"
                    ),
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_GK_CORNER-01",
            "Kraków",
            PriceUnit.LM,
            "10",
            "22",
            reference_price="18",
            methodology_note=(
                "Corner-bead install, LABOR per mb. Local 10 (ekipa-krakow) + 15–22 "
                "(s-szpachlowanie zewnętrzne); national betonizm 15–22/mb. Kraków city cell "
                "22–30 zł/m² excluded (unit mismatch)."
            ),
            checked_at=_BATCH_BD,
            sources=(
                _src(
                    "Ekipa Kraków — cennik usług remontowo-budowlanych",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://ekipa-krakow.pl/cennik-uslug-remontowo-budowlanych-krakow/",
                    single="10",
                    unit=PriceUnit.LM,
                    note="Montaż narożników aluminiowych bez materiału — 10,00 zł/mb",
                ),
                _src(
                    "S-Szpachlowanie — cennik szpachlowania Kraków",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://s-szpachlowanie.pl/szpachlowanie-krakow-cennik",
                    min_="15",
                    max_="22",
                    unit=PriceUnit.LM,
                    note=(
                        "Obrobienie narożników zewnętrznych 15–22 zł/m² (LM-equivalent install; "
                        "jednostka ujawniona)"
                    ),
                ),
                _src(
                    "Betonizm.pl — szpachlowanie łączeń płyt g-k",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://betonizm.pl/ile-kosztuje-szpachlowanie-laczen-plyt-g-k-sprawdz-aktualny-cennik-i-porady-eksperta/",
                    min_="15",
                    max_="22",
                    unit=PriceUnit.LM,
                    note="Montaż i szpachlowanie metalowych narożników perforowanych 15,00–22,00 zł/mb",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_GK_Q4-01",
            "Małopolskie",
            PriceUnit.M2,
            "40",
            "80",
            methodology_note=(
                "Q4 full-surface skim ≥1 mm; two explicit-Q4 sources with different pricing "
                "models (betonizm 60–80 main table; koszt-wykonczen 40–55). betonizm chart 110 "
                "flagged outlier, not merged."
            ),
            checked_at=_BATCH_BD,
            sources=(
                _src(
                    "Betonizm.pl — szpachlowanie łączeń / pełne szpachlowanie",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://betonizm.pl/ile-kosztuje-szpachlowanie-laczen-plyt-g-k-sprawdz-aktualny-cennik-i-porady-eksperta/",
                    min_="60",
                    max_="80",
                    unit=PriceUnit.M2,
                    note=(
                        "Całopowierzchniowe szpachlowanie Q4 (pod malowanie mat/połysk) 60,00–80,00 "
                        "zł/m²; chart Q4 110 zł/m² flagowany jako outlier"
                    ),
                ),
                _src(
                    "Koszt-wykonczen.pl — szpachlowanie płyt gipsowych",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://koszt-wykonczen.pl/ile-kosztuje-szpachlowanie-plyt-gipsowych",
                    min_="40",
                    max_="55",
                    unit=PriceUnit.M2,
                    note="Q4: cała ściana wyceniana na 40–55 zł/m² (3–4 warstwy, gradacja 220–240)",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_GF_MESH-01",
            "Kraków",
            PriceUnit.M2,
            "12",
            "58",
            methodology_note=(
                "Reinforcing mesh embedded in skim/render (tech C). Kraków city table 12–58 "
                "wide window (coverage-dependent); national 30–45 full-wall (siatka elewacyjna "
                "context, partial comparability)."
            ),
            checked_at=_BATCH_BD,
            sources=(
                _src(
                    "CennikRemontow.pl — Karton-gipsy Kraków (city price table)",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://cennikremontow.pl/karton-gipsy-krakow-cennik",
                    min_="12",
                    max_="58",
                    unit=PriceUnit.M2,
                    note="Wszpachlowanie siatki zbrojącej na pęknięciach i zarysowaniach — 12–58 zł/m²",
                ),
                _src(
                    "CenaUsług — renowacja popękanych ścian i sufitów",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://cenauslug.pl/poradniki/renowacja-popekanych-scian-i-sufitow-przeglad-skutecznych-metod",
                    min_="30",
                    max_="45",
                    unit=PriceUnit.M2,
                    note=(
                        "Wtapianie siatki elewacyjnej na całej ścianie 30–45 zł/m² (kontekst siatki "
                        "elewacyjnej — częściowo porównywalny)"
                    ),
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_PAINT_2K-01",
            "Kraków",
            PriceUnit.M2,
            "10",
            "28",
            reference_price="18",
            methodology_note=(
                "2-coat white wall painting of a prepared substrate, LABOR. Kraków floor "
                "malarzkrakow od 12 + city table 10–28; national cluster overlaps upper half. "
                "ekipa-krakow flagged low outlier, not anchored."
            ),
            checked_at=_BATCH_BD,
            sources=(
                _src(
                    "Malarz Kraków — cennik",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://malarzkrakow.pl/cennik/",
                    single="12",
                    unit=PriceUnit.M2,
                    note="Malowanie dwukrotne na biało (ściany i sufity) — od 12 zł/m² (robocizna, netto)",
                ),
                _src(
                    "Totaldecor Kraków — cennik",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://totaldecor.pl/cennik/",
                    single="14",
                    unit=PriceUnit.M2,
                    note="Malowanie (2-krotne) na biało — 14 zł/m²",
                ),
                _src(
                    "CennikRemontow.pl — Malowanie Kraków (city price table)",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://cennikremontow.pl/malowanie-krakow-cennik",
                    min_="10",
                    max_="28",
                    unit=PriceUnit.M2,
                    note="Malowanie ścian dwukrotne (farba-biała) 10–28 zł/m2",
                ),
                _src(
                    "CennikiBudowlane — malowanie mieszkań i domów",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://www.cennikibudowlane.com.pl/cenniki/malowanie-mieszkan-i-domow/",
                    min_="17",
                    max_="35",
                    unit=PriceUnit.M2,
                    note="Malowanie ścian 2 warstwy (standard) — robocizna 17–35 zł/m²",
                ),
                _src(
                    "WZBudowa — cennik usług malarskich",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://wzbudowa.pl/cennik-uslug-malarskich/",
                    min_="20",
                    max_="30",
                    unit=PriceUnit.M2,
                    note="Malowanie ścian na biało, 2 warstwy — ok. 20–30 zł/m² (robocizna)",
                ),
                _src(
                    "CenaUsług — malowanie ścian i sufitów",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://cenauslug.pl/budowa-i-remont/malowanie-scian-i-sufitow",
                    min_="25",
                    max_="36",
                    unit=PriceUnit.M2,
                    note="Średnia 28 zł/m² (min 25, max 36); dwukrotne nałożenie, bez materiałów",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_PAINT_1K-01",
            "Kraków",
            PriceUnit.M2,
            "8",
            "30",
            methodology_note=(
                "1-coat refresh, LABOR. Single clean anchor malarzkrakow od 8; city 1-coat rows "
                "internally inconsistent (16–30 > its 2-coat 10–28) — recorded, not anchored."
            ),
            checked_at=_BATCH_BD,
            sources=(
                _src(
                    "Malarz Kraków — cennik",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://malarzkrakow.pl/cennik/",
                    single="8",
                    unit=PriceUnit.M2,
                    note="Malowanie jednokrotne (odświeżenie koloru) — od 8 zł/m² (robocizna, netto)",
                ),
                _src(
                    "CennikRemontow.pl — Malowanie Kraków (city price table)",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://cennikremontow.pl/malowanie-krakow-cennik",
                    min_="8",
                    max_="30",
                    unit=PriceUnit.M2,
                    note="Jednokrotne (farba-kolor) 8–30 zł/m2; wiersz 1-warstwowy niespójny — zapisany, nie kotwiczony",
                ),
                _src(
                    "M-Malowanie — cennik malowania",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://m-malowanie.pl/cennik-malowania",
                    min_="28",
                    max_="45",
                    unit=PriceUnit.M2,
                    note="Jedna warstwa 28–45 PLN/m² z gruntowaniem (L+M-leaning, context)",
                ),
                _src(
                    "Zleca.pl — cennik usług malarskich",
                    SourceType.MARKETPLACE,
                    "https://zleca.pl/cenniki/remonty-i-wykonczenia-malowanie",
                    min_="10",
                    max_="30",
                    unit=PriceUnit.M2,
                    note="Odświeżenie powłok malarskich 10–30 zł/m² (śr. 20)",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_PAINT_3K-01",
            "Kraków",
            PriceUnit.M2,
            "21.80",
            "48",
            methodology_note=(
                "3-coat painting; two direct rows only (kb.pl Kraków city 21,80 netto / 23,60 "
                "brutto; CennikiBudowlane 25–48 netto). No 3-coat band synthesized from 2-coat."
            ),
            checked_at=_BATCH_BD,
            sources=(
                _src(
                    "KB.pl — Kraków city table 'Malowanie i tapetowanie'",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://kb.pl/cenniki/miejskie/malowanie-i-tapetowanie/krakow/",
                    single="21.80",
                    unit=PriceUnit.M2,
                    note="Malowanie ścian i sufitów (trzy warstwy) 21,80 zł/m² netto, 23,60 brutto",
                ),
                _src(
                    "CennikiBudowlane — malowanie mieszkań i domów",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://www.cennikibudowlane.com.pl/cenniki/malowanie-mieszkan-i-domow/",
                    min_="25",
                    max_="48",
                    unit=PriceUnit.M2,
                    note="Malowanie ścian 3 warstwy (intensywne kolory) — robocizna 25–48 zł/m²",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_PAINT_CEIL-01",
            "Kraków",
            PriceUnit.M2,
            "16",
            "32",
            reference_price="24",
            methodology_note=(
                "2-coat ceiling painting, LABOR. Sole Kraków ceiling set (CennikRemontow 18–32 "
                "white 2-coat; color rows floor at 16); national 20–40 overlap; malarzkrakow "
                "pools ceilings — not double-counted."
            ),
            checked_at=_BATCH_BD,
            sources=(
                _src(
                    "CennikRemontow.pl — Malowanie Kraków (city price table, ceiling rows)",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://cennikremontow.pl/malowanie-krakow-cennik",
                    min_="18",
                    max_="32",
                    unit=PriceUnit.M2,
                    note=(
                        "Malowanie sufitu dwukrotne (farba-biała) 18–32 zł/m2; jednokrotne 18–30; "
                        "kolor 16–22"
                    ),
                ),
                _src(
                    "WZBudowa — cennik usług malarskich",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://wzbudowa.pl/cennik-uslug-malarskich/",
                    min_="20",
                    max_="40",
                    unit=PriceUnit.M2,
                    note="Malowanie sufitów ok. 20–40 zł/m² (robocizna)",
                ),
                _src(
                    "CennikiBudowlane — malowanie mieszkań i domów",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://www.cennikibudowlane.com.pl/cenniki/malowanie-mieszkan-i-domow/",
                    min_="22",
                    max_="38",
                    unit=PriceUnit.M2,
                    note="Malowanie sufitu — robocizna 22–38 zł/m²",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_PAINT_COL-01",
            "Kraków",
            PriceUnit.M2,
            "14",
            "30",
            reference_price="20",
            methodology_note=(
                "2-coat colored painting, LABOR (full color-coverage row). Kraków 14–18 anchors "
                "+ city color window 14–30; dark-color surcharges recorded as context, not merged."
            ),
            checked_at=_BATCH_BD,
            sources=(
                _src(
                    "Malarz Kraków — cennik",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://malarzkrakow.pl/cennik/",
                    single="14",
                    unit=PriceUnit.M2,
                    note="Malowanie dwukrotne w kolorze (ściany i sufity) — od 14 zł/m² (robocizna)",
                ),
                _src(
                    "Totaldecor Kraków — cennik",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://totaldecor.pl/cennik/",
                    single="18",
                    unit=PriceUnit.M2,
                    note="Malowanie (2-krotne) kolor — 18 zł/m²",
                ),
                _src(
                    "CennikRemontow.pl — Malowanie Kraków (city price table, color rows)",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://cennikremontow.pl/malowanie-krakow-cennik",
                    min_="14",
                    max_="30",
                    unit=PriceUnit.M2,
                    note="Malowanie ścian dwukrotne (farba-kolor) 14–30 zł/m2",
                ),
                _src(
                    "WZBudowa — cennik usług malarskich",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://wzbudowa.pl/cennik-uslug-malarskich/",
                    min_="25",
                    max_="40",
                    unit=PriceUnit.M2,
                    note="Malowanie ścian kolorem, 2 warstwy — ok. 25–40 zł/m² (robocizna)",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_REV_WORK_LM-01",
            "Małopolskie",
            PriceUnit.LM,
            "30",
            "110",
            reference_price="60",
            methodology_note=(
                "Canonical reveal row (9E.5 decision 5): linear reveal work per mb, LABOR. "
                "4 numeric origins 50–110 cluster; Kraków-zone via o-okna Strefa I +20–35%; no "
                "LM↔M² conversion."
            ),
            checked_at=_BATCH_BD,
            sources=(
                _src(
                    "NowaBudowa — cennik usług murarskich",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://nowabudowa.pl/index.php/cennik/cennik-uslug-murarskich",
                    single="58.25",
                    unit=PriceUnit.LM,
                    note="Obróbka otworów okiennych 58,25 zł/mb (robocizna, netto); z zaprawą 78,25 L+M",
                ),
                _src(
                    "CenaUsług — obróbka glifów okiennych i drzwiowych",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://cenauslug.pl/budowa-i-remont/obrobka-glifow-okiennych-i-drzwiowych",
                    min_="55",
                    max_="85",
                    unit=PriceUnit.LM,
                    note="Średnio 67 zł/mb; zakres 55 (Kielce) – 85 (Świdnica); materiały 15–30 zł/mb osobno",
                ),
                _src(
                    "KB.pl — cennik obróbki okien",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://kb.pl/okna-i-drzwi/ceny-okien/cennik-obrobki-okien-zobacz-ile-zaplacisz-za-montaz-okien-z-obrobka/",
                    min_="30",
                    max_="70",
                    unit=PriceUnit.LM,
                    note="Od 30 do 70 zł/mb (sama obróbka, brutto)",
                ),
                _src(
                    "Dziennik Budowlany — ile kosztuje obróbka okna 2026",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://dziennikbudowlany.pl/ile-kosztuje-obrobka-okna-2026/",
                    min_="30",
                    max_="70",
                    unit=PriceUnit.LM,
                    note="Sama obróbka 30–70 zł/mb; obróbka tynkarska po montażu 40–65 zł/mb (wspólna rodzina z KB.pl)",
                ),
                _src(
                    "O-Okna — obróbka okna cena",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://o-okna.pl/obrobienie-okna-cena",
                    min_="50",
                    max_="160",
                    unit=PriceUnit.LM,
                    note=(
                        "Obróbka tynkarska 50–160 zł/mb (robocizna); Strefa I (metropolie) 95–160; "
                        "Warszawa/Kraków/Trójmiasto +20–35%"
                    ),
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_MC_WALL_S-01",
            "Kraków / Małopolskie",
            PriceUnit.M2,
            "320",
            "650",
            reference_price="350",
            methodology_note=(
                "Complete thin-layer wall system incl. material (LABOR_AND_MATERIAL); substrate "
                "ready, leveling excluded. Dry-interior core 320–400 (S1/S2/S3 od anchors); "
                "bathroom-wall 450–650 (hydro incl.) is scope-separate."
            ),
            checked_at=_BATCH_BD,
            sources=(
                _src(
                    "Monolite — ile kosztuje mikrocement",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://monolite.pl/ile-kosztuje-mikrocement-w-2025-roku-cennik-porownania-i-praktyczny-przewodnik-z-kalkulatorem/",
                    min_="250",
                    max_="400",
                    unit=PriceUnit.M2,
                    note="Wnętrza 250–400 zł/m²; łazienka ściany 450–650 (hydro wliczone) — osobny zakres",
                ),
                _src(
                    "Zement / MTS pracowniabetonu.pl — ile kosztuje mikrocement",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://pracowniabetonu.pl/ile-kosztuje-mikrocement-cennik/",
                    single="320",
                    unit=PriceUnit.M2,
                    note="Od 320 zł netto (posadzki, ściany, łazienki) — kotwica 'od'",
                ),
                _src(
                    "JAK Chemia — mikrocement podłoga i ściany",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://www.jakposadzki.pl/oferta/mikrocement-podloga/",
                    single="350",
                    unit=PriceUnit.M2,
                    note="Od 350 zł netto all-in; min projekt ~80 m²",
                ),
                _src(
                    "ADREM — mikrocement cena za m² 2026",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://adrem.org.pl/mikrocement-cena-za-m2/",
                    min_="250",
                    max_="400",
                    unit=PriceUnit.M2,
                    note="Ściany 250–400 zł/m² (L+M)",
                ),
                _src(
                    "Profesor Budownictwa — mikrocement na ścianę",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://profesorbudownictwa.pl/mikrocement-na-sciane-cena",
                    min_="250",
                    max_="400",
                    unit=PriceUnit.M2,
                    note="Ściana 250–400 zł/m² (L+M)",
                ),
                _src(
                    "ekipazlecenia.pl (ZUBRA) — cennik mikrocement",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://ekipazlecenia.pl/cennik/cennik-mikrocement",
                    single="326",
                    unit=PriceUnit.M2,
                    note="Ściana kompleksowo od 326 zł/m²",
                ),
                _src(
                    "Technodecor — mikrocement: cena za m²",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://technodecor.pl/mikrocement/cena/",
                    min_="300",
                    max_="500",
                    unit=PriceUnit.M2,
                    note="Podłogi i ściany 300–500 zł/m²; min 50 m²; prep+mesh w cenie",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_MC_FLOOR_S-01",
            "Kraków / Małopolskie",
            PriceUnit.M2,
            "320",
            "400",
            reference_price="380",
            methodology_note=(
                "Full floor system incl. material (LABOR_AND_MATERIAL). Three local/regional "
                "floor-specific anchors (S1 posadzki 360–400/≤50 m² 400; S2 od 320; S3 od 350) "
                "define the 320–400 local window; national typical 350–500 context."
            ),
            checked_at=_BATCH_BD,
            sources=(
                _src(
                    "Monolite — ile kosztuje mikrocement",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://monolite.pl/ile-kosztuje-mikrocement-w-2025-roku-cennik-porownania-i-praktyczny-przewodnik-z-kalkulatorem/",
                    min_="360",
                    max_="400",
                    unit=PriceUnit.M2,
                    note="Posadzki ≤50 m² 400; >50 m² 360–380 zł/m²",
                ),
                _src(
                    "Zement / MTS pracowniabetonu.pl — ile kosztuje mikrocement",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://pracowniabetonu.pl/ile-kosztuje-mikrocement-cennik/",
                    single="320",
                    unit=PriceUnit.M2,
                    note="Od 320 zł netto (posadzki explicit) — kotwica 'od'",
                ),
                _src(
                    "JAK Chemia — mikrocement podłoga i ściany",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://www.jakposadzki.pl/oferta/mikrocement-podloga/",
                    single="350",
                    unit=PriceUnit.M2,
                    note="Od 350 zł netto (podłogi explicit)",
                ),
                _src(
                    "Vnetrze — cena mikrocementu za m² z robocizną i materiałem",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://vnetrze.pl/cena-mikrocementu-za-metr-kwadratowy-z-robocizna-i-materialem/",
                    min_="350",
                    max_="550",
                    unit=PriceUnit.M2,
                    note=">50 m² 350–550 zł/m² netto; cokol 40–80 zł/mb osobno",
                ),
                _src(
                    "Profesor Budownictwa — ile kosztuje m² mikrocementu",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://profesorbudownictwa.pl/koszt-mikrocementu",
                    min_="350",
                    max_="500",
                    unit=PriceUnit.M2,
                    note="Podłoga 350–500 zł/m² (L+M)",
                ),
                _src(
                    "ADREM — mikrocement cena za m² 2026",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://adrem.org.pl/mikrocement-cena-za-m2/",
                    min_="300",
                    max_="500",
                    unit=PriceUnit.M2,
                    note="Podłogi 300–500 zł/m² (L+M)",
                ),
                _src(
                    "Technodecor — mikrocement: cena za m²",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://technodecor.pl/mikrocement/cena/",
                    min_="300",
                    max_="500",
                    unit=PriceUnit.M2,
                    note="Podłogi i ściany 300–500 zł/m²; min 50 m²",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_MC_SHOWER-01",
            "Kraków / Małopolskie",
            PriceUnit.M2,
            "450",
            "650",
            reference_price="550",
            methodology_note=(
                "Shower-zone microcement incl. membrane (hydroizolacja), L+M. Local S1 łazienka "
                "ściany 450–650 anchors; national wet-zone 380–580 (S7) and brute city band "
                "380–720 (sanitmax brutto) support. Netto/brutto split preserved, never merged."
            ),
            checked_at=_BATCH_BD,
            sources=(
                _src(
                    "Monolite — ile kosztuje mikrocement",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://monolite.pl/ile-kosztuje-mikrocement-w-2025-roku-cennik-porownania-i-praktyczny-przewodnik-z-kalkulatorem/",
                    min_="450",
                    max_="650",
                    unit=PriceUnit.M2,
                    note=(
                        "Łazienka – ściany 450–650 zł/m² (Kraków; hydroizolacja + prep + base/finish "
                        "+ topcoat + detale w cenie)"
                    ),
                ),
                _src(
                    "Profesor Budownictwa — mikrocement do łazienki",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://profesorbudownictwa.pl/mikrocement-lazienka-cena",
                    min_="380",
                    max_="580",
                    unit=PriceUnit.M2,
                    note="Strefa mokra (prysznic) 380–580 zł/m² (mat. 120–200 + robocizna 260–380)",
                ),
                _src(
                    "Sanitmax — mikrocement pod prysznic: cena",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://sanitmax.pl/mikrocement-pod-prysznic-cena",
                    min_="380",
                    max_="720",
                    unit=PriceUnit.M2,
                    note="380–720 zł brutto/m² w strefie prysznicowej (Warszawa/Kraków/Wrocław); brutto",
                ),
                _src(
                    "Topciment — ile kosztuje mikrocement za m²",
                    SourceType.MANUFACTURER,
                    "https://www.topciment.com/pl/nouvelle/cena-mikrocementu",
                    min_="300",
                    max_="650",
                    unit=PriceUnit.M2,
                    note="Typowy 350–550; jedna łazienka ~550 (incl. membrana) — przegląd producenta",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_DEC_VEN-01",
            "Małopolskie",
            PriceUnit.M2,
            "100",
            "160",
            reference_price="140",
            methodology_note=(
                "Classic Venetian plaster LABOR per m², STANDARD/ENHANCED complexity. No Kraków "
                "LABOR row; national labor core 120–150 (itynki/jakietynki), 80–120 wistalex, "
                "150–300 premium (ewyposazenie/adrem). Big-city coefficient is an owner decision."
            ),
            checked_at=_BATCH_BD,
            sources=(
                _src(
                    "itynki.pl — koszt robocizny przy tynku dekoracyjnym",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://itynki.pl/tynki-dekoracyjne-cena-robocizny",
                    min_="120",
                    max_="150",
                    unit=PriceUnit.M2,
                    note="Stiuk wenecki robocizna 120–150 zł/m²; Kraków +15–25% (premium big-city)",
                ),
                _src(
                    "jakietynki.pl — tynk dekoracyjny cena za m² robocizny",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://jakietynki.pl/tynk-dekoracyjny-cena-za-m2-robocizny",
                    min_="120",
                    max_="150",
                    unit=PriceUnit.M2,
                    note="Wysoki stopień skomplikowania (stiuk wenecki) robocizna 120–150 zł/m²",
                ),
                _src(
                    "wistalex.pl — stiuk wenecki cena za m² robocizny",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://wistalex.pl/stiuk-wenecki-cena-robocizny/",
                    min_="80",
                    max_="120",
                    unit=PriceUnit.M2,
                    note="Standardowa aplikacja 80–120 zł/m²; techniki specjalistyczne 120–150",
                ),
                _src(
                    "ewyposazenie.pl — tynk dekoracyjny cena za m² robocizny",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://ewyposazenie.pl/tynk-dekoracyjny-cena-za-m2-robocizny/",
                    min_="150",
                    max_="300",
                    unit=PriceUnit.M2,
                    note="Stiuk wenecki robocizna 150–300 zł/m² (za trudne techniki + materiał clause)",
                ),
                _src(
                    "adrem.org.pl — stiuk wenecki cena za m² robocizny",
                    SourceType.CONTRACTOR_PRICE_LIST,
                    "https://adrem.org.pl/stiuk-wenecki-cena-za-m2-robocizny/",
                    min_="150",
                    max_="300",
                    unit=PriceUnit.M2,
                    note="Robocizna 150–300 zł/m² (podstawowy 150–200 / średni 200–250 / premium 250–300)",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_DEC_CONC-01",
            "Małopolskie",
            PriceUnit.M2,
            "60",
            "150",
            reference_price="110",
            methodology_note=(
                "Architectural-concrete effect (thin-layer decorative coating) LABOR per m², "
                "STANDARD complexity. National guides 50–150 core; microcement/panels/resin "
                "excluded (catalog guard); no Kraków LABOR row."
            ),
            checked_at=_BATCH_BD,
            sources=(
                _src(
                    "ewyposazenie.pl — tynk dekoracyjny cena za m² robocizny",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://ewyposazenie.pl/tynk-dekoracyjny-cena-za-m2-robocizny/",
                    min_="70",
                    max_="150",
                    unit=PriceUnit.M2,
                    note="Imitacja betonu architektonicznego robocizna 70–150 zł/m²",
                ),
                _src(
                    "itynki.pl — koszt robocizny przy tynku dekoracyjnym",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://itynki.pl/tynki-dekoracyjne-cena-robocizny",
                    min_="100",
                    max_="140",
                    unit=PriceUnit.M2,
                    note="Beton architektoniczny robocizna 100–140 zł/m² (tabela); tekst 140–180 — niespójność flagowana",
                ),
                _src(
                    "jakietynki.pl — tynk dekoracyjny cena za m² robocizny",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://jakietynki.pl/tynk-dekoracyjny-cena-za-m2-robocizny",
                    min_="80",
                    max_="120",
                    unit=PriceUnit.M2,
                    note="Średnio skomplikowane (struktura betonu) robocizna 80–120 zł/m²",
                ),
                _src(
                    "konkret-beton.pl — cena położenia betonu dekoracyjnego",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://konkret-beton.pl/cena-polozenia-betonu-dekoracyjnego",
                    min_="50",
                    max_="120",
                    unit=PriceUnit.M2,
                    note="Robocizna 50–120 zł/m² (miasta do 150); płyty betonowe wyłączone",
                ),
                _src(
                    "abc-tynki.pl — tynk beton architektoniczny: cena robocizny",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://abc-tynki.pl/tynk-beton-architektoniczny-cena-robocizny",
                    min_="60",
                    max_="270",
                    unit=PriceUnit.M2,
                    note="Robocizna 60–270 zł/m² (outer band); total L+M 80–350",
                ),
            ),
        ),
    )
    refs.append(
        _ref(
            "CENNIK_DEC_GENERIC-01",
            "Małopolskie",
            PriceUnit.M2,
            "40",
            "80",
            reference_price="60",
            methodology_note=(
                "Renamed restricted row (9E.5 decision 7): tynk strukturalny/rustykalny — linia "
                "podstawowa (structural/colored/rustykalny sub-family), LABOR per m², one "
                "pass/one color. Trawertynowe/metallic/limewash kept as context, never merged."
            ),
            checked_at=_BATCH_BD,
            sources=(
                _src(
                    "ewyposazenie.pl — tynk dekoracyjny cena za m² robocizny",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://ewyposazenie.pl/tynk-dekoracyjny-cena-za-m2-robocizny/",
                    min_="40",
                    max_="70",
                    unit=PriceUnit.M2,
                    note="Tynk strukturalny (prosty wzór) robocizna 40–70 zł/m²",
                ),
                _src(
                    "itynki.pl — koszt robocizny przy tynku dekoracyjnym",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://itynki.pl/tynki-dekoracyjne-cena-robocizny",
                    min_="50",
                    max_="80",
                    unit=PriceUnit.M2,
                    note="Strukturalny kolorowy 50–70; rustykalny/efekt rdzy 60–80; trawertyn 80–110 (kontekst)",
                ),
                _src(
                    "jakietynki.pl — tynk dekoracyjny cena za m² robocizny",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://jakietynki.pl/tynk-dekoracyjny-cena-za-m2-robocizny",
                    min_="60",
                    max_="80",
                    unit=PriceUnit.M2,
                    note="Najprostsze modele 60–80 zł/m²",
                ),
                _src(
                    "poilerobocizna.pl — tynk dekoracyjny cena za m² robocizny",
                    SourceType.INDUSTRY_ARTICLE,
                    "https://poilerobocizna.pl/tynk-dekoracyjny-cena-za-m2-robocizny",
                    single="40",
                    unit=PriceUnit.M2,
                    note="Strukturalny 40 zł/m² calculator base / 40–55 na dużych metrażach",
                ),
            ),
        ),
    )

    return {ref.code: ref for ref in refs}


LEGACY_GENERIC_CODES = (
    "CENNIK_PREP_GENERIC_M2",
    "CENNIK_PAINT_GENERIC_M2",
    "CENNIK_REVEAL_GENERIC_M2",
    "CENNIK_REVEAL_GENERIC_LM",
)
"""Stage 9B technical placeholder codes, retired (archived) once on bootstrap."""