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

---

# PART 9E.4 — Normalized master review (all 51 research items)

> Canonical Stage 9, execution sub-stage **9E.4**. This part **normalizes** the raw 9E.3 research
> (five batch evidence files: `price-research-batch-a.md` … `-e.md`) into one master review.
> It is **documentation only**: no rows are written to the database, no placeholder seeds are
> replaced, no migration is created, no API/frontend behavior changes. All 9E.3 raw research is
> preserved verbatim; nothing in the batch files was edited.

## 16.1 Decision framework and invariant

The architectural invariant is preserved:

**`PriceItem.price` (owner/commercial price)  ≠  market reference ranges  ≠  source quoted prices.**

The `market_min` / `market_max` / `reference_price` values below are **normalized evidence windows**
derived in 9E.3 from dated, URL-traceable source quotes — they are *supporting evidence only*, never
an automatic owner price. A starting owner price is **proposed only for `MARKET_SUPPORTED`** rows and
is still subject to the owner's final number at 9E.5. `OWN_PRICE` and `DROP_MERGE_RESTRUCTURE` rows
deliberately carry **no proposable starting price**.

Three decisions are used, each exactly one per item:

1. **MARKET_SUPPORTED** — enough comparable market evidence exists to propose a starting owner
   price (the normalized evidence window becomes the reference frame for the 9E.5 owner price).
2. **OWN_PRICE** — external market evidence is insufficient, structurally incompatible, or too weak
   for a comparable starting price; the owner shall define the commercial price internally.
3. **DROP_MERGE_RESTRUCTURE** — the catalog item does not match how the market actually quotes/sells
   the work and must be dropped, merged, renamed, or structurally changed before implementation.

## 16.2 Decision totals (51/51 covered)

| Decision | Count | Share |
|---|---|---|
| MARKET_SUPPORTED | **26** | 51 % |
| OWN_PRICE | **15** | 29 % |
| DROP_MERGE_RESTRUCTURE | **10** | 20 % |
| **TOTAL** | **51** | 100 % |

## 16.3 Master review table

Reading notes: `min`/`max`/`ref` are **normalized evidence windows** (zł, PLN), region-keyed — not
owner prices. Empty cells (`—`) mean the evidence did not justify a numeric value. `scope` follows
the Stage 9B enum (`LABOR` / `LABOR_AND_MATERIAL`); quality levels appear only where source wording
supports them (`hint` = applicability hint, not a market claim).

| # | Code | PL name (short) | Category | Unit | Scope | Quality | Decision | market_min | market_max | reference | Region basis | Conf. | Sources | Normalization note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | CENNIK_PREP_PROT-01 | Zabezpieczenie podłóg i powierzchni | PREPARATION | M2 | LABOR | — | OWN_PRICE | 5 | 15 | — | Kraków + PL | MEDIUM | 4 (2 partial) | Market usually includes/flat-rates it; catalog §13 pre-flag. Evidence kept as context. |
| 2 | CENNIK_PREP_WALLP-01 | Usuwanie tapet | PREPARATION | M2 | LABOR | — | MARKET_SUPPORTED | 10 | 30 | 20 | Kraków + PL | HIGH | 4 | Solid comparable labor band. |
| 3 | CENNIK_PREP_SCRAPE-01 | Zdzieranie starych powłok / gładzi | PREPARATION | M2 | LABOR | — | MARKET_SUPPORTED | 10 | 35 | 18 | Kraków + PL | HIGH | 4 + 1 suppl. | Comparable scraping to substrate. |
| 4 | CENNIK_PREP_FLEECE-01 | Zdzieranie flizeliny / włókniny szklanej | PREPARATION | M2 | LABOR | — | OWN_PRICE | 35 | 64 | — | PL | LOW | 1 (proxy tier) | Dedicated flizelina removal is never priced standalone; 35–64 is a proxy tier (fiberglass wallpaper), structurally not comparable. |
| 5 | CENNIK_PREP_DEGR-01 | Odtłuszczanie podłoża | PREPARATION | M2 | LABOR | — | OWN_PRICE | 10 | 15 | — | PL | LOW | 1 | Single source; degreasing is normally bundled with substrate washing/prep. Context only. |
| 6 | CENNIK_PREP_MOLD-01 | Usuwanie pleśni i grzyba (z preparatem) | PREPARATION | M2 | LABOR_AND_MATERIAL | — | MARKET_SUPPORTED | 30 | 120 | — | PL | MEDIUM | 4 + 1 suppl. | Broad spread preserved; L+M scope explicit. |
| 7 | CENNIK_PREP_CLEAN-01 | Odkurzanie / czyszczenie podłoża | PREPARATION | M2 | LABOR | — | OWN_PRICE | — | — | — | — | INSUFFICIENT | 0 usable | Never priced standalone (folded into gładź/malowanie or billed hourly). Standalone post-sanding cleaning evidence gap (known issue A). |
| 8 | CENNIK_PRIM_STD-01 | Grunt penetrujący (pod szpachlowanie) | PREPARATION | M2 | LABOR_AND_MATERIAL | — | MARKET_SUPPORTED | 7 | 15 | — | Kraków + PL | MEDIUM | 6 rows / 2 L+M-computable | Primary priming row. |
| 9 | CENNIK_PRIM_ADH-01 | Grunt kontaktowy adhezyjny | PREPARATION | M2 | LABOR_AND_MATERIAL | — | OWN_PRICE | — | — | — | PL | LOW | 1 (component evidence) | Component evidence only (material 20–40/l, uplift 5–10); no direct per-m² quote. Company/product-specific. |
| 10 | CENNIK_PRIM_HIGH-01 | Gruntowanie dwukrotne (wysokochłonne) | PREPARATION | M2 | LABOR_AND_MATERIAL | — | OWN_PRICE | — | — | — | PL | LOW | 1 (+1 qualitative) | Single-source double-coat; usually a custom premium. |
| 11 | CENNIK_PRIM_PAINT-01 | Gruntowanie przed malowaniem | PREPARATION | M2 | LABOR_AND_MATERIAL | — | MARKET_SUPPORTED | 3 | 15 | — | Kraków + PL | MEDIUM | 6 rows / 2 L+M-explicit | Kept separate from PRIM_STD (paint substrate). |
| 12 | CENNIK_SKIM_1L-01 | Gładź szpachlowa — 1 warstwa | SKIM_COAT | M2 | LABOR | — | MARKET_SUPPORTED | 30 | 50 | 40 | Kraków + PL | HIGH | 4 | One full-surface coat. |
| 13 | CENNIK_SKIM_2L-01 | Gładź szpachlowa — 2 warstwy | SKIM_COAT | M2 | LABOR | — | MARKET_SUPPORTED | 35 | 75 | 55 | Kraków + PL | HIGH | 4 | Two full-surface coats. |
| 14 | CENNIK_SKIM_3L-01 | Gładź szpachlowa — 3 warstwy | SKIM_COAT | M2 | LABOR | — | DROP_MERGE_RESTRUCTURE | 60 | 80 | — | PL | MEDIUM | 2 (1 suspected dup.) + 2 partial | Overlap/duplication risk with SKIM_2L + SAND (known issue A). Restructure as **SKIM_2L + 3rd-layer add-on**; keep a standalone 3-coat row only if owner needs it as an explicit package. Do not seed as a full-surface row while 2-coat+SAND already covers the same band. |
| 15 | CENNIK_SKIM_SAND-01 | Szlifowanie gładzi z odpylaniem | SKIM_COAT | M2 | LABOR | — | MARKET_SUPPORTED | 10 | 25 | 14 | Kraków + PL | HIGH | 4 | Sanding + dust extraction. |
| 16 | CENNIK_SKIM_PKG-01 | Pakiet gładź 2x + szlifowanie | SKIM_COAT | M2 | LABOR | — | DROP_MERGE_RESTRUCTURE | 35 | 70 | 50 | PL (+ Kraków L+M suppl.) | MEDIUM | 4 | Component-sum mismatch (known issue A): SKIM_2L + SAND ≈ **65–91** exceeds package band **35–70** → package is volume-discounted/component-limited. Restructure: define exact package scope (which components included), then either re-anchor to component-sum consistency or merge into SKIM_2L + SKIM_SAND. |
| 17 | CENNIK_SKIM_CRACK-01 | Naprawa rys i pęknięć | SKIM_COAT | LM | LABOR | — | MARKET_SUPPORTED | 62 | 95 | — | PL | LOW | 2 direct + 2 non-comp. | Market prices crack repair per mb; thin evidence. Resolve unit (LM) and scope (widen + fill, material excluded) explicitly before owner pricing. |
| 18 | CENNIK_SKIM_CORNER-01 | Montaż narożników ochronnych | SKIM_COAT | LM | LABOR | — | MARKET_SUPPORTED | 12 | 22 | 16 | Kraków + PL | HIGH | 3 | — |
| 19 | CENNIK_SKIM_LOCAL-01 | Szpachlowanie lokalne / punktowe | SKIM_COAT | M2 | LABOR | — | OWN_PRICE | 9 | 50 | — | Kraków + PL | MEDIUM | 4 (3 orgs) | Real band is extremely context-dependent (hole size, depth). Owner defines a rate; research suggests Kraków 25–40 as sanity anchor, never a market claim. |
| 20 | CENNIK_SKIM_SQ-01 | Gładź pod wyższą klasę z lampą smugową (S3/S4) | SKIM_COAT | M2 | LABOR | S3/S4 (hint) | MARKET_SUPPORTED | 60 | 80 | — | PL (+ Kraków mention) | LOW | 3 priced partial + 1 qual. | Quality hint only on literal "lampa smugowa" wording. |
| 21 | CENNIK_GK_JOINT-01 | Szpachlowanie spoin g-k z taśmą (Q1/Q2) | DRYWALL | M2 | LABOR | Q1/Q2 (hint) | DROP_MERGE_RESTRUCTURE | 34 | 46 | — | Kraków-regional + PL | MEDIUM | 3 (+1 flagged) | Unit model mismatch (known issue C): market cenniki price joints per **mb**; the M2 evidence is a single local Kraków row (34–46/m² board). Restructure: confirm **LM as the joint-finishing unit** (betonizm Q1 12–18, koszt-wykonczen Q1 15/Q2 18–20, Kraków Q2 24/mb) with the M2 aggregate optional/report-only. |
| 22 | CENNIK_GK_FULL-01 | Szpachlowanie całopowierzchniowe (Q3) | DRYWALL | M2 | LABOR | Q3 (hint) | MARKET_SUPPORTED | 28 | 45 | 40 | Kraków + PL | MEDIUM | 3 (2 explicit Q3) | Full-surface board skim. |
| 23 | CENNIK_GK_SCREW-01 | Maskowanie łbów wkrętów | DRYWALL | M2 | LABOR | — | OWN_PRICE | — | — | — | — | INSUFFICIENT | 0 standalone | Bundled into the Q1/Q2 joint tier; catalog "do not duplicate". Seed only if the owner wants a standalone billable line. |
| 24 | CENNIK_GK_CORNER-01 | Wykończenie naroży zewnętrznych g-k | DRYWALL | LM | LABOR | — | MARKET_SUPPORTED | 10 | 22 | 18 | Kraków + PL | MEDIUM | 3 (+2 partial) | Unit normalized to LM; the mismatched Kraków "22–30 zł/m²" cell (linear service on an M2 unit) is excluded, not merged. |
| 25 | CENNIK_GK_Q4-01 | Szpachlowanie całopowierzchniowe g-k pod smugę (Q4) | DRYWALL | M2 | LABOR | Q4 | MARKET_SUPPORTED | 40 | 80 | — | PL | MEDIUM | 2 explicit Q4 | Conflict resolved: betonizm.pl main-table 60–80 is used; its chart 110 is a documented outlier, not merged. |
| 26 | CENNIK_GF_FLIZ_L-01 | Klejenie flizeliny / włókniny szklanej — robocizna | GLASS_FIBER | M2 | LABOR | — | OWN_PRICE | — | — | — | PL (+ Kraków row) | LOW | 0 tech-A | No technology-A (flizelina malarska) labour price exists; tech-B fiberglass wallpaper analog (48,82–77) is NOT substitutable (known issue D). |
| 27 | CENNIK_GF_FLIZ_M-01 | Klejenie flizeliny — z materiałem | GLASS_FIBER | M2 | LABOR_AND_MATERIAL | — | OWN_PRICE | — | — | — | PL (+ Kraków row) | LOW | 0 tech-A; 1 tech-B analog | Same as above for L+M (tech-B L+M analog 110–190 excluded from a tech-A price basis). |
| 28 | CENNIK_GF_MESH-01 | Montaż siatki zbrojącej na tynki | GLASS_FIBER | M2 | LABOR | — | MARKET_SUPPORTED | 12 | 58 | — | Kraków + PL | MEDIUM | 2 (scope caveat) | Wide band; scope caveat — confirm "embedded in the render coat" only. |
| 29 | CENNIK_PAINT_2K-01 | Malowanie ścian — 2 warstwy (standard) | PAINTING | M2 | LABOR | — | MARKET_SUPPORTED | 10 | 28 | 18 | Kraków + PL | HIGH | 5 (1 partial, 1 flagged) | Default reference row. Coat-count structure: 2 coats on prepared substrate; no double-count of PRIM_PAINT/SKIM (known issue B). |
| 30 | CENNIK_PAINT_1K-01 | Malowanie — 1 warstwa (odświeżenie) | PAINTING | M2 | LABOR | — | MARKET_SUPPORTED | 8 | 30 | — | Kraków + PL | MEDIUM | 1 strong + 2 partial | Re-verify cennikremontów Kraków 1-coat row (16–30 vs own 2-coat 10–28) before owner pricing (known issue B). |
| 31 | CENNIK_PAINT_3K-01 | Malowanie — 3 warstwy | PAINTING | M2 | LABOR | — | MARKET_SUPPORTED | 21,80 | 48 | — | Kraków + PL | MEDIUM | 1 Kraków + 1 national | 1-coat/2-coat/3-coat kept as distinct coat sets; no overlap. |
| 32 | CENNIK_PAINT_CEIL-01 | Malowanie sufitów — 2 warstwy | PAINTING | M2 | LABOR | — | MARKET_SUPPORTED | 16 | 32 | 24 | Kraków + PL | MEDIUM | 1 Kraków table + 4 national | Ceiling rates kept structurally separate from walls (known issue B). |
| 33 | CENNIK_PAINT_COL-01 | Malowanie kolorem (zmiana koloru) | PAINTING | M2 | LABOR | — | MARKET_SUPPORTED | 14 | 30 | 20 | Kraków + PL | MEDIUM | 3 | Full color-coverage row kept separate from **dark-color surcharges** (+8–15 zł/m²; +5–15% color — documented as context, not merged). |
| 34 | CENNIK_PAINT_MASK-01 | Maskowanie stolarki i detali | PAINTING | M2 | LABOR | — | OWN_PRICE | 5 | 20 | — | Kraków + PL | LOW | 4 (scope-variant) | Ambiguous package scope (simple foil 5–9 vs comprehensive 18,7–20,2); normally bundled or flat-rated. |
| 35 | CENNIK_PAINT_MULTI-01 | Malowanie wielokolorowe / wzory | PAINTING | M2 | LABOR | — | OWN_PRICE | — | — | — | — | INSUFFICIENT | 0 comparable | No fixed per-m² market row; market prices it as surcharges. Owner defines a per-colour surcharge policy (known issue B). |
| 36 | CENNIK_REV_PREP-01 | Ościeża — przygotowanie podłoża | REVEAL | M2 | LABOR | — | DROP_MERGE_RESTRUCTURE | — | — | — | — | INSUFFICIENT | 0 | No standalone M2 market rate — reveal work is quoted **per mb (LM)** or as complete bundles (80–120 / 113 zł/m²) (known issue E). Restructure per group 16.6. |
| 37 | CENNIK_REV_SKIM-01 | Ościeża — szpachlowanie | REVEAL | M2 | LABOR | — | DROP_MERGE_RESTRUCTURE | — | — | — | — | INSUFFICIENT | 0 | Same as 36. |
| 38 | CENNIK_REV_SAND-01 | Ościeża — szlifowanie | REVEAL | M2 | LABOR | — | DROP_MERGE_RESTRUCTURE | — | — | — | — | INSUFFICIENT | 0 | Same as 36 for sanding. |
| 39 | CENNIK_REV_PAINT-01 | Ościeża — malowanie (m²) | REVEAL | M2 | LABOR | — | DROP_MERGE_RESTRUCTURE | — | — | — | — | INSUFFICIENT | 0 | Same as 36 for painting; reveal paint is measured into wall area or inside the LM obróbka. |
| 40 | CENNIK_REV_PAINT_LM-01 | Ościeża — malowanie (mb) | REVEAL | LM | LABOR | — | DROP_MERGE_RESTRUCTURE | — | — | — | — | INSUFFICIENT | 0 | No per-mb paint-only reveal rate exists; always bundled. Merge into REV_WORK_LM (paint is part of the linear obróbka) (known issue E). |
| 41 | CENNIK_REV_WORK_LM-01 | Ościeża — prace liniowe / obróbka ościeży (mb) | REVEAL | LM | LABOR | — | MARKET_SUPPORTED | 30 | 110 | 60 | PL national (Kraków-zone mapped; 0 local firm rates) | MEDIUM | 1 regional-zone + 5 national | 5F mb-basis row. LM is the dominant market unit for reveal work. Kraków-zone LM evidence is calculator-zone mapping (o-okna Strefa I 95–160; Kraków +20–35%) — offerable as regional-coefficient guidance, pending owner decision (known issue E, issue 9). No LM↔M² conversion performed. |
| 42 | CENNIK_MC_WALL_L-01 | Mikrocement na ściany — robocizna | MICROCEMENT | M2 | LABOR | — | OWN_PRICE | 100 | 180 | 140 | PL national only (0 local/reg.) | MEDIUM | 4 national | No Kraków/Małopolskie firm prices wall MC labor separately; labor-only band is a national-guide construct (known issue F, issue 10). Owner defines the rate or applies a regional coefficient (+20–30% per Kraków premium evidence); 100–180 kept as national context, never a local basable price. |
| 43 | CENNIK_MC_WALL_S-01 | Mikrocement — pełny system z materiałem | MICROCEMENT | M2 | LABOR_AND_MATERIAL | — | MARKET_SUPPORTED | 320 | 650 | 350 | Kraków + Małopolskie | MEDIUM | 1 local + 2 reg. + 6 nat. | Dry-interior core 320–400; 250–650 includes premium/premium-tier L+M. Seed must declare a prep assumption ("substrate ready, leveling excluded") (known issue F, issue 16). |
| 44 | CENNIK_MC_FLOOR_L-01 | Mikrocement na posadzkę — robocizna | MICROCEMENT | M2 | LABOR | — | OWN_PRICE | 180 | 250 | 220 | PL national only (0 local/reg.) | MEDIUM | 3 national | Same local-basis gap as 42 for floors; national band (broad 180–400 flagged) is context only. |
| 45 | CENNIK_MC_FLOOR_S-01 | Mikrocement — pełny system posadzka | MICROCEMENT | M2 | LABOR_AND_MATERIAL | — | MARKET_SUPPORTED | 320 | 400 | 380 | Kraków + Małopolskie | HIGH | 1 local + 2 reg. + 7 nat. | Local 320–400 (≤50 m² tier to 400); national 300–550 (typ. 350–500). Highest-confidence MC row. |
| 46 | CENNIK_MC_SHOWER-01 | Mikrocement — strefa prysznicowa (system z hydroizolacją) | MICROCEMENT | M2 | LABOR_AND_MATERIAL | — | MARKET_SUPPORTED | 450 | 650 | 550 | Kraków + Małopolskie | MEDIUM | 1 local + 1 reg. + 5 nat. | L+M with membrane (hydroizolacja) incl.; netto/brutto split preserved (sanitmax explicit brutto 380–720 separated, never merged) (known issue F, issue 12/13). |
| 47 | CENNIK_MC_STAIRS-01 | Mikrocement na schody | MICROCEMENT | M2 (or per step — TBD) | LABOR_AND_MATERIAL | — | DROP_MERGE_RESTRUCTURE | 750 | 950 | — | Kraków (m²) + PL | LOW | 1 local + 7 nat. | Stairs unit model (known issue F): m² 350–950 vs per-step 400–1300 vs per-flight are NOT convertible without geometry. Restructure: choose the seed unit + scope (tread/riser/edge/nosing/prep) before implementation; m² row kept only as report basis. |
| 48 | CENNIK_DEC_VEN-01 | Stiuk wenecki — klasyczny | DECORATIVE | M2 | LABOR | — | MARKET_SUPPORTED | 100 | 160 | 140 | PL national; Kraków L+M city anchor only (405) | MEDIUM | 0 local + 1 reg. + 6 nat. | Classic Venetian LABOR core 120–150 (premium to 300 context). No Kraków labor row; big-city coefficient (+15–25% per itynki) is an owner/9E.5 decision (known issue G). |
| 49 | CENNIK_DEC_VEN_MAR-01 | Stiuk wenecki — efekt marmuru z żyłkowaniem | DECORATIVE | M2 | LABOR | — | OWN_PRICE | — | — | — | PL/regional | LOW | 0 local + 1 reg. + 3 nat. | No Polish veined-LABOR m² row exists (surrogate non-veined 80–160; explicit veined L+M 350–550). Strongest OWN_PRICE candidate; derive from workshop man-hours at 9E.5, keep 350–550 L+M as sanity window (issue 20/24) (known issue G). |
| 50 | CENNIK_DEC_CONC-01 | Efekt betonu / beton architektoniczny | DECORATIVE | M2 | LABOR | — | MARKET_SUPPORTED | 60 | 150 | 110 | PL national | MEDIUM | 0 local + 1 reg. + 5 nat. | Thin-layer wall-applied concrete effect; core 60–150 (outer 50–270 context). Permanent boundary vs microcement/panels/resin kept (issue 27) (known issue G). Big-city coefficient owner decision. |
| 51 | CENNIK_DEC_GENERIC-01 | Tynk dekoracyjny — ogólny | DECORATIVE | M2 | LABOR | — | DROP_MERGE_RESTRUCTURE | 40 | 80 | 60 | PL national | MEDIUM | 0 local + 4 nat. | Generic "tynk dekoracyjny" technology breadth (issue 23/29). Restructure: restrict scope to structural/colored/rustykalny family explicitly (rename the row, e.g. "Tynk strukturalny/rustykalny — linia podstawowa"), keep 40–80 as reference context; travertine/metallic/limewash kept as `COMMON_DECORATIVE_CONTEXT`, never merged. |


## 16.4 OWN_PRICE rows — why the market cannot support a comparable starting price (15)

- **Normally bundled / internally priced (7)**: `PREP_PROT`, `PREP_DEGR`, `PREP_CLEAN`, `SKIM_LOCAL`,
  `GK_SCREW`, `PAINT_MASK`, `PAINT_MULTI`. The market either includes these in a package, flat-rates
  them, prices them per piece/polish, or quotes them on a context-dependent basis (hole-size, project
  scope) that cannot yield a comparable per-unit reference.
- **Technology-specific evidence gap (3)**: `PREP_FLEECE`, `GF_FLIZ_L`, `GF_FLIZ_M` — dedicated
  tech-A (flizelina malarska / glass fleece) rows have no standalone price; only proxy/surrogate
  tech-B fiberglass-wallpaper figures exist, which are legitimately not substitutable.
- **Component-only / custom-premium market (3)**: `PRIM_ADH`, `PRIM_HIGH` — component/material evidence
  only, no direct per-m² quote; `DEC_VEN_MAR` — veined marble is artistic/custom work, no fixed LABOR
  row; `PAINT_MULTI` — no fixed per-m² multi-color row (see first group too).
- **No local (Kraków/Małopolskie) basis (2)**: `MC_WALL_L`, `MC_FLOOR_L` — labor-only microcement is a
  national-price-guide construct; no Kraków firm publishes it. Owner sets the rate or applies a
  regional coefficient; the national bands (100–180 / 180–250) are sanity context only.

## 16.5 DROP_MERGE_RESTRUCTURE rows — proposed structural corrections (10)

1. **`SKIM_3L-01 (14)** — overlap risk with SKIM_2L + SAND. Restructure as **SKIM_2L + 3rd-layer
   add-on**; standalone 3-coat full-surface row only if the owner explicitly wants a 3-coat package.
2. **`SKIM_PKG-01 (16)** — component-sum mismatch (35–70 vs component equivalent 65–91). Restructure:
   define the exact package scope, then re-anchor to component-sum consistency or merge into
   SKIM_2L + SKIM_SAND.
3. **`GK_JOINT-01 (21)** — M2 vs LM unit mismatch. Restructure to **LM joint-finishing** (market
   basis) with optional M2 aggregate/report-only, or explicitly redefine M2 scope.
4. **`REV_PREP-01 (36)** / `REV_SKIM-01 (37)** / `REV_SAND-01 (38)** / `REV_PAINT-01 (39)** /
   `REV_PAINT_LM-01 (40)** — the market quotes reveal work per **mb (LM)** or as complete bundles;
   M2 component rows have no standalone market. Restructure: make **REV_WORK_LM (41)** the single
   canonical commercial reveal row; keep M2 only as the 5F measurement/report aggregate; optionally
   derive M2 component rates from wall-work (Batch A/B) + a reveal-handling surcharge if the owner
   prefers a component structure.
5. **`MC_STAIRS-01 (47)** — stairs unit model fragmented (m² / per-step / per-flight). Restructure:
   choose seed unit + scope (tread/riser/edge/nosing/prep) before implementation.
6. **`DEC_GENERIC-01 (51)** — technology breadth of "generic decorative render". Restructure: restrict
   to structural/colored/rustykalny scope with an explicit renamed row ("Tynk strukturalny/
   rustykalny — linia podstawowa"), or drop it in favor of the specific VEN/CONC rows; 40–80 stays
   reference context only.

## 16.6 Known-issues resolution map (A–G → decision)

| Known issue | Resolved by | Result |
|---|---|---|
| A. SKIM_PKG market range vs component-sum | row 16 DROP_MERGE | package scope must be re-defined; component sum kept as consistency anchor |
| A. 3-layer skim duplication / overlap | row 14 DROP_MERGE | restructure to 2-coat + add-on |
| A. post-sanding cleaning / vacuuming evidence gap | row 7 OWN_PRICE | standalone cleaning remains internally priced |
| A. crack-repair unit/scope consistency | row 17 MARKET_SUPPORTED (LOW) | LM unit + scope note; no invented LM↔M² conversion |
| B. 1/2/3-coat structure | rows 29–31 MARKET_SUPPORTED | three coat sets distinct on the same prepared-substrate/labor basis |
| B. ceiling vs wall prices | rows 29 vs 32 MARKET_SUPPORTED | separate rows kept (ceiling 16–32 vs wall 10–28) |
| B. color / dark-color surcharges | row 33 MARKET_SUPPORTED + note | color-coverage row kept separate from dark surcharge context |
| B. masking/protection structure | row 34 OWN_PRICE | compounded into bundles/flat rates |
| B. multi-color fixed market | row 35 OWN_PRICE | owner defines per-colour surcharge policy |
| C. Q1/Q2 m² vs lm ambiguity | row 21 DROP_MERGE | unit model decision (LM preferred) |
| C. Q3 full finish | row 22 MARKET_SUPPORTED | Q3 hint; range 28–45 real |
| C. Q4 source conflicts | row 25 MARKET_SUPPORTED | betonizm 60–80 used; chart 110 noted as outlier |
| C. corner bead / corner unit mismatch | row 24 MARKET_SUPPORTED | unit normalized to LM; mismatched M² cell excluded |
| C. screw correction OWN_PRICE | row 23 OWN_PRICE | remains bundled; seed only if owner wants standalone |
| C. no invented Q-level compatibility | rows 20/22/25 quality hints | S/Q attached only on literal wording |
| D. flizelina vs fiberglass wall covering | rows 26–27 OWN_PRICE | tech-B not substituted for tech-A |
| D. GF_MESH support | row 28 MARKET_SUPPORTED | mesh embedding has a market basis |
| E. complete bundle vs component M² | rows 36–40 DROP_MERGE | reveal M2 components folded into LM canonical row |
| E. LM vs M² quoting model / 5F geometry | rows 36–41 | LM canonical row (41); M2 as 5F report aggregate; no arbitrary LM↔M² conversion |
| E. structural decide rows | rows 36–41 | §16.7 Group 1 (5 restructure + `REV_WORK_LM` kept numeric) |
| F. labor-only vs system scope | rows 42, 44 OWN_PRICE | national-only labor bands are context; no local basis |
| F. hydroizolacja in wet areas | row 46 MARKET_SUPPORTED | L+M membrane incl.; brutto separated; scope explicit |
| F. minimum-job effects | rows 43/45/46 notes | min-m² tiers documented as context; no M2-rate conversion |
| F. wall vs floor | rows 43 vs 45 MARKET_SUPPORTED | per-surface seeds separated |
| F. stairs unit | row 47 DROP_MERGE | unit model decision |
| F. Festfloor/material data ≠ labor | rows 42–47 notes | material echelons kept as Stage-10 estimate input only |
| G. classic Venetian LABOR basis | row 48 MARKET_SUPPORTED | national core 120–150; big-city coefficient is owner decision |
| G. veined/marble no LABOR | row 49 OWN_PRICE | workshop man-hours at 9E.5 |
| G. concrete effect | row 50 MARKET_SUPPORTED | thin-layer wall scope; boundary vs microcement permanent |
| G. generic family | row 51 DROP_MERGE | restrict/rename rows or drop; 40–80 context |
| G. material vs labor separation | rows 48–50 notes | manufacturer material rows never fed LABOR |
| G. complexity surcharge not invented | rows 49/51 notes | no % surcharge in the rows; ENHANCED/ARTISTIC documented as scope notes |

## 16.7 OWNER DECISIONS REQUIRED — grouped (answer these before 9E.5 implementation approval)

**Group 1 — Reveal row structure (rows 36–41):** Confirm the proposed restructure — make
`REV_WORK_LM` (30–110 zł/mb, ref 60) the **single canonical commercial reveal row**; fold the M2
component rows (PREP/SKIM/SAND/PAINT) and `REV_PAINT_LM` into it, keeping M2 only as the 5F
measurement/report aggregate. Alternative: (b) keep M2 components derived from wall-work + a
reveal-handling surcharge. Owner picks (a) or (b); applying the Kraków-zone LM regional coefficient
(+20–35%) is part of this decision set.

**Group 2 — OWN_PRICE starting rates (15 items):** provide owner rates (or approve their future
derivation in 9E.5): `PREP_PROT`, `PREP_DEGR`, `PREP_CLEAN`, `PREP_FLEECE`, `PRIM_ADH`, `PRIM_HIGH`,
`SKIM_LOCAL`, `GK_SCREW`, `GF_FLIZ_L`, `GF_FLIZ_M`, `PAINT_MASK`, `PAINT_MULTI`, `MC_WALL_L`,
`MC_FLOOR_L`, `DEC_VEN_MAR`. For the "usually bundled" subset (PREP_PROT/DEGR/CLEAN, GK_SCREW,
PAINT_MASK, PAINT_MULTI) the owner may instead decide to **not seed them as separate billable lines**.

**Group 3 — SKIM package structure (rows 14, 16):** approve the restructure — `SKIM_PKG` becomes
SKIM_2L + SAND (or a re-scoped package), and `SKIM_3L` becomes a 2-coat + 3rd-layer add-on (or a
single explicit 3-coat package). Confirm which lines the owner wants to sell.

**Group 4 — GK joint unit model (row 21):** approve **LM** as the joint-finishing unit (market basis)
with M2 as optional aggregate; or require an explicitly re-defined M2 joint row.

**Group 5 — MC_STAIRS unit (row 47):** choose the seed unit (**M2 with explicit tread/riser/edge/
nosing scope, or per-step) and whether the per-flight rate is a future optional mode.

**Group 6 — DEC_GENERIC scope (row 51):** keep a **renamed/restricted** generic decorative row
(structural/colored/rustykalny family, 40–80 reference context) or drop it in favor of the specific
VEN/CONC rows.

**Group 7 — regional (big-city) pricing policy (rows 48, 50 + reveal row 41):** confirm applying the
documented big-city coefficient (+15–25% decorative, +20–35% Kraków-zone LM) or using national
defaults, as the owner's pricing policy input for 9E.5.

Only these groups require owner input before 9E.5; the 26 `MARKET_SUPPORTED` rows also have a
starting-price proposal pending at 9E.5, but that is the normal owner-approval step, not a blocking
decision.