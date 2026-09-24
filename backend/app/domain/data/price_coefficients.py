"""Idempotent baseline data for the `CoefficientGroup`/`CoefficientOption`
catalog (Stage 12C mechanism, Stage 12G content).

Mirrors `app/domain/data/work_recommendation_rules.py`'s shape exactly: a
pure dataclass list, materialized lazily and idempotently per owner by
`PriceCoefficientService.ensure_owner_catalog` (never an Alembic data seed --
see `docs/stage-12-architecture.md` Sec 5 for the rationale).

Stage 12G ships the owner-approved v1 default catalog, exactly as specified in
`docs/stage-12-architecture.md` Sec 27.3 and `README.md` ("Model wyceny"):
four SINGLE_SELECT execution-condition groups, twelve options, one explicit
0% `is_base` option per group, Polish names and descriptions.

Deliberately NOT here (Sec 27.3): quality targets (S1-S4, Q1-Q4/PSG1-PSG4 are
never coefficients), negative defaults, furniture, ceiling, colour, small-job,
urgency/night/weekend, travel, scaffolding/equipment, commercial discounts or
fixed surcharges. Do not add entries without an explicit owner-approved
specification.

Names are seeded as Polish `display_name` (not `name_key`) because an
Estimate's coefficient snapshot stores the resolved label verbatim. Every
seeded field stays owner-editable; the bootstrap never rewrites an existing
row.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CoefficientOptionData:
    code: str
    percentage: str
    is_base: bool = False
    display_name: str | None = None
    name_key: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class CoefficientGroupData:
    code: str
    display_name: str | None = None
    name_key: str | None = None
    description: str | None = None
    options: tuple[CoefficientOptionData, ...] = field(default_factory=tuple)


_WYSOKOSC_PRACY = CoefficientGroupData(
    code="WYSOKOSC_PRACY",
    display_name="Wysokość pracy",
    description=(
        "Korekta robocizny za rzeczywisty spadek wydajności spowodowany "
        "wysokością, na której wykonywana jest praca.\n\n"
        "Stosuj, gdy cena bazowa zakłada pracę z podłogi lub niskiej drabiny, "
        "a ta konkretna praca wymaga pracy wyżej (np. wysokie ściany i sufity, "
        "klatki schodowe, antresole).\n\n"
        "Nie stosuj, jeżeli wysokość jest już uwzględniona w cenie bazowej "
        "pozycji. Koszt rusztowania, podestu lub wynajmu sprzętu NIE jest "
        "częścią tego współczynnika — rozlicz go osobno (osobna pozycja lub "
        "dopłata do zlecenia)."
    ),
    options=(
        CoefficientOptionData(
            code="STANDARDOWA",
            display_name="Standardowa",
            percentage="0",
            is_base=True,
            description=(
                "Wysokość zakładana w cenie bazowej — praca z podłogi lub "
                "niskiej drabiny/podestu. Bez korekty ceny. Wybór tej opcji "
                "zapisuje świadomą decyzję, że wysokość nie utrudnia pracy."
            ),
        ),
        CoefficientOptionData(
            code="PODWYZSZONA",
            display_name="Podwyższona",
            percentage="15",
            description=(
                "Praca wyraźnie wyżej niż zakłada cena bazowa, wymagająca "
                "częstego wchodzenia i przestawiania drabiny lub podestu, co "
                "obniża wydajność. Sam koszt sprzętu rozlicz osobno."
            ),
        ),
        CoefficientOptionData(
            code="WYSOKA",
            display_name="Wysoka",
            percentage="25",
            description=(
                "Praca na dużej wysokości (np. z rusztowania), gdzie wydajność "
                "spada znacząco przez ograniczony zasięg i przemieszczanie się. "
                "Koszt rusztowania lub wynajmu sprzętu NIE jest wliczony — "
                "rozlicz go osobno."
            ),
        ),
    ),
)

_DOSTEP_DO_POWIERZCHNI = CoefficientGroupData(
    code="DOSTEP_DO_POWIERZCHNI",
    display_name="Dostęp do powierzchni",
    description=(
        "Korekta robocizny za ograniczenie dostępu do powierzchni, które "
        "utrzymuje się przez cały czas wykonywania pracy.\n\n"
        "Stosuj, gdy nie da się swobodnie podejść lub operować narzędziem, np. "
        "wąskie przejścia, powierzchnie za zabudową lub instalacjami, praca w "
        "ciasnych pomieszczeniach, stała zabudowa lub wyposażenie, którego nie "
        "można usunąć.\n\n"
        "Nie stosuj za jednorazowe przesunięcie mebli lub wyposażenia — jeżeli "
        "jest płatne, rozlicz je jako osobną pozycję. Nie łącz z pozycjami, w "
        "których utrudniony dostęp jest już wyceniony."
    ),
    options=(
        CoefficientOptionData(
            code="SWOBODNY",
            display_name="Swobodny",
            percentage="0",
            is_base=True,
            description=(
                "Swobodny dostęp do całej powierzchni, zakładany w cenie "
                "bazowej. Bez korekty ceny."
            ),
        ),
        CoefficientOptionData(
            code="UTRUDNIONY",
            display_name="Utrudniony",
            percentage="10",
            description=(
                "Dostęp częściowo ograniczony przez cały czas pracy (np. wąskie "
                "przejście, elementy stałej zabudowy przy powierzchni), co "
                "zauważalnie spowalnia pracę."
            ),
        ),
        CoefficientOptionData(
            code="BARDZO_UTRUDNIONY",
            display_name="Bardzo utrudniony",
            percentage="20",
            description=(
                "Dostęp mocno ograniczony przez cały czas pracy (np. praca w "
                "bardzo ciasnej przestrzeni, za instalacjami, w niewygodnej "
                "pozycji). Nie dotyczy jednorazowego przestawienia mebli."
            ),
        ),
    ),
)

_ZLOZONOSC_POWIERZCHNI = CoefficientGroupData(
    code="ZLOZONOSC_POWIERZCHNI",
    display_name="Złożoność powierzchni",
    description=(
        "Korekta robocizny za spadek wydajności wynikający z kształtu i "
        "rozdrobnienia powierzchni: wiele małych fragmentów, dojść, krawędzi "
        "lub częste zmiany kierunku pracy.\n\n"
        "Stosuj np. przy powierzchniach podzielonych na wąskie pasy, wielu "
        "załamaniach, skosach, podciągach lub drobnych fragmentach między "
        "otworami.\n\n"
        "Nie stosuj do ponownego wyceniania elementów, które są już osobnymi "
        "pozycjami cennika (np. ościeża, narożniki lub inne oddzielnie mierzone "
        "prace) — to byłoby podwójne naliczenie."
    ),
    options=(
        CoefficientOptionData(
            code="STANDARDOWA",
            display_name="Standardowa",
            percentage="0",
            is_base=True,
            description=(
                "Typowa, w większości jednolita powierzchnia zakładana w cenie "
                "bazowej. Bez korekty ceny."
            ),
        ),
        CoefficientOptionData(
            code="ZLOZONA",
            display_name="Złożona",
            percentage="10",
            description=(
                "Powierzchnia z wieloma załamaniami, krawędziami lub małymi "
                "fragmentami, które wyraźnie spowalniają pracę. Nie dotyczy "
                "elementów wycenianych osobno (ościeża, narożniki)."
            ),
        ),
        CoefficientOptionData(
            code="BARDZO_ZLOZONA",
            display_name="Bardzo złożona",
            percentage="20",
            description=(
                "Powierzchnia silnie rozdrobniona — przeważają małe fragmenty, "
                "dojścia i częste zmiany kierunku pracy. Nie łącz z osobnymi "
                "pozycjami za te same elementy."
            ),
        ),
    ),
)

_ORGANIZACJA_PRACY = CoefficientGroupData(
    code="ORGANIZACJA_PRACY",
    display_name="Organizacja pracy",
    description=(
        "Korekta robocizny za spadek wydajności spowodowany organizacją "
        "realizacji, a nie samą powierzchnią.\n\n"
        "Stosuj np. przy ograniczonych godzinach dostępu, pracy w zamieszkanym "
        "lub czynnym obiekcie, wielokrotnym udostępnianiu stref albo "
        "konieczności regularnego przerywania i wznawiania pracy.\n\n"
        "Nie obejmuje dodatkowych czynności, takich jak zabezpieczenie, "
        "przenoszenie wyposażenia czy dodatkowe sprzątanie — jeżeli są płatne, "
        "rozlicz je jako osobne pozycje. Praca nocna, weekendowa lub pilna to "
        "dopłata do zlecenia, nie ten współczynnik."
    ),
    options=(
        CoefficientOptionData(
            code="CIAGLA",
            display_name="Ciągła",
            percentage="0",
            is_base=True,
            description=(
                "Praca ciągła, bez ograniczeń organizacyjnych, zakładana w "
                "cenie bazowej. Bez korekty ceny."
            ),
        ),
        CoefficientOptionData(
            code="OGRANICZONA",
            display_name="Ograniczona",
            percentage="10",
            description=(
                "Praca w ograniczonych godzinach lub w obiekcie czynnym / "
                "zamieszkanym, co zmniejsza efektywny czas pracy."
            ),
        ),
        CoefficientOptionData(
            code="ETAPOWA",
            display_name="Etapowa / przerywana",
            percentage="20",
            description=(
                "Praca prowadzona etapami lub regularnie przerywana i "
                "wznawiana (np. wielokrotne udostępnianie stref). Zabezpieczenie "
                "i sprzątanie rozliczaj osobno."
            ),
        ),
    ),
)


def build_baseline_price_coefficients() -> list[CoefficientGroupData]:
    """Return the owner-approved v1 default catalog served by bootstrap.

    Exactly four groups / twelve options (docs/stage-12-architecture.md
    Sec 27.3). Do not add entries without an explicit, separate
    owner-approved specification.
    """
    return [
        _WYSOKOSC_PRACY,
        _DOSTEP_DO_POWIERZCHNI,
        _ZLOZONOSC_POWIERZCHNI,
        _ORGANIZACJA_PRACY,
    ]
