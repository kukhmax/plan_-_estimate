# Batch C research evidence — Kraków market research — Reveals / ościeża / glify / szpalety (9E.3C)

Research date: **2026-09-14** — web research + documentation only.
Branch: `stage-9`. Status: **COMPLETE**. Hard rule: **no seeds, no `PriceItem.price`, no migrations,
no backend/frontend code** (9E.3 contract).

Scope: the **6 canonical reveal items** from `docs/price-research-catalog.md` §9 (Batch C,
Stage 5F compatible). Every figure below is a **verbatim quote** read from the opened source page
(`checked_at 2026-09-14`); search snippets were never used. No price is implemented.

---

## 1. Purpose — Stage 5F compatibility

Stage 5F (approved reveal measurement design) calculates separately:

- **total reveal length — LM** (e.g. window reveals 10 m; door reveals 5 m);
- **reveal area — M2** (e.g. window reveals 3.00 m²; door reveals 0.75 m²).

The Price Book **must preserve separate M2 and LM pricing models** and must not treat
`10 LM == any fixed M2 value`: reveal depth varies and is part of the geometry. This research keeps
M2 and LM completely separated and does no unit conversions.

## 2. Terminology research — actual source wording

Sources use the full family of Polish terms, **not always with the same scope**:

- **ościeża / ościeżnica** — generic reveal; `ościeżnica` more often means the *door/window frame
  unit* than the wall reveal (e.g. nowabudowa "Demontaż ościeżnicy 136,4 zł/szt"; strzelec
  "obróbka ościeżnicy" priced per door leaf).
- **glify** — window/door jambs (vertical reveal planes); e.g. nowabudowa "Obróbka otworów
  okiennych", "Dwustronna obróbka glifów przy drzwiach".
- **szpalety** — used **two ways** in the market (must not be merged):
  - generic reveal treatment — cenauslug "obróbka szpalet okiennych i drzwiowych" (tynkowa
    obróbka, same work as glify);
  - **prefab reveal profile systems** (ready szpaleta panes / profiles) — remonty-rolety
    "Szpaleta wewnętrzna tynk 80–140 zł/mb; Profile PCV 120–200; Profile aluminiowe 200–350 zł/mb"
    (material-mounted system, a different technology).
- **obróbka ościeży / obróbka okien / obróbka drzwi** — umbrella service term quoted per **mb** in
  real contractor cenniki; split "otwory okienne" vs "otwory okienne i drzwiowe".
- **wykończenie ościeży** — complete finish (usually plaster/skim + paint).
- **wykończenie po wymianie okien / po montażu okien i drzwi** — replacement/installation context;
  more expensive than finishing an already prepared reveal.
- **skosy (połać) pod oknami** — attic slants under dormer windows; found only as a *surcharge*
  factor in prose (+20–30% on ceilings, mczp.pl), **never as a standalone reveal price**.
- **Not comparable scope**: **ocieplenie ościeży** (external thermal insulation of the reveal —
  styrofoam/mineral-wool cladding around the window on the facade). cenauslug ran an
  "Ocieplenie ościeży okiennych w Krakowie" page; that city subpage now returns HTTP 410. This is a
  **different service** (insulation, not finishing) and is excluded from all ranges.

## 3. Market pricing structure (what the market actually quotes)

Polish reveal-finishing market quotes reveal work in **three quoting modes**:

1. **Per mètre run (zł/mb)** — the dominant professional mode for *obróbka ościeży/glifów*.
2. **Per window / per door (zł/okno, zł/skrzydło, zł/ościeżnica)** — complete obróbka packages.
3. **Per m² of reveal surface (zł/m²)** — rare; appears only as a *complete obróbka* bundle
   (~80–120 zł/m²) or as one real-firm cennik row for "dwustronna obróbka glifów przy drzwiach"
   (113 zł/m²). **No source prices the five operations separately per m²**
   (prep / skim / sand / paint) for reveals.

Two separate technologies must never be merged:
- **tynkowa / szpachlowa obróbka** (the catalog model) — 30–110 zł/mb labor;
- **prefab szpaleta / profile systems** (PCV/alu factory reveal panels) — 80–350 zł/mb material+assembly.

## 4. Geographic priority — source counts (per canonical item)

| Code | LOCAL_SOURCE_COUNT | REGIONAL_SOURCE_COUNT | NATIONAL_SOURCE_COUNT | Basis |
|---|---|---|---|---|
| CENNIK_REV_PREP-01 | 0 | 0 | 0 (range: none) | no standalone M2 reveal-prep price exists |
| CENNIK_REV_SKIM-01 | 0 | 0 | 0 (range: none) | only complete-m² bundles (non-comparable) |
| CENNIK_REV_SAND-01 | 0 | 0 | 0 (range: none) | no standalone M2 reveal-sand price exists |
| CENNIK_REV_PAINT-01 | 0 | 0 | 0 (range: none) | only complete-m² bundles (non-comparable) |
| CENNIK_REV_WORK_LM-01 | 0 | 1 (o-okna Kraków-zone) | 5 (nowabudowa, cenauslug, kb.pl, dziennikbudowlany, remonty-rolety*) | LM band 30–110 labor |
| CENNIK_REV_PAINT_LM-01 | 0 | 0 | 0 (range: none) | painting always bundled; no per-mb paint rate |

\* remonty-rolety is a **szpaleta/profile-system** quote (material-inclusive) — recorded as
technology context, not LABOR evidence.
`REGIONAL_SOURCE_COUNT = 1` for REV_WORK_LM is the **o-okna.pl metropolis-zone row** (Strefa I,
explicit "Warszawa / Kraków / Trójmiasto +20–35%") — a national-calculator *zone mapping*,
**not** a Kraków-firm quote. Recorded with that caveat.

### 4.1 Kraków-local negative-result audit (documented)

The following Kraków / Małopolskie-local pages were checked for reveal rows and have **no**
ościeża/glify/szpalety price rows (documented finding supporting `LOCAL_SOURCE_COUNT = 0`):

- https://malarzkrakow.pl/cennik — no reveal rows (closest: "Malowanie okien od 180 zł/szt." — the
  window itself, not reveals). *(Kraków firm)*
- https://kubamalarz.pl/cennik/ — no reveal rows. *(Kraków firm)*
- https://krakow-malowanie.pl/cennik — no reveal rows. *(Kraków firm)*
- https://s-szpachlowanie.pl/szpachlowanie-krakow-cennik — no reveal rows. *(Kraków firm)*
- https://cennikremontow.pl/krakow-remonty-cennik — "dwustronne obrobienie glifów" appears only in
  prose (Montaż drzwi section), no price row; the only window row is "Montaż okien drewnianych
  94–260 zł/mb" (installation of the window, not reveal). *(Kraków city table)*
- https://kb.pl/cenniki/miejskie/remonty-mieszkan/krakow/ — no reveal rows. *(Kraków city table)*
- https://cennikremontow.pl/malowanie-krakow-cennik — "Malowanie okien 134–440 zł/m²" (window
  itself, not reveal). *(Kraków)*
- https://cenauslug.pl/budowa-i-remont/obrobka-glifow-okiennych-i-drzwiowych/krakow and
  .../ocieplenie-osciezy-okiennych/krakow — HTTP 410 (dead links). *(Małopolskie)*

National content cenniki also had no reveal rows: tani-komin.pl, mczp.pl (skosy only as a +20–30%
surcharge in prose), ceny-uslug.pl.

**Finding for 9E.4**: no Kraków-area contractor publishes reveal-finishing rates. This is the
strongest support for an LM-dominant model plus OWN_PRICE / regional-coefficient decisions at
normalization (see §15, §16).

## 5. Source evidence index (10 used; exact URLs preserved — future `PriceSource` candidates)

| # | Source name | URL | Type | Region |
|---|---|---|---|---|
| S1 | nowabudowa.pl | https://nowabudowa.pl/index.php/cennik/cennik-uslug-murarskich | real-firm cennik (netto, informative) | PL (region unspecified) |
| S2 | CenaUsług — obróbka glifów | https://cenauslug.pl/budowa-i-remont/obrobka-glifow-okiennych-i-drzwiowych | price portal | PL (city rows) |
| S3 | KB.pl — cennik obróbki okien | https://kb.pl/okna-i-drzwi/ceny-okien/cennik-obrobki-okien-zobacz-ile-zaplacisz-za-montaz-okien-z-obrobka/ | price portal | PL |
| S4 | Dziennik Budowlany — obróbka okna 2026 | https://dziennikbudowlany.pl/ile-kosztuje-obrobka-okna-2026/ | price article | PL |
| S5 | Okna-Porady — obróbka okna za mb | https://okna-porady.pl/ile-kosztuje-obrobka-okna-za-metr-biezacy | price article | PL |
| S6 | O-Okna — obróbka okna cena | https://o-okna.pl/obrobienie-okna-cena | price article + zone calculator | PL (strefy; Kraków-zone) |
| S7 | Remonty-Rolety — obróbka okna za mb | https://remonty-rolety.pl/ile-kosztuje-obrobka-okna-za-metr-biezacy | price article | PL |
| S8 | Strzelec Południe — obróbka ościeżnic drzwi wewnętrznych | https://strzelec-poludnie.pl/obrobka-oscieznic-drzwi-wewnetrzne-wykonczenie-cena | price article | PL (doors) |
| S9 | Wspólny Dom Wilga — obróbka drzwi zewnętrznych po montażu | https://wspolnydom-wilga.pl/obrobka-drzwi-zewnetrznych-po-montazu-cena | price article | PL (doors) |
| S10 | HouseOfSolutions — obróbka okien po wymianie | https://houseofsolutions.pl/obrobka-okien-po-wymianie-ile-kosztuje-cennik/ | price article | Warszawa (dated 2024–25) |

**Content-network / duplication flags** (per catalog §12 — copied tables are one data point):
- **S3 ↔ S4**: identical "30–70 zł/mb" (sama obróbka) and **S4 ↔ S5**: identical "80–120 zł/m²"
  strongly suggest one shared content family (kb.pl / dziennikbudowlany.pl / okna-porady.pl).
  Counted as **one content origin** (S3 anchor). S4 adds its own distinct rows (40–65 zł/mb
  tynkarska po montażu; 250–550 zł/okno), so it is *partially* additive.
- **S6** overlaps with that family on the "50–160 zł/mb" headline figure; its zone/calculator
  detail is distinct and is recorded separately with a caution flag.
- Excluded as unreachable/untested likely clones: terraglass.com.pl (403), assystem.com.pl (403),
  koszt-ile.pl, messaya.pl, oknanapoddasze.pl, thermopanel.pl — not counted.

## 6. Summary table (Batch C — 6 items)

| Code | PL name | Unit | Scope | Local range | Suppl. PL range | Reference | Confidence | Local src | Reg. src | Nat. src | Checked |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CENNIK_REV_PREP-01 | Ościeża — przygotowanie podłoża | M2 | LABOR | — | — | — | INSUFFICIENT | 0 | 0 | 0 | 2026-09-14 |
| CENNIK_REV_SKIM-01 | Ościeża — szpachlowanie | M2 | LABOR | — | — | — | INSUFFICIENT | 0 | 0 | 0 | 2026-09-14 |
| CENNIK_REV_SAND-01 | Ościeża — szlifowanie | M2 | LABOR | — | — | — | INSUFFICIENT | 0 | 0 | 0 | 2026-09-14 |
| CENNIK_REV_PAINT-01 | Ościeża — malowanie (m²) | M2 | LABOR | — | — | — | INSUFFICIENT | 0 | 0 | 0 | 2026-09-14 |
| CENNIK_REV_WORK_LM-01 | Ościeża — prace liniowe / obróbka ościeży (mb) | LM | LABOR | — | 30–110 | 60 | MEDIUM | 0 | 1 | 5 | 2026-09-14 |
| CENNIK_REV_PAINT_LM-01 | Ościeża — malowanie (mb) | LM | LABOR | — | — | — | INSUFFICIENT | 0 | 0 | 0 | 2026-09-14 |

**No implementation-ready seed decision yet — this is research evidence only (9E.3C §6).**
Confidence key: HIGH = 3+ genuinely comparable local/regional sources; MEDIUM = 2+ useful
comparable sources or strong anchor + supplementary; LOW = single usable source / scope ambiguity;
INSUFFICIENT = no defensible comparable numerical range.

---

## 7. CENNIK_REV_WORK_LM-01 — Ościeża — prace liniowe / obróbka ościeży (mb)

- **Canonical scope**: linear reveal work per running meter (mb, LABOR). **Prio P1.**
- **Unit**: LM. **Price scope**: LABOR (per the sources that state it); one L+M row kept separate.
- **Market result**:
  - `local_market_min` / `local_market_max`: **null / null** (no Kraków-firm quote).
  - `supplementary_pl_min` / `supplementary_pl_max`: **30 / 110** zł/mb (LABOR, netto/mixed-VAT).
  - `reference_price`: **60 zł/mb** — method: three independent publishers' single/mid LABOR rates
    cluster 50–67 (nowabudowa 58,25 netto; cenauslug avg 67; kb-family mid ≈ 50; S6 mid-range
    50–110). A central commonly-observed value, not an arithmetic mean across all rows.
  - **Confidence: MEDIUM** — 4 usable numeric origins (S1, S2, S3-family, S6) converge on a LABOR
    band 50–110, but scope widths differ (sama obróbka vs tynkarska), so not HIGH.
- **Source counts**: LOCAL 0 · REGIONAL 1 (S6 Strefa I / Kraków-zone) · NATIONAL 5 (S1, S2, S3, S4,
  S7-technology-context).
- **Methodology**: mb-only rows retained; all zł/m², zł/okno and zł/skrzydło rows excluded
  (see §12). The LABOR band uses LABOR rows; the L+M row (S1 78,25 zł/mb z tynkarską zaprawą) is
  recorded as L+M evidence, never merged.
- **Source evidence** (window, unless noted):
  - S1 nowabudowa.pl — "Obróbka otworów okiennych — **58,25 zł/mb**" (robocizna, netto);
    "Obróbka otworów okiennych i drzwiowych wraz z gotową tynkarską zaprawą — **78,25 zł/mb**" (L+M).
  - S2 cenauslug.pl — "Obróbka glifów okiennych i drzwiowych … średnio **67 zł/mb**", range
    "**55 zł** (Kielce, min) … **85 zł** (Świdnica, max)"; city rows 58/61/63/64/66/71/73/74 zł/mb;
    "materiały eksploatacyjne średnio **15–30 zł/mb**" (material, separate). Labor.
  - S3 kb.pl — "od **30 zł/mb** (min) do **70 zł/mb** (u części wykonawców)" (sama obróbka, brutto);
    "Obróbka glifów/szpalet okiennych **45–150 zł/mb brutto**"; "Robocizna z materiałem (zaprawa
    tynkarska, wewnątrz i na zewnątrz) **50–120 zł/mb**"; "Montaż okien z obróbką (kompleksowa)
    **50–160 zł/mb**".
  - S4 dziennikbudowlany.pl — "za metr bieżący (sama obróbka) **30–70 zł/mb**" (duplicate of S3 —
    shared figure); "obróbka tynkarska po montażu **40–65 zł/mb**".
  - S6 o-okna.pl — "obróbka tynkarska **50–160 zł/mb**" (robocizna); per-type robocizna: PCV
    **50–110**, drewno **70–140**, alu **120–160** zł/mb; "z materiałem": PCV **80–140**, drewno
    **110–180**, alu **170–220** zł/mb. **Obróbka glifów okiennych by zone (robocizna / z materiałem):
    Strefa I (metropolie) 95–160 / 130–200; II 75–120 / 100–160; III 60–100 / 80–130;
    IV 50–85 / 70–110**; calculator base rates IV 60 / III 80 / II 95 / I 125 zł/mb; explicit
    market-locator adjustment "Warszawa / Kraków / Trójmiasto **+20–35%**".
  - S7 remonty-rolety.pl — "Szpaleta wewnętrzna tynk **80–140 zł/mb**; Profile PCV **120–200**;
    Profile aluminiowe **200–350 zł/mb**" — **prefab profile system (material+assembly)**, recorded
    as technology context (excluded from the LABOR band).
- **Window / door applicability**: window and door share the same LM rate when quoted together
  (S1 has "otworów okiennych" 58,25 and "okiennych i drzwiowych z zaprawą" 78,25 — the ~20 zł/mb
  delta is the material+finish addition, not a door surcharge; S2 quotes "okiennych i drzwiowych"
  as one rate). Door-only quotations exist per piece (S8, S9) — see §12.
- **New / repair context**: mixed. S2 = new finish after new carpentry; S4 = po montażu
  (replacement); S6 = both new and replacement; S1 = general cennik (new-construction bias). No
  source isolates REPAIR_DAMAGE (naprawa glifów) at an LM rate.
- **Included work**: varies — "sama obróbka" (S3/S4: minimal, preparation to be painted),
  "obróbka tynkarska" (S6: plastering), "obróbka glifów okiennych i drzwiowych" (S2: complete
  tynk-based obróbka). The S3/S4 lower bound (30) is minimal scope.
- **Excluded / unknown**: reveal painting (never itemized separately per mb — see REV_PAINT_LM);
  corner beads; prefab profile systems (S7); external insulation (ocieplenie).
- **Depth / width dependence**: o-okna — glif >30 cm +20–40%; nietypowe kształty +40%
  (remonty-rolety); strzelec — krzywizna ściany >10 mm/m +100–200 zł/ościeżnica. Depth is a real
  cost driver; **no depth-normalization attempted** (catalog §9 / sub-stage §10).
- **Minimum-charge notes**: no explicit minimum at LM level; per-piece floors (S8 "od 200 zł brutto
  za kompletn± obróbkę skrzydła") recorded in §12 as commercial context.
- **Comparability notes**: the 30–110 LABOR band spans 4 origins because S3/S4 "sama obróbka" (30)
  is minimal, while S6 "tynkarska" upper bound (110) includes plastering. A narrow "complete
  obróbka" labor core for 9E.4 is **50–85 zł/mb** (S1 58,25; S2 55–85; S6 Strefa IV 50–85), with
  Kraków-metropolis at the upper side per S6 zone mapping.

## 8. CENNIK_REV_PAINT_LM-01 — Ościeża — malowanie (mb)

- **Canonical scope**: reveal painting per mb (LABOR). **Prio P2** ("only if sources quote LM").
- **Market result**: **INSUFFICIENT** — no source publishes a per-mb painting-only reveal rate;
  reveal painting is always quoted bundled (inside the mb obróbka or per window/door).
  `local`/`supplementary` ranges = null; `reference_price` = null.
- **Source counts**: LOCAL 0 · REGIONAL 0 · NATIONAL 0 (range: none).
- **Methodology / evidence**: the only paint-specific reveal numbers are per *job* (S9 "Malowanie
  ościeży (2 warstwy) **60–100 zł**" per door; S8 "Malowanie odcinające przy listwie **20–40 zł
  netto/ościeżnica**") — PCS/FLAT, excluded from LM (see §12). S1's 78,25 zł/mb row includes
  finish but is an aggregate, not a paint row.
- **OWN_PRICE candidate**: **yes** (no market basis for a per-mb painting-only reveal row). 9E.4
  decision: either OWN_PRICE, or declare painting inside REV_WORK_LM / wall-paint scope at seeding.

## 9. CENNIK_REV_PREP-01 — Ościeża — przygotowanie podłoża (M2)

- **Canonical scope**: reveal substrate preparation, per m² of visible reveal surface (LABOR).
  **Prio P1**.
- **Market result**: **INSUFFICIENT** — no source prices reveal-substrate preparation alone in
  zł/m². Preparation before skim is never itemized for reveals; it exists only inside complete
  "obróbka" bundles or the per-mb rate. `local`/`supplementary` = null; `reference_price` = null.
- **Source counts**: LOCAL 0 · REGIONAL 0 · NATIONAL 0 (range: none).
- **Methodology / supporting context**: nearest market blocks are the per-mb obróbka rates (S1
  58,25; S2 55–85) which include substrate prep, and S8 per-piece "Szpachlowanie narożników + siatka
  50–90 zł netto/ościeżnica". None is a standalone M2-prep rate.
- **OWN_PRICE candidate**: **yes**. 9E.4 may seed from equivalent *wall* PREP rates plus a reveal
  difficulty surcharge, or keep reveal scope LM-only — decision, not research.

## 10. CENNIK_REV_SKIM-01 — Ościeża — szpachlowanie (M2)

- **Canonical scope**: reveal skim coat, per m² (LABOR). **Prio P1**.
- **Market result**: **INSUFFICIENT** as a standalone M2 skim row. The only M2 figures in the market
  are **complete-bundle** reveal finishing (not "szpachlowanie" alone):
  - S1 nowabudowa.pl — "Dwustronna obróbka glifów przy drzwiach — **113 zł/m²**" (netto; door;
    complete obróbka; labor/material not separately stated);
  - S4/S5 (shared family) — "za metr kwadratowy ościeży — **80–120 zł/m²**" (kompleksowa, in a
    replacement-install context, materials effectively bundled).
  Both are aggregate complete-finish per m² — **not** decomposable into a standalone skim rate
  without inventing a split (forbidden). `local`/`supplementary` = null; `reference_price` = null.
- **Source counts**: LOCAL 0 · REGIONAL 0 · NATIONAL 0 for the *component* row (2 m²-complete
  bundles exist only as context).
- **Methodology / supporting context**: m²-complete band 80–120 (S4/S5) and 113 (S1) sit far above
  wall skim rates (wall 2× 55–75 zł/m², Batch A) — consistent with reveal intensity + material
  inclusion in those rows. 9E.4 must not relabel these complete figures as "szpachlowanie".
- **OWN_PRICE candidate**: **yes** (standalone skim M2 has no independent market basis).

## 11. CENNIK_REV_SAND-01 — Ościeża — szlifowanie (M2)

- **Canonical scope**: reveal sanding, per m² (LABOR). **Prio P2**.
- **Market result**: **INSUFFICIENT** — no source prices reveal sanding alone in zł/m²; sanding is
  always inside complete obróbka/mb rates. `local`/`supplementary` = null; `reference_price` =
  null.
- **Source counts**: LOCAL 0 · REGIONAL 0 · NATIONAL 0 (range: none).
- **Methodology**: wall sanding rates (S9 "Szpachlowanie i szlifowanie 80–140 zł" per door job;
  Batch A wall sanding 10–16 zł/m²) are not reveal-surface evidence and were **not** substituted.
- **OWN_PRICE candidate**: **yes**.

## 12. CENNIK_REV_PAINT-01 — Ościeża — malowanie (m²)

- **Canonical scope**: reveal painting, per m² of reveal (LABOR). Not comparable to LM quotations.
  **Prio P1**.
- **Market result**: **INSUFFICIENT** as a standalone M2 paint row. The M2 figures in the market
  are again complete bundles (S1 113 zł/m² dwustronna obróbka glifów przy drzwiach; S4/S5 80–120
  zł/m² kompleksowa) and per-job door paint rows (S9 60–100 zł). None is a labor-only
  reveal-paint m² rate. `local`/`supplementary` = null; `reference_price` = null.
- **Source counts**: LOCAL 0 · REGIONAL 0 · NATIONAL 0 (range: none).
- **Methodology note for 9E.4**: Polish painting practice measures a reveal's paint into the *wall*
  surface area (reveals counted into the wall m² at the same paint rate) rather than pricing
  reveals separately per m²; no source itemizes a reveal-paint m² rate. If the Price Book keeps an
  M2 REV_PAINT row, 9E.4 must justify its basis explicitly (equivalent wall paint rate + handling
  surcharge) or treat it as OWN_PRICE; no such rate exists to cite here.
- **OWN_PRICE candidate**: **yes**.

---

## 13. Cross-unit context table (non-comparable pricing)

Per-piece / per-window / per-door / FLAT / prefab-system / bundled figures below are **useful
commercial context that must NOT enter the M2 or LM ranges** (catalog §15 / sub-stage §5, §18).

| Source | Service | Quoted price | Unit | Window/Door | Scope | Why not comparable |
|---|---|---|---|---|---|---|
| Dziennik Budowlany (S4) | "podstawowa obróbka okna PCV (gładź, malowanie)" | 250–400 zł | /okno | WINDOW | labor + podstawowe materiały | per-piece; not M2/LM |
| Dziennik Budowlany (S4) | "obróbka wymagająca większych napraw tynkarskich" | 350–500 zł | /okno | WINDOW | labor | per-piece |
| Dziennik Budowlany (S4) | średnie widełki obróbki jednego okna | 250–550 zł | /okno | WINDOW | labor | per-piece average |
| Okna-Porady (S5) | "kompleksowa obróbka okien … wykończenie ościeży" | 80–120 zł | /m² | WINDOW | labor+materiał, REPLACE (demontaż+montaż+pianki) | bundled incl. window install; not a component |
| nowabudowa (S1) | "Dwustronna obróbka glifów przy drzwiach" | 113 zł | /m² | DOOR | complete obróbka; L/M not split | complete bundle, door m², not a component |
| nowabudowa (S1) | "Montaż drzwi — pojedyncze wraz z dwustronnym obrobieniem glifów" | 467,25 zł | /szt | DOOR | labor + częściowy materiał | bundle with door install |
| Strzelec Południe (S8) | "kompletna obróbka jednego skrzydła" (drzwi wewnętrzne) | 120–400 zł | /skrzydło | DOOR | labor | per-piece; includes opaski |
| Strzelec Południe (S8) | "Montaż z obróbką … komplet" | 200–750 zł | /skrzydło | DOOR | labor+materiał | per-piece bundle |
| Strzelec Południe (S8) | "Szpachlowanie narożników + siatka" | 50–90 zł | /ościeżnica (netto) | DOOR | labor | per-jamb component |
| Strzelec Południe (S8) | "Malowanie odcinające przy listwie" | 20–40 zł | /ościeżnica (netto) | DOOR | labor | per-jamb |
| Wspólny Dom Wilga (S9) | "Tynkowanie ościeży (1 strona / 2 strony)" | 120–180 / 200–320 zł | /zlecenie | DOOR (zewn.) | labor | per-door job; ościeżnica do 100 mm |
| Wspólny Dom Wilga (S9) | "Szpachlowanie i szlifowanie" | 80–140 zł | /zlecenie | DOOR | labor | per-job |
| Wspólny Dom Wilga (S9) | "Malowanie ościeży (2 warstwy)" | 60–100 zł | /zlecenie | DOOR | labor | per-job (only paint-only reveal number found anywhere) |
| Wspólny Dom Wilga (S9) | "Kompletna obróbka (1/2 strony, pod malowanie)" | 250–400 / 400–650 zł | /zlecenie | DOOR | labor | per-job complete |
| Remonty-Rolety (S7) | "Szpaleta wewnętrzna tynk / profile PCV / alu" | 80–140 / 120–200 / 200–350 zł | /mb | WINDOW | labor+materiał prefab | different technology (prefab szpaleta), not tynkowa obróbka |
| O-Okna (S6) | "Obróbka drzwi HS (tarasowe przesuwne)" | od 350 do 1200 zł | /szt | DOOR | labor | per-piece |
| HouseOfSolutions (S10) | "Kompleksowa obróbka pod klucz" | 100–150 zł | /okno | WINDOW | labor (Warszawa, 2024–25) | per-piece, dated, other city |
| HouseOfSolutions (S10) | "Od 6 zł/mb" | od 6 zł | /mb | WINDOW | labor | unreliable outlier (Warszawa, 2024–25); flagged |
| CennikRemontów Kraków | "Montaż okien drewnianych" | 94–260 zł | /mb | WINDOW | labor install | window installation, not reveal |
| CennikRemontów Kraków | "Malowanie okien" | 134–440 zł | /m² | WINDOW | labor | window itself (frame), not reveal |

## 14. OWN_PRICE candidates (Batch C)

| Code | Item | Reason |
|---|---|---|
| CENNIK_REV_PREP-01 | Ościeża — przygotowanie podłoża (M2) | no standalone market M2 rate; only inside bundles |
| CENNIK_REV_SKIM-01 | Ościeża — szpachlowanie (M2) | only complete-m² bundles (80–120 / 113); not split-able |
| CENNIK_REV_SAND-01 | Ościeża — szlifowanie (M2) | never priced standalone |
| CENNIK_REV_PAINT-01 | Ościeża — malowanie (m²) | no labor-only reveal-paint m² rate; painting measured into wall area |
| CENNIK_REV_PAINT_LM-01 | Ościeża — malowanie (mb) | no per-mb paint-only reveal rate; always bundled |
| *(not a candidate)* | CENNIK_REV_WORK_LM-01 | LM market band 30–110, ref 60 — keep numeric |

## 15. STAGE 5F NORMALIZATION NOTE — pricing modes (evidence only, no change now)

**Does the market evidence support keeping BOTH an M2 and an LM reveal pricing model?**

**VERDICT: PARTIALLY_SUPPORTED.**

- **LM reveal pricing: SUPPORTED.** Real contractor cenniki and price portals robustly quote
  obróbka ościeży/glifów per **mb** (S1 58,25; S2 55–85; S3/S4 30–70; S6 50–110 robocizna; Strefa I
  95–160). LM is the dominant market unit for reveal work and directly matches the 5F
  `total reveal length — LM` measurement.
- **M2 reveal pricing (component rows): NOT separately supported.** No source isolates reveal
  prep / skim / sand / paint per m² of reveal surface. M2 exists only as a *complete obróbka*
  aggregate (80–120 zł/m²; 113 zł/m² door glifs) — i.e. M2 is supported as part of a bundled
  finish, not as a component-unit basis. The 5F `reveal area — M2` measurement therefore has no
  direct per-component market reference yet.
- **Future optional commercial pricing modes evidenced by the market** (recorded only — not
  implemented): **per window** (S4 250–550 zł/okno; S10 100–150 zł/okno), **per door** (S8 120–400
  zł/skrzydło; S9 250–650 zł/zlecenie), and **minimum/floor charges** (S8 "od 200 zł brutto za
  kompletną obróbkę skrzydła" as a de-facto floor; S9 per-job flooring of small operations).
  These are strongly present and should be evaluated at 9E.4 as potential optional quoting modes —
  **without changing Stage 5F or the Price Book architecture**.

## 16. NORMALIZATION_REVIEW_NOTE (Batch A/B issues preserved + new Batch C issues, for 9E.4)

Preserved from 9E.3A / 9E.3B (not fixed here — **Batch A/B numbers untouched**):
1. **SKIM_PKG-01 vs SKIM_1L-01 / SKIM_2L-01** — package band 35–70 vs component equivalent 65–91;
   decide package scope at 9E.4.
2. **Painting coat-count** — 2-coat PAINT_2K default; no double-count of PRIM_PAINT/SKIM;
   re-verify the inconsistent cennikremontow 1-coat row.
3. **betonizm.pl Q4** — main-table 60–80 vs chart 110 conflict; re-check at 9E.4.
4. **GK_JOINT unit model** — M2 vs LM (mb) evidence family; confirm unit at 9E.4.
5. **Kraków "Montaż narożników" cell** — 22–30 zł/m² for a linear service; unit mismatch.

New issues exposed by Batch C:
6. **Reveal unit model (NEW)** — 4 of 6 REV items are M2 component rows (PREP/SKIM/SAND/PAINT) with
   **no standalone market pricing**; the market prices reveals per **mb** (30–110 labor) or per
   window/door. 9E.4 must decide the reveal row strategy — e.g. derive M2 component rows from
   equivalent wall-work rates (Batch A/B) plus a reveal handling surcharge, or make the reveal scope
   LM-dominant while keeping 5F's M2 aggregate as a report-only basis. Both 9B seeds
   (`CENNIK_REVEAL_GENERIC_M2` / `_LM`) exist; internal consistency must be proven at 9E.4.
7. **M2 complete-bundle vs component (NEW)** — 80–120 zł/m² (S4/S5) and 113 zł/m² (S1) are complete
   reveal finishing; they must not be relabeled as component (szpachlowanie/malowanie) rates.
8. **Szpaleta dual scope (NEW)** — prefab profile systems (S7 80–350 zł/mb) are a different
   technology than tynkowa obróbka; do not mix into the tynk-based LM range.
9. **Kraków-zone LM evidence (NEW)** — only S6's metropolis/large-city mapping (Strefa I 95–160
   zł/mb robocizna; Kraków +20–35%) positions Kraków; no Kraków firm publishes reveal rates. 9E.4
   may use this zone map as regional-coefficient guidance or keep the national cluster (50–67,
   ref 60) as default — pending owner decision.

## 17. Research summary (for `docs/development-progress.md`)

- Items researched: **6 / 6** Batch C items.
- Sources: **10 referenced evidence pages** used (9 numeric/context + 1 shared-family add-on), of
  which **0 are Kraków-local anchors**, **1 is regional-zone (o-okna Strefa I = Kraków-metropolis
  mapping, national-calculator origin)**, **9 Poland-wide** (incl. 1 Warsaw-dated row flagged).
  A further **10 negative-check pages** (7 Kraków/Małopolskie + 3 national) were audited and
  contain **no** reveal price rows.
- Confidence distribution: **HIGH 0** · **MEDIUM 1** (REV_WORK_LM) · **LOW 0** ·
  **INSUFFICIENT 5** (REV_PREP, REV_SKIM, REV_SAND, REV_PAINT, REV_PAINT_LM).
- OWN_PRICE candidates: **5** (all M2 component rows + REV_PAINT_LM). REV_WORK_LM keeps the only
  market band (30–110 zł/mb labor, ref 60).
- Stage 5F compatibility conclusion: **PARTIALLY_SUPPORTED** (LM strongly supported; M2 only as a
  complete-bundle basis) — see §15.
- Additional technology finding: "szpaleta" is dual-scope (generic reveal vs prefab profile
  system); the catalog model is tynkowa obróbka — prefab systems excluded (§2, §13).

## 18. CROSS-CHECK (9E.3C §22)

- **All 6 canonical items researched** — yes; codes verbatim from the catalog.
- **Every numeric claim traceable** — each figure carries source, URL, type, region,
  `checked_at 2026-09-14`; quotes read from the opened page.
- **Exact URLs present** — §5 index + item sections.
- **Local vs national separated** — LOCAL 0 (documented negative audit §4.1), REGIONAL 1 (S6 zone,
  caveat), NATIONAL band for REV_WORK_LM only.
- **M2 vs LM never merged** — M2 component rows get **no** band (INSUFFICIENT); LM band uses only
  mb rows; m²-complete figures kept separate (§10/§12/§13).
- **Per-piece quotes never converted** — all PCS/window/door/FLAT rows isolated in §13.
- **Window vs door context recorded** — per row (item notes, §13).
- **New vs repair recorded** — new / po-montażu / replacement contexts classified (item notes).
- **Labor vs L+M separated** — LABOR band 30–110 from LABOR rows; L+M rows (S1 78,25/mb; S3
  50–120; S7) kept out or separately flagged.
- **Minimum charges excluded from unit ranges** — per-piece floors recorded in §13 only.
- **No invented geometry** — no default window/door dimensions assumed; depth/width recorded only
  as source-stated surcharges.
- **No invented prices** — honest INSUFFICIENT for rows without market basis; no manufactured
  conversions anywhere.

## 19. Source archival & exclusion notes

- Dynamic/aggregator pages (S2, S3, S6) were captured with each page's own stated figures;
  figures may drift — re-verify before seeding (9E.5/9E.7).
- Shared-family flag S3↔S4↔S5 keeps single-content duplication out of the count; S6 caution flag
  set (§5).
- Unreachable at check time (not used): cenauslug Kraków glify/ocieplenie subpages (410);
  terraglass (403); assystem (403); hejmalarz (no prices, editorial-only); sccot
  (editorial-only, excluded in 9E.3B too).
- **Excluded scope**: external reveal insulation ("ocieplenie ościeży") — thermal insulation, not
  finishing; window-frame painting ("malowanie okien" 180 zł/szt., 134–440 zł/m²) — the window
  itself, not the reveal.

## 20. Checked-at note

All `checked_at` values in this file: **2026-09-14**.