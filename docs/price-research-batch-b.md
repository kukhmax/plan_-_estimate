# Kraków / Małopolskie — Price Research — Batch B (Stage 9E.3B)

> Canonical Stage 9, execution sub-stage **9E.3B**. Input contract: `docs/price-research-catalog.md`
> (9E.2), groups: Painting (7), Glass fiber / fleece (3), Gypsum board finishing (5) — 15 items.
> Output contract: 9E.1 market reference & sources architecture.
> **This file is research evidence ONLY.** It contains no seed decisions, no `PriceItem.price`
> values, and no implementation-ready market ranges for the app. All prices below are **verbatim
> quotes from the listed sources**, recorded with `checked_at`. Aggregated `market_min/market_max`
> are the defensible observed window for that scope; `reference_price` is used only where a central
> commonly-observed value exists and the methodology is stated (never a fake arithmetic average).

Research date (all source records): **2026-09-14**.

Geographic priorities (9E.3B §1 — stronger local-source rule): **Kraków contractors first** →
Kraków painting / drywall / renovation firms → nearby Kraków agglomeration (Wieliczka, Skawina,
Zabierzów) and Małopolskie rows → Poland-wide supplementary. Every source is stamped with a
`LOCAL / REGIONAL / NATIONAL` classification per item. A nationwide source is **never** silently
treated as a Kraków source; sources are not merged across tiers.

Technology / scope rules applied (9E.3B, verbatim requirements):
- **Painting**: standard baseline = 2 coats, prepared substrate, labour, per m². 1-coat, 3-coat,
  "z materiałem", primer-inclusive, wall-repair, skim, and whole-room FLAT quotes are never merged
  into the 2-coat LABOR range. Scope is classified strictly `LABOR / MATERIAL / LABOR_AND_MATERIAL /
  UNKNOWN`; material inclusion is never assumed.
- **Fleece**: the actual Polish term is recorded per source; every source is classified A
  (paint / renovation fleece — *flizelina malarska / włóknina szklana* underlay), B (glass-fiber
  wall covering — *tapeta z włókna szklanego*), or C (reinforcing mesh embedded in render/skim —
  *siatka zbrojąca*). No single range is built across different technologies.
- **Gypsum board**: finishing only (joints/tape/screws/corners/full-surface skim). **Q-level
  evidence rule**: a source counts as explicit Q1–Q4 evidence only if it literally labels the
  standard Q1/Q2/Q3/Q4 or gives an unambiguous Polish technical equivalent tied to that level.
  Marketing phrases ("gotowe pod malowanie", "idealnie gładkie") are _not_ Q-level evidence.
- **VAT**: `netto / brutto / VAT-unknown` recorded per source; VAT is never auto-added; mixing is
  flagged.
- **No invented prices**: items without a defensible quote are `INSUFFICIENT`, with an explicit
  `OWN_PRICE` candidate flag. No price is invented to fill a catalog gap.

---

## 16. Summary table

| Code | PL name | Unit | Scope | Market min | Market max | Reference | Confidence | Comparable sources | Region | Checked |
|---|---|---|---|---|---|---|---|---|---|---|
| CENNIK_PAINT_2K-01 | Malowanie ścian — 2 warstwy (standard) | M2 | LABOR | 10 | 28 | 18 | HIGH | 5 (1 partial, 1 flagged) | Kraków + PL | 2026-09-14 |
| CENNIK_PAINT_1K-01 | Malowanie ścian — 1 warstwa (odświeżenie) | M2 | LABOR | 8 | 30 | — | MEDIUM | 1 strong + 2 partial | Kraków + PL | 2026-09-14 |
| CENNIK_PAINT_3K-01 | Malowanie ścian — 3 warstwy | M2 | LABOR | 21,80 | 48 | — | MEDIUM | 1 Kraków row + 1 national | Kraków + PL | 2026-09-14 |
| CENNIK_PAINT_CEIL-01 | Malowanie sufitów — 2 warstwy | M2 | LABOR | 16 | 32 | 24 | MEDIUM | 1 Kraków table + 4 national | Kraków + PL | 2026-09-14 |
| CENNIK_PAINT_COL-01 | Malowanie w kolorze — 2 warstwy | M2 | LABOR | 14 | 30 | 20 | MEDIUM | 3 | Kraków + PL | 2026-09-14 |
| CENNIK_PAINT_MASK-01 | Maskowanie / zabezpieczanie powierzchni | M2 | LABOR | 5 | 20 | — | LOW | 4 (scope-variant; 1 PCS) | Kraków + PL | 2026-09-14 |
| CENNIK_PAINT_MULTI-01 | Malowanie wielokolorowe (2+ kolory) | M2 | LABOR | — | — | — | INSUFFICIENT | 0 comparable | — | 2026-09-14 |
| CENNIK_GF_FLIZ_L-01 | Włóknina/flizelina malarska — robocizna | M2 | LABOR | — | — | — | LOW | 0 tech-A; 3 tech-B analog | PL (+ Kraków row) | 2026-09-14 |
| CENNIK_GF_FLIZ_M-01 | Włóknina/flizelina z materiałem | M2 | LABOR_AND_MATERIAL | — | — | — | LOW | 0 tech-A; 1 tech-B L+M analog | PL (+ Kraków row) | 2026-09-14 |
| CENNIK_GF_MESH-01 | Wtapianie siatki zbrojącej | M2 | LABOR | 12 | 58 | — | MEDIUM | 2 (scope caveat) | Kraków + PL | 2026-09-14 |
| CENNIK_GK_JOINT-01 | Szpachlowanie łączeń płyt g-k (Q1/Q2) | M2 | LABOR | 34 | 46 | — | MEDIUM | 3 (+ 1 flagged) | Kraków-regional + PL | 2026-09-14 |
| CENNIK_GK_FULL-01 | Pełne szpachlowanie powierzchniowe (Q3) | M2 | LABOR | 28 | 45 | 40 | MEDIUM | 3 (2 explicit Q3) | Kraków + PL | 2026-09-14 |
| CENNIK_GK_SCREW-01 | Zaszpachlowanie łbów wkrętów | M2 | LABOR | — | — | — | INSUFFICIENT | 0 standalone | — | 2026-09-14 |
| CENNIK_GK_CORNER-01 | Obróbka narożników (za mb) | LM | LABOR | 10 | 22 | 18 | MEDIUM | 3 (+ 2 add-on/partial) | Kraków + PL | 2026-09-14 |
| CENNIK_GK_Q4-01 | Szpachlowanie Q4 (całopowierzchniowe ≥1 mm) | M2 | LABOR | 40 | 80 | — | MEDIUM | 2 explicit Q4 | PL | 2026-09-14 |

No implementation-ready seed decision yet — this is research evidence only (9E.3B §16).

Confidence key (9E.3B): HIGH = 3+ good comparable local/regional sources; MEDIUM = 2+ useful
sources or strong local + supplementary national; LOW = single useful source / scope or
terminology ambiguity; INSUFFICIENT = no defensible range.

---

## CENNIK_PAINT_2K-01 — Malowanie ścian — 2 warstwy (standard)

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P1
- NOT comparable: paint/material included, 1 coat, substrate repairs, room flat rate, colored-paint
  premium (see PAINT_COL).

Market result:
- market_min: 10
- market_max: 28
- reference_price: 18
- region: Kraków + PL
- checked_at: 2026-09-14
- confidence: HIGH

Source counts:
- LOCAL_SOURCE_COUNT: 5 (malarzkrakow, totaldecor, cennikremontow Kraków city table, ekipa-krakow,
  kubamalarz) — of which 3 clean LABOR anchors, 1 partial (kubamalarz, scope ambiguous), 1 flagged
  low-outlier (ekipa-krakow).
- REGIONAL_SOURCE_COUNT: 0 (no Małopolskie-specific row beyond the Kraków entries above).
- NATIONAL_SOURCE_COUNT: 5 (cennikibudowlane, wzbudowa, cenauslug, zleca, m-malowanie).

Methodology: comparable LABOR quotes for 2-coat white wall painting of a prepared substrate, per m².
Kraków floor: malarzkrakow "od 12 zł/m²" (netto, robocizna) and the cennikremontow Kraków city
table row "10–28 zł/m²" (labour-implied intro); the top of the Kraków window (28) also comes from
that city table. totaldecor (Kraków firm, "14 zł/m²") sits inside the band. The national
supplementary cluster (17–35 zł/m² netto, labour-only — cennikibudowlane; 20–30 — wzbudowa;
25–36 — cenauslug) overlaps the upper half of the local window; zleca.pl (10–25 brutto,
marketplace) and m-malowanie (2nd coat 18–28 with priming, per-coat basis) are recorded
separately as partially comparable. ekipa-krakow's 10 zł/m² labour-only row corroborates the local
floor but the firm is flagged as a uniform low outlier (its gładź 15–18 and łączenia 5 zł/m² are well
below every other checked source), so it is not used to anchor the range. reference_price 18
= the central commonly-observed value of the clean local+national LABOR cluster (city tables and
contractor cenniki converge on 14–18 / 20–28).

Comparable source count: 5 local pages (3 clean LABOR + 1 partial + 1 flagged) and 5 national pages
(2 partial: zleca, m-malowanie).

Sources:

1.
- Name: Malarz Kraków — cennik (firma Kraków)
- URL: https://malarzkrakow.pl/cennik/
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków (LOCAL)
- Checked: 2026-09-14
- Quoted value: "Malowanie dwukrotne na biało (ściany i sufity) — od 12 zł/m²"; page: "Podane ceny
  są cenami netto za samą robociznę"
- Unit: M2
- Price scope: LABOR
- Included work: 2 coats, white, walls and ceilings; flat-roller ("wałek") baseline implied
- Excluded/unknown: paints/materials; VAT (netto); orientacyjny, non-binding
- Comparability: fully comparable — same work, labour-only, Kraków firm.

2.
- Name: Totaldecor Kraków — cennik (firma remontowa Kraków)
- URL: https://totaldecor.pl/cennik/
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków (LOCAL)
- Checked: 2026-09-14
- Quoted value: "Malowanie (2-krotne) – na biało — 14 zł/m²"; page: "Podane ceny są jedynie
  orientacyjne"
- Unit: M2
- Price scope: UNKNOWN (labour/material not stated)
- Included work: 2-coat wall painting white
- Excluded/unknown: materials; VAT; coverage of prep work
- Comparability: partially comparable — same work and city, but scope (labour vs L+M) not stated;
  used as a local floor corroborator, not converted into a LABOR claim.

3.
- Name: CennikRemontow.pl — Malowanie Kraków (city price table)
- URL: https://cennikremontow.pl/malowanie-krakow-cennik
- Type: CITY_PRICE_TABLE (national portal, Kraków page)
- Region: Kraków (LOCAL table)
- Checked: 2026-09-14
- Quoted value: "Malowanie ścian dwukrotne (farba-biała) — 10–28 zł/m2"; intro: "ceny i koszt
  robocizny"
- Unit: M2
- Price scope: UNKNOWN (labour-implied by intro; not stated per row)
- Included work: 2-coat white wall painting
- Excluded/unknown: materials; netto/brutto; the same page's 1-coat row (16–30) exceeds this
  2-coat row — flagged internally inconsistent (see PAINT_1K)
- Comparability: partially comparable — same work, city table, but per-row scope unstated; treated
  as a town-level window, not a firm LABOR quote.

4.
- Name: Ekipa Kraków — cennik usług remontowo-budowlanych (firma Kraków)
- URL: https://ekipa-krakow.pl/cennik-uslug-remontowo-budowlanych-krakow/
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków (LOCAL)
- Checked: 2026-09-14
- Quoted value: "Malowanie (dwukrotne) farbami emulsyjnymi (Biała-kolor) bez materiału — 10,00 zł/m2"
  (labour only; with material 13,00 zł/m2)
- Unit: M2
- Price scope: LABOR (with-material row given separately)
- Included work: 2-coat white/color emulsion painting, no material
- Excluded/unknown: VAT; paints
- Comparability: comparable work but **flagged as a uniform low outlier** across this firm's whole
  list (gładź 15–18, łączenia 5 zł/m²) — corroborates the city-table floor only; not a range anchor.

5.
- Name: Malarz Kraków (kubamalarz.pl) — cennik (firma Kraków)
- URL: https://kubamalarz.pl/cennik/
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków (LOCAL) — addr. Skowronia, 30-650 Kraków
- Checked: 2026-09-14
- Quoted value: "Dwukrotne malowanie ścian od 27 zł/m2" (table 1) / "Dwukrotne malowanie od
  25 zł/m2" (table 2)
- Unit: M2
- Price scope: UNKNOWN (only gładź row states "z materiałem")
- Included work: 2-coat wall painting
- Excluded/unknown: materials; VAT (prices "od")
- Comparability: partially comparable — same city, but scope unstated (L+M-leaning likely);
  recorded as a trade-level premium signal, not merged into the clean LABOR range.

6.
- Name: CennikiBudowlane — Malowanie mieszkań i domów
- URL: https://www.cennikibudowlane.com.pl/cenniki/malowanie-mieszkan-i-domow/
- Type: NATIONAL_PRICE_LIST
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Malowanie ścian 2 warstwy (standardowo) — robocizna: 17–35 zł/m²"; "Malowanie
  ścian w 2026: 17–50 zł/m² za samą robociznę (dwukrotne malowanie)"
- Unit: M2
- Price scope: LABOR
- Included work: 2-coat standard wall painting
- Excluded/unknown: materials; VAT (netto per table header); full-premium tiers (42–65) noted by
  the source itself (eko 17–28 / standard 28–42 / premium 42–65)
- Comparability: fully comparable at standard tier.

7.
- Name: WZBudowa — cennik usług malarskich
- URL: https://wzbudowa.pl/cennik-uslug-malarskich/
- Type: NATIONAL_EDITORIAL_PRICE_LIST
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Malowanie ścian na biało, 2 warstwy — ok. 20–30 zł/m² (za robociznę)"
- Unit: M2
- Price scope: LABOR (editorial "ceny za samą robociznę")
- Included work: 2-coat white wall painting
- Excluded/unknown: materials ("Farba, grunt, taśmy, folie… mogą być doliczane osobno"); VAT
- Comparability: fully comparable.

8.
- Name: CenAUsług — Malowanie ścian i sufitów (national price portal)
- URL: https://cenauslug.pl/budowa-i-remont/malowanie-scian-i-sufitow
- Type: NATIONAL_PRICE_PORTAL
- Region: PL (NATIONAL; city averages incl. Nowy Sącz 27 — Małopolskie)
- Checked: 2026-09-14
- Quoted value: "Malowanie ścian i sufitów — średnia 28 zł/m² (min 25, max 36)"; "Podana kwota
  obejmuje zazwyczaj dwukrotne nałożenie farby na przygotowane podłoże"; "Cena … nie zawiera
  materiałów"
- Unit: M2
- Price scope: LABOR
- Included work: 2 coats on prepared substrate, walls and ceilings
- Excluded/unknown: materials (15–25 zł/m² extra); netto/brutto (not stated; portal warns figures
  are "szacunkowe")
- Comparability: fully comparable for the 2-coat labour baseline.

9.
- Name: Zleca.pl — cennik usług malarskich (marketplace)
- URL: https://zleca.pl/cenniki/remonty-i-wykonczenia-malowanie
- Type: MARKETPLACE_PRICE_LIST
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Malowanie ścian na biało — 10–25 zł/m² (śr. 17,50)" (brutto)
- Unit: M2
- Price scope: UNKNOWN (marketplace rates; labour-only assumed by portal, not stated)
- Included work: wall painting to white
- Excluded/unknown: coats (1 vs 2 not separated on this row); materials; VAT (listed brutto)
- Comparability: partially comparable — used as a national cross-check only, not merged into the
  netto LABOR band.

10.
- Name: M-Malowanie — cennik malowania (national contractor list)
- URL: https://m-malowanie.pl/cennik-malowania
- Type: NATIONAL_PRICE_LIST
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Drugie malowanie (dowolna powierzchnia) — 18–28 PLN/m²"; ceny "za m²,
  z gruntowaniem"
- Unit: M2
- Price scope: LABOR_AND_MATERIAL (for the priming component); per-coat basis
- Included work: second coat; priming included in base rate
- Excluded/unknown: paints; VAT
- Comparability: partially comparable — per-coat system with priming included; only the "2nd coat
  18–28" figure is cross-referenced, never folded into a per-job 2-coat LABOR claim.

Notes / exclusions:
- kubamalarz (25–27) and zleca (10–25 brutto) and m-malowanie (18–28) are cross-checks, not
  points of the clean range.
- ekipa-krakow is a flagged uniform low outlier (see Comparability #4).
- The 1-coat row of the same Kraków city table (16–30) is higher than its 2-coat row (10–28) —
  a self-inconsistency flagged to 9E.4; the 2-coat row is retained.

---

## CENNIK_PAINT_1K-01 — Malowanie ścian — 1 warstwa (odświeżenie)

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P2
- NOT comparable: 2-coat jobs, "z materiałem"/grunt-inclusive quotes merged into the range.

Market result:
- market_min: 8
- market_max: 30
- reference_price: —
- region: Kraków + PL
- checked_at: 2026-09-14
- confidence: MEDIUM

Source counts:
- LOCAL_SOURCE_COUNT: 2 (malarzkrakow "od 8"; cennikremontow Kraków 1-coat rows — flagged).
- REGIONAL_SOURCE_COUNT: 0.
- NATIONAL_SOURCE_COUNT: 3 (m-malowanie 1-coat with priming; zleca white row coats-unstated;
  cenauslug qualitative markup note).

Methodology: the only clean, unambiguous 1-coat LABOR floor is the Kraków firm malarzkrakow "od
8 zł/m²" ("Malowanie jednokrotne — odświeżenie koloru", netto, robocizna). The cennikremontow
Kraków city table publishes 1-coat rows (white 16–30, color 8–30) that contradict the page's own
2-coat row (white 10–28) — the 1-coat table is internally inconsistent and is therefore recorded
but **not used as a range anchor**. Upper bound (30) reflects the least-bad city table row (color
8–30) and the national context (m-malowanie 1-coat 28–45 with priming — partially comparable).
Confidence is MEDIUM only because "strong local floor + supplementary national" exists; 9E.4 should
re-verify the cennikremontow 1-coat row set.

Comparable source count: 1 strong local (malarzkrakow) + 2 partial national (m-malowanie, zleca) +
1 flagged local table (cennikremontow Kraków).

Sources:

1.
- Name: Malarz Kraków — cennik (firma Kraków)
- URL: https://malarzkrakow.pl/cennik/
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków (LOCAL)
- Checked: 2026-09-14
- Quoted value: "Malowanie jednokrotne (odświeżenie koloru) — od 8 zł/m²" (netto, za samą robociznę)
- Unit: M2
- Price scope: LABOR
- Included work: 1-coat refresh of existing color
- Excluded/unknown: materials; VAT; substrate repairs
- Comparability: fully comparable — the single clean 1-coat LABOR anchor.

2.
- Name: CennikRemontow.pl — Malowanie Kraków (city price table)
- URL: https://cennikremontow.pl/malowanie-krakow-cennik
- Type: CITY_PRICE_TABLE
- Region: Kraków (LOCAL table)
- Checked: 2026-09-14
- Quoted value: "Malowanie ścian jednokrotne (farba-biała) — 16–30 zł/m2"; "…(farba-kolor) —
  8–30 zł/m2"
- Unit: M2
- Price scope: UNKNOWN
- Included work: 1-coat wall painting
- Excluded/unknown: materials; netto/brutto
- Comparability: **flagged** — 1-coat white (16–30) exceeds the same table's 2-coat white row
  (10–28); the table is internally inconsistent and must be re-verified in 9E.4. Not a range anchor.

3.
- Name: M-Malowanie — cennik malowania
- URL: https://m-malowanie.pl/cennik-malowania
- Type: NATIONAL_PRICE_LIST
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Malowanie ścian (jedna warstwa) — 28–45 PLN/m² — z gruntowaniem, bez demontażu
  osłon"
- Unit: M2
- Price scope: LABOR_AND_MATERIAL (priming included); per-coat
- Included work: 1 coat + priming
- Excluded/unknown: paints; VAT; also notes Warszawa/Kraków +15–25%
- Comparability: partially comparable — includes priming, so the range top is not merged into a
  clean LABOR band; recorded for context.

4.
- Name: Zleca.pl — cennik usług malarskich (marketplace)
- URL: https://zleca.pl/cenniki/remonty-i-wykonczenia-malowanie
- Type: MARKETPLACE_PRICE_LIST
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Malowanie ścian na biało — 10–25 zł/m² (śr. 17,50)"; "Odświeżenie powłok
  malarskich — 10–30 zł/m² (śr. 20)"
- Unit: M2
- Price scope: UNKNOWN; coat count not separated on this row
- Included work: wall painting / refresh
- Excluded/unknown: coats; materials; VAT (brutto)
- Comparability: partially comparable — the "odświeżenie" row is a 1-coat-leaning context row only.

Notes / exclusions:
- The cennikremontow Kraków 1-coat white row (16–30) being more expensive than its own 2-coat row
  (10–28) is a data-quality alert recorded for 9E.4; no 1-coat range is anchored to it.
- No 3rd independent firm publishes an unambiguous 1-coat white LABOR rate in the checked set —
  PAINT_1K relies on one strong local anchor + national context.

---

## CENNIK_PAINT_3K-01 — Malowanie ścian — 3 warstwy

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P3
- NOT comparable: per-coat quotes extrapolated up to three.

Market result:
- market_min: 21,80
- market_max: 48
- reference_price: —
- region: Kraków + PL
- checked_at: 2026-09-14
- confidence: MEDIUM

Source counts:
- LOCAL_SOURCE_COUNT: 1 (kb.pl Kraków city table, "Malowanie ścian i sufitów (trzy warstwy)").
- REGIONAL_SOURCE_COUNT: 0.
- NATIONAL_SOURCE_COUNT: 1 (cennikibudowlane 3-coat 25–48, netto) + premium/colour context
  (cennikibudowlane dark-colour +8–15; wzbudowa qualitative).

Methodology: a single Kraków city row prices 3-coat painting directly — kb.pl Kraków table
"Malowanie ścian i sufitów (trzy warstwy) — 21,80 zł/m² netto / 23,60 brutto" (single colour
context, szacunkowe averages for Kraków and adjacent towns). A single national list (cennikibudowlane)
prices 3-coat "intensywne kolory" at 25–48 zł/m² netto, labour. Both are netto, which is the only
slice where the pair is comparable (VAT mixing avoided; the brutto 23,60 equivalent is stated
separately). market_max 48 reflects the national 3-coat window; the gap 23,6–25 is the same-city
vs national-list anchor spread and is disclosed rather than smoothed. No reference_price is
selected — only two independent 3-coat rows exist.

Comparable source count: 1 local city row + 1 national list row (2 direct 3-coat figures) + context
rows.

Sources:

1.
- Name: KB.pl — Kraków city table "Malowanie i tapetowanie" (kb.pl)
- URL: https://kb.pl/cenniki/miejskie/malowanie-i-tapetowanie/krakow/
- Type: CITY_PRICE_TABLE
- Region: Kraków (LOCAL table; the page covers Kraków "jak i w przyległych miejscowościach")
- Checked: 2026-09-14
- Quoted value: "Malowanie ścian i sufitów (trzy warstwy) — 21,80 zł/m2 netto, 23,60 zł/m2 brutto"
- Unit: M2
- Price scope: UNKNOWN (city "szacunkowe" average; single-colour context)
- Included work: 3-coat walls and ceilings
- Excluded/unknown: materials; VAT pending netto/brutto columns both shown; "szacunkowe, nie
  stanowią oferty handlowej"
- Comparability: comparable — the only direct Kraków 3-coat row; single-colour framing.

2.
- Name: CennikiBudowlane — Malowanie mieszkań i domów
- URL: https://www.cennikibudowlane.com.pl/cenniki/malowanie-mieszkan-i-domow/
- Type: NATIONAL_PRICE_LIST
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Malowanie ścian 3 warstwy (intensywne kolory) — robocizna: 25–48 zł/m²"; dark
  colours "+8–15 zł/m²"
- Unit: M2
- Price scope: LABOR
- Included work: 3-coat wall painting, intensive colours
- Excluded/unknown: materials; VAT (netto)
- Comparability: comparable at the labour tier.

3.
- Name: WZBudowa — cennik usług malarskich
- URL: https://wzbudowa.pl/cennik-uslug-malarskich/
- Type: NATIONAL_EDITORIAL_PRICE_LIST
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Trzecia warstwa farby" listed among "Najczęstsze dopłaty" — no zł/m² figure given
- Unit: M2
- Price scope: —
- Comparability: qualitative — confirms 3rd coat is a surcharge, not a tier on most cenniki.

Notes / exclusions:
- 3-coat evidence is intentionally thin (two direct rows). Do not synthesize a 3-coat band from
  2-coat + "third coat" add-ons without a 9E.4 check against the 2-coat normalization (see §21).

---

## CENNIK_PAINT_CEIL-01 — Malowanie sufitów — 2 warstwy

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P1

Market result:
- market_min: 16
- market_max: 32
- reference_price: 24
- region: Kraków + PL
- checked_at: 2026-09-14
- confidence: MEDIUM

Source counts:
- LOCAL_SOURCE_COUNT: 1 (cennikremontow Kraków ceiling rows). malarzkrakow pools ceilings into its
  walls+ceilings rows (no separate ceiling row); totaldecor does not price flat ceiling painting.
- REGIONAL_SOURCE_COUNT: 0.
- NATIONAL_SOURCE_COUNT: 4 (wzbudowa 20–40; cennikibudowlane 22–38; cenauslug +20% over wall
  25–36 → 30–43 context; m-malowanie 35–55 1-coat with priming — partial).

Methodology: the local window comes from the cennikremontow Kraków city ceiling rows — 2-coat white
18–32, 1-coat white 18–30, 2-coat color 16–22, 1-coat color 16–22 (recorded per source). market
min 16 / max 32 reflect the standard 2-coat rows within that single table (white is the baseline:
18–32; color rows floor at 16). National labour-only supplements (wzbudowa 20–40; cennikibudowlane
22–38) overlap the local band; cenauslug publishes ceilings as "bywa droższe o 20%" over its wall
average (25–36) — recorded as context. reference_price 24 = central value of the observed
2-coat ceiling cluster (Kraków 18–32 / PL 20–40).

Comparable source count: 1 Kraków city table (4 ceiling rows) + 3 national labour lists + 1 context
markup note.

Sources:

1.
- Name: CennikRemontow.pl — Malowanie Kraków (city price table, ceiling rows)
- URL: https://cennikremontow.pl/malowanie-krakow-cennik
- Type: CITY_PRICE_TABLE
- Region: Kraków (LOCAL table)
- Checked: 2026-09-14
- Quoted value: "Malowanie sufitu dwukrotne (farba-biała) — 18–32 zł/m2"; "…(farba-kolor) —
  16–22 zł/m2"; "Malowanie sufitu jednokrotne (farba-biała) — 18–30 zł/m2"
- Unit: M2
- Price scope: UNKNOWN (labour-implied intro)
- Included work: ceiling painting, 1–2 coats
- Excluded/unknown: materials; netto/brutto
- Comparability: comparable — the sole Kraków ceiling set; white 2-coat retains the 18–32 band.

2.
- Name: WZBudowa — cennik usług malarskich
- URL: https://wzbudowa.pl/cennik-uslug-malarskich/
- Type: NATIONAL_EDITORIAL_PRICE_LIST
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Malowanie sufitów — ok. 20–40 zł/m² (za robociznę)"
- Unit: M2
- Price scope: LABOR
- Included work: ceiling painting
- Excluded/unknown: materials; VAT
- Comparability: fully comparable.

3.
- Name: CennikiBudowlane — Malowanie mieszkań i domów
- URL: https://www.cennikibudowlane.com.pl/cenniki/malowanie-mieszkan-i-domow/
- Type: NATIONAL_PRICE_LIST
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Malowanie sufitu — robocizna: 22–38 zł/m²"
- Unit: M2
- Price scope: LABOR
- Included work: ceiling painting
- Excluded/unknown: materials; VAT (netto)
- Comparability: fully comparable.

4.
- Name: CenAUsług — Malowanie ścian i sufitów
- URL: https://cenauslug.pl/budowa-i-remont/malowanie-scian-i-sufitow
- Type: NATIONAL_PRICE_PORTAL
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Malowanie sufitów bywa droższe o 20% ze względu na trudność prac" (over wall
  average 25–36 zł/m² → ~30–43 context)
- Unit: M2
- Price scope: LABOR
- Comparability: context markup note — recorded, not used as a point.

5.
- Name: M-Malowanie — cennik malowania
- URL: https://m-malowanie.pl/cennik-malowania
- Type: NATIONAL_PRICE_LIST
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Malowanie sufitów (jedna warstwa) — 35–55 PLN/m² — z gruntowaniem"
- Unit: M2
- Price scope: LABOR_AND_MATERIAL (priming included); per-coat
- Comparability: partially comparable — priming-inclusive, per-coat; context only.

Notes / exclusions:
- malarzkrakow pools ceilings into "ściany i sufity" rows; do not double-count its "od 12" as a
  ceiling figure.
- Color vs white ceiling rows span 16–32 within one city table; 9E.4 should decide whether PAINT_CEIL
  keeps a single band or splits color.

---

## CENNIK_PAINT_COL-01 — Malowanie w kolorze — 2 warstwy

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P2
- NOT comparable: white-only jobs; decorative / fantasy / artistic painting (PAINT_MULTI).

Market result:
- market_min: 14
- market_max: 30
- reference_price: 20
- region: Kraków + PL
- checked_at: 2026-09-14
- confidence: MEDIUM

Source counts:
- LOCAL_SOURCE_COUNT: 3 (malarzkrakow od 14; totaldecor 18; cennikremontow Kraków color rows
  14–30).
- REGIONAL_SOURCE_COUNT: 0.
- NATIONAL_SOURCE_COUNT: 2 (wzbudowa 25–40; cennikibudowlane dark-colour +8–15 surcharge context).

Methodology: three Kraków sources price 2-coat color painting as a LABOR line: malarzkrakow
"Malowanie dwukrotne w kolorze (ściany i sufity) — od 14 zł/m²" (netto, robocizna), totaldecor 18
(color at the same firm's white 14), and the cennikremontow Kraków city row "Malowanie ścian
dwukrotne (farba-kolor) — 14–30 zł/m2". wzbudowa supplies the national labour supplement
(25–40). No source publishes a separate percentage color premium that could be converted to
zł/m² — cennikibudowlane quotes dark colours only as "+8–15 zł/m²" / "+5–15%" (recorded as a
surcharge pattern, not converted). reference_price 20 = central value of the Kraków color
cluster (14–18 / 14–30 city window).

Comparable source count: 3 Kraków LABOR rows + 1 national supplement + 1 surcharge context.

Sources:

1.
- Name: Malarz Kraków — cennik (firma Kraków)
- URL: https://malarzkrakow.pl/cennik/
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków (LOCAL)
- Checked: 2026-09-14
- Quoted value: "Malowanie dwukrotne w kolorze (ściany i sufity) — od 14 zł/m²" (netto, za samą
  robociznę)
- Unit: M2
- Price scope: LABOR
- Included work: 2-coat colored paint, walls and ceilings
- Excluded/unknown: materials; VAT; deep/dark shades as separate premium not priced
- Comparability: fully comparable.

2.
- Name: Totaldecor Kraków — cennik (firma Kraków)
- URL: https://totaldecor.pl/cennik/
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków (LOCAL)
- Checked: 2026-09-14
- Quoted value: "Malowanie (2-krotne) – kolor — 18 zł/m²"
- Unit: M2
- Price scope: UNKNOWN (not stated)
- Included work: 2-coat colored wall painting
- Excluded/unknown: materials; VAT; prep
- Comparability: partially comparable (scope unstated) — corroborates the Kraków floor area.

3.
- Name: CennikRemontow.pl — Malowanie Kraków (city price table, color rows)
- URL: https://cennikremontow.pl/malowanie-krakow-cennik
- Type: CITY_PRICE_TABLE
- Region: Kraków (LOCAL table)
- Checked: 2026-09-14
- Quoted value: "Malowanie ścian dwukrotne (farba-kolor) — 14–30 zł/m2"
- Unit: M2
- Price scope: UNKNOWN
- Included work: 2-coat colored wall painting
- Excluded/unknown: materials; netto/brutto
- Comparability: comparable (city-window perspective).

4.
- Name: WZBudowa — cennik usług malarskich
- URL: https://wzbudowa.pl/cennik-uslug-malarskich/
- Type: NATIONAL_EDITORIAL_PRICE_LIST
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Malowanie ścian kolorem, 2 warstwy — ok. 25–40 zł/m² (za robociznę)"
- Unit: M2
- Price scope: LABOR
- Included work: 2-coat colored wall painting
- Excluded/unknown: materials; VAT
- Comparability: fully comparable.

5.
- Name: CennikiBudowlane — Malowanie mieszkań i domów
- URL: https://www.cennikibudowlane.com.pl/cenniki/malowanie-mieszkan-i-domow/
- Type: NATIONAL_PRICE_LIST
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Malowanie w kolorach ciemnych (grzejący 3x) — dopłata +8–15 zł/m²"; FAQ "kolor
  inny niż biały to dopłata 5-15%"
- Unit: M2
- Price scope: LABOR (surcharge)
- Comparability: surcharge-pattern context — percentage/absolute surcharges are recorded as the
  pricing structure, never converted to a standalone zł/m².

Notes / exclusions:
- PAINT_MULTI (2+ colors, cut-ins) is NOT covered here; decorative/artistic clusters are excluded
  from this LABOR range (see PAINT_MULTI).

---

## CENNIK_PAINT_MASK-01 — Maskowanie / zabezpieczanie powierzchni

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P3 (catalog flags an OWN_PRICE candidate)

Market result:
- market_min: 5
- market_max: 20
- reference_price: —
- region: Kraków + PL
- checked_at: 2026-09-14
- confidence: LOW

Source counts:
- LOCAL_SOURCE_COUNT: 3 (malarzkrakow od 5 — foliowanie; ekipa-krakow 10 — z folią i taśmą;
  kb.pl Kraków city 18,70 net / 20,20 brutto — zabezpieczenie folią przed malowaniem).
- REGIONAL_SOURCE_COUNT: 0.
- NATIONAL_SOURCE_COUNT: 2 (wzbudowa 5–15; cenauslug od 9) + 1 PCS-row (m-malowanie 5–12 zł/szt).

Methodology: masking/protection is quoted under at least two different packages even within the
local set: simple floor/furniture foil protection ("od 5 zł/m²", malarzkrakow; "5–15 zł/m²",
wzbudowa; "od 9 zł/m²", cenauslug) and comprehensive room protection — floors, furniture, windows,
sills — at 18,70 net / 20,20 brutto (kb.pl Kraków) and 10 zł/m² with foil+tape material
(ekipa-krakow). Because packages differ, the defensible window is wide (5–20) and LOW-confidence:
masking is usually bundled by contractors, so standalone masking rates are scarce and the scope is
ambiguous. m-malowanie prices masking only per piece ("5–12 PLN za sztukę" — outlets, switches,
niches) — a PCS unit, recorded separately and never merged into the M2 band.

Comparable source count: 4 per-m² pages (3 package variants) + 1 PCS row.

Sources:

1.
- Name: Malarz Kraków — cennik (firma Kraków)
- URL: https://malarzkrakow.pl/cennik/
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków (LOCAL)
- Checked: 2026-09-14
- Quoted value: "Zabezpieczenie powierzchni (foliowanie mebli, podłóg, okien) — od 5 zł/m²"
  (netto, za samą robociznę)
- Unit: M2
- Price scope: LABOR
- Included work: foil protection of furniture/floors/windows
- Excluded/unknown: materials; VAT
- Comparability: comparable (simple-protection package).

2.
- Name: Ekipa Kraków — cennik (firma Kraków)
- URL: https://ekipa-krakow.pl/cennik-uslug-remontowo-budowlanych-krakow/
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków (LOCAL)
- Checked: 2026-09-14
- Quoted value: "Zabezpieczenie folią lub wystawienie do pomieszczeń sąsiednich mebli… (nakład na
  m2 podłogi) z kosztem folii i taśmy — 10,00 zł/m2"
- Unit: M2
- Price scope: LABOR_AND_MATERIAL (foil and tape included)
- Included work: floor foil protection + moving furniture, with foil/tape material
- Excluded/unknown: VAT
- Comparability: comparable with L+M package; flagged firm-wide low-outlier (see PAINT_2K #4).

3.
- Name: KB.pl — Kraków city table "Malowanie i tapetowanie"
- URL: https://kb.pl/cenniki/miejskie/malowanie-i-tapetowanie/krakow/
- Type: CITY_PRICE_TABLE
- Region: Kraków (LOCAL table)
- Checked: 2026-09-14
- Quoted value: "Zabezpieczenie folią przed malowaniem — 18,70 zł/m2 netto, 20,20 zł/m2 brutto"
  (floors, furniture, windows, sills)
- Unit: M2
- Price scope: UNKNOWN (city average)
- Included work: comprehensive room protection before painting
- Excluded/unknown: materials; "szacunkowe" averages
- Comparability: comparable (comprehensive package — the same work class as the foil rows, broader
  coverage explains the top of the band).

4.
- Name: WZBudowa — cennik usług malarskich
- URL: https://wzbudowa.pl/cennik-uslug-malarskich/
- Type: NATIONAL_EDITORIAL_PRICE_LIST
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Zabezpieczenie folią i taśmą — ok. 5–15 zł/m² powierzchni zabezpieczanej (robocizna)"
- Unit: M2
- Price scope: LABOR
- Comparability: comparable.

5.
- Name: CenAUsług — Malowanie ścian i sufitów
- URL: https://cenauslug.pl/budowa-i-remont/malowanie-scian-i-sufitow
- Type: NATIONAL_PRICE_PORTAL
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Zabezpieczenie folią malarską — od 9 zł/m²"
- Unit: M2
- Price scope: UNKNOWN
- Comparability: comparable (floor).

6.
- Name: M-Malowanie — cennik malowania
- URL: https://m-malowanie.pl/cennik-malowania
- Type: NATIONAL_PRICE_LIST
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Ekipy malarskie często doliczają za każde takie wykończenie od 5 do 12 PLN za
  sztukę" (okna, gniazdka, włączniki, wnęki wymagające oklejania taśmą malarską)
- Unit: PCS (per piece)
- Price scope: LABOR
- Comparability: different unit (PCS) — recorded as the per-outlet pricing structure; never merged
  into the M2 band.

Notes / exclusions:
- The scope split (simple foil vs comprehensive room protection) makes this a LOW-confidence item.
  Strong OWN_PRICE candidate: the catalog flags PAINT_MASK as P3/OWN_PRICE; the checked evidence
  suggests masking is normally bundled or flat-rated.

---

## CENNIK_PAINT_MULTI-01 — Malowanie wielokolorowe (2+ kolory / odcinanie)

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P3 (catalog flags an OWN_PRICE candidate)

Market result:
- market_min: —
- market_max: —
- reference_price: —
- region: —
- checked_at: 2026-09-14
- confidence: INSUFFICIENT

Source counts:
- LOCAL_SOURCE_COUNT: 0 comparable.
- REGIONAL_SOURCE_COUNT: 0.
- NATIONAL_SOURCE_COUNT: 0 comparable (decorative/artistic clusters exist but are a different
  commodity).

Methodology: no checked source prices "2+ colours with cut-ins" as a standalone per-m² service.
The pricing structure that does appear is **surcharge-based**, not per-m² line-item:
- cenauslug: "skomplikowane odcięcia kolorów przy taśmie tesa oraz malowanie grzejników to usługi
  dodatkowo płatne" (qualitative surcharge, no value).
- cennikibudowlane: dark colours "+8–15 zł/m²" / FAQ "kolor inny niż biały to dopłata 5-15%"
  (per-colour surcharges).
Sources quoting decorative and artistic painting — cennikremontow Kraków table "Malowanie
fantazyjne/dekoracyjne 20–40 zł/m²", "Malowanie artystyczne 132–632 zł/m²"; kubamalarz "Malowanie
dekoracyjne od 85 zł/m²"; wzbudowa structural paints 80–120 zł/m² — are a different product
(hand-finish/decorative techniques), explicitly excluded from a standard multi-colour cut-in
baseline. No percentage→zł/m² conversion is manufactured (spec rule). Because there is no
defensible numeric range, PAINT_MULTI stays INSUFFICIENT and is an OWN_PRICE candidate; 9E.4/9E.5
should define the owner policy (e.g. per-colour surcharge) rather than import a market range.

Comparable source count: 0.

Sources: (no numeric source — see surcharge references above: cenauslug, cennikibudowlane,
cennikremontow Kraków, kubamalarz, wzbudowa — all recorded under their items or here in notes).

Notes / exclusions:
- Guard against folding "malowanie kolorowe" (PAINT_COL, single colour) or decorative/artistic
  rates into PAINT_MULTI.

---

## CENNIK_GF_FLIZ_L-01 — Włóknina / flizelina malarska — robocizna (tech A)

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P1
- Technology (tech-A): *flizelina malarska* — paint/renovation fleece underlay (włóknina szklana /
  welon), typically 40–50 g/m² per the catalog.

Market result:
- market_min: — (tech A)
- market_max: — (tech A)
- reference_price: —
- region: PL (+ Kraków row, tech-B analog only)
- checked_at: 2026-09-14
- confidence: LOW

Source counts:
- LOCAL_SOURCE_COUNT: 0 for tech A. Tech-B analog row (LOCAL): KB.pl Kraków city row
  "Tapetowanie ścian (tapety z włókna szklanego) — 59,50 net / 64,30 brutto".
- REGIONAL_SOURCE_COUNT: 0.
- NATIONAL_SOURCE_COUNT: 2 for tech-B analog — kb.pl national table (48,82–77 brutto),
  t-tapety (50–80 netto). aikfarby (Kraków 65,40–74,30; national 48,82–77, network) duplicates
  the kb.pl band and is counted as one content point (see §18).

Methodology: **No technology-A price exists in the checked sources.** Dedicated application-labor
quotes for *flizelina malarska* / *włóknina szklana* underlay are not published standalone by any
contractor list, city table, cost portal, or editorial page examined (product pages at Leroy
Merlin / Ceneo / Allegro / OLX / SIG and the like price rolls of material only — excluded as not
a labour service). Per the technology rule, a band is NOT synthesized from a different
technology. Instead, the **glass-fiber wall covering (tech B — *tapeta z włókna szklanego*)
application-labour band** is recorded explicitly as a labeled analog in the supplementary column:
- kb.pl national table: 48,82–77,00 zł/m² brutto, national average 59,66 (glass-fibre wallpaper
  labour; kb.pl Kraków city row 64,30 brutto).
- aikfarby (same publisher network): Kraków labour 65,40–74,30 (śr. 69,80), "Stawki są brutto
  z materiałem po stronie zleceniodawcy" (labour-only).
- t-tapety (independent): 50–80 zł/m² **netto**, complex patterns +10–15% (VAT 8% private / 23%
  business).
Tech B differs from tech A in material class and working method (board/paper adjoining, overlap
joints, different glue), so these numbers are **not** a tech-A estimate; they are recorded so 9E.4
has the closest published floor for the fleece family, and the item is flagged OWN_PRICE (no
tech-A market basis).

Technology classification per source:
- KB.pl city Kraków: **B** (tapety z włókna szklanego).
- KB.pl tapetowanie table: **B**.
- aikfarby: **B** (włókno szklane; the page even notes "Włókno szklane nie rozciąga się jak
  flizelina" — explicitly distinguishing from flizelina).
- t-tapety: **B** (tapeta z włókna szklanego; grammar 120–150 / 200+ g/m² — again not the 40–50
  g/m² tech-A welon grammage).

Comparable source count: 0 tech-A; 3 tech-B analog pages (2 publishers: kb.network incl.
aikfarby counted once, t-tapety).

Sources:

1.
- Name: KB.pl — cennik tapetowania. Tapety z włókna szklanego (national table + Kraków city row)
- URL: https://kb.pl/cenniki/tapetowanie-scian-tapetami-z-wlokna-szklanego/
  (city row: https://kb.pl/cenniki/miejskie/malowanie-i-tapetowanie/krakow/)
- Type: NATIONAL_PRICE_TABLE + CITY_PRICE_TABLE
- Region: PL (NATIONAL); Kraków row LOCAL
- Checked: 2026-09-14
- Quoted value: "48,82 – 77,00 zł/m² brutto (średnia krajowa 59,66)" — tech B; Kraków:
  "Tapetowanie ścian (tapety z włókna szklanego) — 59,50 zł/m2 netto, 64,30 zł/m2 brutto"
- Unit: M2
- Price scope: LABOR (glass-fibre wallpapering; materials on the client's side generally)
- Included work: laying fiberglass wall covering
- Excluded/unknown: wallpaper material; VAT columns both shown (netto/brutto); "szacunkowe"
- Comparability: tech-B analog only for tech-A item — labeled, not merged.

2.
- Name: Aikfarby — Klejenie tapety z włókna szklanego — cena (content network w/ kb.pl)
- URL: https://aikfarby.pl/klejenie-tapety-z-wlokna-szklanego-cena
- Type: NATIONAL_PRICE_ARTICLE (Kraków city breakdown)
- Region: PL (NATIONAL); Kraków row REGIONAL (city breakdown)
- Checked: 2026-09-14
- Quoted value: "klejenie tapety z włókna szklanego … między 48,82 a 77,00 zł brutto za metr
  kwadratowy, średnia krajowa 59,66"; "Kraków: 65,40 / 69,80 / 74,30 zł/m²"; "Stawki są brutto
  z materiałem po stronie zleceniodawcy"; total with materials "110-190 zł/m²"
- Unit: M2
- Price scope: LABOR (materials on client's side for the 69,80 figure)
- Included work: laying fiberglass wall covering; separate painting coat 12–22 zł/m²
- Excluded/unknown: materials; VAT (brutto quotes)
- Comparability: tech-B analog; **suspected duplication with kb.pl national band (identical
  48,82–77 / 59,66 figures)** — counted as one content point, not an independent source.

3.
- Name: T-tapety — Cena położenia tapety z włókna szklanego
- URL: https://t-tapety.pl/cena-polozenia-tapety-z-wlokna-szklanego
- Type: NATIONAL_PRICE_ARTICLE
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Stawka robocizny oscyluje w przedziale od 50 do 80 zł za m²" (netto; complex
  patterns +10–15%; "Wszystkie podane wartości są cenami netto"; VAT 8%/23%)
- Unit: M2
- Price scope: LABOR
- Included work: laying fiberglass wall covering
- Excluded/unknown: wallpaper material; comple_service flat 500 zł netto noted separately (FLAT,
  scope unit unclear)
- Comparability: tech-B analog, independent publisher — the only independent tech-B figure.

Notes / exclusions:
- koszt-remonty.pl flizelina page was checked and excluded as unusable (internally inconsistent:
  labour 2–4 zł/m² vs full-service 45–69 zł/m² in the same article).
- Do NOT later reinterpret the tech-B band (48,82–77 brutto) as tech-A evidence when seeds are
  built.
- OWN_PRICE candidate flag ON (no tech-A market basis).

---

## CENNIK_GF_FLIZ_M-01 — Włóknina / flizelina — z materiałem (tech A)

Canonical scope:
- Unit: M2
- Price scope: LABOR_AND_MATERIAL
- Priority: P2 (catalog notes grammage 40–50 g/m²)

Market result:
- market_min: — (tech A)
- market_max: — (tech A)
- reference_price: —
- region: PL (+ Kraków row, tech-B analog only)
- checked_at: 2026-09-14
- confidence: LOW

Source counts:
- LOCAL_SOURCE_COUNT: 0 for tech A.
- REGIONAL_SOURCE_COUNT: 0.
- NATIONAL_SOURCE_COUNT: 1 tech-B L+M analog (aikfarby 110–190 zł/m² total) + the kb.pl material
  component estimate (43–110 zł/m²) in the same network.

Methodology: no tech-A LABOR_AND_MATERIAL price exists in the checked sources either (same
evidence gap as GF_FLIZ_L). The only published L+M figure for the fleece family is the tech-B
total-cost range: aikfarby "koszt łączny 110-190 zł/m²" (labour 48,82–77 + materials 43–110,
both per m²) — recorded strictly as a labeled tech-B analog, never as tech-A. A tech-A owner rate
would need to be defined by the owner (OWN_PRICE candidate). Note the catalog grammage (40–50 g/m²
paint fleece) does not appear in any service quote; the tech-B sources price wallpapers of
120–150 / 200+ g/m².

Comparable source count: 0 tech-A; 1 tech-B L+M analog (1 publisher).

Sources:

1.
- Name: Aikfarby — Klejenie tapety z włókna szklanego — cena
- URL: https://aikfarby.pl/klejenie-tapety-z-wlokna-szklanego-cena
- Type: NATIONAL_PRICE_ARTICLE (Kraków city breakdown)
- Region: PL; Kraków row REGIONAL
- Checked: 2026-09-14
- Quoted value: "koszt łączny 110-190 zł/m²" (robocizna 48,82–77 brutto; materiały —
  klej 3,5–5,5 zł/m², grunt 0,8–1,5, farba lateksowa 4–8, rolka 35–95 → "materiały 43-110 zł")
- Unit: M2
- Price scope: LABOR_AND_MATERIAL (tech-B composition)
- Included work: fiberglass covering labour + materials
- Excluded/unknown: VAT specifics (brutto framing); tech-A inapplicability
- Comparability: tech-B L+M analog — labeled; suspected kb.network duplication (see §18).

Notes / exclusions:
- t-tapety's flat kompleksowa "~500 zł netto" is a FLAT unit with an unspecified coverage area —
  recorded, never converted to zł/m².
- OWN_PRICE candidate flag ON.

---

## CENNIK_GF_MESH-01 — Wtapianie siatki zbrojącej

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P2
- Technology (tech C): reinforcing mesh embedded in skim/render for crack stabilisation
  (*siatka zbrojąca* / *włóknina szklana zbrojąca*).

Market result:
- market_min: 12
- market_max: 58
- reference_price: —
- region: Kraków + PL
- checked_at: 2026-09-14
- confidence: MEDIUM

Source counts:
- LOCAL_SOURCE_COUNT: 1 (cennikremontow Kraków city table row "Wszpachlowanie siatki zbrojącej na
  pęknięciach i zarysowaniach").
- REGIONAL_SOURCE_COUNT: 0.
- NATIONAL_SOURCE_COUNT: 1 (cenauslug "Wtapianie siatki elewacyjnej na całej ścianie" 30–45) +
  qualitative references to mesh as *flizelina* masking material (cenauslug article, unpriced).

Methodology: two sources price tech-C mesh embedding per m² of wall. The Kraków city table gives
the widest exposed window — "Wszpachlowanie siatki zbrojącej na pęknięciach i zarysowaniach"
12–58 zł/m² (per m² of board/wall surface; labour-implied) — the range reflecting how little vs how
much of the surface the mesh covers. The national article gives "Wtapianie siatki elewacyjnej na
całej ścianie — 30–45 zł/m²" (full wall, very damaged renders; brutto averages; cities like
Warszawa/Kraków/Wrocław +15–20%). **Terminology caveat**: the national quote says *siatka
elewacyjna* (facade reinforcing mesh) laid into a new plaster layer — technically the same
glass-fibre mesh-embedding motion as tech C, but in an exterior-repair context; comparability is
marked partial. Because only two pages price the row, the range stays MEDIUM.

Comparable source count: 2 pages (1 Kraków city table + 1 national article, partial comparability).

Sources:

1.
- Name: CennikRemontow.pl — Karton-gipsy Kraków (city price table)
- URL: https://cennikremontow.pl/karton-gipsy-krakow-cennik
- Type: CITY_PRICE_TABLE
- Region: Kraków (LOCAL table)
- Checked: 2026-09-14
- Quoted value: "Wszpachlowanie siatki zbrojącej na pęknięciach i zarysowaniach — 12–58 zł/m²"
- Unit: M2
- Price scope: UNKNOWN (labour-implied; table lacks per-row scope)
- Included work: embedding reinforcing mesh in skim over cracks/crazing
- Excluded/unknown: materials; netto/brutto
- Comparability: comparable (tech-C, Kraków table).

2.
- Name: CenAUsług — Renowacja popękanych ścian i sufitów
- URL: https://cenauslug.pl/poradniki/renowacja-popekanych-scian-i-sufitow-przeglad-skutecznych-metod
- Type: NATIONAL_PRICE_ARTICLE
- Region: PL (NATIONAL; notes Kraków +15–20% vs. smaller towns)
- Checked: 2026-09-14
- Quoted value: "Wtapianie siatki elewacyjnej na całej ścianie — 30–45 zł/m²" (brutto averages;
  "Metoda dla bardzo zniszczonych tynków. Tworzy nową, stabilną warstwę."); flizelina/włóknina
  mentioned only qualitatively as a ceiling "pajęczynki" masking material — **unpriced**
- Unit: M2
- Price scope: UNKNOWN (labour/service framing; material price for mesh not given)
- Included work: embedding glass-fibre reinforcing mesh over the full wall
- Excluded/unknown: mesh material; VAT (brutto averages)
- Comparability: partially comparable — *siatka elewacyjna* context vs a skim-based interior
  crack-mesh row; flagged rather than treated as identical.

Notes / exclusions:
- The unpriced qualitative flizelina description in source 2 is NOT evidence for GF_FLIZ_L/M; it
  merely confirms that *flizelina* is used as a surface-stabilising layer (tech-A/C overlap).
- No local LM rows for mesh were verified on 2026-09-14; earlier unverified notes of LM mesh rows
  are dropped rather than repeated.

---

## CENNIK_GK_JOINT-01 — Szpachlowanie łączeń płyt g-k (Q1/Q2)

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P1 (catalog hint: Q1 — joint filling with tape; Q2 — joints + feathering)
- Finishing only — NOT board/frame construction.

Market result:
- market_min: 34
- market_max: 46
- reference_price: —
- region: Kraków-regional + PL
- checked_at: 2026-09-14
- confidence: MEDIUM

Explicit Q-level evidence: **YES** — betonizm.pl literally labels "standard Q1 z taśmą" (12–18
zł/mb) and "standard Q2" (20–30 zł/m²); koszt-wykonczen.pl labels Q1 (≈15 zł/mb) and Q2 (18–20
zł/mb; Kraków 24 zł/mb / 30–35 zł/m²). Unit discipline: catalog GK_JOINT is M2, so per-m² quotes
anchor the range; per-mb quotes are recorded as LM-context, never converted to m².

Source counts:
- LOCAL_SOURCE_COUNT: 2 (cennikremontow Kraków table 34–46 zł/m²; ekipa-krakow 5 zł/m² — flagged
  uniform low outlier).
- REGIONAL_SOURCE_COUNT: 1 (koszt-wykonczen Kraków city row: Q2 24 zł/mb / 30–35 zł/m²).
- NATIONAL_SOURCE_COUNT: 2 (betonizm Q1/Q2 explicit; algrom standard 20–40 zł/m²).

Methodology: per-m² joint work on board area — the only local figure is the Kraków city table
"Szpachlowanie łączeń między płytami gipsowo-kartonowymi — 34–46 zł/m²" (labour-implied; the same
table includes tape work in this row). Two national sources give explicit Q-level per-m² prices
for joint work: betonizm Q2 "Szpachlowanie łączeń ze szlifowaniem (standard Q2) — 20,00–30,00
zł/m²" and algrom "Szpachlowanie standardowe — 20–40 zł/m²", with koszt-wykonczen placing Kraków
at the high end of its agglomeration set (30–35 zł/m² Q2). The local 34–46 band therefore aligns
with the Q2 national ceiling — consistent, but resting on one city table plus Q-labeled national
rows. ekipa-krakow's łączenia 5 zł/m² is flagged (uniform low outlier) and excluded. Reference:
none — the per-m² joint pricing model is not the one most sources use (most quote per mb of joint),
so no single central M2 value is defensible.

Comparable source count: 3 useful (cennikremontow Kraków; betonizm; algrom) + 1 regional city row
(koszt-wykonczen) + 1 flagged (ekipa) + 2 per-mb LM-context rows (betonizm Q1 12–18; koszt-wykonczen
Q1/Q2 15/18–20).

Sources:

1.
- Name: CennikRemontow.pl — Karton-gipsy Kraków (city price table)
- URL: https://cennikremontow.pl/karton-gipsy-krakow-cennik
- Type: CITY_PRICE_TABLE
- Region: Kraków (LOCAL table)
- Checked: 2026-09-14
- Quoted value: "Szpachlowanie łączeń między płytami gipsowo-kartonowymi — 34–46 zł/m²"
- Unit: M2
- Price scope: UNKNOWN (labour-implied)
- Included work: joint filling between GK boards incl. tape work (no separate tape row in the table)
- Excluded/unknown: materials; netto/brutto
- Comparability: comparable (per-m² board-surface pricing, Kraków).

2.
- Name: Betonizm.pl — Ile kosztuje szpachlowanie łączeń płyt g-k
- URL: https://betonizm.pl/ile-kosztuje-szpachlowanie-laczen-plyt-g-k-sprawdz-aktualny-cennik-i-porady-eksperta/
- Type: NATIONAL_PRICE_ARTICLE
- Region: PL (NATIONAL; notes Warszawa Q3 ≥40, smaller towns ~30)
- Checked: 2026-09-14
- Quoted value (EXPLICIT Q-LEVELS): "Szpachlowanie łączeń płyt g-k (standard Q1 z taśmą)
  12,00–18,00 zł/mb"; "Szpachlowanie łączeń ze szlifowaniem (standard Q2) 20,00–30,00 zł/m²";
  prose: "za samo zbrojenie łączeń taśmą i wypełnienie masą szpachlową zapłacisz średnio 12-18 zł
  za metr bieżący netto"
- Unit: LM (Q1) / M2 (Q2)
- Price scope: LABOR (netto; "samej robocizny")
- Included work: joint filling with tape (Q1); + sanding (Q2)
- Excluded/unknown: materials (8–15 zł/m² separate); VAT; per-mb and per-m² mixed in one article
- Comparability: explicit Q1/Q2 evidence. Only the M2 Q2 row anchors GK_JOINT; Q1 mb is LM-context.

3.
- Name: Algrom.pl — Ile za szpachlowanie łączeń płyt?
- URL: https://algrom.pl/ile-za-szpachlowanie-laczen-plyt/
- Type: NATIONAL_PRICE_ARTICLE
- Region: PL (NATIONAL; agglomeration rows 35–50 — "Warszawa i Kraków ceny mogą sięgać 35-50 zł/m²")
- Checked: 2026-09-14
- Quoted value: "Szpachlowanie standardowe — 20-40 zł/m²"; jednokrotne spoinowanie 10–15 zł/m²;
  dwukrotne 19–25 zł/m²
- Unit: M2
- Price scope: UNKNOWN (labour ~60–70% of total per article; materials 30–40%)
- Included work: standard joint skimming / single / double pass
- Excluded/unknown: materials (10–30 zł/kg masa); VAT
- Comparability: comparable (per-m² joint work; unlabeled Q-level).

4.
- Name: Koszt-wykonczen.pl — Ile kosztuje szpachlowanie płyt gipsowych
- URL: https://koszt-wykonczen.pl/ile-kosztuje-szpachlowanie-plyt-gipsowych
- Type: NATIONAL_PRICE_ARTICLE (city rows)
- Region: PL; Kraków row REGIONAL
- Checked: 2026-09-14
- Quoted value (EXPLICIT Q-LEVELS): "Q1 … okolice 15 zł/mb" (1 warstwa, brak szlifowania); "Q2 …
  do przedziału 18-20 zł" za mb (2 warstwy, szlifowanie 150-180); city table: "Kraków 24 zł/mb /
  30–35 zł/m²" (standard Q2); national avg "19 zł/mb, widełki 15-25"
- Unit: LM / M2
- Price scope: LABOR
- Included work: joint filling/taping per Q-level; sanding grade per level
- Excluded/unknown: materials ("materiały 1300-1500 zł per 250 mb" separate); VAT
- Comparability: explicit Q1/Q2 evidence; Kraków Q2 row = REGIONAL anchor (30–35 zł/m²).

5.
- Name: Ekipa Kraków — cennik (firma Kraków)
- URL: https://ekipa-krakow.pl/cennik-uslug-remontowo-budowlanych-krakow/
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków (LOCAL)
- Checked: 2026-09-14
- Quoted value: "Szpachlowanie łączeń płyt k.g. — 5,00 zł/m2"
- Unit: M2
- Price scope: LABOR
- Comparability: **flagged** — uniform low outlier (alongside gładź 15–18, painting 10); excluded.

Notes / exclusions:
- Per-mb quotes (betonizm Q1 12–18; koszt-wykonczen Q1 15 / Q2 18–20) are NOT merged into the M2
  range; they inform 9E.4 on the LM pricing model for a possible GK_JOINT_LM row.
- The catalog's GK_JOINT M2 unit is the binding reference; most real-life cenniki price joints per
  mb — this unit mismatch is the reason for MEDIUM despite decent evidence.

---

## CENNIK_GK_FULL-01 — Pełne szpachlowanie powierzchniowe (Q3)

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P1 (catalog hint: full-surface skim — Q3)

Market result:
- market_min: 28
- market_max: 45
- reference_price: 40
- region: Kraków + PL
- checked_at: 2026-09-14
- confidence: MEDIUM

Explicit Q-level evidence: **YES** — betonizm.pl "Pełne szpachlowanie powierzchniowe (standard Q3)
30,00–45,00 zł/m²" and koszt-wykonczen.pl "Q3 … 28-35 zł/m² całej ściany" (2–3 warstwy +
szpachlowanie całej płyty, gradacja 180–220). totaldecor (Kraków) prices full-surface gładź at
40 zł/m² without a Q-label — recorded as a local unlabeled corroborator inside the band.

Source counts:
- LOCAL_SOURCE_COUNT: 1 (totaldecor 40 zł/m² — unlabeled).
- REGIONAL_SOURCE_COUNT: 0.
- NATIONAL_SOURCE_COUNT: 2 (betonizm Q3 30–45; koszt-wykonczen Q3 28–35/m²) — both explicit Q3.

Methodology: market window rests on the two explicit-Q3 national sources (28–45 zł/m², labour,
Q3-definitional full-surface multi-layer skim with sanding grade 180–220); the sole Kraków firm
figure (totaldecor "Wykonanie gładzi gipsowych — 40 zł/m²", unlabeled, scope unstated) falls
inside the band and corroborates the Kraków-consistent ceiling but does not itself carry a Q-label.
reference_price 40 reflects the local firm value and the central Q3 cluster.

Comparable source count: 3 (2 explicit Q3 national + 1 local unlabeled).

Sources:

1.
- Name: Totaldecor Kraków — cennik (firma Kraków)
- URL: https://totaldecor.pl/cennik/
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków (LOCAL)
- Checked: 2026-09-14
- Quoted value: "Wykonanie gładzi gipsowych — 40 zł/m²" ("Podane ceny są jedynie orientacyjne")
- Unit: M2
- Price scope: UNKNOWN (materials not stated)
- Included work: full-surface gypsum skim
- Excluded/unknown: materials; VAT; sanding grade; Q-label absent
- Comparability: comparable work, local, but **unlabeled Q-level** and scope unstated.

2.
- Name: Betonizm.pl — szpachlowanie łączeń / pełne szpachlowanie
- URL: https://betonizm.pl/ile-kosztuje-szpachlowanie-laczen-plyt-g-k-sprawdz-aktualny-cennik-i-porady-eksperta/
- Type: NATIONAL_PRICE_ARTICLE
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value (EXPLICIT Q3): "Pełne szpachlowanie powierzchniowe (standard Q3) 30,00–45,00 zł/m²";
  prose: "w Warszawie koszt wykonania standardu Q3 rzadko spada poniżej 40 zł/m²" (mniejsze
  miejscowości "około 30 zł")
- Unit: M2
- Price scope: LABOR
- Included work: full-surface skim, Q3 standard
- Excluded/unknown: materials 8–15 zł/m² separate; VAT; netto
- Comparability: explicit Q3 evidence.

3.
- Name: Koszt-wykonczen.pl — szpachlowanie płyt gipsowych
- URL: https://koszt-wykonczen.pl/ile-kosztuje-szpachlowanie-plyt-gipsowych
- Type: NATIONAL_PRICE_ARTICLE
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value (EXPLICIT Q3): "Wykonawcy kwotują Q3 na poziomie 28-35 zł/m² całej ściany" (2-3
  warstwy + szpachlowanie całej płyty, gradacja 180-220; ekwiwalent ~22–25 zł/mb łączenia)
- Unit: M2
- Price scope: LABOR
- Included work: Q3 full-surface skim + joints
- Excluded/unknown: materials; VAT
- Comparability: explicit Q3 evidence.

Notes / exclusions:
- Marketing phrases like "idealnie gładkie" or "gotowe pod malowanie" in unlabeled sources are NOT
  treated as Q3; totaldecor 40 is included only as a numeric local corroborator of the Q3 band.

---

## CENNIK_GK_SCREW-01 — Zaszpachlowanie łbów wkrętów

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P3 (catalog flag: "do not duplicate — usually within joint work"; OWN_PRICE candidate)

Market result:
- market_min: —
- market_max: —
- reference_price: —
- region: —
- checked_at: 2026-09-14
- confidence: INSUFFICIENT

Source counts:
- LOCAL_SOURCE_COUNT: 0 (no standalone screw-head row).
- REGIONAL_SOURCE_COUNT: 0.
- NATIONAL_SOURCE_COUNT: 0 standalone.

Methodology: no checked source prices screw-head (wkręt / łby wkrętów) filling as a standalone
line. The Q1/Q2 sources (betonizm, koszt-wykonczen) describe joint work in the Q1–Q2 tiers without
itemising screw heads — screw-head filling is bundled into standard joint filling/Q1 per both
sources' Q-definitions. Per the catalog note, GK_SCREW is therefore **not a separate market row**;
it should be defined by the owner as part of the joint/board skim price book logic (OWN_PRICE
candidate) or folded into GK_JOINT/GK_FULL tiers. No numeric range is defensible.

Comparable source count: 0.

Sources: (no numeric source; bundling references — betonizm Q1/Q2 tiers, koszt-wykonczen Q1/Q2 —
are recorded under GK_JOINT.)

Notes / exclusions:
- Do not price screw heads twice (catalog "do not duplicate" note): if joint work is loaded at
  GK_JOINT, screw filling is included in the tier.

---

## CENNIK_GK_CORNER-01 — Obróbka narożników (za mb)

Canonical scope:
- Unit: LM
- Price scope: LABOR
- Priority: P2

Market result:
- market_min: 10
- market_max: 22
- reference_price: 18
- region: Kraków + PL
- checked_at: 2026-09-14
- confidence: MEDIUM

Source counts:
- LOCAL_SOURCE_COUNT: 3 (ekipa-krakow 10 zł/mb; s-szpachlowanie zewnętrzne 15–22; cennikremontow
  Kraków "Montaż narożników aluminiowych 22–30" — flagged unit mismatch, per-m² table cell).
- REGIONAL_SOURCE_COUNT: 0.
- NATIONAL_SOURCE_COUNT: 2 (betonizm 15–22 zł/mb metalowe perforowane / FAQ 25–40; koszt-wykonczen
  add-ons wewn. +2–4, zewn. +5–7 zł/mb) + daibau excluded (no verbatim table at check).

Methodology: corner-bead install is a linear-metre service. Local: ekipa-krakow "Montaż narożników
aluminiowych bez materiału — 10,00 zł/mb" (labour) and s-szpachlowanie Kraków "Obrobienie narożników
zewnętrznych — 15–22 zł/m²" (the Kraków skim firm's corner row; the site cell says zł/m² but the
row describes a per-corner metallic profile install comparable to the mb rows — flagged unit-wise,
used as LM with note). The cennikremontow Kraków cell "Montaż narożników aluminiowych — 22–30 zł/m²"
is recorded but is a per-m² table cell for a linear service — unit mismatch flagged, not merged.
National: betonizm main table "Montaż i szpachlowanie metalowych narożników perforowanych
15,00–22,00 zł/mb" and its FAQ "Montaż i wtapianie narożników ochronnych … 25-40 zł"; koszt-wykonczen
prices corners only as add-ons (wewnętrzne +2–4 zł/mb, zewnętrzne z profilem metalowym +5–7 zł/mb —
add-ons on łączenia, recorded as such). reference_price 18 = central value of the local+national
per-mb cluster (10 / 15–22 / 15–22).

Comparable source count: 3 local (1 flagged) + 2 national (1 direct, 1 add-on) + 1 unit-mismatch.

Sources:

1.
- Name: Ekipa Kraków — cennik (firma Kraków)
- URL: https://ekipa-krakow.pl/cennik-uslug-remontowo-budowlanych-krakow/
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków (LOCAL)
- Checked: 2026-09-14
- Quoted value: "Montaż narożników aluminiowych bez materiału — 10,00 zł/mb"
- Unit: LM
- Price scope: LABOR
- Included work: aluminium corner-bead mounting
- Excluded/unknown: material (narożnik); VAT; flagged firm-wide low-outlier
- Comparability: comparable (LM, labour); excluded from range ceiling weighting.

2.
- Name: S-szpachlowanie.pl — szpachlowanie Kraków cennik
- URL: https://s-szpachlowanie.pl/szpachlowanie-krakow-cennik
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków (LOCAL)
- Checked: 2026-09-14
- Quoted value: "Obrobienie narożników zewnętrznych — 15–22 zł/m²" ("Narożnik aluminiowy 3 m —
  8–14 zł" as material row)
- Unit: LM (site cell: zł/m²; row represents per-corner metallic profile work — LM-equivalent
  install; flagged)
- Price scope: LABOR
- Included work: external corner-bead fabrication/install
- Excluded/unknown: material (narożnik priced separately 8–14 zł/3 m); VAT
- Comparability: comparable as LM install with unit disclosure.

3.
- Name: CennikRemontow.pl — Karton-gipsy Kraków (city price table)
- URL: https://cennikremontow.pl/karton-gipsy-krakow-cennik
- Type: CITY_PRICE_TABLE
- Region: Kraków (LOCAL table)
- Checked: 2026-09-14
- Quoted value: "Montaż narożników aluminiowych — 22–30 zł/m²"
- Unit: M2 (table cell) — **unit mismatch flagged** for a linear corner service
- Price scope: UNKNOWN
- Comparability: recorded for traceability only; not merged into the LM band.

4.
- Name: Betonizm.pl — szpachlowanie łączeń płyt g-k
- URL: https://betonizm.pl/ile-kosztuje-szpachlowanie-laczen-plyt-g-k-sprawdz-aktualny-cennik-i-porady-eksperta/
- Type: NATIONAL_PRICE_ARTICLE
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Montaż i szpachlowanie metalowych narożników perforowanych 15,00–22,00 zł/mb";
  FAQ "Montaż i wtapianie narożników ochronnych (aluminiowych, PCV lub taśm typu tuff-tape) …
  rzędu 25-40 zł"
- Unit: LM
- Price scope: LABOR (netto; materials separate)
- Comparability: comparable (direct per-mb rows).

5.
- Name: Koszt-wykonczen.pl — szpachlowanie płyt gipsowych
- URL: https://koszt-wykonczen.pl/ile-kosztuje-szpachlowanie-plyt-gipsowych
- Type: NATIONAL_PRICE_ARTICLE
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value: "Wykonawcy zwykle doliczają za narożniki wewnętrzne 2-4 zł/mb dodatkowo"; "za
  narożniki zewnętrzne z użyciem profilu metalowego nawet 5-7 zł/mb"
- Unit: LM
- Price scope: LABOR (add-on on łączenia)
- Comparability: add-on only — corners are quoted as surcharges on joint work here; recorded as
  the alternate pricing structure.

Notes / exclusions:
- Kraków city cell (22–30 zł/m²) uses an inconsistent unit for a linear service — 9E.4 decision
  point.
- Corner material (narożnik 8–14 zł/3 m, betonizm taśma narożnikowa 18–26 zł/mb) is MATERIAL, not
  LABOR — excluded from the LABOR catalogue row.

---

## CENNIK_GK_Q4-01 — Szpachlowanie Q4 (całopowierzchniowe ≥1 mm)

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P2 (catalog: count only if source describes ≥1 mm skim or strip-light readiness)

Market result:
- market_min: 40
- market_max: 80
- reference_price: —
- region: PL
- checked_at: 2026-09-14
- confidence: MEDIUM

Explicit Q-level evidence: **YES** — 2 sources literally label Q4 with an unambiguous Polish
technical definition: betonizm.pl "Całopowierzchniowe szpachlowanie Q4 (pod malowanie mat/połysk)
60,00–80,00 zł/m²" + prose "całopowierzchniowe szpachlowanie na gładko o grubości powyżej 1 mm";
koszt-wykonczen.pl "Q4 … cała ściana wyceniana jest na 40-55 zł/m²" (3–4 warstwy + pełne
szpachlowanie, gradacja 220–240; per mb 25–35 zł).

Source counts:
- LOCAL_SOURCE_COUNT: 0 labelled Q4 (s-szpachlowanie Kraków publishes no Q4/strip-light-labelled
  per-m² figure in its checked price list).
- REGIONAL_SOURCE_COUNT: 0.
- NATIONAL_SOURCE_COUNT: 2 explicit Q4 (betonizm; koszt-wykonczen).

Methodology: the range rests exclusively on the two explicit-Q4 sources, both of which define Q4
by full-surface skim ≥1 mm / multi-layer full-board completion. betonizm main table
(60–80 zł/m²) marks the top; koszt-wykonczen (40–55 zł/m²) marks the bottom. **betonizm's own
chart lists "Pełny finisz Q4 — 110 zł/m²"**, contradicting its main table — flagged below and to
9E.4; the range uses the main-table figure. The wide 40–80 gap is the two publications' pricing
model spread (detail-heavy vs all-in finish), disclosed rather than averaged; no reference_price
is set. No Kraków source publishes a Q4-labelled row (catalog §12 note holds: Q1–Q4 levels are not
generally published by Kraków contractors).

Comparable source count: 2 explicit-Q4 national pages (1 of them internally inconsistent).

Sources:

1.
- Name: Betonizm.pl — szpachlowanie łączeń / pełne szpachlowanie
- URL: https://betonizm.pl/ile-kosztuje-szpachlowanie-laczen-plyt-g-k-sprawdz-aktualny-cennik-i-porady-eksperta/
- Type: NATIONAL_PRICE_ARTICLE
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value (EXPLICIT Q4): "Całopowierzchniowe szpachlowanie Q4 (pod malowanie mat/połysk)
  60,00–80,00 zł/m²"; prose "całopowierzchniowe szpachlowanie na gładko o grubości powyżej 1 mm"
  → "podnosi cenę robocizny do poziomu 60-80 zł/m²"; **chart conflicts: "Pełny finisz Q4 —
  110 zł/m²"**
- Unit: M2
- Price scope: LABOR
- Included work: full-surface skim ≥1 mm, mat/gloss-paint ready
- Excluded/unknown: materials (8–15 zł/m² separate); VAT; chart-vs-table discrepancy flagged
- Comparability: explicit Q4 evidence; upper edge + internal-inconsistency alert.

2.
- Name: Koszt-wykonczen.pl — szpachlowanie płyt gipsowych
- URL: https://koszt-wykonczen.pl/ile-kosztuje-szpachlowanie-plyt-gipsowych
- Type: NATIONAL_PRICE_ARTICLE
- Region: PL (NATIONAL)
- Checked: 2026-09-14
- Quoted value (EXPLICIT Q4): "Cena za metr bieżący łączenia przekracza 25 zł i sięga nawet 30-35
  zł, a cała ściana wyceniana jest na 40-55 zł/m²"; Q4 = "3-4 warstwy + pełne szpachlowanie,
  gradacja 220-240"
- Unit: M2 (per m² wall) / LM (per mb joint)
- Price scope: LABOR
- Included work: Q4 full-surface multi-layer skim
- Excluded/unknown: materials (1300–1500 zł per 250 mb); VAT
- Comparability: explicit Q4 evidence; lower edge + LM-equivalent context.

Notes / exclusions:
- Marketing-only descriptions ("pod światło", "idealnie gładkie") without Q4/≥1 mm/grade 220–240
  definitions were excluded from evidence (catalog §12 and 9E.3B rule).
- betonizm Q4 table-vs-chart conflict (60–80 vs 110) is a 9E.4 verification point.

---

## 17. Potential OWN_PRICE candidates (Batch B)

Items where 9E.4/9E.5 should consider an **owner-defined** price (with an OWN_PRICE source in the
9E.1 model) instead of importing a market range. No final owner price is assigned here.

| Code | Reason |
|---|---|
| CENNIK_PAINT_MASK-01 | Ambiguous package scope (simple foil 5–9 vs comprehensive room protection 18,70/20,20); masking is normally bundled or flat-rated by contractors. LOW confidence. |
| CENNIK_PAINT_MULTI-01 | **INSUFFICIENT** — no source prices 2+ colors / cut-ins per m²; the market structures it as surcharges (dark +8–15 zł/m²; "kolor" +5–15%; tesa cut-ins "usługi dodatkowo płatne"). Owner should define a per-colour surcharge policy. |
| CENNIK_GF_FLIZ_L-01 | **No technology-A (flizelina malarska) labour price exists in the checked market.** Only tech-B glass-fibre wallpaper analog (48,82–77 brutto; Kraków 64,30) is published. |
| CENNIK_GF_FLIZ_M-01 | **No technology-A L+M price exists.** Only tech-B L+M analog (110–190 zł/m²) is published. |
| CENNIK_GK_SCREW-01 | **INSUFFICIENT** — screw-head filling is never itemised; it is bundled into Q1/Q2 joint tiers (catalog "do not duplicate" note). |

(Catalog Batch B already flagged PAINT_MASK, PAINT_MULTI, GK_SCREW; GF_FLIZ_L/M are added on the
strength of the technology-A evidence gap.)

---

## 18. Source archival note

- Each source above is recorded as **URL + checked_at + relevant quoted value/scope + a short
  evidence note** — no full-page content is copied (respecting the 9E.1 archival contract).
- **Dynamic-page caution:** `malarzkrakow.pl/cennik/`, `kubamalarz.pl/cennik/`,
  `totaldecor.pl/cennik/`, `ekipa-krakow.pl/…`, `s-szpachlowanie.pl/szpachlowanie-krakow-cennik`,
  `cennikremontow.pl/*` (Kraków pages) and the kb.pl price tables are live price lists / regularly
  updated cost pages. They must be **re-checked during 9E.4 before any data load**; figures herein
  are valid as of 2026-09-14.
- **Content-network duplication (flagged):** kb.pl tapetowanie table `48,82–77,00 / średnia 59,66`
  is republished verbatim by aikfarby.pl (`klejenie-tapety-z-wlokna-szklanego-cena`) — including the
  same national average 59,66. They are counted as **one** content point (kb.network), even though
  each adds a slightly different Kraków city breakdown (kb.pl Kraków row 64,30 brutto vs aikfarby
  Kraków 65,40–74,30 / śr. 69,80). A third site (tapetysztukaterie.pl) mirrors the same article
  and is excluded. Batch A's sccot↔itodesign network note is carried forward (Batch B used neither
  for numerics). Do not count these as independent sources in any later tally.
- **Checked but unusable / excluded (traceability):**
  - hejmalarz.pl (`uslugi-malarskie-cennik/`) — Kraków painter; page carries **no published
    prices** ("ceny … ustalane indywidualnie"); qualitative local signal only.
  - sccot.pl (`cennik-uslug-malarskich/`) — editorial 2025 guide; regional-premium context only;
    its numeric table was not reliably retrievable at the 2026-09-14 fetch, so no sccot figures
    are quoted in Batch B (a change from the Batch-A approach, where sccot was numeric).
  - daibau.pl (`ceny/malowanie_scian_malarz`) — professional-services marketplace; page content did
    not yield a verbatim price table at checked_at — excluded from numerics.
  - koszt-remonty.pl (`ile-kosztuje-polozenie-tapety-flizelinowej`) — internally inconsistent
    (labour 2–4 zł/m² vs full-service 45–69 zł/m² in one article) — excluded.
  - kolormajster.pl — HTTP 406 at fetch; excluded.
  - e-gladz.pl (`cena-za-m2-gladzi-robocizna`) — gładź cross-reference page (used already in
    Batch A); not load-bearing for Batch B items.
  - wowporadnik.pl Kraków guide and defi-home.pl / xck.pl GK-joint articles — HTTP 403/403 at
    fetch; the underlying data appear on reachable sources (cennikremontow / algrom / betonizm /
    koszt-wykonczen), which were used instead.
- **Netto/brutto discipline:** kb.pl city rows quote both columns (netto/brutto); cennikibudowlane
  is netto; t-tapety is explicitly netto (VAT 8%/23% stated); zleca.pl is listed brutto; most
  contractor cenniki do not state VAT. Ranges were built per scope class; mixing is disclosed per
  item (PAINT_3K mixes only netto rows; zleca brutto is cross-check-only).
- **Outside-region supplementary:** none of the checked national sources were masqueraded as
  Kraków sources; Kraków rows inside national pages (kb Kraków city table, aikfarby Kraków
  breakdown, koszt-wykonczen Kraków city row, cennikremontow Kraków tables) are the only
  regional-tier evidence.

---

## 19. Cross-check (9E.3B §19)

- **Traceability:** every number in §16 maps to at least one verbatim quote in the Sources of its
  item; no figure is invented and no catalog gap is filled with a guessed price.
- **URL duplication / independence:** kb.network (kb.pl ↔ aikfarby ↔ tapetysztukaterie) flagged
  per §18 and counted once; sccot/itodesign not used numerically; cennikremontow Kraków pages and
  its national pages are one publisher but different city tables (counted per city table).
- **No LABOR / L+M mixing:** each numeric range is built from one scope class. L+M rows
  (kubamalarz 25–27 ambiguous; m-malowanie priming-inclusive; ekipa 13 with material;
  aikfarby 110–190 tech-B L+M; kb.network materials 43–110) are recorded separately and never
  merged into LABOR ranges.
- **Units:** M2 vs LM kept compatible per row; **never** mixed. Per-mb joint prices
  (betonizm Q1 12–18, koszt-wykonczen Q1 15 / Q2 18–20, koszt-wykonczen Q4 25–35) are LM-context
  only. PCS (m-malowanie maskowanie 5–12 zł/szt) and FLAT (t-tapety 500 zł netto kompleksowa)
  are recorded as their own pricing structures; no FLAT↔M2 / PCS↔M2 conversion anywhere.
- **No Q/S inference:** explicit Q-labels are used only where sources literally state them
  (betonizm, koszt-wykonczen). totaldecor (40 zł/m² GK_FULL) is carried as an unlabeled local
  corroborator with the Q-flag OFF. No Q-value is manufactured from marketing text.
- **Fleece technology separation:** GF_FLIZ_L/M ranges are left empty (tech-A evidence gap); the
  tech-B analog (48,82–77 brutto, Kraków row 64,30; t-tapety 50–80 netto) and tech-B L+M
  (110–190) are logged only in the supplementary column with explicit classification A/B/C per
  source. No mixed-technology band is presented.
- **Nationwide sources:** every `Region: PL` source is disclosed per item; none silently become
  Kraków sources; Kraków rows inside national pages are the only regional-tier evidence.
- **No invented prices:** PAINT_MULTI, GK_SCREW, GF_FLIZ_L, GF_FLIZ_M stay INSUFFICIENT / LOW
  without a numeric market range rather than receiving an invented figure.
- **Catalog integrity:** all 15 codes (CENNIK_PAINT_* / CENNIK_GF_* / CENNIK_GK_*) are taken
  verbatim from `docs/price-research-catalog.md` (Batch B); PL labels match the catalog.

---

## 20. Research summary (for `docs/development-progress.md`)

- Items researched: **15 / 15** Batch B catalog items (Painting 7 · Glass fiber/fleece 3 · Gypsum
  board finishing 5).
- Sources: **20 numeric evidence pages referenced** + 2 contextual pages, of which **8 are
  Kraków / regional anchors** (5 Kraków firms — malarzkrakow, kubamalarz, totaldecor, ekipa-krakow,
  s-szpachlowanie — and 3 Kraków city- / regional-tables — cennikremontow ×2, kb.pl Kraków) and
  **12 are Poland-wide**, incl. Kraków city rows inside national pages (kb.network, koszt-wykonczen,
  cennikremontow) and 1 Małopolskie city row on a national portal (cenauslug, Nowy Sącz).
- Confidence distribution: **HIGH 1** (PAINT_2K) · **MEDIUM 9** (PAINT_1K, PAINT_3K, PAINT_CEIL,
  PAINT_COL, GF_MESH, GK_JOINT, GK_FULL, GK_CORNER, GK_Q4) · **LOW 3** (PAINT_MASK, GF_FLIZ_L,
  GF_FLIZ_M) · **INSUFFICIENT 2** (PAINT_MULTI, GK_SCREW).
- OWN_PRICE candidates: **5** (PAINT_MASK, PAINT_MULTI, GF_FLIZ_L, GF_FLIZ_M, GK_SCREW).
- Explicit Q-level sources: **betonizm.pl** (Q1/Q2/Q3/Q4) and **koszt-wykonczen.pl** (Q1–Q4);
  Q1/Q2/Q3/Q4 all found in at least one source each; GK_FULL (Q3) additionally corroborated by a
  local unlabeled firm row (totaldecor 40).
- Normalization review notes for 9E.4: see §21.

---

## 21. NORMALIZATION_REVIEW_NOTE (Batch A ↔ Batch B, for 9E.4)

Batch A numbers are **not changed** here. The following inconsistencies are flagged for the 9E.4
normalization review:

1. **SKIM_PKG-01 vs SKIM_1L-01 / SKIM_2L-01 — differing package scopes.**
   - SKIM_1L-01: 30–50 (single skim layer, LABOR).
   - SKIM_2L-01: 35–75 (double skim layer, LABOR).
   - SKIM_PKG-01: 35–70 (package: 2× + sanding, LABOR).
   The observed windows overlap so heavily that the "package" band (35–70) is dominated by
   component rows rather than by a real package discount: the Kraków component equivalent per the
   same evidence family (SKIM_2L 55–75 + szlifowanie 10–16 ≈ **65–91**) **exceeds** the package
   band (35–70), which strongly indicates that published "package" prices are
   volume-discounted or component-limited (e.g. without full-surface sanding, without dedusting,
   or L+M in some rows). 9E.4 must decide whether SKIM_PKG keeps an independent seed row and at
   what internal consistency vs SKIM_1L/SKIM_2L/SKIM_SAND.

2. **Painting coat-count differentiation (Batch B ↔ Batch A).** Market prices are quoted **per
   coat set** (1-coat from 8, 2-coat 10–30, 3-coat 21,80–48). 9E.4 should verify that seed
   `PAINT_2K` default is exactly "2 coats on prepared substrate, labour, per m²" and that no
   PRIM_PAINT / SKIM row double-counts into it; the cennikremontow Kraków 1-coat row
   (white 16–30 vs its own 2-coat 10–28) must be re-verified.

3. **betonizm.pl Q4 internal inconsistency (Batch B).** Main table "Całopowierzchniowe
   szpachlowanie Q4 … 60–80 zł/m²" vs the same article's chart "Pełny finisz Q4 — 110 zł/m²".
   9E.4 re-check before Q4 seeds; the evidence file uses the main-table figure.

4. **GK_JOINT unit model.** Real cenniki price joints per **mb**, while catalog GK_JOINT is **M2**;
   cennikremontow Kraków (34–46/m² boards) is the only local M2 row. 9E.4 should confirm the unit
   and, if LM is preferred, re-run the mb evidence (betonizm Q1 12–18; koszt-wykonczen Q1 15 /
   Q2 18–20; Kraków Q2 24/mb).

5. **Kraków city "Montaż narożników" unit mismatch (19.3GK_CORNER).** Cennikremontow Kraków cell
   "22–30 zł/m²" for a linear corner service — flagged, not merged; confirm unit at 9E.4.

---

## PAINT_2K-01 veracity footnote

This annotation is part of the same file; see methodology in the PAINT_2K section (reference 18 =
central commonly-observed value of the clean 2-coat LABOR cluster; ekipa-krakow excluded from
anchoring as a flagged uniform low outlier).