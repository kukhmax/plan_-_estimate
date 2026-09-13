# Kraków / Małopolskie — Price Research Catalog (Stage 9E.2)

> Canonical Stage 9, execution sub-stage **9E.2**. Architectural contracts: Stage 9A (price book & estimate boundary) and 9E.1 (market reference & sources architecture).
> This file defines **WHAT we will research in 9E.3**. It contains **NO PRICES and no invented market rates.**

## 1. Purpose & principles

Every research item must represent **one commercially understandable scope**. The market prices
several finishing scopes differently, so vague entries ("szpachlowanie") are forbidden. Each row
carries an explicit scope, a compatible unit, a labor/material scope, and wording concrete enough
that multiple sources can be compared in 9E.3.

Dominant default for the catalog: **labor-only, prepared substrate, per m²** — stated explicitly on
each row wherever the market normally prices it that way. Labor+material rows exist only where the
market commonly quotes them combined (priming, mold treatment, glass fiber with material, full
microcement system).

## 2. Catalog conventions

- **Columns** (per group table): Code · PL name · RU name · Category · Unit · Price scope · Quality · Priority · Comparability · Notes.
- **Categories / units / scopes** reuse the Stage 9B enums: `PriceCategory` (11), `PriceUnit` (`M2 LM PCS HOUR DAY FLAT`), `PriceScope` (`LABOR MATERIAL LABOR_AND_MATERIAL`).
- **Code policy** — stable, implementation-friendly, `CENNIK_*` style: `<CENNIK_>_<SEMANTIC-GROUP>_<VARIANT>-<NN>`, e.g. `CENNIK_SKIM_2L-01`. Codes are **proposals** for 9E.6 implementation; they remain immutable after data creation per Stage 9A §16.
- **Quality column** — the 9E.1 rule: quality levels are recorded **only where source wording supports them**; otherwise `—` and the row is treated generically (see §9 Quality strategy).
- **Priority** — `P1` core / must research · `P2` useful / research if enough sources · `P3` optional / later (and frequent OWN_PRICE candidate).
- **Comparability** — what counts as comparable evidence for that exact row (the 9E.3 / 9E.4 filter).

## 3. Preparation & protection (Batch A)

| Code | PL name | RU name | Cat. | Unit | Scope | Quality | Prio | Comparability | Notes |
|---|---|---|---|---|---|---|---|---|---|
| CENNIK_PREP_PROT-01 | Zabezpieczenie podłóg i powierzchni (folia, taśma, osłony stolarki) | Защита полов и поверхностей (пленка, лента, укрытие столярки) | PREPARATION | M2 | LABOR | — | P2 | Comparable: floor protection with foil+tape across the flat, per m² protected area (or a flat-rate that converts to m²). Not comparable: protecting only stairs, foil without tape, demolition work. | Often included in the overall price — skip if sources bill a flat rate with no breakdown. |
| CENNIK_PREP_WALLP-01 | Usuwanie tapet (zdzieranie, utylizacja) | Снятие обоев (сдирание, утилизация) | PREPARATION | M2 | LABOR | — | P1 | Comparable: wallpaper removal incl. leaving the substrate ready, per m², labor. Not comparable: removal + re-skimming package, fiber wall coverings (PREP_FLEECE), wallpapering. | Thick / fiber wall coverings belong to PREP_FLEECE. |
| CENNIK_PREP_SCRAPE-01 | Zdzieranie starych powłok malarskich / starej gładzi kredowej | Сдирание старых лакокрасочных покрытий / старой шпаклевки | PREPARATION | M2 | LABOR | — | P1 | Comparable: scraping paint/old chalk skim coat down to substrate, per m², labor. Not comparable: oil-paint "lamperia" needing degrease+sanding, plaster demolition, waste disposal billed separately. | |
| CENNIK_PREP_FLEECE-01 | Zdzieranie starej flizeliny / włókniny szklanej | Снятие старого стеклохолста | PREPARATION | M2 | LABOR | — | P2 | Comparable: full removal of old glass-fiber fleece, per m². Not comparable: leaving fleece in place (re-cover), removal bundled with skim coat. | |
| CENNIK_PREP_DEGR-01 | Odtłuszczanie i usuwanie zabrudzeń podłoża (np. kuchnia) | Обезжиривание и удаление загрязнений основания | PREPARATION | M2 | LABOR | — | P2 | Comparable: degreasing substrate before painting, per m², degreaser within labor. Not comparable: mechanical sanding with flattening, disinfection. | |
| CENNIK_PREP_MOLD-01 | Usuwanie pleśni i grzyba z preparatem grzybobójczym | Удаление плесени и грибка с биоцидной обработкой | PREPARATION | M2 | LABOR_AND_MATERIAL | — | P1 | Comparable: mold removal + biocide/impregnation, per m², material included. Not comparable: biocide only without removing the layer, wooden substrates, damp-wall warranty cases. | |
| CENNIK_PREP_CLEAN-01 | Odkurzanie i czyszczenie podłoża przed wykończeniem | Пылесосная очистка основания перед отделкой | PREPARATION | M2 | LABOR | — | P3 | Comparable: vacuuming/cleaning the substrate after sanding. Not comparable: final flat cleaning, window washing, furniture removal. | OWN_PRICE candidate — rarely priced independently. |

## 4. Priming (Batch A) — category mapping: `PREPARATION`

Stage 9 `PriceCategory` has **no dedicated priming member**; priming rows use `PREPARATION`
(documenting §3 of the 9E.2 contract). A future category split, if ever needed, is a separate decision.

| Code | PL name | RU name | Cat. | Unit | Scope | Quality | Prio | Comparability | Notes |
|---|---|---|---|---|---|---|---|---|---|
| CENNIK_PRIM_STD-01 | Gruntowanie gruntem penetrującym (pod szpachlowanie) | Грунтование проникающей грунтовкой (под шпаклевку) | PREPARATION | M2 | LABOR_AND_MATERIAL | — | P1 | Comparable: 1 coat penetrating primer + labor, per m², material included. Not comparable: primer material only (no labor), reinforced 2-coat priming (PRIM_HIGH), primer under paint. | Most common focus for web research. |
| CENNIK_PRIM_ADH-01 | Gruntowanie gruntem kontaktowym adhezyjnym | Грунтование адгезионной (контактной) грунтовкой | PREPARATION | M2 | LABOR_AND_MATERIAL | — | P2 | Comparable: quartz-contact primer on difficult substrate, per m². Not comparable: tile adhesive markets, mineral decorative plasters. | |
| CENNIK_PRIM_HIGH-01 | Gruntowanie podłoża wysokochłonnego (dwukrotne) | Грунтование высоковпитывающего основания (2 слоя) | PREPARATION | M2 | LABOR_AND_MATERIAL | — | P3 | Comparable: double priming of high-absorption substrate (gas concrete, cement render). Not comparable: single coat, priming with defect repair. | |
| CENNIK_PRIM_PAINT-01 | Gruntowanie przed malowaniem (pod farbę) | Грунтование перед покраской | PREPARATION | M2 | LABOR_AND_MATERIAL | — | P2 | Comparable: primer under paint on smoothed skim coat, per m². Not comparable: primer under skim coat (PRIM_STD), undercoat paint billed within painting. | |

## 5. Skim coat / filling / szpachlowanie (Batch A)

| Code | PL name | RU name | Cat. | Unit | Scope | Quality | Prio | Comparability | Notes |
|---|---|---|---|---|---|---|---|---|---|
| CENNIK_SKIM_1L-01 | Gładź szpachlowa — 1 warstwa (cała powierzchnia) | Шпаклевка — 1 слой (вся поверхность) | SKIM_COAT | M2 | LABOR | — | P1 | Comparable: one full-surface skim coat, labor, per m². Not comparable: two coats, skim+sanding package, drywall joint finishing. | |
| CENNIK_SKIM_2L-01 | Gładź szpachlowa — 2 warstwy (pakiet) | Шпаклевка — 2 слоя (пакет) | SKIM_COAT | M2 | LABOR | — | P1 | Comparable: two full-surface coats, labor, per m². Not comparable: one coat, 3 coats, package incl. sanding. | |
| CENNIK_SKIM_3L-01 | Gładź szpachlowa — 3 warstwy | Шпаклевка — 3 слоя | SKIM_COAT | M2 | LABOR | — | P2 | Comparable: three full-surface coats, labor, per m². | Only if sources actually price 3 coats. |
| CENNIK_SKIM_SAND-01 | Szlifowanie gładzi z odpylaniem | Шлифовка шпаклевки с обеспыливанием | SKIM_COAT | M2 | LABOR | — | P1 | Comparable: sanding + dust extraction, per m². Not comparable: sanding bundled with painting, wet sanding. | |
| CENNIK_SKIM_PKG-01 | Pakiet gładź 2x + szlifowanie | Пакет: шпаклевка 2 слоя + шлифовка | SKIM_COAT | M2 | LABOR | — | P1 | Comparable: full 2-coat skim + sanding + dust removal package, per m². Not comparable: skim alone, sanding alone, 3-coat package. | Prime web-research target; many firms quote this package. |
| CENNIK_SKIM_CRACK-01 | Naprawa rys i pęknięć (poszerzenie, wypełnienie) | Ремонт трещин (расшивка, заполнение) | SKIM_COAT | LM | LABOR | — | P2 | Comparable: crack repair per running meter, labor. Not comparable: flat-rate per room (only if not convertible to mb), reinforcing mesh included. | |
| CENNIK_SKIM_CORNER-01 | Montaż narożników ochronnych (kątowniki) | Монтаж защитных уголков | SKIM_COAT | LM | LABOR | — | P2 | Comparable: corner-bead installation embedded in skim, per mb. Not comparable: decorative aluminum profiles, material prices. | |
| CENNIK_SKIM_LOCAL-01 | Szpachlowanie lokalne / naprawy punktowe | Локальная шпаклевка / точечный ремонт | SKIM_COAT | M2 | LABOR | — | P3 | Comparable: small-area defect repair, labor, per m². Not comparable: full skim, "per point" flat rates. | OWN_PRICE candidate. |
| CENNIK_SKIM_SQ-01 | Gładź pod wyższą klasę z kontrolą lampą smugową (S3/S4) | Шпаклевка повышенного качества с контролем лампой (S3/S4) | SKIM_COAT | M2 | LABOR | S3/S4 (hint) | P3 | Comparable: **only** if the source explicitly describes skimming/sanding under strip light (lampa smugowa / gładź szlifowana). Not comparable: ordinary "smooth" skim. | Quality S-level **only** on literal source wording — see Quality strategy, §9. |

## 6. Gypsum board / drywall finishing (Batch B)

**Q1–Q4 structure decision (§5):** generic commercial rows + optional `quality_level` hint — **not**
four separate research items. Contractors rarely publish Q1–Q4 labels; they price distinguishable
scopes (joint finishing vs full-surface skim). Mapping notes: Q1 = joint filling only · Q2 = joints +
feathering · Q3 = full-surface skim · Q4 = full-surface skim ≥1 mm / under strip light. Explicit
quality rows (CENNIK_GK_Q4-01) exist **only** where source wording justifies them.

Structural installation (partition construction) is **out of scope** — this is finishing only.

| Code | PL name | RU name | Cat. | Unit | Scope | Quality | Prio | Comparability | Notes |
|---|---|---|---|---|---|---|---|---|---|
| CENNIK_GK_JOINT-01 | Szpachlowanie spoin płyt g-k z taśmą (Q1/Q2) | Шпаклевка швов ГКЛ с лентой (Q1/Q2) | DRYWALL | M2 | LABOR | Q1/Q2 (hint) | P1 | Comparable: joint filling + tape embedding + screw heads, per m² of board, labor. Not comparable: full-surface skim, board installation. | |
| CENNIK_GK_FULL-01 | Szpachlowanie całopowierzchniowe płyt g-k (Q3) | Шпаклевка всей поверхности ГКЛ (Q3) | DRYWALL | M2 | LABOR | Q3 (hint) | P1 | Comparable: full-surface skim over the whole board, labor, per m². | |
| CENNIK_GK_SCREW-01 | Maskowanie łbów wkrętów | Маскировка шляпок саморезов | DRYWALL | M2 | LABOR | — | P3 | Comparable: screw-head filling alone. Not comparable: any package. | Usually priced within joint work — **do not duplicate**. OWN_PRICE candidate. |
| CENNIK_GK_CORNER-01 | Wykończenie naroży zewnętrznych g-k (kątownik + szpachla) | Отделка внешних углов ГКЛ (уголок + шпаклевка) | DRYWALL | LM | LABOR | — | P2 | Comparable: external corner with bead + skim, per mb. | |
| CENNIK_GK_Q4-01 | Szpachlowanie całopowierzchniowe g-k pod oświetlenie smugowe (Q4) | Шпаклевка ГКЛ под боковой свет (Q4) | DRYWALL | M2 | LABOR | Q4 | P2 | Comparable: **only** if the source describes full ≥1 mm skim or strip-light readiness. Not comparable: generic smooth-wall skim. | |

## 7. Glass fiber / fleece (Batch A→B split: research with GK batch)

Category `GLASS_FIBER`. **Do not merge** plaster-reinforcing mesh with decorative/paint fleece.

| Code | PL name | RU name | Cat. | Unit | Scope | Quality | Prio | Comparability | Notes |
|---|---|---|---|---|---|---|---|---|---|
| CENNIK_GF_FLIZ_L-01 | Klejenie flizeliny / włókniny szklanej — robocizna | Поклейка стеклохолста — работа | GLASS_FIBER | M2 | LABOR | — | P1 | Comparable: application only, per m², labor. Not comparable: material included (GF_FLIZ_M), painting the fleece included, heavy 50 g vs light 40 g walec (record grammage). | |
| CENNIK_GF_FLIZ_M-01 | Klejenie flizeliny / włókniny szklanej z materiałem (klej + włóknina) | Поклейка стеклохолста с материалом (клей + холст) | GLASS_FIBER | M2 | LABOR_AND_MATERIAL | — | P2 | Comparable: adhesive + fleece + application, per m², material included. Note grammage 40–50 g/m². | |
| CENNIK_GF_MESH-01 | Montaż siatki zbrojącej / włókniny zbrojącej na tynki | Монтаж армирующей сетки на штукатурке | GLASS_FIBER | M2 | LABOR | — | P2 | Comparable: reinforcing mesh embedded in the render coat, labor, per m². Not comparable: paint fleece, facades. | |

## 8. Painting (Batch B)

**Standard default row** (PAINT_2K): 2 coats · white wall paint on a **prepared substrate** (after skim/
sanding) · **labor-only** · per m². Every painting source is compared against this default first.

| Code | PL name | RU name | Cat. | Unit | Scope | Quality | Prio | Comparability | Notes |
|---|---|---|---|---|---|---|---|---|---|
| CENNIK_PAINT_2K-01 | Malowanie ścian — 2 warstwy (standard) | Покраска стен — 2 слоя (стандарт) | PAINTING | M2 | LABOR | — | P1 | Comparable: 2 coats, white wall paint, prepared substrate, labor, per m². **Not comparable:** paint included (material), 1 coat, substrate repairs included, flat-rate per room, colored paint premium. | The default reference row. |
| CENNIK_PAINT_1K-01 | Malowanie — 1 warstwa (odświeżenie) | Покраска — 1 слой (освежение) | PAINTING | M2 | LABOR | — | P2 | Comparable: single refresh coat, labor, per m². | |
| CENNIK_PAINT_3K-01 | Malowanie — 3 warstwy | Покраска — 3 слоя | PAINTING | M2 | LABOR | — | P3 | Comparable: 3 coats. | Only if commercially common in sources. |
| CENNIK_PAINT_CEIL-01 | Malowanie sufitów — 2 warstwy | Покраска потолков — 2 слоя | PAINTING | M2 | LABOR | — | P1 | Comparable: ceilings, 2 coats, labor, per m². | Ceiling rates often differ from walls — keep separate. |
| CENNIK_PAINT_COL-01 | Malowanie kolorem (zmiana koloru / kolor) | Покраска в цвет (смена цвета) | PAINTING | M2 | LABOR | — | P2 | Comparable: full color coverage, labor, per m². Not comparable: white at standard price, premium paints. | |
| CENNIK_PAINT_MASK-01 | Maskowanie stolarki i detali (taśma, folia) | Оклейка столярки и деталей (лента, пленка) | PAINTING | M2 | LABOR | — | P3 | Comparable: masking/frame-protection labor only, per m². | OWN_PRICE candidate — frequently included. |
| CENNIK_PAINT_MULTI-01 | Malowanie wielokolorowe / wzory | Многоцветная покраска / узоры | PAINTING | M2 | LABOR | — | P3 | Comparable: multi-color/pattern labor, per m². | Only if sources distinguish it. |

## 9. Reveals / ościeża (Batch C) — Stage 5F compatible

Reveal rows must align with the future 5F ościeża work scale and with the existing
9B seed (`CENNIK_REVEAL_GENERIC_M2` / `CENNIK_REVEAL_GENERIC_LM`). **Do NOT assume LM and M2 are
interchangeable** — the m² rows cover the reveal *as a surface*, the LM rows cover linear reveal work.
Window reveal is the default; door reveal **only** if sources price it differently.

| Code | PL name | RU name | Cat. | Unit | Scope | Quality | Prio | Comparability | Notes |
|---|---|---|---|---|---|---|---|---|---|
| CENNIK_REV_PREP-01 | Ościeża — przygotowanie podłoża | Откосы — подготовка основания | REVEAL | M2 | LABOR | — | P1 | Comparable: reveal substrate prep, per m² of visible reveal surface. Not comparable: whole-wall prep. | |
| CENNIK_REV_SKIM-01 | Ościeża — szpachlowanie | Откосы — шпаклевка | REVEAL | M2 | LABOR | — | P1 | Comparable: reveal skim coat, per m². | |
| CENNIK_REV_SAND-01 | Ościeża — szlifowanie | Откосы — шлифовка | REVEAL | M2 | LABOR | — | P2 | Comparable: reveal sanding, per m². | |
| CENNIK_REV_PAINT-01 | Ościeża — malowanie (m²) | Откосы — покраска (м²) | REVEAL | M2 | LABOR | — | P1 | Comparable: reveal painting, per m² of reveal. Not comparable: LM-based quotations. | |
| CENNIK_REV_WORK_LM-01 | Ościeża — prace liniowe / obróbka ościeży (mb) | Откосы — линейные работы / отводы (пог. м) | REVEAL | LM | LABOR | — | P1 | Comparable: linear reveal work per running meter (mb). **Not comparable:** m² reveal pricing — different basis. | 5F mb basis. |
| CENNIK_REV_PAINT_LM-01 | Ościeża — malowanie (mb) | Откосы — покраска (пог. м) | REVEAL | LM | LABOR | — | P2 | Comparable: reveal painting per mb, **only if** sources quote LM. | |

## 10. Microcement (Batch D) — system vs labor separation preserved

**Critical rule (9E.1 §11):** never collapse labor-only and full-system (labor+material) prices into
one market range. Labor-only rows are `LABOR`; full-system rows are `LABOR_AND_MATERIAL`. Substrate
prep, primer/epoxy leveling coat and membrane (hydroizolacja) are recorded in comparability notes —
never silently assumed.

| Code | PL name | RU name | Cat. | Unit | Scope | Quality | Prio | Comparability | Notes |
|---|---|---|---|---|---|---|---|---|---|
| CENNIK_MC_WALL_L-01 | Mikrocement na ściany — robocizna | Микроцемент на стены — работа | MICROCEMENT | M2 | LABOR | — | P1 | Comparable: application labor only (owner supplies system materials), per m². Not comparable: any system/material price. | |
| CENNIK_MC_WALL_S-01 | Mikrocement na ściany — pełny system z materiałem | Микроцемент на стены — полная система с материалом | MICROCEMENT | M2 | LABOR_AND_MATERIAL | — | P1 | Comparable: complete thin-layer microcement system (primer + leveling + microcement + sealer) incl. material, per m². Must state substrate prep scope. | |
| CENNIK_MC_FLOOR_L-01 | Mikrocement na posadzkę — robocizna | Микроцемент на пол — работа | MICROCEMENT | M2 | LABOR | — | P2 | Comparable: floor application labor only, per m². | Floor flatness prep almost always extra. |
| CENNIK_MC_FLOOR_S-01 | Mikrocement na posadzkę — pełny system z materiałem | Микроцемент на пол — полная система с материалом | MICROCEMENT | M2 | LABOR_AND_MATERIAL | — | P2 | Comparable: full floor system incl. material, per m². Not comparable: wall system price. | |
| CENNIK_MC_SHOWER-01 | Mikrocement — strefa prysznicowa (system z hydroizolacją) | Микроцемент — душевая зона (система с гидроизоляцией) | MICROCEMENT | M2 | LABOR_AND_MATERIAL | — | P2 | Comparable: shower-zone microcement incl. membrane (hydroizolacja), per m². Must state membrane + fall requirements. | |
| CENNIK_MC_STAIRS-01 | Mikrocement na schody | Микроцемент на лестницу | MICROCEMENT | M2 | LABOR_AND_MATERIAL | — | P3 | Comparable: stair microcement, per m² or per step (record basis). | OWN_PRICE candidate if no market basis. |

## 11. Decorative / Venetian finish (Batch E)

Focus on services relevant to our business. **Do not over-expand** exotic finishes in 9E.3.

| Code | PL name | RU name | Cat. | Unit | Scope | Quality | Prio | Comparability | Notes |
|---|---|---|---|---|---|---|---|---|---|
| CENNIK_DEC_VEN-01 | Stiuk wenecki — klasyczny | Венецианская штукатурка — классическая | DECORATIVE | M2 | LABOR | — | P1 | Comparable: classic Venetian plaster application, labor, per m². Not comparable: veined marble-look workshop grades, lime plaster interior coats. | |
| CENNIK_DEC_VEN_MAR-01 | Stiuk wenecki — efekt marmuru z żyłkowaniem | Венецианская штукатурка — мраморный эффект с прожилками | DECORATIVE | M2 | LABOR | — | P2 | Comparable: custom veining/waxing workshop work, labor, per m². | Substantially higher than classic. |
| CENNIK_DEC_CONC-01 | Efekt betonu / beton architektoniczny | Эффект бетона / архитектурный бетон | DECORATIVE | M2 | LABOR | — | P2 | Comparable: architectural-concrete effect, labor, per m². | |
| CENNIK_DEC_GENERIC-01 | Tynk dekoracyjny — ogólny | Декоративная штукатурка — общая | DECORATIVE | M2 | LABOR | — | P2 | Comparable: generic decorative render (stone/sand, glaze effects), labor, per m². | Fallback row; specific systems researched separately. |

## 12. Quality levels S1–S4 — research limitation (documented)

Contractors in the Kraków / Małopolskie market **do not generally publish S1–S4 (or Q1–Q4) labels**.
Consequently:

- The catalog uses **generic commercial rows** as the primary research vehicle.
- Quality levels are attached **only where source wording supports them** (`CENNIK_GK_Q4-01`,
  `CENNIK_SKIM_SQ-01`, P3-only).
- **We will not manufacture S1–S4 market prices** from unpriced or vague sources; quality-dependent
  pricing is derived from words, never invented from labels (9E.1 §13).
- In 9E.6 implementation the generic rows may carry the `quality_level` **applicability hint** —
  never an inferred market claim.

## 13. OWN_PRICE / internal items

Rows that should exist in the catalog but **may have no external market evidence** — attach
`OWN_PRICE` sources or derive later from labor/time, and never force fake market references (9E.1 §7):

- `CENNIK_PREP_CLEAN-01` — cleaning/vacuuming (usually internal).
- `CENNIK_SKIM_LOCAL-01` — local/point repairs.
- `CENNIK_GK_SCREW-01` — screw-head masking (usually bundled).
- `CENNIK_PAINT_MASK-01` — masking/frame protection (usually included).
- `CENNIK_PAINT_MULTI-01` — multi-color/patterns (project-based).
- `CENNIK_MC_STAIRS-01` — stairs microcement (mostly bespoke).
- `CENNIK_PREP_PROT-01` — floor protection (often flat-rate or internal).

If 9E.3 finds no market basis for these, they are assigned `OWN_PRICE` in 9E.4/9E.5 — **no invented
"market" values**.

## 14. Research batches (Stage 9E.3 execution)

Research is split into manageable batches. **Do not perform research now** (9E.2 is catalog-only).

- **Batch A — Preparation / priming / skim / sanding**: CENNIK_PREP_* (7), CENNIK_PRIM_* (4), CENNIK_SKIM_* (9).
- **Batch B — Painting / glass fiber / GK**: CENNIK_PAINT_* (7), CENNIK_GF_* (3), CENNIK_GK_* (5).
- **Batch C — Reveals**: CENNIK_REV_* (6).
- **Batch D — Microcement**: CENNIK_MC_* (6).
- **Batch E — Decorative / Venetian**: CENNIK_DEC_* (4).

Total catalog: **51 research items** (P1 = 20 · P2 = 22 · P3 = 9).

## 15. Source compatibility quick rules (global)

- Compare **labor-only** with labor-only; never mix labor-only and labor+material numbers into one range (9E.1 §11).
- Compare **only compatible units**: M2↔m²↔m2 · LM↔mb/metr bieżący · PCS↔szt. · HOUR↔godz. · DAY↔dzień · FLAT↔ryczałt only with comparable scope. **No FLAT↔M2 conversion** (9E.1 §12).
- Each source contributes in exactly one quoting mode: a single quoted price, a quoted range, or qualitative context (9E.1 §7).
- A **single contractor page is a data point, never a "market average"**; high-impact items prefer 3+ independent sources; single-source references carry a methodology note (9E.1 §7).
- Manufacturer/material-store sources support **material/system costs**, not labor rates (9E.1 §7).
- Quality evidence requires **source wording** — never infer S/Q from marketing text (9E.1 §13).