"""Owner-approved program-default technological workflows (Stage 13D).

Sixteen recipes, exactly as specified by the binding Stage 13D owner
decisions (docs/STAGE_13_TECHNOLOGICAL_WORKFLOWS_ARCHITECTURE.md §23):
BETON / TYNK GIPSOWY / TYNK CEMENTOWO-WAPIENNY x S1-S4 and PŁYTA G-K x Q1-Q4.
Materialized lazily and insert-only per owner by
`WorkflowTemplateService.ensure_owner_catalog` (never an Alembic data seed),
mirroring the Stage 11/12 bootstrap precedent: an existing template (matched
by code) is never rewritten, re-stepped or un-archived.

Binding content rules (do not change without an explicit owner decision):
- S1-S4 = "Standard Wykończenia Powierzchni" -- wewnętrzna klasyfikacja
  wykonawcy, never a normative scale and never defined by a number of layers;
  Q1-Q4 is the separate gypsum-board scale.
- Recipes end with a surface ready for the next finishing/painting system: no
  painting items, no PRIM_PAINT, no PAINT_MASK.
- SKIM_2L is the commercial two-layer package; SKIM_ADD is always optional;
  SKIM_SQ is never used.
- No fleece/mesh, no geometry correction (SKIM_LEVEL), no REVEAL, no
  GK_SCREW, no legacy GK_JOINT (Q1/Q2) -- GK uses GK_JOINT_Q1 (+ GK_JOINT_Q2).
- Primers are optional alternatives, never a substrate-mandated pair.
- wait_after_hours is always NULL; drying guidance lives in Polish notes.
- Names use `name_key` (PL/RU locale); descriptions and notes are canonical
  Polish technological text (owner-editable data once materialized).
- Optional steps are meant to start UNSELECTED in the 13E apply preview.
"""
from dataclasses import dataclass

from app.models.checklist import QualityLevel, Substrate
from app.models.surface import SurfaceType


@dataclass(frozen=True)
class WorkflowStepData:
    price_item_code: str
    is_optional: bool
    note: str | None = None


@dataclass(frozen=True)
class WorkflowTemplateData:
    code: str
    name_key: str
    description: str
    substrate: Substrate
    quality: QualityLevel
    steps: tuple[WorkflowStepData, ...]


SURFACE_TYPES: tuple[SurfaceType, ...] = (
    SurfaceType.WALL,
    SurfaceType.CEILING,
    SurfaceType.OTHER,
)

_DRY = (
    "Kolejny etap po całkowitym wyschnięciu, zgodnie z wymaganiami "
    "zastosowanego materiału i warunkami na obiekcie."
)
_INTERNAL = "Wewnętrzna klasyfikacja wykonawcy."
_NO_PAINT = "Bez malowania — powierzchnia gotowa do kolejnego systemu wykończeniowego."


def _req(code: str, note: str | None = None) -> WorkflowStepData:
    return WorkflowStepData(code, False, note)


def _opt(code: str, note: str | None = None) -> WorkflowStepData:
    return WorkflowStepData(code, True, note)


# ---- shared steps -----------------------------------------------------------

_PROT = _opt(
    "CENNIK_PREP_PROT-01",
    "Zabezpieczenie podłóg, stolarki i elementów nieobjętych pracami — "
    "jeśli wymagane na obiekcie.",
)
_CLEAN = _req(
    "CENNIK_PREP_CLEAN-01",
    "Podłoże odpylone i oczyszczone przed gruntowaniem i naprawami.",
)
_CRACK = _opt(
    "CENNIK_SKIM_CRACK-01",
    "Rysy i pęknięcia stwierdzone przy ocenie podłoża. Ilość w mb "
    "wprowadzana ręcznie. " + _DRY,
)
_LOCAL = _opt(
    "CENNIK_SKIM_LOCAL-01",
    "Naprawy punktowe ubytków i nierówności lokalnych. Ilość do weryfikacji — "
    "zwykle dotyczy części powierzchni. " + _DRY,
)
_CORNER = _opt(
    "CENNIK_SKIM_CORNER-01",
    "Gdy występują narożniki zewnętrzne; montaż przed szpachlowaniem. Ilość "
    "w mb wprowadzana ręcznie.",
)
_SKIM_2L = _req(
    "CENNIK_SKIM_2L-01",
    "Dwie warstwy gładzi w ramach pakietu; kolejna warstwa po wystarczającym "
    "wyschnięciu poprzedniej. " + _DRY,
)
_SKIM_ADD = _opt(
    "CENNIK_SKIM_ADD-01",
    "Dodatkowa warstwa tylko wtedy, gdy wymaga tego stan powierzchni po "
    "pakiecie dwóch warstw lub uzgodniony standard wizualny. " + _DRY,
)
_SAND = _req(
    "CENNIK_SKIM_SAND-01",
    "Szlifowanie końcowe z odpylaniem. Powierzchnia gotowa do kolejnego "
    "systemu wykończeniowego (np. malarskiego).",
)
_SAND_S4 = _req(
    "CENNIK_SKIM_SAND-01",
    "Szlifowanie końcowe z odpylaniem. Ocena powierzchni w warunkach "
    "oglądu i oświetlenia uzgodnionych indywidualnie dla obiektu przed "
    "rozpoczęciem prac. Powierzchnia gotowa do kolejnego systemu "
    "wykończeniowego.",
)

# ---- substrate-specific steps ----------------------------------------------

_CONC = _opt(
    "CENNIK_PREP_CONC-01",
    "Beton monolityczny: usunięcie nadlewek i wyszlifowanie styków "
    "szalunku. Ilość do weryfikacji, jeśli dotyczy części powierzchni.",
)
_BETON_ADH = _opt(
    "CENNIK_PRIM_ADH-01",
    "Beton gładki, zwarty lub słabo chłonny. Alternatywa dla gruntu "
    "penetrującego — wybierz jeden grunt zależnie od stanu podłoża, nie oba. "
    + _DRY,
)
_BETON_STD = _opt(
    "CENNIK_PRIM_STD-01",
    "Beton chłonny lub pylący. Alternatywa dla gruntu kontaktowego — wybierz "
    "jeden grunt zależnie od stanu podłoża, nie oba. " + _DRY,
)
_GIPS_STD = _opt(
    "CENNIK_PRIM_STD-01",
    "Tylko gdy podłoże jest chłonne lub pylące — zgodnie z oceną podłoża. "
    + _DRY,
)
_CW_STD = _opt(
    "CENNIK_PRIM_STD-01",
    "Podłoże o typowej chłonności. Alternatywa dla gruntowania podłoża "
    "wysokochłonnego — wybierz jeden grunt zależnie od chłonności, nie oba. "
    + _DRY,
)
_CW_HIGH = _opt(
    "CENNIK_PRIM_HIGH-01",
    "Podłoże silnie chłonne. Alternatywa dla gruntu penetrującego — wybierz "
    "jeden grunt zależnie od chłonności, nie oba. " + _DRY,
)

# ---- gypsum board -------------------------------------------------------------

_GK_Q1 = _req(
    "CENNIK_GK_JOINT_Q1-01",
    "Szpachlowanie konstrukcyjne spoin z wtopieniem taśmy zbrojącej oraz "
    "zaszpachlowanie łbów wkrętów zgodnie z przyjętym systemem. Ilość w mb "
    "wprowadzana ręcznie. " + _DRY,
)
_GK_CORNER = _opt(
    "CENNIK_GK_CORNER-01",
    "Gdy występują narożniki zewnętrzne g-k. Ilość w mb wprowadzana ręcznie.",
)
_GK_Q2 = _req(
    "CENNIK_GK_JOINT_Q2-01",
    "Warstwa wykończeniowa spoin z łagodnym przejściem do powierzchni płyty "
    "(Q2), wykonywana po zakończeniu i wyschnięciu obróbki Q1. Ilość w mb "
    "wprowadzana ręcznie. " + _DRY,
)
_GK_PRIM = _opt(
    "CENNIK_PRIM_STD-01",
    "Tylko gdy wymaga tego przyjęty system szpachlowania lub stan płyty "
    "(wyrównanie chłonności przed szpachlowaniem całopowierzchniowym). "
    + _DRY,
)
_GK_FULL = _req(
    "CENNIK_GK_FULL-01",
    "Cienkowarstwowe szpachlowanie całej powierzchni płyty (Q3). " + _DRY,
)
_GK_Q4 = _req(
    "CENNIK_GK_Q4-01",
    "Szpachlowanie całopowierzchniowe pod oświetlenie smugowe (Q4). " + _DRY,
)
_GK_SAND = _req(
    "CENNIK_SKIM_SAND-01",
    "Szlifowanie końcowe z odpylaniem. Powierzchnia gotowa do kolejnego "
    "systemu wykończeniowego.",
)
_GK_SAND_Q4 = _req(
    "CENNIK_SKIM_SAND-01",
    "Szlifowanie końcowe z odpylaniem. Warunki oglądu i oświetlenia przy "
    "odbiorze muszą zostać uzgodnione dla obiektu przed rozpoczęciem prac. "
    "Powierzchnia gotowa do kolejnego systemu wykończeniowego.",
)

# ---- descriptions -------------------------------------------------------------

_S_DESC = {
    QualityLevel.S1: (
        "Standard Wykończenia Powierzchni S1 — " + _INTERNAL + " Podstawowe "
        "techniczne przygotowanie podłoża do uzgodnionego dalszego wykończenia; "
        "bez gwarancji szpachlowania całej powierzchni. " + _NO_PAINT
    ),
    QualityLevel.S2: (
        "Standard Wykończenia Powierzchni S2 — " + _INTERNAL + " Typowy "
        "standard powierzchni gotowej do zwykłego malowania wnętrz. " + _NO_PAINT
    ),
    QualityLevel.S3: (
        "Standard Wykończenia Powierzchni S3 — " + _INTERNAL + " Podwyższony "
        "standard wizualny; dodatkową warstwę wybiera się tylko tam, gdzie jest "
        "potrzebna. " + _NO_PAINT
    ),
    QualityLevel.S4: (
        "Standard Wykończenia Powierzchni S4 — " + _INTERNAL + " Indywidualnie "
        "uzgodniony standard premium; warunki oglądu i oświetlenia przy odbiorze "
        "uzgadniane dla obiektu przed rozpoczęciem prac. Dodatkowa warstwa "
        "zależy od stanu powierzchni. " + _NO_PAINT
    ),
}
_Q_DESC = {
    QualityLevel.Q1: "Poziom jakości Q1 (PSG1) dla płyt g-k: szpachlowanie konstrukcyjne spoin z taśmą. ",
    QualityLevel.Q2: "Poziom jakości Q2 (PSG2) dla płyt g-k: Q1 oraz warstwa wykończeniowa spoin. ",
    QualityLevel.Q3: "Poziom jakości Q3 (PSG3) dla płyt g-k: Q2 oraz cienkowarstwowe szpachlowanie całej powierzchni. ",
    QualityLevel.Q4: "Poziom jakości Q4 (PSG4) dla płyt g-k: Q2 oraz szpachlowanie całopowierzchniowe pod oświetlenie smugowe; warunki odbioru uzgadniane dla obiektu. ",
}

_S_LEVELS = (QualityLevel.S1, QualityLevel.S2, QualityLevel.S3, QualityLevel.S4)


def _s_steps(
    level: QualityLevel, preparation: tuple[WorkflowStepData, ...]
) -> tuple[WorkflowStepData, ...]:
    if level == QualityLevel.S1:
        return preparation
    if level == QualityLevel.S2:
        return (*preparation, _CORNER, _SKIM_2L, _SAND)
    sand = _SAND_S4 if level == QualityLevel.S4 else _SAND
    return (*preparation, _CORNER, _SKIM_2L, _SKIM_ADD, sand)


_S_FAMILIES: tuple[tuple[str, Substrate, tuple[WorkflowStepData, ...]], ...] = (
    ("BETON", Substrate.CONCRETE,
     (_PROT, _CONC, _CLEAN, _BETON_ADH, _BETON_STD, _CRACK, _LOCAL)),
    ("TYNK_GIPSOWY", Substrate.GYPSUM_PLASTER,
     (_PROT, _CLEAN, _GIPS_STD, _CRACK, _LOCAL)),
    ("TYNK_CW", Substrate.CEMENT_LIME_PLASTER,
     (_PROT, _CLEAN, _CW_STD, _CW_HIGH, _CRACK, _LOCAL)),
)

_GK_STEPS: dict[QualityLevel, tuple[WorkflowStepData, ...]] = {
    QualityLevel.Q1: (_PROT, _GK_Q1, _GK_CORNER),
    QualityLevel.Q2: (_PROT, _GK_Q1, _GK_CORNER, _GK_Q2),
    QualityLevel.Q3: (_PROT, _GK_Q1, _GK_CORNER, _GK_Q2, _GK_PRIM, _GK_FULL, _GK_SAND),
    QualityLevel.Q4: (_PROT, _GK_Q1, _GK_CORNER, _GK_Q2, _GK_PRIM, _GK_Q4, _GK_SAND_Q4),
}


def build_default_workflow_templates() -> list[WorkflowTemplateData]:
    """Return the sixteen owner-approved default recipes, in display order."""
    templates: list[WorkflowTemplateData] = []
    for family, substrate, preparation in _S_FAMILIES:
        for level in _S_LEVELS:
            code = f"TECH_{family}_{level.value}-01"
            templates.append(
                WorkflowTemplateData(
                    code=code,
                    name_key=f"workflow_templates.seed.{code[:-3].lower()}",
                    description=_S_DESC[level],
                    substrate=substrate,
                    quality=level,
                    steps=_s_steps(level, preparation),
                )
            )
    for level, steps in _GK_STEPS.items():
        code = f"TECH_GK_{level.value}-01"
        templates.append(
            WorkflowTemplateData(
                code=code,
                name_key=f"workflow_templates.seed.{code[:-3].lower()}",
                description=_Q_DESC[level] + _NO_PAINT,
                substrate=Substrate.GYPSUM_BOARD,
                quality=level,
                steps=steps,
            )
        )
    return templates
