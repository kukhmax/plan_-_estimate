# Kraków / Małopolskie — Price Research — Batch A (Stage 9E.3A)

> Canonical Stage 9, execution sub-stage **9E.3A**. Input contract: `docs/price-research-catalog.md`
> (9E.2). Output contract: 9E.1 market reference & sources architecture.
> **This file is research evidence ONLY.** It contains no seed decisions, no `PriceItem.price`
> values, and no implementation-ready market ranges for the app. All prices below are **verbatim
> quotes from the listed sources**, recorded with `checked_at`. Aggregated `market_min/market_max`
> are the defensible observed window for that scope; `reference_price` is used only where a central
> commonly-observed value exists and the methodology is stated (never a fake arithmetic average).

Research date (all source records): **2026-09-13**.
Re-verification: the three load-bearing local anchors — `s-szpachlowanie.pl` (Kraków skim table),
`malarzkrakow.pl` (Kraków painting price list) and `kb.pl` (gruntowanie city table) — were re-opened
and their quoted values re-confirmed on **2026-09-14**.

Geographic priorities (9E.3A §2): Kraków → Kraków + Małopolskie → Małopolskie → PL-supplementary.
Nationwide sources are marked `Region: PL` and used only as supplementary evidence; they are never
merged into a local range without being disclosed per item.

---

## 16. Summary table

| Code | PL name | Unit | Scope | Market min | Market max | Reference | Confidence | Comparable sources | Region | Checked |
|---|---|---|---|---|---|---|---|---|---|---|
| CENNIK_PREP_PROT-01 | Zabezpieczenie podłóg i powierzchni (folia, taśma) | M2 | LABOR | 5 | 15 | — | MEDIUM | 4 (2 partially comparable) | Kraków + PL | 2026-09-13 |
| CENNIK_PREP_WALLP-01 | Usuwanie tapet | M2 | LABOR | 10 | 30 | 20 | HIGH | 4 | Kraków (floor) + PL | 2026-09-13 |
| CENNIK_PREP_SCRAPE-01 | Zdzieranie starych powłok / starej gładzi | M2 | LABOR | 10 | 35 | 18 | HIGH | 4 + 1 supplementary | Kraków + PL | 2026-09-13 |
| CENNIK_PREP_FLEECE-01 | Zdzieranie flizeliny / włókniny szklanej | M2 | LABOR | 35 | 64 | — | LOW | 1 (proxy tier) | PL | 2026-09-13 |
| CENNIK_PREP_DEGR-01 | Odtłuszczanie podłoża | M2 | LABOR | 10 | 15 | — | LOW | 1 | PL | 2026-09-13 |
| CENNIK_PREP_MOLD-01 | Usuwanie pleśni i grzyba (z preparatem) | M2 | LABOR_AND_MATERIAL | 30 | 120 | — | MEDIUM | 4 + 1 supplementary | PL | 2026-09-13 |
| CENNIK_PREP_CLEAN-01 | Odkurzanie / czyszczenie podłoża po szlifowaniu | M2 | LABOR | — | — | — | INSUFFICIENT | 0 usable | — | 2026-09-13 |
| CENNIK_PRIM_STD-01 | Grunt penetrujący (pod szpachlowanie) | M2 | LABOR_AND_MATERIAL | 7 | 15 | — | MEDIUM | 6 rows / 2 L+M-computable | Kraków + PL | 2026-09-13 |
| CENNIK_PRIM_ADH-01 | Grunt kontaktowy adhezyjny | M2 | LABOR_AND_MATERIAL | — | — | — | LOW | 1 (component evidence) | PL | 2026-09-13 |
| CENNIK_PRIM_HIGH-01 | Gruntowanie dwukrotne (wysokochłonne) | M2 | LABOR_AND_MATERIAL | — | — | — | LOW | 1 (+1 qualitative) | PL | 2026-09-13 |
| CENNIK_PRIM_PAINT-01 | Gruntowanie przed malowaniem | M2 | LABOR_AND_MATERIAL | 3 | 15 | — | MEDIUM | 6 rows / 2 L+M-explicit | Kraków + PL | 2026-09-13 |
| CENNIK_SKIM_1L-01 | Gładź szpachlowa — 1 warstwa | M2 | LABOR | 30 | 50 | 40 | HIGH | 4 | Kraków anchor + PL | 2026-09-13 |
| CENNIK_SKIM_2L-01 | Gładź szpachlowa — 2 warstwy | M2 | LABOR | 35 | 75 | 55 | HIGH | 4 | Kraków anchor + PL | 2026-09-13 |
| CENNIK_SKIM_3L-01 | Gładź szpachlowa — 3 warstwy | M2 | LABOR | 60 | 80 | — | MEDIUM | 2 (1 suspected dup.) + 2 partial | PL | 2026-09-13 |
| CENNIK_SKIM_SAND-01 | Szlifowanie gładzi z odpylaniem | M2 | LABOR | 10 | 25 | 14 | HIGH | 4 | Kraków + PL | 2026-09-13 |
| CENNIK_SKIM_PKG-01 | Pakiet gładź 2x + szlifowanie | M2 | LABOR | 35 | 70 | 50 | MEDIUM | 4 | PL (+ Kraków L+M suppl.) | 2026-09-13 |
| CENNIK_SKIM_CRACK-01 | Naprawa rys i pęknięć (za mb) | LM | LABOR | 62 | 95 | — | LOW | 2 direct + 2 non-comparable | PL | 2026-09-13 |
| CENNIK_SKIM_CORNER-01 | Montaż narożników (za mb) | LM | LABOR | 12 | 22 | 16 | HIGH | 3 | Kraków + PL | 2026-09-13 |
| CENNIK_SKIM_LOCAL-01 | Szpachlowanie lokalne / punktowe | M2 | LABOR | 9 | 50 | — | MEDIUM | 4 rows / 3 orgs | Kraków + PL | 2026-09-13 |
| CENNIK_SKIM_SQ-01 | Gładź pod światło smugowe (S3/S4) | M2 | LABOR | 60 | 80 | — | LOW | 3 priced partial + 1 qualitative | PL (+ Kraków mention) | 2026-09-13 |

No implementation-ready seed decision yet — this is research evidence only (9E.3A §16).

---

## CENNIK_PREP_PROT-01 — Zabezpieczenie podłóg i powierzchni (folia, taśma, osłony stolarki)

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P2

Market result:
- market_min: 5
- market_max: 15
- reference_price: — (evidence is floor/bundled-based; explicit standalone rates rare)
- region: Kraków + PL
- checked_at: 2026-09-13
- confidence: MEDIUM

Methodology: comparable LABOR quotes for foil+tape protection of floors/surfaces per m² protected
area. Kraków floor from a Kraków firm's cennik (`od 5 zł/m²` net); the upper edge (15) comes from a
Poland-wide contractor price list ("około 5–15 zł/m²") and a flat estimate ("5–10 zł/m² of floor
area"). The daart Kraków row (15–19 zł/m²) is **partially comparable** — broader scope (protection of
a furnished room) — and is therefore logged, not folded into the range ceiling.

Comparable source count: 4 pages (2 fully comparable, 2 partially comparable).

Sources:

1.
- Name: Malarz Kraków — cennik (firma Kraków)
- URL: https://malarzkrakow.pl/cennik/
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków
- Checked: 2026-09-13 (re-confirmed 2026-09-14)
- Quoted value: "Zabezpieczenie powierzchni (foliowanie mebli, podłóg, okien) — od 5 zł/m²"
- Unit: M2
- Price scope: LABOR
- Included work: foil protection of floors / furniture / windows
- Excluded/unknown: materials; VAT (cennik is net, "za samą robociznę"); orientacyjny, not a binding offer
- Comparability: comparable — same work, Kraków firm, labor-only.

2.
- Name: WZBudowa — cennik usług malarskich 2026
- URL: https://wzbudowa.pl/cennik-uslug-malarskich/
- Type: CONTRACTOR_PRICE_LIST
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Zabezpieczenie folią i taśmą — około 5–15 zł/m² powierzchni zabezpieczanej"
- Unit: M2
- Price scope: LABOR
- Included work: foil + tape application
- Excluded/unknown: materials "may be billed separately"; VAT unknown
- Comparability: comparable — same service.

3.
- Name: Daart — zabezpieczenie przed malowaniem (per-city rate table)
- URL: https://daart.pl/zabezpieczenie-przed-malowaniem-cena
- Type: INDUSTRY_ARTICLE
- Region: PL (Kraków city rate row)
- Checked: 2026-09-13
- Quoted value: "Kraków 15–19 zł/m²"
- Unit: M2
- Price scope: LABOR
- Included work: protection of a furnished room incl. floor (labor only)
- Excluded/unknown: foils/tapes (materiały: folia PE 0,30–0,80 zł/m², HDPE 1,20–5 zł/m², taśma 8–18 zł/rolkę); VAT unknown
- Comparability: partially comparable — broader scope (furnished flat with furniture present) than pure floor foil+tape.

4.
- Name: New Bridge — gruntowanie cena za m²
- URL: https://newbridge.com.pl/gruntowanie-cena-za-m2/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Koszt zabezpieczenia pomieszczenia folią szacuje się na 5–10 zł/m² powierzchni podłogi"
- Unit: M2
- Price scope: unspecified
- Included work: room floor protection with foil
- Excluded/unknown: labor/material split; VAT unknown
- Comparability: partially comparable — flat estimate, scope not split.

Notes / exclusions: stand-alone floor protection is usually bundled by contractors into the overall
quote (catalog §13 flags this row as an OWN_PRICE candidate). The 5 zł/m² "od" value is a floor
rate, not a modal rate; the 15–19 Kraków row is a broader scope and excluded from the main range.

---

## CENNIK_PREP_WALLP-01 — Usuwanie tapet (zdzieranie, utylizacja)

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P1

Market result:
- market_min: 10
- market_max: 30
- reference_price: 20 — methodology: central commonly-observed band for standard single-layer
  removal incl. leaving substrate ready (cenauslug 16–24, kb normal 18–22, vinyl tier 20–30); the
  Kraków floor ("od 10") is a floor, excluded from the central band.
- region: Kraków (floor) + PL
- checked_at: 2026-09-13
- confidence: HIGH

Methodology: LABOR per m², "removal incl. leaving the substrate ready", single (normal) layer as
the comparable baseline. Kraków floor from a local firm; three nationwide portals/portals agree in
the 16–30 band. The t-tapety multi-layer / fiberglass tiers (35–64 zł/m²) belong to thicker
coverings and are mapped to PREP_FLEECE, not this row. Scraping away leftover glue is treated as
included where the source says so.

Comparable source count: 4 independent pages.

Sources:

1.
- Name: Malarz Kraków — cennik (firma Kraków)
- URL: https://malarzkrakow.pl/cennik/
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków
- Checked: 2026-09-13 (re-confirmed 2026-09-14)
- Quoted value: "Zrywanie tapet (jedna warstwa) — od 10 zł/m²"
- Unit: M2
- Price scope: LABOR
- Included work: stripping wallpaper, 1 layer, net rate
- Excluded/unknown: multi-layer, materials, VAT
- Comparability: comparable — direct match, Kraków floor.

2.
- Name: KB.pl — cennik zrywania tapet
- URL: https://kb.pl/cenniki/uslugi/cennik-zrywania-tapet-ze-scian-w-czasie-remontu/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Zrywanie tapet — normalny stopień: 18,00–22,00 zł/m2; wyższy stopień: 22,00–38,00 zł/m2"
- Unit: M2
- Price scope: LABOR
- Included work: stripping + scraping adhesive (average labor)
- Excluded/unknown: prep chemicals; price includes 8% VAT for individual clients (gross)
- Comparability: comparable.

3.
- Name: cenauslug.pl — usuwanie starych tapet
- URL: https://cenauslug.pl/budowa-i-remont/usuwanie-starych-tapet
- Type: MARKETPLACE
- Region: PL (no Kraków row published for this city on checked date)
- Checked: 2026-09-13
- Quoted value: "16–24 zł/m² (średnio 19 zł/m2); min 16, max 24"
- Unit: M2
- Price scope: LABOR
- Included work: vertical-surface stripping + scraping adhesive
- Excluded/unknown: materials ("Cena nie zawiera materiałów"); VAT unknown
- Comparability: comparable.

4.
- Name: T-Tapety — zdzieranie tapety cena
- URL: https://t-tapety.pl/zdzieranie-tapety-cena
- Type: INDUSTRY_ARTICLE
- Region: PL (notes "duże miasta, w tym Kraków 35–64 zł/m²" for heavy coverings)
- Checked: 2026-09-13
- Quoted value: "papierowa luźna 10–15; winylowa 20–30; fiberglassowa/wielowarstwowa 35–50; silny klej 50–64 zł/m²"
- Unit: M2
- Price scope: LABOR
- Included work: stripping only ("cennik skupia się głównie na robociźnie")
- Excluded/unknown: chemicals (+2–5 zł/m²), furniture moving; VAT inconsistent on page
- Comparability: comparable-to-partial — the 35–64 band is for multi-layer/fiber coverings (→ PREP_FLEECE), not the standard single-layer scope of this row.

Notes / exclusions: Warsaw-firm Derty Serwis charges "usuwanie tapety 30 zł/m2 netto" — outside the
target region, referenced as context only, not merged into the range.

---

## CENNIK_PREP_SCRAPE-01 — Zdzieranie starych powłok malarskich / starej gładzi kredowej

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P1

Market result:
- market_min: 10
- market_max: 35
- reference_price: 18 — methodology: central commonly-observed band for manual (non-olejowa)
  scraping to substrate (kb.pl 12–17, mocnyfundament 10–25, Kraków floor od 10); upper bound 35 from
  aikfarby manual band 22–35. Excluded: oil paint ("lamperia") and mechanical/chemical removal tiers.
- region: Kraków + PL
- checked_at: 2026-09-13
- confidence: HIGH

Methodology: comparable scope = scraping old paint / old chalk skim coat down to substrate, per m²,
labor. Sources that split by paint type are kept: the oil-paint (20–40) and chemical-mechanical
(20–45 / 38–55) tiers are **not** part of this row (catalog §3 excludes "oil-paint lamperia needing
degrease+sanding" from comparability).

Comparable source count: 4 independent pages + 1 supplementary outside-region.

Sources:

1.
- Name: Malarz Kraków — cennik (firma Kraków)
- URL: https://malarzkrakow.pl/cennik/
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków
- Checked: 2026-09-13 (re-confirmed 2026-09-14)
- Quoted value: "Skrobanie starych powłok malarskich — od 10 zł/m²"
- Unit: M2
- Price scope: LABOR
- Included work: scraping old paints, net rate
- Excluded/unknown: materials; VAT
- Comparability: comparable — direct match, Kraków floor.

2.
- Name: KB.pl — cena gruntowania (table: usuwanie starych powłok)
- URL: https://kb.pl/cenniki/uslugi/cena-gruntowania-scian-i-sufitu-przed-malowaniem-za-m2/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Usuwanie starych powłok malarskich: 12,00–17,00 zł/m2"
- Unit: M2
- Price scope: LABOR
- Included work: removing old paint coats (gross incl. 8% VAT)
- Excluded/unknown: materials
- Comparability: comparable.

3.
- Name: Mocny Fundament — przygotowanie ścian do malowania
- URL: https://mocnyfundament.pl/ile-kosztuje-przygotowanie-scian-i-sufitu-do-malowania-gladzie-gruntowanie-usuwanie-starych-powlok/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Skrobanie farby (emulsyjna, akrylowa) 10–25 zł/m²; Skrobanie farby olejnej 20–40; Chemiczne usuwanie farby 20–45; Kompleksowe usuwanie (ze szpachlą) 25–60"
- Unit: M2
- Price scope: LABOR
- Included work: labor, net-table
- Excluded/unknown: chemicals (chem. removal quoted without the prep cost); VAT (+8% per article)
- Comparability: comparable (emulsion/acrylic tier); oil/chemical tiers recorded for contrast.

4.
- Name: Aikfarby — zdzieranie starej farby cennik
- URL: https://aikfarby.pl/zdzieranie-starej-farby-cennik
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "zdzieranie ręczne 22–35 zł/m²; mechaniczne 38–55 zł/m²; same środki chemiczne 8–14 zł/m²"
- Unit: M2
- Price scope: LABOR (materials listed separately)
- Included work: stripping old paint layers by hand / by machine
- Excluded/unknown: materials; VAT unknown
- Comparability: partially comparable — median (manual) band used; mechanical excluded.

5. *Supplementary (outside target region):*
- Name: Derty Serwis (Warszawa) — odgrzybianie ścian cena
- URL: https://dertys-odgrzybianie.pl/odgrzybianie-scian-cena
- Type: CONTRACTOR_PRICE_LIST
- Region: PL (firm in Warszawa)
- Checked: 2026-09-13
- Quoted value: "Skrobanie starej farby — 35 zł/m2; Usuwanie tapety — 30 zł/m2"
- Unit: M2
- Price scope: unspecified
- Included work: removal
- Excluded/unknown: "Cena netto bez 23% VAT"
- Comparability: comparable but Warsaw market — context only.

Notes / exclusions: the 35 ceiling for the main range is the top of the manual (aikfarby) band;
mechanical 38–55 and oil-paint tiers are excluded from the primary range because the catalog
comparability explicitly excludes oil-paint lamperia work.

---

## CENNIK_PREP_FLEECE-01 — Zdzieranie starej flizeliny / włókniny szklanej

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P2

Market result:
- market_min: 35
- market_max: 64
- reference_price: —
- region: PL
- checked_at: 2026-09-13
- confidence: LOW

Methodology: **proxy evidence only.** No contractor price list prices "zdzieranie flizeliny /
włókniny szklanej" as a stand-alone line; the only usable numeric is the fiberglass / multi-layer
wallpaper removal tier (35–50 zł/m²) and the "strong glue / from substrate" tier (50–64 zł/m²) on a
single portal. Labour effort for removing glass-fiber fleece is analogous, but this is one source
presenting a proxy tier, so it is NOT a market average and NOT a defensible localized range.

Comparable source count: 1 page (proxy tier, single portal).

Sources:

1.
- Name: T-Tapety — zdzieranie tapety cena
- URL: https://t-tapety.pl/zdzieranie-tapety-cena
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Fiberglassowa lub wielowarstwowa — 35–50 zł/m²; Z silnym klejem, z gruntu — 50–64 zł/m²"
- Unit: M2
- Price scope: LABOR
- Included work: stripping fiberglass / multi-layer wall coverings
- Excluded/unknown: materials; VAT variable on page
- Comparability: partially comparable — priced for fiberglass *wallpaper* removal; closest public
  proxy for flizelina (glass-fibre lining); analogous effort.

Notes / exclusions: search for "zdzieranie flizeliny/włókniny" found only installation prices for
włókno szklane (e.g. KB.pl Kraków 64,30 zł/m² for *application*), which are not removal evidence.
Because the market normally bundles fleece removal with the stripping/repair job, this row is a
strong OWN_PRICE candidate (see §17).

---

## CENNIK_PREP_DEGR-01 — Odtłuszczanie i usuwanie zabrudzeń podłoża (np. kuchnia)

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P2

Market result:
- market_min: 10
- market_max: 15
- reference_price: —
- region: PL
- checked_at: 2026-09-13
- confidence: LOW

Methodology: single usable source. Degreasing walls is nearly always priced inside washing/prep
work bundles; no Kraków or Małopolskie contractor prices it standalone (the cenauslug.pl Kraków
sub-page for roof degreasing returned HTTP 410 — dead, see archival note).

Comparable source count: 1 page.

Sources:

1.
- Name: Mocny Fundament — przygotowanie ścian do malowania
- URL: https://mocnyfundament.pl/ile-kosztuje-przygotowanie-scian-i-sufitu-do-malowania-gladzie-gruntowanie-usuwanie-starych-powlok/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Odtłuszczanie ścian może kosztować 10–15 zł/m²"
- Unit: M2
- Price scope: LABOR
- Included work: degreasing walls
- Excluded/unknown: cleaning agents; VAT (net-table context, +8% noted generally)
- Comparability: partially comparable — generic wall degreasing, no method detail.

Notes / exclusions: single-source record — do NOT report as a market average. OWN_PRICE candidate
(usually bundled with substrate washing / cleaning).

---

## CENNIK_PREP_MOLD-01 — Usuwanie pleśni i grzyba z preparatem grzybobójczym

Canonical scope:
- Unit: M2
- Price scope: LABOR_AND_MATERIAL
- Priority: P1

Market result:
- market_min: 30
- market_max: 120
- reference_price: — (area-scaled ladder; no single stable mode)
- region: PL
- checked_at: 2026-09-13
- confidence: MEDIUM

Methodology: the catalog scope requires **labor + biocide material included**. The only source that
markets that scope cleanly is daart ("atestowane środki chemiczne" included; area-scaled 30–120
zł/m²). NewBridge (50–150 zł/m², deep removal 200–350) is a bundled lump-service quote and is
partially comparable. The two labor-only quotes (cenauslug 52–75 zł/m² labor-only + material on
top; MocnyFundament 15–30 zł/m² labor) are recorded as labor context and are **not mixed into the
L+M range**. No dedicated Kraków/Małopolskie mold-treatment price was found; all evidence is
Poland-wide.

Comparable source count: 4 pages within region + 1 supplementary outside region.

Sources:

1.
- Name: Daart — odgrzybianie cena za m²
- URL: https://daart.pl/odgrzybianie-scian-cena-za-m2
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "od około 30 do nawet 120 zł/m²"; area tiers: "do 5 m²: 30–50; 5–15 m²: 50–80; 15–30 m²: 80–100; powyżej 30 m²: 100–120"
- Unit: M2
- Price scope: LABOR_AND_MATERIAL
- Included work: labor + approved biocidal chemicals + basic moisture diagnostics
- Excluded/unknown: osuszanie, scaffolding, transport >30 km, VAT unknown
- Comparability: comparable — closest match to the LABOR_AND_MATERIAL + biocide definition.

2.
- Name: cenauslug.pl — odgrzybianie ścian
- URL: https://cenauslug.pl/budowa-i-remont/odgrzybianie-scian
- Type: MARKETPLACE
- Region: PL (no Kraków row for this city on checked date)
- Checked: 2026-09-13
- Quoted value: "52–75 zł/m², średnia 60 zł/m2"
- Unit: M2
- Price scope: LABOR (labor only — "Cena nie zawiera materiałów")
- Included work: mold removal labor
- Excluded/unknown: tynku skuwanie / repairs / painting; materials; VAT unknown
- Comparability: comparable **as labor-only** — materials add on top; used as labor context, not the L+M range.

3.
- Name: New Bridge — odgrzybianie cena za m²
- URL: https://newbridge.com.pl/odgrzybianie-cena-za-m2/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Średnie ceny wahają się od 50 do 150 zł za m2; głębokie: 200–350 zł/m2 (skucie tynku)"
- Unit: M2
- Price scope: unspecified
- Included work: bundled service quote, no labor/material split
- Excluded/unknown: diagnostics often extra; VAT (8%/23%)
- Comparability: partially comparable — bundled lump-service vs itemized row.

4.
- Name: Mocny Fundament — przygotowanie ścian
- URL: https://mocnyfundament.pl/ile-kosztuje-przygotowanie-scian-i-sufitu-do-malowania-gladzie-gruntowanie-usuwanie-starych-powlok/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Usuwanie grzyba lub pleśni to wydatek rzędu 15–30 zł/m²"
- Unit: M2
- Price scope: LABOR
- Included work: mold removal, labor
- Excluded/unknown: biocide cost; VAT
- Comparability: partially comparable — lower-edge, materials likely extra.

5. *Supplementary (outside target region):*
- Name: SLIM-POL (Łódź) — odgrzybianie ścian cena
- URL: https://www.slim-pol.pl/odgrzybianie-scian-cena/
- Type: CONTRACTOR_PRICE_LIST
- Region: PL (firm in Łódź)
- Checked: 2026-09-13
- Quoted value: "standardowe odgrzybianie 10–30 zł/m²; ze specjalistycznymi preparatami 30–60 zł/m²; kompleksowe ze skuwaniem 100–200 zł/m²"
- Unit: M2
- Price scope: unspecified (net table)
- Included work: mold removal (tiered)
- Excluded/unknown: VAT
- Comparability: partially comparable — priced outside the target region; context only.

Notes / exclusions: wide absolute spread is driven by surface area (most sources apply a
minimum-area charge) and by whether the plaster is being removed. Kraków/Małopolskie-specific mold
prices are absent from the checked sources; if local evidence is required in 9E.4, a separate local
round is needed.

---

## CENNIK_PREP_CLEAN-01 — Odkurzanie i czyszczenie podłoża przed wykończeniem

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P3

Market result:
- market_min: —
- market_max: —
- reference_price: —
- region: —
- checked_at: 2026-09-13
- confidence: INSUFFICIENT

**INSUFFICIENT MARKET EVIDENCE.**

Methodology: no contractor price list or cost portal prices *post-sanding substrate vacuuming /
odpylanie podłoża* as a standalone per-m² item. Consulted pages are qualitative how-to guides with
no service price (e.g. daart "jak odpylić ściany po gładzi" — zero PLN figures; noted in §18).
Existing "sprzątanie po remoncie" rates (kb.pl) are whole-flat cleaning (45–72 zł/h or 7–13,50
zł/m²) and are **non-comparable** to substrate vacuuming. Recommended treatment in 9E.4/9E.5:
OWN_PRICE (folded into gładź/malowanie, or priced by labour hour).

Comparable source count: 0 usable.

Sources: none usable. Consulted (qualitative / non-comparable, recorded for traceability):

1.
- Name: Daart — jak odpylić ściany po gładzi (no prices)
- URL: https://daart.pl/jak-odpylic-sciany-po-gladzi
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: qualitative only (zero PLN figures)
- Comparability: non-comparable — no price.

2.
- Name: KB.pl — sprzątanie po remoncie
- URL: https://kb.pl/cenniki/uslugi/sprzatanie-po-remoncie/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "sprzątanie po remoncie 45–72 zł/h; puste mieszkanie 7–13,50 zł/m²"
- Unit: HOUR / M2 (whole flat)
- Comparability: non-comparable — whole-flat cleaning, not substrate vacuuming.

---

## CENNIK_PRIM_STD-01 — Gruntowanie gruntem penetrującym (pod szpachlowanie)

Canonical scope:
- Unit: M2
- Price scope: LABOR_AND_MATERIAL
- Priority: P1

Market result:
- market_min: 7
- market_max: 15
- reference_price: — (only two sources support the L+M scope directly; see methodology)
- region: Kraków (labor anchors) + PL (L+M)
- checked_at: 2026-09-13
- confidence: MEDIUM

Methodology: the **catalog scope is labor + material** (1 coat penetrating primer + labor, per m²,
material included). Only zleca.pl prices that scope explicitly (labor-only 4–10 vs "z materiałem
ok. 7–15 zł/m²"); NewBridge splits the same job (labor 1x 5–8 + penetrating material ~3–5 → L+M
~8–13), which is consistent with the 7–15 band. The abundant labor-only rows — including the
verifiable Kraków municipal row (kb.pl Kraków 7,73 zł/m² brutto, labor-only) and a Kraków firm's
"od 5 zł/m²" — are recorded as labor anchors and **not mixed into the L+M range**. Because the
direct L+M evidence rests on two sources, confidence is MEDIUM despite the large number of rows.

Comparable source count: 6 rows across 5 independent publishers (2 rows support L+M directly).

Sources:

1.
- Name: KB.pl — gruntowanie ścian przed malowaniem (table by city)
- URL: https://kb.pl/cenniki/gruntowanie-scian-przed-malowaniem/
- Type: INDUSTRY_ARTICLE
- Region: Kraków (city row) / Małopolskie (voivodeship row)
- Checked: 2026-09-13 (re-confirmed 2026-09-14)
- Quoted value: "Kraków 7,73 zł/m² brutto; małopolskie 6,68–7,73; średnia krajowa 6,95 zł/m²"
- Unit: M2
- Price scope: LABOR ("Cena zawiera wyłącznie koszt robocizny"), gross incl. 8% VAT
- Included work: single priming coat, labor
- Excluded/unknown: grunt material; non-typical wall heights
- Comparability: comparable — clean per-city labor datapoint. Same row is the primary evidence for
  PRIM_PAINT-01 below; it must count once across both rows, not twice.

2.
- Name: KB.pl — cena gruntowania przed malowaniem (article table)
- URL: https://kb.pl/cenniki/uslugi/cena-gruntowania-scian-i-sufitu-przed-malowaniem-za-m2/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Gruntowanie przed malowaniem (jednokrotne): 9,00–15,00 zł/m2"
- Unit: M2
- Price scope: LABOR
- Included work: single priming coat, labor, gross incl. 8% VAT
- Excluded/unknown: material
- Comparability: comparable.

3.
- Name: Malarz Kraków — cennik (firma Kraków)
- URL: https://malarzkrakow.pl/cennik/
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków
- Checked: 2026-09-13 (re-confirmed 2026-09-14)
- Quoted value: "Gruntowanie ścian i sufitów — od 5 zł/m²"
- Unit: M2
- Price scope: LABOR
- Included work: priming walls/ceilings, net rate
- Excluded/unknown: material; VAT
- Comparability: comparable — Kraków floor price.

4.
- Name: Zleca.pl — gruntowanie ściany
- URL: https://zleca.pl/cennik/gruntowanie-sciany-cena
- Type: MARKETPLACE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "około 10 zł/m2; 5–15 zł/m2; sama robocizna 4–10 zł/m², z materiałem ok. 7–15 zł/m²"
- Unit: M2
- Price scope: LABOR and LABOR_AND_MATERIAL (both split explicitly)
- Included work: labor-only vs with grunt
- Excluded/unknown: VAT unknown
- Comparability: comparable — the only source that splits labor vs labor+material explicitly.

5.
- Name: New Bridge — gruntowanie cena za m²
- URL: https://newbridge.com.pl/gruntowanie-cena-za-m2/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "jedna warstwa: 5–8 zł/m² robocizna; materiał ok. 3–5 zł/m²; grunt głęboko penetrujący 15–30 zł/litr"
- Unit: M2
- Price scope: LABOR + MATERIAL (split)
- Included work: one coat labor + penetrating grunt material
- Excluded/unknown: VAT (8%/23% stated)
- Comparability: comparable — the labor+material split sums to ~8–13 zł/m², consistent with zleca.

6.
- Name: WZBudowa — cennik usług malarskich 2026
- URL: https://wzbudowa.pl/cennik-uslug-malarskich/
- Type: CONTRACTOR_PRICE_LIST
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Gruntowanie ścian i sufitów — około 6–12 zł/m²"
- Unit: M2
- Price scope: LABOR
- Included work: priming walls and ceilings
- Excluded/unknown: material; VAT unknown
- Comparability: comparable.

Notes / exclusions: the Kraków municipal labor row (7,73) and the Kraków floor ("od 5") are
single-coat **labor** anchors; they are used to sanity-check the labor component of the L+M range,
not added directly to it. The same kb.pl city table row supports PRIM_PAINT-01 — it is counted once
across the two priming rows.

---

## CENNIK_PRIM_ADH-01 — Gruntowanie gruntem kontaktowym adhezyjnym

Canonical scope:
- Unit: M2
- Price scope: LABOR_AND_MATERIAL
- Priority: P2

Market result:
- market_min: —
- market_max: —
- reference_price: —
- region: PL
- checked_at: 2026-09-13
- confidence: LOW

Methodology: **component evidence only; no direct per-m² market quote found.** The single usable
source prices the adhesion (quartz/contact) primer per litre (20–40 zł/litr) plus a per-m² material
cost uplift (5–10 zł/m²) and states labor follows standard priming (5–8 zł/m², 1 coat). A defensible
blended "market" figure would require inventing an m² consumption factor — not done here. The derived
working note (~10–18 zł/m² L+M) is a calculation, not a quoted market datapoint.

Comparable source count: 1 page (component evidence only).

Sources:

1.
- Name: New Bridge — gruntowanie cena za m²
- URL: https://newbridge.com.pl/gruntowanie-cena-za-m2/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Grunt adhezyjny (sczepny) 20–40 zł/litr … przy płytkach może podnieść koszt materiału o 5–10 zł/m²"; labor "5–8 zł/m2 (jedna warstwa)"
- Unit: LITRE (primer) / M2 (labor and material uplift)
- Price scope: MATERIAL (primer) + LABOR (separate lines)
- Included work: quartz/adhesion primer material premium + standard priming labor
- Excluded/unknown: VAT; blended L+M price not given by the source
- Comparability: partially comparable — material premium expressed per m²; labor inferred from standard priming.

Notes / exclusions: bonding-primer pricing is strongly product- and substrate-specific; market rows
for "grunt kontaktowy" were not found in the checked cenniks. Strong OWN_PRICE candidate.

---

## CENNIK_PRIM_HIGH-01 — Gruntowanie podłoża wysokochłonnego (dwukrotne)

Canonical scope:
- Unit: M2
- Price scope: LABOR_AND_MATERIAL
- Priority: P3

Market result:
- market_min: —
- market_max: —
- reference_price: —
- region: PL
- checked_at: 2026-09-13
- confidence: LOW

Methodology: **single source, labor-only.** The one usable quote prices double-coat priming labor at
10–15 zł/m² (vs 5–8 for one coat); the grunt material for such coats (~3–5 zł/m² per NewBridge's
own split) is listed separately. No direct L+M double-priming quote exists in the checked sources.
Aikfarby's "12 zł/m²" upper band is qualitative confirmation only (scope stated as "repairs,
leveling, two coats" but not confirmed as double-coat labor).

Comparable source count: 1 page (+ 1 qualitative context).

Sources:

1.
- Name: New Bridge — gruntowanie cena za m²
- URL: https://newbridge.com.pl/gruntowanie-cena-za-m2/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Robocizna za gruntowanie dwukrotne … 10–15 zł/m2" (vs "jedna warstwa: 5–8 zł/m2"); "nowe tynki: 2–4 zł/m²; ściany i sufity (bez malowania): 10–14 zł/m²"
- Unit: M2
- Price scope: LABOR
- Included work: two priming coats, labor
- Excluded/unknown: grunt material (~3–5 zł/m² extra per same source); VAT
- Comparability: comparable for LABOR; L+M not directly quoted.

2. *Qualitative context:*
- Name: Aikfarby — cena gruntowania
- URL: https://aikfarby.pl/cena-gruntowania
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: upper "12 zł/m²" band described as "repairs, leveling, two coats" (scope not stated)
- Comparability: qualitative only — not used for the range.

Notes / exclusions: double priming of high-absorption substrate is usually priced as a custom
premium; a direct market rate was not found. OWN_PRICE candidate.

---

## CENNIK_PRIM_PAINT-01 — Gruntowanie przed malowaniem (pod farbę)

Canonical scope:
- Unit: M2
- Price scope: LABOR_AND_MATERIAL
- Priority: P2

Market result:
- market_min: 3
- market_max: 15
- reference_price: —
- region: Kraków (labor anchors) + PL (L+M)
- checked_at: 2026-09-13
- confidence: MEDIUM

Methodology: catalog scope is **labor + material** (primer under paint on a smoothed skim coat).
Two sources state the L+M scope explicitly: zleca (7–15 zł/m² "z materiałem") and MocnyFundament
(FAQ: 3–8 zł/m² "wliczając materiał i robociznę"). The five otherwise-labor/unspecified rows are
recorded so the labor component stays separate; the Kraków-local rows (kb 7,73 brutto labor;
totaldecor 8; kubamalarz od 8; cennikremontow 4–16) anchor the labor side locally. Wide range
reflects the labor-only vs L+M mix; confidence MEDIUM.

Comparable source count: 6 rows across 5 independent publishers (2 rows L+M-explicit).

Sources:

1.
- Name: KB.pl — gruntowanie ścian przed malowaniem (table by city)
- URL: https://kb.pl/cenniki/gruntowanie-scian-przed-malowaniem/
- Type: INDUSTRY_ARTICLE
- Region: Kraków (city row) / Małopolskie (voivodeship row)
- Checked: 2026-09-13 (re-confirmed 2026-09-14)
- Quoted value: "Kraków 7,73 zł/m² brutto (labor); małopolskie 6,68–7,73; krajowa 6,95"
- Unit: M2
- Price scope: LABOR (gross incl. 8% VAT)
- Included work: single priming coat, labor
- Excluded/unknown: material
- Comparability: comparable. Same row as PRIM_STD-01 — counted once across both rows.

2.
- Name: TOTALDECOR Kraków — cennik (firma Kraków)
- URL: https://totaldecor.pl/cennik/
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków
- Checked: 2026-09-13
- Quoted value: "Przygotowanie ścian i gruntowanie — 8 zł/m²"
- Unit: M2
- Price scope: unspecified
- Included work: combined wall-prep + priming
- Excluded/unknown: split, materials, VAT unknown
- Comparability: partially comparable — bundled line.

3.
- Name: kubamalarz.pl — cennik (firma Kraków)
- URL: https://kubamalarz.pl/cennik/
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków
- Checked: 2026-09-13
- Quoted value: "Gruntowanie ścian od 8 zł/m2"
- Unit: M2
- Price scope: unspecified
- Included work: priming walls
- Excluded/unknown: material/VAT not stated
- Comparability: partially comparable — labor implied but not confirmed.

4.
- Name: Zleca.pl — gruntowanie ściany
- URL: https://zleca.pl/cennik/gruntowanie-sciany-cena
- Type: MARKETPLACE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "z materiałem około 7–15 zł/m²; sama robocizna 4–10 zł/m²"
- Unit: M2
- Price scope: LABOR_AND_MATERIAL and LABOR (both explicit)
- Included work: labor + primer material bundle
- Excluded/unknown: VAT unknown
- Comparability: comparable — explicitly includes material.

5.
- Name: Cennik Remontów — malowanie Kraków 2026 (Kraków market page)
- URL: https://cennikremontow.pl/malowanie-krakow-cennik
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków
- Checked: 2026-09-13
- Quoted value: "Gruntowanie: 4–16 zł/m²" (page text: "1 do 5 zł za m²")
- Unit: M2
- Price scope: unspecified
- Included work: priming before painting
- Excluded/unknown: labor/material split; VAT unknown
- Comparability: partially comparable — wide local band, inconsistent within the page.

6.
- Name: Mocny Fundament — przygotowanie ścian
- URL: https://mocnyfundament.pl/ile-kosztuje-przygotowanie-scian-i-sufitu-do-malowania-gladzie-gruntowanie-usuwanie-starych-powlok/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Gruntowanie robocizna 5–15 zł/m²; FAQ: 3–8 zł/m² wliczając materiał i robociznę"
- Unit: M2
- Price scope: LABOR and LABOR_AND_MATERIAL
- Included work: priming before painting
- Excluded/unknown: VAT
- Comparability: comparable.

Notes / exclusions: the market quotes "gruntowanie 1x" at essentially the same rate whether the coat
sits under skim or under paint; the catalog splits these rows for Stage 9B estimate use. The kb.pl
city table row is the single shared datapoint across PRIM_STD and PRIM_PAINT and is counted once.

---

## CENNIK_SKIM_1L-01 — Gładź szpachlowa — 1 warstwa (cała powierzchnia)

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P1

Market result:
- market_min: 30
- market_max: 50
- reference_price: 40 — methodology: central commonly-observed LABOR band for a single full-surface
  coat (Kraków table 35–50; kb.pl national 30–45); the local table's midpoint is the reference.
- region: Kraków anchor + PL
- checked_at: 2026-09-13
- confidence: HIGH

Methodology: comparable = one full-surface skim coat, labor, per m², without sanding. Four
independent sources with good agreement once scope is matched: Kraków local table 35–50 (LABOR,
0,4–0,6 h/m²), kb.pl 30–45 (LABOR; 38–55 L+M kept separate), sccot 40–60 read as "całkowity koszt"
(partially comparable — labor+material blur), idealny-sufit 15–25 flagged as a low outlier. Sanding
(10–16/12–19) is billed separately by all sources and is not included.

Comparable source count: 4 independent pages.

Sources:

1.
- Name: S-Szpachlowanie — Cennik szpachlowania Kraków (firma Kraków)
- URL: https://s-szpachlowanie.pl/szpachlowanie-krakow-cennik
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków
- Checked: 2026-09-13 (re-confirmed 2026-09-14)
- Quoted value: "Gładzenie jednokrotne (1 warstwa) 35–50 zł/m²", 0,4–0,6 h/m²
- Unit: M2
- Price scope: LABOR
- Included work: 1 layer only
- Excluded/unknown: szlifowanie 10–16 zł/m² billed separately; VAT unspecified; page notes a
  blanket labor band 45–70 zł/m² for szpachlowanie with material 60–80
- Comparability: comparable — local Kraków table row.

2.
- Name: KB.pl — cennik gładzi gipsowej i szpachlowania
- URL: https://kb.pl/cenniki/uslugi/cennik-gladzi-gipsowej-i-szpachlowania-scian-w-calej-polsce/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Szpachlowanie 1x 30,00–45,00 zł/m²" (robocizna); 38–55 zł/m² z materiałem
- Unit: M2
- Price scope: LABOR (also L+M row kept separate)
- Included work: jednokrotne nakładanie szpachli
- Excluded/unknown: sanding separate (12–19 zł/m²); price includes 8% VAT (gross); "ceny poglądowe"
- Comparability: comparable — national index.

3.
- Name: sccot.pl — ile kosztuje szpachlowanie ścian
- URL: https://sccot.pl/dobra-robota/ile-kosztuje-szpachlowanie-scian/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Szpachlowanie 1× 40–60 zł/m²" ("całkowity koszt")
- Unit: M2
- Price scope: unspecified ("całkowity koszt"; gruntowanie i szlifowanie wyceniane osobno)
- Included work: jednokrotne szpachlowanie 1 m²
- Excluded/unknown: labor/material mix; VAT unknown
- Comparability: partially comparable — scope reads all-in, not clean LABOR.

4.
- Name: Idealny-Sufit — gładź szpachlowa cena robocizny
- URL: https://idealny-sufit.pl/gladz-szpachlowa-cena-robocizny
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Przy jednej warstwie szpachlowania płacisz 15–25 zł/m²"
- Unit: M2
- Price scope: LABOR
- Included work: jedna warstwa
- Excluded/unknown: sanding separate (5–10 zł/m²); includes 8% VAT (gross); article also cites
  Kraków/Warszawa 35–60 "razem"
- Comparability: comparable — low end of labor scale; flagged outlier vs the Kraków/national tables.

Notes / exclusions: idealny-sufit's 15–25 is kept in the record but is below the 30–50 core band;
it is a content/aggregator page and treated as a low outlier, not a range anchor. sccot's all-in
reading (40–60) overlaps the core band but is not scope-pure.

---

## CENNIK_SKIM_2L-01 — Gładź szpachlowa — 2 warstwy (pakiet)

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P1

Market result:
- market_min: 35
- market_max: 75
- reference_price: 55 — methodology: central commonly-observed band 45–70 for two coats (Kraków
  rows 40–70 and 55–75; kb national 35–54); 55 chosen as a typical Kraków contractor quote.
- region: Kraków anchor + PL
- checked_at: 2026-09-13
- confidence: HIGH

Methodology: comparable = two full-surface skim coats, labor, per m², **without sanding** (sanding is
separate for the CRC group; packages incl. sanding go to SKIM_PKG). Kraków local table 55–75
(LABOR, 0,8–1,2 h/m²); CennikiBudowlane "Kraków 40–70" and "standard 35–60 (2 warstwy z
gruntowaniem)"; kb national 35–54 LABOR; sccot 50–70 all-in (partial). The "z materiałem" rows
(48–70) and the grunt-inclusive rows are scope-augmented and classified as partially comparable.

Comparable source count: 4 independent pages.

Sources:

1.
- Name: S-Szpachlowanie — Cennik szpachlowania Kraków (firma Kraków)
- URL: https://s-szpachlowanie.pl/szpachlowanie-krakow-cennik
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków
- Checked: 2026-09-13 (re-confirmed 2026-09-14)
- Quoted value: "Szpachlowanie dwukrotne (2 warstwy) 55–75 zł/m²", 0,8–1,2 h/m²
- Unit: M2
- Price scope: LABOR
- Included work: 2 layers
- Excluded/unknown: szlif osobno 10–16 zł/m²; VAT unspecified; blanket labor band 45–70 zł/m² also
  present on page
- Comparability: comparable — local table.

2.
- Name: KB.pl — cennik gładzi gipsowej
- URL: https://kb.pl/cenniki/uslugi/cennik-gladzi-gipsowej-i-szpachlowania-scian-w-calej-polsce/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Szpachlowanie 2x 35,00–54,00 zł/m²" (robocizna); 48–70 zł/m² z materiałem
- Unit: M2
- Price scope: LABOR (also L+M row kept separate)
- Included work: dwukrotne nakładanie szpachli
- Excluded/unknown: sanding separate; 8% VAT included (gross)
- Comparability: comparable — national index.

3.
- Name: CennikiBudowlane.com.pl — cennik gładzi szpachlowych
- URL: https://www.cennikibudowlane.com.pl/cenniki/polozenie-gladzi/
- Type: INDUSTRY_ARTICLE
- Region: PL (contains a Kraków row)
- Checked: 2026-09-13
- Quoted value: "Standard 35–60 zł/m² (2 warstwy z gruntowaniem) netto; Kraków 40–70 zł/m²"
- Unit: M2
- Price scope: LABOR with gruntowanie (sanding inclusion unspecified)
- Included work: 2 warstwy + gruntowanie
- Excluded/unknown: sanding not itemized; net prices; VAT 8/23% separately
- Comparability: comparable — scope-augmented (includes gruntowanie); recorded as partially
  comparable for the pure 2-coat scope (sanding status unspecified).

4.
- Name: sccot.pl — ile kosztuje szpachlowanie
- URL: https://sccot.pl/dobra-robota/ile-kosztuje-szpachlowanie-scian/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Szpachlowanie 2× 50–70 zł/m²"
- Unit: M2
- Price scope: unspecified ("całkowity koszt")
- Included work: dwukrotne szpachlowanie
- Excluded/unknown: scope mix; VAT unknown
- Comparability: partially comparable — numbers align with the itodesign.pl article; possible shared
  content network (see SKIM_3L note); treat as one network with SKIM_1L/3L rows.

Notes / exclusions: the two Kraków rows (55–75 s-szpachlowanie; 40–70 cennikibudowlane) define the
local band; kb.pl's 35–54 (national, gross) is the low edge. sccot/itodesign likelihood of sharing a
content network is flagged but does not distort this row because local + kb anchors are independent.

---

## CENNIK_SKIM_3L-01 — Gładź szpachlowa — 3 warstwy

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P2

Market result:
- market_min: 60
- market_max: 80
- reference_price: —
- region: PL
- checked_at: 2026-09-13
- confidence: MEDIUM

Methodology: direct 3-coat quotes exist only on two pages that publish **identical** figures
("3 warstwy 60–80 zł/m²") and read as the same content network (sccot.pl / itodesign.pl) — treated
as effectively one independent source. Supporting mechanics: daart prices the third coat as an
add-on (+12–18 zł/m² over the base rate), and CennikiBudowlane states "każda warstwa zwiększa cenę o
50–70%" (mechanism, not a direct rate). Given the duplication risk, the 60–80 window is recorded with
LOW-to-MEDIUM evidential weight (rated MEDIUM per §14 as "2+ useful sources" with an explicit
duplication caveat).

Comparable source count: 2 pages (suspected single content network) + 2 partial mechanisms.

Sources:

1.
- Name: sccot.pl — ile kosztuje szpachlowanie ścian
- URL: https://sccot.pl/dobra-robota/ile-kosztuje-szpachlowanie-scian/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Szpachlowanie 3× 60–80 zł/m² — trzykrotne szpachlowanie … perfekcyjna gładkość, np. pod oświetlenie LED"
- Unit: M2
- Price scope: unspecified (całkowity koszt)
- Included work: 3 warstwy
- Excluded/unknown: scope mix; sanding; VAT
- Comparability: comparable for the 3x level, but near-identical text to itodesign.pl — possible
  same content network (duplication flag).

2.
- Name: itodesign.pl — ile kosztuje szpachlowanie ścian
- URL: https://itodesign.pl/ile-kosztuje-szpachlowanie-scian-cennik-i-od-czego-zalezy/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "3 warstwy 60–80 zł/m² (efekt „pod LED”)"; "robocizna z podstawowym materiałem"
- Unit: M2
- Price scope: "robocizna z podstawowym materiałem" (L+M-leaning)
- Included work: 3 warstwy, standardowa gładź
- Excluded/unknown: sanding separate (10–20 zł/m²); VAT; premium materials extra
- Comparability: partially comparable — near-identical figures to sccot.pl (suspected same content
  network).

3.
- Name: CennikiBudowlane.com.pl (FAQ) — położenie gładzi
- URL: https://www.cennikibudowlane.com.pl/cenniki/polozenie-gladzi/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "18–45 zł za m² (w zależności 1–3 warstw)"; "Każda warstwa zwiększa cenę o 50-70%"
- Unit: M2
- Price scope: LABOR vs L+M not split
- Included work: położenie gładzi 1–3 warstw (range; 3x not isolated)
- Excluded/unknown: no clean 3x figure; VAT
- Comparability: partially comparable — 3x is inside the range but not separately priced.

4.
- Name: Daart — gładź cena za m²
- URL: https://daart.pl/gladz-cena-za-m2
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Trzecia warstwa: +12–18 zł/m²" (dodatek do stawki bazowej)
- Unit: M2
- Price scope: LABOR
- Included work: third layer as add-on
- Excluded/unknown: VAT
- Comparability: partially comparable — add-on price, not a full 3x quote.

Notes / exclusions: for any subsequent use, the 3-coat rate should either be corroborated with a
genuinely independent source or derived as 2x + third-layer add-on. The market rarely separates 3x;
this row is also a candidate to fold into OWN_PRICE / package pricing.

---

## CENNIK_SKIM_SAND-01 — Szlifowanie gładzi z odpylaniem

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P1

Market result:
- market_min: 10
- market_max: 25
- reference_price: 14 — methodology: central commonly-observed band for standard sanding (Kraków
  10–16; kb 12–19; pl itodesign 10–20); the Kraków table midpoint.
- region: Kraków + PL
- checked_at: 2026-09-13
- confidence: HIGH

Methodology: comparable = sanding of skim coat with dust extraction (odpylanie), labor, per m².
Standard (manual/machine) sanding bands agree well: Kraków 10–16, kb 12–19, itodesign 10–20,
e-gladz 10–25 (machine-only 15–30; bezpyłowe 8 + odpylanie 2 items). The upper limit (25) is the top
of the standard e-gladz band; the "na lustro" / mirror-finish surcharge (10–20 extra) belongs to
SKIM_SQ, not here.

Comparable source count: 4 independent pages.

Sources:

1.
- Name: S-Szpachlowanie — Cennik szpachlowania Kraków (firma Kraków)
- URL: https://s-szpachlowanie.pl/szpachlowanie-krakow-cennik
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków
- Checked: 2026-09-13 (re-confirmed 2026-09-14)
- Quoted value: "Szlifowanie gładzi 10–16 zł/m²", 0,2–0,4 h/m²
- Unit: M2
- Price scope: LABOR
- Included work: sanding
- Excluded/unknown: dedusting not itemized separately on the row; VAT unspecified
- Comparability: comparable — local table.

2.
- Name: E-Gładź — szlifowanie gładzi cena za m2
- URL: https://e-gladz.pl/szlifowanie-gladzi-cena-za-m2
- Type: CONTRACTOR_PRICE_LIST
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Szlifowanie gładzi 10–25 PLN/m²; szlifowanie maszynowe 15–30 PLN/m²; szlifowanie bezpyłowe 8 zł/m² + odpylanie 2 zł/m²"
- Unit: M2
- Price scope: LABOR
- Included work: levelling removal before painting
- Excluded/unknown: VAT
- Comparability: comparable — includes separate dedust lines.

3.
- Name: KB.pl — cennik szlifowania gładzi
- URL: https://kb.pl/cenniki/uslugi/cennik-gladzi-gipsowej-i-szpachlowania-scian-w-calej-polsce/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Szlifowanie gładzi 12,00–19,00 zł/m² (bez usługi gładzenia)"
- Unit: M2
- Price scope: LABOR
- Included work: sanding of gypsum skim
- Excluded/unknown: 8% VAT included (gross); dedusting not stated
- Comparability: comparable.

4.
- Name: itodesign.pl — ile kosztuje szpachlowanie ścian
- URL: https://itodesign.pl/ile-kosztuje-szpachlowanie-scian-cennik-i-od-czego-zalezy/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Szlifowanie liczone osobno 10–20 zł/m²; szlifowanie „na lustro” dodatkowe 10–20 zł/m²"
- Unit: M2
- Price scope: LABOR
- Included work: sanding billed separately
- Excluded/unknown: VAT; mirror-finish surcharge separate
- Comparability: comparable.

Notes / exclusions: machine-only sanding (15–30) is distinct from the standard band and is recorded
but not merged upward; bezpyłowe (8) + odpylanie (2) indicates that basic dedusting is priced
separately by some firms, matching the catalog's odpylanie note.

---

## CENNIK_SKIM_PKG-01 — Pakiet gładź 2x + szlifowanie

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P1

Market result:
- market_min: 35
- market_max: 70
- reference_price: 50 — methodology: central commonly-observed band 40–60 for the 2-coat + sanding
  package (e-gladz 40–70, s-szpachlowanie full-gładź 35–70, cennikibudowlane 35–60); 50 chosen as a
  typical mid-market package quote.
- region: PL (Kraków L+M supplementary: wolthome Kraków 50–65 kompleksowa — recorded separately)
- checked_at: 2026-09-13
- confidence: MEDIUM

Methodology: comparable = full 2-coat skim + sanding (+dedust where stated), labor, per m², without
clean material inclusion. Sources vary in exact inclusion (gruntowanie, odpylanie, material) — each
classified. e-gladz: "szlifowanie i dwukrotne nałożenie gładzi 40–70" (dedust itemized separately);
s-szpachlowanie full-gładź 35–70 (grunt + szlif included); cennikibudowlane 35–60 (2x + grunt,
sanding status unspecified); wolthome "kompleksowa" 45–80 **z materiałem** (+ Kraków 50–65) is
LABOR_AND_MATERIAL and therefore excluded from the LABOR range — recorded as local cross-check.

Comparable source count: 4 pages (3 LABOR-comparable, 1 L+M kept separate).

Sources:

1.
- Name: E-Gładź — szlifowanie gładzi cena
- URL: https://e-gladz.pl/szlifowanie-gladzi-cena-za-m2
- Type: CONTRACTOR_PRICE_LIST
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Szlifowanie i dwukrotne nałożenie gładzi 40–70 PLN/m²"; osobno "szlifowanie bezpyłowe 8 zł/m², odpylanie 2 zł/m²"
- Unit: M2
- Price scope: LABOR
- Included work: 2 warstwy + szlifowanie
- Excluded/unknown: dedusting not in the package row (2 zł/m² extra); VAT
- Comparability: comparable — closest match to "2x + szlif".

2.
- Name: S-Szpachlowanie — cena szpachlowania
- URL: https://s-szpachlowanie.pl/cena-szpachlowania
- Type: CONTRACTOR_PRICE_LIST
- Region: PL (same Kraków firm, nationwide article page)
- Checked: 2026-09-13
- Quoted value: "Pełna gładź gipsowa 35–70 zł/m² — zawiera gruntowanie + szlifowanie; szlifowanie maszynowe 10–20 zł/m²"
- Unit: M2
- Price scope: LABOR (opcja z materiałem 50–90 zł/m² osobno)
- Included work: grunt + gładź + szlif
- Excluded/unknown: dedusting not mentioned; VAT
- Comparability: partially comparable — does not isolate "2x".

3.
- Name: Wolthome — cennik szpachlowania 2025 (z wierszem Kraków)
- URL: https://wolthome.pl/poradnik/ile-kosztuje-szpachlowanie-scian-aktualny-cennik-na-2025-rok-i-praktyczny-poradnik/
- Type: INDUSTRY_ARTICLE
- Region: PL (Kraków row: kompleksowa 50–65 zł/m²)
- Checked: 2026-09-13
- Quoted value: "Usługa kompleksowa (robocizna + materiały + szlifowanie) 45–80 zł/m²; Kraków 50–65 zł/m²; Szlifowanie 5–10 zł/m²"
- Unit: M2
- Price scope: LABOR_AND_MATERIAL (kompleksowa) — **not merged into the LABOR range**
- Included work: robocizna + materiał + szlifowanie
- Excluded/unknown: dedusting; VAT
- Comparability: partially comparable — comprehensive scope; used only as a local L+M cross-check.

4.
- Name: CennikiBudowlane.com.pl — położenie gładzi
- URL: https://www.cennikibudowlane.com.pl/cenniki/polozenie-gladzi/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Standard 35–60 zł/m² za dwie warstwy z gruntowaniem"
- Unit: M2
- Price scope: LABOR (z gruntowaniem)
- Included work: 2 warstwy + grunt
- Excluded/unknown: sanding status unspecified
- Comparability: partially comparable — sanding inclusion unstated.

Notes / exclusions: LABOR_L+M mixing is the main risk on this row — wolthome's comprehensive
45–80 (incl. materials) is shown separately and is NOT part of the 35–70 labor package range. For
9E.4/9E.5, the package is best defined by the owner against the LABOR band 40–60 plus itemized
dedusting.

---

## CENNIK_SKIM_CRACK-01 — Naprawa rys i pęknięć (poszerzenie, wypełnienie)

Canonical scope:
- Unit: LM
- Price scope: LABOR
- Priority: P2

Market result:
- market_min: 62
- market_max: 95
- reference_price: — (single city-varied source; Warsaw 95 / Radom 62 — not a local average)
- region: PL
- checked_at: 2026-09-13
- confidence: LOW

Methodology: the only directly comparable (poszerzenie + wypełnienie za mb, labor) source is
cenauslug 62–95 zł/mb (avg 75) with materials at 15–30 zł/mb extra — a national city-varied figure,
not Kraków. zleca.pl prices per crack (200–350 zł for a 1–2 m crack with szpachlowanie +
przeszlifowanie): unit mismatch (per-crack, not per mb) → partially comparable. Two "klamrowanie"
rows (kb.pl 150 zł/mb betonu; s-szpachlowanie 30–45 zł/mb) are **non-comparable** — structural
crack stapling (klamrowanie), not skim repair (this matches the 9E.3A research note).

Comparable source count: 2 direct (1 mb-basis + 1 per-crack partial) + 2 non-comparable.

Sources:

1.
- Name: cenauslug.pl — naprawa pęknięć ścian wewnętrznych
- URL: https://cenauslug.pl/budowa-i-remont/naprawa-pekniec-scian-wewnetrznych
- Type: INDUSTRY_ARTICLE
- Region: PL (city rows: Warszawa 95 / Radom 62)
- Checked: 2026-09-13
- Quoted value: "62–95 zł/mb (śr. 75 zł/mb)"
- Unit: LM
- Price scope: LABOR (materiały osobno 15–30 zł/mb)
- Included work: poszerzenie i pogłębienie rysy, odkurzenie, gruntowanie, dwukrotne szpachlowanie +
  szlifowanie, wtapianie taśmy zbrojącej
- Excluded/unknown: materials; VAT
- Comparability: comparable — exactly "poszerzenie + wypełnienie za mb".

2.
- Name: zleca.pl — szpachlowanie pęknięć cena
- URL: https://zleca.pl/cennik/szpachlowanie-pekniec-cena
- Type: MARKETPLACE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "200–350 zł za pęknięcie o długości 1–2 m (ze szpachlowaniem i przeszlifowaniem, bez malowania)"; per m² "20–50 zł/m²"
- Unit: PCS (per crack 1–2 m) / M2 (fallback)
- Price scope: LABOR_AND_MATERIAL (by implication)
- Included work: szpachlowanie + przeszlifowanie
- Excluded/unknown: VAT; region not stated
- Comparability: partially comparable — unit is per-crack (1–2 m), not cleanly convertible to mb.

3.
- Name: KB.pl — cennik naprawy ubytków
- URL: https://kb.pl/cenniki/uslugi/cennik-naprawy-ubytkow-w-scianie-i-suficie-aktualne-ceny/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Klamrowanie niewielkiego pęknięcia w ścianie betonowej 150,00 zł/mb"
- Unit: LM
- Price scope: LABOR
- Included work: klamrowanie (structural stapling)
- Excluded/unknown: VAT 8% (gross); structural scope
- Comparability: **non-comparable** — klamrowanie is not skim-crack repair.

4.
- Name: S-Szpachlowanie — szpachlowanie ubytków cena
- URL: https://s-szpachlowanie.pl/szpachlowanie-ubytkow-cena
- Type: CONTRACTOR_PRICE_LIST
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Klamrowanie pęknięć 30–45 zł/mb (spinanie 80–150 zł/mb); pręty helikalne 3–6 zł/szt."
- Unit: LM
- Price scope: LABOR
- Included work: klamrowanie
- Excluded/unknown: VAT
- Comparability: **non-comparable** for standard uszczelnienie — klamrowanie is structural.

Notes / exclusions: the defensible mb-basis figure is a single national city-varied source —
reported as LOW. If a Kraków/Małopolskie rate is needed for 9E.5, local contractor sourcing is
required.

---

## CENNIK_SKIM_CORNER-01 — Montaż narożników ochronnych (kątowniki)

Canonical scope:
- Unit: LM
- Price scope: LABOR
- Priority: P2

Market result:
- market_min: 12
- market_max: 22
- reference_price: 16 — methodology: central commonly-observed band (Kraków internal 12–18 / external
  15–22; cenauslug 14–22); 16 typical for an average mix of internal/external corners.
- region: Kraków + PL
- checked_at: 2026-09-13
- confidence: HIGH

Methodology: comparable = corner-bead installation embedded in skim, labor, per running meter
(material excluded). Three sources agree tightly: Kraków internal 12–18 / external 15–22,
cenauslug 14–22 (materials +5–9 zł/mb separate), e-gladz 12 zł/mb for aluminum beads. Range 12–22
MB labor.

Comparable source count: 3 independent pages.

Sources:

1.
- Name: S-Szpachlowanie — Cennik szpachlowania Kraków (firma Kraków)
- URL: https://s-szpachlowanie.pl/szpachlowanie-krakow-cennik
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków
- Checked: 2026-09-13 (re-confirmed 2026-09-14)
- Quoted value: "Obrobienie narożników wewnętrznych 12–18 zł/mb; zewnętrznych 15–22 zł/mb", 0,1–0,3 h/mb
- Unit: LM
- Price scope: LABOR
- Included work: obrobienie narożników
- Excluded/unknown: material; VAT
- Comparability: comparable — local, per mb.

2.
- Name: cenauslug.pl — montaż narożników tynkarskich
- URL: https://cenauslug.pl/budowa-i-remont/montaz-naroznikow-tynkarskich
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "14–22 zł/mb (śr. 18 zł/mb) — osadzenie, wypoziomowanie, wstępne zatarcie profilu; materiały osobno ok. 5–9 zł/mb"
- Unit: LM
- Price scope: LABOR
- Included work: osadzenie + wypoziomowanie + zatarcie profilu
- Excluded/unknown: materials (5–9 zł/mb extra); VAT
- Comparability: comparable — pure installation per mb.

3.
- Name: E-Gładź — gładź cena za m2 (usługi dodatkowe)
- URL: https://e-gladz.pl/gladz-cena-za-m2
- Type: CONTRACTOR_PRICE_LIST
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Montaż narożników aluminiowych 12 zł/mb"
- Unit: LM
- Price scope: LABOR
- Included work: montaż narożników aluminiowych
- Excluded/unknown: material; VAT
- Comparability: comparable — bottom of the range.

Notes / exclusions: external corners carry a premium (+~3 zł/mb) over internal in the Kraków table;
both are inside the 12–22 band. Decorative aluminum profile installation is out of catalog scope.

---

## CENNIK_SKIM_LOCAL-01 — Szpachlowanie lokalne / naprawy punktowe

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P3

Market result:
- market_min: 9
- market_max: 50
- reference_price: — (spread is extreme and defect-complexity-driven; no stable mode)
- region: Kraków + PL
- checked_at: 2026-09-13
- confidence: MEDIUM

Methodology: comparable = small-area defect repair, labor, per m². The spread is expected: point
repairs are priced by defect size/complexity. Kraków local "ubytki punktowo 25–40 zł/m²";
s-szpachlowanie-wide 3–30 (with prep/material 50–80); kb.pl 9–16 (11–20 z materiałem);
pewnyfachowiec 20–50. The full observed LABOR window is 9–50; the Kraków-anchored sub-band is
25–40. Do not treat the midpoints as a central reference.

Comparable source count: 4 pages across 3 independent publishers.

Sources:

1.
- Name: S-Szpachlowanie — Cennik szpachlowania Kraków (firma Kraków)
- URL: https://s-szpachlowanie.pl/szpachlowanie-krakow-cennik
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków
- Checked: 2026-09-13 (re-confirmed 2026-09-14)
- Quoted value: "Szpachlowanie ubytków punktowo 25–40 zł/m²"
- Unit: M2
- Price scope: LABOR
- Included work: naprawa punktowa
- Excluded/unknown: VAT
- Comparability: comparable — local, punktowo.

2.
- Name: KB.pl — cennik gładzi (szpachlowanie ubytków)
- URL: https://kb.pl/cenniki/uslugi/cennik-gladzi-gipsowej-i-szpachlowania-scian-w-calej-polsce/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Szpachlowanie ubytków 9,00–16,00 zł/m²" (robocizna); 11–20 zł/m² z materiałem
- Unit: M2
- Price scope: LABOR (also L+M)
- Included work: niewielkie ubytki
- Excluded/unknown: VAT 8% (gross)
- Comparability: comparable — wide divergence vs Kraków = complexity-dependent.

3.
- Name: S-Szpachlowanie — szpachlowanie ubytków cena
- URL: https://s-szpachlowanie.pl/szpachlowanie-ubytkow-cena
- Type: CONTRACTOR_PRICE_LIST
- Region: PL (same Kraków firm, nationwide page)
- Checked: 2026-09-13
- Quoted value: "Robocizna 3–30 zł/m² (z materiałem i przygotowaniem 50–80 zł/m²)"; "całopowierzchniowo 20–30 zł/m² dla porównania"
- Unit: M2
- Price scope: LABOR (also L+M)
- Included work: szpachlowanie ubytków
- Excluded/unknown: VAT; scope-dependent
- Comparability: comparable — very wide range.

4.
- Name: PewnyFachowiec — szlifowanie gładzi cena za m2
- URL: https://pewnyfachowiec.pl/szlifowanie-gladzi-cena-za-m2/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Naprawa drobnych pęknięć czy ubytków 20–50 zł/m²"
- Unit: M2
- Price scope: LABOR (in the context of gładź service)
- Included work: naprawa pęknięć / ubytków
- Excluded/unknown: VAT
- Comparability: comparable — drobne ubytki.

Notes / exclusions: catalog §13 lists this row as an OWN_PRICE candidate; the market evidence shows
a real but highly complex-dependent band. For 9E.4/9E.5 the owner should define an own per-m² defekt
rate (e.g. Kraków 25–40 anchor) rather than importing the wide market window.

---

## CENNIK_SKIM_SQ-01 — Gładź pod wyższą klasę z kontrolą lampą smugową (S3/S4)

Canonical scope:
- Unit: M2
- Price scope: LABOR
- Priority: P3

Market result:
- market_min: 60
- market_max: 80
- reference_price: —
- region: PL (+ Kraków strip-light mention, no premium rate)
- checked_at: 2026-09-13
- confidence: LOW

Methodology: catalog comparability allows this row **only** where the source explicitly describes
skimming/sanding under strip light (lampa smugowa / pod światło boczne / pod LED). Three priced
sources qualify by wording: CennikiBudowlane "Premium 60–80 zł/m² (2 warstwy), Q3 — 'brak nierówności
w świetle padającym' — droższa o 30–50%"; itodesign "3 warstwy 60–80 (pod LED)" + "szlifowanie 'na
lustro' dodatkowe 10–20"; s-szpachlowanie Kraków mentions gładź "pod światło boczne lub lampy LED"
at 35–55 but without a separate premium rate → partially comparable. wolthome confirms qualitatively
that strip-light quality costs more. Because the priced rows rest on the same likely content network
(itodesign) plus one clean premium datapoint (CennikiBudowlane), confidence is LOW. **S1–S4 / Q
labels are quoted verbatim from the sources and are not mapped further** (9E.3A §11).

Comparable source count: 3 priced (1 clean premium + 2 partial) + 1 qualitative.

Sources:

1.
- Name: CennikiBudowlane.com.pl — położenie gładzi
- URL: https://www.cennikibudowlane.com.pl/cenniki/polozenie-gladzi/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "Premium 60–80 zł/m² (2 warstwy); Q3 — 'brak nierówności w świetle padającym' — droższa o 30–50%"
- Unit: M2
- Price scope: LABOR
- Included work: klasa premium Q3 (wording as in source; no S/Q mapping by us)
- Excluded/unknown: sanding status unspecified; net prices; VAT
- Comparability: comparable — verbatim "w świetle padającym".

2.
- Name: S-Szpachlowanie — Cennik szpachlowania Kraków (firma Kraków)
- URL: https://s-szpachlowanie.pl/szpachlowanie-krakow-cennik
- Type: CONTRACTOR_PRICE_LIST
- Region: Kraków
- Checked: 2026-09-13 (re-confirmed 2026-09-14)
- Quoted value: "Gładź gipsowa (1–3 mm) 35–55 zł/m² … wymaga szlifowania: tak … wykonanie pod światło boczne lub lampy LED"
- Unit: M2
- Price scope: LABOR
- Included work: gładź pod światło boczne / lampy LED
- Excluded/unknown: no separate premium rate; VAT
- Comparability: comparable as an explicit strip-light mention, but **no dedicated premium line** —
  partially comparable for the premium tier.

3.
- Name: itodesign.pl — ile kosztuje szpachlowanie ścian
- URL: https://itodesign.pl/ile-kosztuje-szpachlowanie-scian-cennik-i-od-czego-zalezy/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: "3 warstwy 60–80 zł/m² (efekt „pod LED”)"; "szlifowanie „na lustro” dodatkowe 10–20 zł/m²"
- Unit: M2
- Price scope: "robocizna z podstawowym materiałem" (L+M-leaning)
- Included work: efekt pod LED / lustro
- Excluded/unknown: VAT; premium materials extra
- Comparability: comparable wording ("pod LED" / "na lustro"); content-network caveat as SKIM_3L.

4.
- Name: Wolthome — cennik szpachlowania 2025
- URL: https://wolthome.pl/poradnik/ile-kosztuje-szpachlowanie-scian-aktualny-cennik-na-2025-rok-i-praktyczny-poradnik/
- Type: INDUSTRY_ARTICLE
- Region: PL
- Checked: 2026-09-13
- Quoted value: no figure — "Ustal standard gładkości, bo 'pod lampę' kosztuje więcej niż 'pod normalne światło'"
- Unit: none
- Price scope: n/a
- Included work: qualitative confirmation of a premium for strip-light quality
- Excluded/unknown: —
- Comparability: qualitative only.

Notes / exclusions: SKIM_SQ must never be presented as an S3/S4 "market price" — the sources use
their own wording ("Premium", "Q3 — w świetle padającym", "pod LED", "na lustro") and the compiler
only reproduces that wording. The Kraków firm's strip-light mention carries no separate rate, which
keeps the local premium open.

---

## 17. Potential OWN_PRICE candidates (Batch A)

Items where 9E.4/9E.5 should consider an **owner-defined** price (with an OWN_PRICE source in the
9E.1 model) instead of importing a market range. No final owner price is assigned here.

| Code | Reason |
|---|---|
| CENNIK_PREP_CLEAN-01 | **INSUFFICIENT market evidence.** Post-sanding substrate vacuuming is never priced standalone in the checked sources; it is normally folded into gładź/malowanie or billed by the hour. |
| CENNIK_PREP_PROT-01 | Thin, floor-anchored evidence ("od 5 zł/m²"); floor protection is usually included or flat-rated by contractors (catalog §13 flags it). |
| CENNIK_PREP_FLEECE-01 | Single proxy tier (fiberglass wallpaper removal 35–64 zł/m²); dedicated flizelina removal is not priced standalone. |
| CENNIK_PREP_DEGR-01 | Single source (10–15 zł/m²); degreasing is normally bundled with substrate washing/prep. |
| CENNIK_PRIM_ADH-01 | Component evidence only (20–40 zł/litr material; 5–10 zł/m² uplift; standard labor 5–8). No direct per-m² market quote; company/product-specific. |
| CENNIK_PRIM_HIGH-01 | Single-source labor (10–15 zł/m² double coat) with separate material; double-priming is usually a custom premium. |
| CENNIK_SKIM_3L-01 | Direct 3-coat quotes limited to one suspected content network (60–80 zł/m²); market usually prices 2x + third-layer add-on (+12–18) — candidate to fold into own package pricing. |
| CENNIK_SKIM_LOCAL-01 | Real but extremely complex-dependent band (9–50 zł/m²); recommended owner rate anchored on Kraków 25–40. |

(Remaining catalog OWN_PRICE candidates — GK_SCREW, PAINT_MASK, PAINT_MULTI, MC_STAIRS — belong to
Batches B–E and are not part of 9E.3A.)

---

## 18. Source archival note

- Each source above is recorded as **URL + checked_at + relevant quoted value/scope + a short
  evidence note** — no full-page content is copied (respecting the 9E.1 archival contract).
- **Dynamic-page caution:** `s-szpachlowanie.pl/szpachlowanie-krakow-cennik`, `malarzkrakow.pl/cennik/`,
  `e-gladz.pl/*`, `wzbudowa.pl/cennik-uslug-malarskich/` and the kb.pl price tables are live price
  lists / regularly updated cost pages. They should be **re-checked during 9E.4 before any data
  load**; the figures in this file are valid as of `checked_at`.
- Deprecated/checked-but-unusable references recorded for traceability: cenauslug.pl Kraków
  sub-pages for gruntowanie / odtłuszczanie dachu / usuwanie tapet / odgrzybianie returned **HTTP 410
  (dead)** on 2026-09-13 for the city rows; the national pages listed above were live. Any figure
  re-used from a live page in later stages must be re-validated against the site at that time.
- Outside-region supplementary references (Warszawa Derty Serwis; Łódź SLIM-POL) are marked and used
  only as context, never as local anchors.
- Suspected content-network duplication: sccot.pl ↔ itodesign.pl publish near-identical skim figures;
  the s-szpachlowanie.pl Kraków table and its two nationwide article pages are one publisher;
  kb.pl city and article pages are one publisher. These are flagged per item and not counted as
  independent where noted.

---

## 19. Cross-check (9E.3A §19)

- **Traceability:** every numerical range above maps to at least one verbatim quote listed in the
  item's Sources; no figure is invented.
- **URL duplication / independence:** flagged per the archival note (sccot/itodesign; single-publisher
  pages; the shared kb.pl city row across PRIM_STD/PRIM_PAINT counted once).
- **No labor / L+M mixing:** each item's range is built from one scope class; L+M rows (wolthome
  kompleksowa, kb "z materiałem", PREP_MOLD labor-only row) are recorded separately, per the 9E.1
  invariant.
- **Units:** M2 and LM kept compatible; per-crack pricing (zleca) and per-litre pricing (NewBridge
  adhesion primer) are recorded but never converted; no FLAT↔M2 conversion anywhere.
- **Nationwide sources:** every `Region: PL` source is marked and used as supplementary context only
  where local evidence is insufficient.
- **No Q/S inference:** SKIM_SQ quotes the sources' own wording ("pod światło boczne", "pod LED",
  "Premium", "w świetle padającym"); no S1–S4/Q1–Q4 values are invented or mapped from labels.
- **No invented prices:** items without a defensible quote are `INSUFFICIENT` (PREP_CLEAN) or
  component-only (PRIM_ADH, PRIM_HIGH) with market range left empty.
- **Catalog integrity:** all 20 codes (CENNIK_PREP_* / CENNIK_PRIM_* / CENNIK_SKIM_*) are taken
  verbatim from `docs/price-research-catalog.md` (Batches A); PL labels match the catalog.

---

## 20. Research summary (for `docs/development-progress.md`)

- Items researched: **20 / 20** Batch A catalog items (Preparation 7 · Priming 4 · Skim 9).
- Sources: **40 referenced evidence pages** (37 with usable numeric quotes; 3 qualitative /
  non-comparable context pages), of which **6 are Kraków / Małopolskie-region anchors** (5 Kraków
  firms + kb.pl Kraków municipal row) and **34 are Poland-wide**, incl. 2 outside-target-region
  supplementary (Warszawa, Łódź).
- Confidence distribution: **HIGH 6** (PREP_WALLP, PREP_SCRAPE, SKIM_1L, SKIM_2L, SKIM_SAND,
  SKIM_CORNER) · **MEDIUM 7** (PREP_PROT, PREP_MOLD, PRIM_STD, PRIM_PAINT, SKIM_3L, SKIM_PKG,
  SKIM_LOCAL) · **LOW 6** (PREP_FLEECE, PREP_DEGR, PRIM_ADH, PRIM_HIGH, SKIM_CRACK, SKIM_SQ) ·
  **INSUFFICIENT 1** (PREP_CLEAN).
- Insufficient-evidence items: **1** (CENNIK_PREP_CLEAN-01).
- OWN_PRICE candidates after research: **8** (PREP_CLEAN, PREP_PROT, PREP_FLEECE, PREP_DEGR,
  PRIM_ADH, PRIM_HIGH, SKIM_3L, SKIM_LOCAL).
- Key Kraków anchors: s-szpachlowanie.pl Kraków skim table (1L 35–50 · 2L 55–75 · szlif 10–16 ·
  narożniki 12–18/15–22 · punktowo 25–40 · strip-light mention 35–55); malarzkrakow.pl (protection od
  5 · gruntowanie od 5 · scraping od 10 · wallpaper od 10 zł/m², net labor); kb.pl municipal table
  (Kraków gruntowanie 7,73 zł/m² brutto labor).