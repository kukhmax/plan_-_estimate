# Batch D research evidence — Kraków market research — Microcement / mikrocement (9E.3D)

Research date: **2026-09-14** — web research + documentation only.
Branch: `stage-9`. Status: **COMPLETE**. Hard rule: **no seeds, no `PriceItem.price`, no migrations,
no backend/frontend code** (9E.3 contract).

Scope: the **6 canonical microcement items** from `docs/price-research-catalog.md` §10 (Batch D).
Every figure below is a **verbatim quote** read from the opened source page
(`checked_at 2026-09-14`); search snippets were never used. No price is implemented.

---

## 1. Purpose — labor vs full-system separation preserved

The catalog (§10) requires the **labor-only / full-system** distinction to survive research
unchanged (`LABOR` vs `LABOR_AND_MATERIAL`). Microcement is **predominantly quoted as a complete
system** ("pod klucz", "kompleksowo", "all-in robocizna + materiał"); true labor-only rates are
rare and come mostly from national price guides. Substrate preparation, primer/epoxy leveling,
fiberglass mesh and **hydroizolacja (membrane)** are scope items that sources include or price
separately — they are recorded per source, **never silently assumed**.

This file also records, separately, the material/system context (manufacturer/store) — it is
**not** contractor market evidence and must not be mixed into the labor or complete-system ranges
(9E.1 §7, §11).

## 2. Terminology research — actual market wording

The Polish market uses several overlapping terms; **not all have identical scope**:

- **mikrocement** — the dominant generic service term.
- **mikrobeton / mikrowylewka / beton cienkowarstwowy** — used interchangeably by contractors for
  the same thin-layer system (JAK Chemia, Monolite).
- **beton ciré** — French-origin term for the same material; **"beton cire Kraków" searches
  returned almost exclusively concrete-cutting (cięcie betonu) and ready-mix concrete
  (betoniarnia) vendors** — i.e. the term is not a distinct local service in this market and was
  treated as a synonym lead only.
- **efekt betonu / beton architektoniczny** — marketing wording for the decorative effect (used by
  ekipazlecenia "Mikrocement / efekt betonu"); **architectural concrete (beton architektoniczny)
  as a thick-cast product is a different technology** and excluded.
- **zestaw na posadzkę / ścianę / łazienkę / schody** — manufacturers sell **10 m² ready kits**
  (Conbar, Festfloor); kit price ÷ 10 m² = a published material PLN/m² (see §10).
- **stopień / schodek** — the market prices stairs **per step (tread + riser)** OR per **m²**,
  depending on the firm; **per bieg (flight)** for whole stairs. Units are **not converted**
  anywhere in this file (catalog §15).
- **hydroizolacja / membrana / taśmy hutbetum** — wet-zone waterproofing; priced inside the shower
  system (sanitmax, Monolite, profesorbudownictwa) or as a separate line (+40–90 zł/m²).
- **lakier / impregnat / sealer** — the final PU lacquer; "the single most expensive component"
  (cementibeton.pl); usually included in complete-system quotes, never priced as a standalone
  surface service.

## 3. System / brand recording

Brands actually encountered (every source labeled accordingly; **no brand made authoritative**):

| Brand / system | Role | Seen in |
|---|---|---|
| Resistone® (Hiszpania) | microcement + microbeton system | Monolite (Kraków), Pracownia Betonu (Warszawa) |
| Festfloor (Life, GO!, Festwall, HYDROFEST, TITAN) + lakier PU FEST 2K, archiFEST | PL producer | Festfloor, cementibeton.pl |
| Conbar (CONGRUNT, CONCONTACT, CONONE(+Waterproof), CONDUO(+Waterproof/Loft/Loft Waterproof), CONEPOX, CONPU 2K, CONTOP 1K, CONCOVER PRO, CONPRIMER) | PL producer (Mirzec, Świętokrzyskie) | Conbar shop |
| Topciment | producer (Hiszpania) | Topciment PL |
| Remmers (lakier PU) | sealer | Technodecor |
| Kerakoll · Topciment · Luxury Concrete · Ferber | system brands cited by abcremontu | abcremontu.pl |
| Mikrobet (Tychy), Conbar, Monolite, JAK Chemia, Zement pracowniabetonu.pl | application firms | various |

Different systems have different consumption and application processes; brand-specific evidence
stays labeled as such (§11). A Français-spanish producer's PLN price guide (Topciment) is a market
**overview**, not local labor evidence — classified MANUFACTURER.

## 4. Geographic priority — source counts (per canonical item)

| Code | LOCAL_KRAKOW | MALOPOLSKIE/REGIONAL | POLAND_SUPPLEMENTARY | Basis |
|---|---|---|---|---|
| CENNIK_MC_WALL_L-01 | 0 | 0 | 4 (poilerobocizna, abcremontu, profesorbudownictwa robocizna, murator robocizna-general) | no Kraków labor-only microcement quote found |
| CENNIK_MC_WALL_S-01 | 1 (Monolite) | 2 (pracowniabetonu.pl, JAK Chemia) | 6 (adrem, profesorbudownictwa, Topciment*, ekipazlecenia, technodecor, vnetrze-general) | 1 local wall-specific + 2 regional unified L+M system quotes |
| CENNIK_MC_FLOOR_L-01 | 0 | 0 | 3 (poilerobocizna podłogi, murator robocizna, abcremontu general) | no Kraków labor-only floor quote found |
| CENNIK_MC_FLOOR_S-01 | 1 (Monolite posadzki) | 2 (pracowniabetonu.pl, JAK Chemia) | 7 (murator, vnetrze, adrem, profesorbudownictwa podłoga, technodecor, Festfloor* L+M context, Topciment*) | 3 local/regional floor-specific L+M system quotes |
| CENNIK_MC_SHOWER-01 | 1 (Monolite łazienka ściany) | 1 (pracowniabetonu.pl, strefa mokra — price not split) | 5 (sanitmax**kraków, profesorbudownictwa łazienka, abcremontu prysznic, Topciment*, pryszcionline-weak) | 1 local wet-zone quote + explicit Kraków-city guidance (sanitmax) |
| CENNIK_MC_STAIRS-01 | 1 (Monolite, m²) | 0 | 7 (Festfloor*, vnetrze, technodecor, adrem, profesorbudownictwa, poilerobocizna robocizna, pracowniabetonu.eu) | both m² and per-step pricing exist; unit model unsolvable from market alone |

\* = MANUFACTURER/market-overview source (counted as national context, never as local pricing).
\*\* sanitmax explicitly says its widełki "obejmują Warszawę, Kraków i Wrocław" and were
"zweryfikowane w 12 firmach z Warszawy, Krakowa, Wrocławia, Poznania i Gdańska" — a national
calculator/city-mapping source with an explicit Kraków band, **not** a Kraków-firm quote.

### 4.1 Kraków-local negative-result audit (documented)

Kraków / Małopolskie-local pages checked that have **no** usable microcement price row (supporting
the source-count ceilings above):

- https://conbar.pl/mikrocement/krakow/ — landing only; "Koszty zależą od…", no prices.
  *(producer, Mirzec/Świętokrzyskie, marketing Kraków)*
- https://mikrobet.pl/mikrocement-krakow/ — "Cena zależy od rodzaju powierzchni…", no prices.
  *(Tychy firm marketing Małopolska)*
- https://www.oferteo.pl/mikrocement/krakow and .../wieliczka — marketplace; **no firm publishes a
  per-m² rate** (all "Zapytaj o ofertę"); only the Poland-wide auto-average "20 326–35 660 zł
  netto / średnio 27 993 zł" (project-scale, not per m²). Kraków firms listed but unpriced:
  Intero, MALIFLOOR, Dorothea (mikrocement+żywica), R2.POSADZKI ("mikrocement na podłogę"),
  BodChem (posadzki żywiczne/mikrocement), Serwis Koncept, Termokrak (+40 km). *(marketplaces,
  Kraków + Wieliczka)*
- https://cennikibudowlane.com.pl/miasto/krakow/wykonczenia-wnetrz/ — Kraków city table; **no
  mikrocement row**. *(Kraków city table)*
- https://remonty-inplus.pl/wykonczenia-wnetrz-krakow-cennik — Kraków cennik article; **no
  mikrocement occurrence**. *(Kraków cennik article)*
- https://www.loftsurface.pl/realizacje/mikrocement-sciany-podloga-schody-krakow — HTTP 404 at check
  time (the Kraków realization page is gone; Loft Surface currently shows Warszawa/Choceń
  realizations). Not counted as Kraków-local.
- https://www.olx.pl/uslugi/krakow/q-posadzka-mikrocement/ and national `q-mikrocement` /
  `q-mikrobeton` — marketplace category pages exist and list regional adverts, but the page is
  JS-rendered and ad-level rates were **not extractable** at check time; flagged as a future
  verification channel, not scored.

**Finding for 9E.4**: Kraków publishes L+M complete-system **starting anchors** (Monolite and the
two regional unified firms at 320–400 zł/m²) but no true labor-only and no per-scope local
breakdowns. This is the opposite of the painting/skim market (Batch A/B), where local cenniki were
common — microcement is sold locally as a specialist product.

## 5. Source evidence index (19 used; exact URLs preserved — future `PriceSource` candidates)

| # | Source name | URL | Type | Region |
|---|---|---|---|---|
| S1 | Monolite — ile kosztuje mikrocement (cennik/guide) | https://monolite.pl/ile-kosztuje-mikrocement-w-2025-roku-cennik-porownania-i-praktyczny-przewodnik-z-kalkulatorem/ | CONTRACTOR_PRICE_LIST (firm guide, schemat) | Kraków (salon ul. Kard. Kominka 193) |
| S2 | Zement / MTS Poland — ile kosztuje mikrocement? Cennik od 320 zł netto | https://pracowniabetonu.pl/ile-kosztuje-mikrocement-cennik/ | CONTRACTOR_PRICE_LIST | Śląsk + Małopolska (Częstochowa/Katowice/Gliwice/Kraków) |
| S3 | JAK Chemia — mikrocement podłoga i ściany od 350 zł/m² | https://www.jakposadzki.pl/oferta/mikrocement-podloga/ | CONTRACTOR_PRICE_LIST | Małopolska (showroom Kraków, biuro Libiąż; "cała Polska") |
| S4 | ADREM — mikrocement cena za m2 2026 | https://adrem.org.pl/mikrocement-cena-za-m2/ | INDUSTRY_ARTICLE | Warszawa / Mazowsze (supplementary) |
| S5 | Murator — ile kosztuje m² posadzki z mikrocementu 2026 | https://muratordom.pl/wnetrza/prace-wykonczeniowe/ile-kosztuje-m2-posadzki-z-mikrocementu-w-2026-szokujaca-cena-za-60-m2-wady-i-zalety-aa-hGKZ-qCko-yums.html | INDUSTRY_ARTICLE | PL |
| S6 | Profesor Budownictwa — mikrocement na ścianę cena | https://profesorbudownictwa.pl/mikrocement-na-sciane-cena | INDUSTRY_ARTICLE | PL |
| S7 | Profesor Budownictwa — mikrocement do łazienki cena | https://profesorbudownictwa.pl/mikrocement-lazienka-cena | INDUSTRY_ARTICLE | PL |
| S8 | Profesor Budownictwa — ile kosztuje m² mikrocementu 2026 | https://profesorbudownictwa.pl/koszt-mikrocementu | INDUSTRY_ARTICLE | PL |
| S9 | ABC Remontu — mikrocement do łazienki cena 2026 | https://abcremontu.pl/mikrocement-do-lazienki-cena | INDUSTRY_ARTICLE | PL |
| S10 | Poile Robocizna — mikrocement cena za m² robocizny 2025 | https://poilerobocizna.pl/mikrocement-cena-za-m2-robocizny | INDUSTRY_ARTICLE (robocizna focus) | PL |
| S11 | Topciment — ile kosztuje mikrocement za m²? Cena 2026 | https://www.topciment.com/pl/nouvelle/cena-mikrocementu | MANUFACTURER | PL market view (producer) |
| S12 | Sanitmax — mikrocement pod prysznic: cena 2025 | https://sanitmax.pl/mikrocement-pod-prysznic-cena | INDUSTRY_ARTICLE (kalkulator) | Warszawa/Kraków/Wrocław cities |
| S13 | Festfloor — cena mikrocementu, ile kosztuje, stawka | https://www.festfloor.pl/mikrocement-cena/ | MANUFACTURER (+L+M context rows) | PL producer |
| S14 | ekipazlecenia.pl (ZUBRA) — cennik mikrocement / efekt betonu | https://ekipazlecenia.pl/cennik/cennik-mikrocement | CONTRACTOR_PRICE_LIST | cała Polska (Wrocław HQ; Kraków listed) |
| S15 | Vnetrze — cena mikrocementu za m² z robocizną i materiałem | https://vnetrze.pl/cena-mikrocementu-za-metr-kwadratowy-z-robocizna-i-materialem/ | INDUSTRY_ARTICLE | PL |
| S16 | Technodecor — mikrocement: cena za m² | https://technodecor.pl/mikrocement/cena/ | CONTRACTOR_PRICE_LIST | PL (Warsaw-distance pricing) |
| S17 | Conbar — Sklep (produkty/zestawy) | https://conbar.pl/produkty/ | MANUFACTURER | PL (Mirzec, Świętokrzyskie) |
| S18 | CementiBeton — mikrocement koszt m2 (2025) | https://cementibeton.pl/mikrocement-koszt-m2 | INDUSTRY_ARTICLE (material focus) | PL (Festfloor-affiliated content — see §11) |
| S19 | Pracownia Betonu — mikrocement cena za m² (Warszawa) | https://pracowniabetonu.eu/mikrocement-cena-za-m%C2%B2-ile-wynosi-koszt-materialu-i-robocizny/ | CONTRACTOR_PRICE_LIST | Warszawa (supplementary; **distinct** from S2) |
| S20 | Prysznic.Online — mikrocement pod prysznic cena 2025 | https://prysznic.online/mikrocement-pod-prysznic-cena | INDUSTRY_ARTICLE (weak) | PL |
| S21 | jak-wykonac.fun — mikrocement cena za m2 2025 | https://jak-wykonac.fun/mikrocement-cena-za-m2 | INDUSTRY_ARTICLE (**content-farm flags**) | PL — **flag / not independent** |
| S22 | Loft Surface — strona główna | https://www.loftsurface.pl/ | CONTRACTOR_PRICE_LIST (marketing "od 180 zł/m²") | PL (Warszawa/Choceń realizations) — context only |

**Content-network / duplication flags** (per catalog §12 — copied content is one data point):
- **S6–S8 (profesorbudownictwa)** are three separate articles **of one publisher**; their numbers
  are internally coherent (walls 250–400, wet zone 380–580, floors 300–450/350–500, stairs
  350–550/600–900). Counted as **one content origin** (S6 anchor + S7/S8 partial adds).
- **S18 (cementibeton)** endorses `PU FEST 2K` — a Festfloor product — and its material-echelon
  structure mirrors Festfloor's own guidance; treated as **Festfloor-affiliated content** (S13
  family), kept for material context only.
- **S5 (murator)** press photos credited to Festfloor and Conbar (co-marketing) but the numbers are
  independently researched — kept as an independent INDUSTRY_ARTICLE.
- **S21 (jak-wykonac.fun)**: `.fun` TLD, corrupted numerals ("250500 zł/m²"), missing "FF" chart
  reference, an unrelated article cluster (container shooting range) — classic content farm,
  internally contradictory (stated wall range 450–600 **below**/above floor 250–500 vs its own FAQ
  "podłoga jest wyższa"). **Not counted as independent**; a few figures referenced only with flags.
- **S20 (pryszcionline)** partially overlaps the sanitmax/profesorbudownictwa figure families;
  only its material-system figure (90–100 zł/m²) and labor-share statement are retained as context.
- **Not used** (excluded as unreachable/unprocessed content-network clones): apartamentywazewskiego.pl,
  pewnyfachowiec.pl, luxbuddesign.pl, moje-remonty.pl, twojekarnisze.pl, nieruchomosci-ceny.pl,
  posadzki-remont.pl, remwyk.pl, wzbudowa.pl, awbud.pl, mybudio.eu.

## 6. Summary table (Batch D — 6 items)

| Code | PL name | Unit | Scope | Local range | Suppl. PL range | Reference | Confidence | Local src | Reg. src | Nat. src | Checked |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CENNIK_MC_WALL_L-01 | Mikrocement na ściany — robocizna | M2 | LABOR | — | 100–180 (clean 100–160) | 140 | MEDIUM | 0 | 0 | 4 | 2026-09-14 |
| CENNIK_MC_WALL_S-01 | Mikrocement na ściany — pełny system z materiałem | M2 | LABOR_AND_MATERIAL | 320–650 (dry-interior core 320–400) | 250–400 | 350 | MEDIUM | 1 | 2 | 6 | 2026-09-14 |
| CENNIK_MC_FLOOR_L-01 | Mikrocement na posadzkę — robocizna | M2 | LABOR | — | 180–250 (broad 180–400) | 220 | MEDIUM | 0 | 0 | 3 | 2026-09-14 |
| CENNIK_MC_FLOOR_S-01 | Mikrocement na posadzkę — pełny system z materiałem | M2 | LABOR_AND_MATERIAL | 320–400 (≤50 m² tier to 400) | 300–550 (typical 350–500) | 380 | HIGH | 1 | 2 | 7 | 2026-09-14 |
| CENNIK_MC_SHOWER-01 | Mikrocement — strefa prysznicowa (system z hydroizolacją) | M2 | LABOR_AND_MATERIAL | 450–650 (łazienka ściany, L+M, hydro incl.) | 380–580 (brutto to 380–720) | 550 | MEDIUM | 1 | 1 | 5 | 2026-09-14 |
| CENNIK_MC_STAIRS-01 | Mikrocement na schody | M2 (or per step — record basis) | LABOR_AND_MATERIAL | 750–950 (m², stopnica+podstopnica) | M²: 350–900; per step: 400–1300 | — | LOW | 1 | 0 | 7 | 2026-09-14 |

**No implementation decision yet — research evidence only (9E.3D §6).**
Confidence key: HIGH = 3+ genuinely comparable local/regional sources; MEDIUM = 2+ useful
comparable sources or strong local anchor + supplementary; LOW = single usable source / scope
ambiguity; INSUFFICIENT = no defensible comparable numerical range.

---

## 7. CENNIK_MC_WALL_L-01 — Mikrocement na ściany — robocizna (M2, LABOR)

- **Canonical scope**: wall application labor only (owner supplies system materials), per m².
  **Prio P1.** Substrate prep recorded, never assumed.
- **Market result**:
  - `local_market_min` / `local_market_max`: **null / null** — no Kraków/Małopolskie firm quotes a
    wall labor-only rate (labor-only is not how Kraków microcement is sold; S1/S2/S3 all quote
    complete systems).
  - `supplementary_pl_min` / `supplementary_pl_max`: **100 / 180** zł/m² (LABOR; "clean" wall
    cluster 100–160). Sources: S10 "Robocizna mikrocementu na ścianach to zazwyczaj **100–160**;
    120–180 zł/m² dla ścian"; S6 "Robocizna … startuje **od 150 zł/m²** przy prostej aplikacji na
    gładką powierzchnię"; S9 big-city application "**120–160 zł/m²**", smaller towns "**80–110**".
  - `reference_price`: **140 zł/m²** — method: central value of the wall-labor cluster once the
    big-city premium is applied (S10 100–160/120–180, S6 od 150, S9 120–160 big cities). A
    commonly-observed figure, not an arithmetic mean; the murator S5 broad labor band (180–400,
    floors-leaning) is deliberately not folded in.
  - **Confidence: MEDIUM** — 3 usable national labor sources converge (S10, S6, S9) but **none is
    local** and S9 is general (not wall-only).
- **Source counts**: LOCAL 0 · REGIONAL 0 · NATIONAL 4 (S10, S6, S9, S5-labor-general).
- **Methodology**: only explicit labor-only rows used (S10 walls; S6 robocizna; S9 "sama aplikacja
  bez materiału"). The S5 labor figure (180–400) is floors/general and kept out of the clean band.
  No labor value was derived by subtracting material (9E.1 §11).
- **Included work**: application (2–3 labor-light layers walls, S10), primer within labor bracket
  (S10 "gruntowanie … 10–15% całkowitej robocizny"), final layers. S6 hourly-reference 80–120 zł/h,
  4–6 h/m² on walls.
- **Excluded / unknown**: all system/material prices; substrate leveling (S10 prep = 20–30% of
  labor, billed within the labor but recorded separately per source), hydroizolacja (no wall labor
  source prices a membrane), VAT (UNKNOWN on S10/S6/S9).
- **Region note**: S10 explicitly names **Kraków / Warszawa** as premium labor zones: "Warszawa czy
  Kraków mają stawki premium"; "W dużych miastach robocizna mikrocementu jest wyższa o
  **20–30%**". This is a **city-premium statement**, not a Kraków-firm quote — recorded with that
  caveat for 9E.4 regional-coefficient decisions.
- **Minimum charge**: S10 small projects (e.g. 20 m²) carry higher rates; no published fixed
  minimum. Recorded in §13.

## 8. CENNIK_MC_WALL_S-01 — Mikrocement na ściany — pełny system z materiałem (M2, LABOR_AND_MATERIAL)

- **Canonical scope**: complete thin-layer system — primer + leveling + microcement layers +
  sealer — **incl. material**, per m²; substrate-prep scope must be stated. **Prio P1.**
- **Market result**:
  - `local_market_min` / `local_market_max`: **320 / 650** zł/m² (LABOR_AND_MATERIAL). The clean
    **dry-interior wall core is 320–400** (S1 general interior 250–400; S2 "od 320 netto"; S3
    "od 350 netto"); the upper local bound **450–650** is S1's **bathroom walls** figure (hydro
    included) and is scope-separate.
  - `supplementary_pl_min` / `supplementary_pl_max`: **250 / 400** zł/m² L+M (dry walls): S4 ściany
    250–400; S6 total 250–400; S8 ściana 280–380; S14 "od 326"; S16 300–500 (walls+floors).
  - `reference_price`: **350 zł/m²** — method: the local "od" anchors cluster at 320/326/350 (S2,
    S14, S3) and S1's interior band tops at 400; national dry-wall band 250–400 centers ≈325. 350
    is the common local-positioned value, chosen over the wider national mid (≈325) because the
    Kraków premium is documented by S10 (+20–30%) and S12/S5 big-city deltas.
  - **Confidence: MEDIUM** — strong local/regional L+M system trio (S1, S2, S3) **but only S1
    separates walls**; S2/S3 quote unified surface rates that include walls. National wall-specific
    support (S4, S6, S8) is solid → borderline HIGH, kept MEDIUM because local wall-exclusive
    comparability is partial.
- **Source counts**: LOCAL 1 (S1) · REGIONAL 2 (S2, S3) · NATIONAL 6 (S4, S6/S7/S8-origin, S11*,
  S14, S16, S15-general).
- **Substrate-prep scope (stated per source)**: S1 includes substrate prep (szlifowanie/
  wyrównanie/dust/moisture measurement) and hydro in wet zones; S2 "przygotowanie i gruntowanie
  podłoża"; S3 prep is a pricing variable; S6 prep inside the 250–400 total; S16 includes "ocena
  techniczna i przygotowanie podłoża", resin primers and full-surface fiberglass mesh — a **higher
  CLI detail than a bare wall system**; S14 prices prep individually ("wycena indyw.").
- **Included operations**: multiple microcement layers, sealer/lacquer (S1 topcoat; S14
  impregnacja/lakier; S16 PU Remmers), detail work (S1 cokoły/narożniki/odpływy).
- **Excluded / unknown**: leveling/self-levelling compounds (S8 hidden costs 35–55 zł/m²), crack
  repair, tile removal (S6 kucie 100–200; S7 skuwanie 35–70), reinforcement mesh (S16 includes it,
  S18 prices it separately 25–45) — all per-source, none silently folded into the range.
- **VAT**: S1/S2/S3 netto; S4/S6/S7/S8/S14 UNKNOWN; S16 netto (8%/23% rules); S11 netto typical
  (+23%). **Band mixes net/A-brutto; flagged for 9E.4**, not re-adjusted here.
- **Comparability**: "complete wall system" is the closest market-defensible scope. Bathroom-wall
  prices (S1 450–650) are **not** merged into the dry-wall band — they belong to the wet-zone item
  (§11 row) and are cross-referenced.

## 9. CENNIK_MC_FLOOR_L-01 — Mikrocement na posadzkę — robocizna (M2, LABOR)

- **Canonical scope**: floor application labor only, per m²; floor flatness prep almost always
  extra. **Prio P2.**
- **Market result**:
  - `local_market_min` / `local_market_max`: **null / null** — no Kraków labor-only floor quote.
  - `supplementary_pl_min` / `supplementary_pl_max`: **180 / 250** zł/m² LABOR (clean cluster);
    broad S5 band to 400 recorded separately. Sources: S10 "Na podłogach robocizna mikrocementu
    wynosi średnio **180–250 zł/m²**" (approx 220 at 50 m², ~170 at 200 m²; floors +40–50% vs
    walls); S5 robocizna **180–400** (consumer-facing, floors-leaning).
  - `reference_price`: **220 zł/m²** — method: S10's mid-volume (50 m²) floor rate ≈220 and its
    band center 215; S9 application labor caps at 160 (general) below the floor-specific S10
    figures — 220 is the floor-specific common value.
  - **Confidence: MEDIUM** — S10 (floor-specific, well-developed) + S5 (broad); no local row, S9
    general only.
- **Source counts**: LOCAL 0 · REGIONAL 0 · NATIONAL 3 (S10, S5, S9-general).
- **Methodology**: only explicit labor-only rows for floors (S10) / general application (S9) /
  consumer labor band (S5) used; no subtraction anywhere.
- **Included work**: 3–4 floor layers (S10), primer (inside labor percentage), floor prep
  documented as "usunięcie starych powłok i wyrównanie … 30% robocizny" (S10) — i.e. prep is a
  separate surcharge inside floor labor, never the flatness system itself.
- **Excluded / unknown**: self-levelling (wylewka samopoziomująca S8 35–55; S15 warns microcement
  "to nie wylewka wyrównująca"), grinding/leveling of substrate (S5 30–80), hydroizolacja,
  VAT (UNKNOWN).
- **Minimum charge**: S10 small-project markups; S10 >100 m² −15–25%; recorded in §13.

## 10. CENNIK_MC_FLOOR_S-01 — Mikrocement na posadzkę — pełny system z materiałem (M2, LABOR_AND_MATERIAL)

- **Canonical scope**: full floor system incl. material, per m². **Prio P2.** Wall-system prices
  are not floor prices (catalog note).
- **Market result**:
  - `local_market_min` / `local_market_max`: **320 / 400** zł/m² (L+M). Anchors: S2 "od 320
    netto" (posadzki explicit); S3 "od 350 netto" (podłogi explicit); S1 posadzki ≤50 m² **400**,
    >50 m² **360–380**. Upper tier for small residential floors (≤50 m²) = 400.
  - `supplementary_pl_min` / `supplementary_pl_max`: **300 / 550** zł/m² (L+M; typical 350–500):
    S15 350–550 (>50 m²); S5 350–500 "gotowa posadzka", tiers 300–450 / 450–600 / 600–750 (small/
    detail); S4 podłogi 300–500; S8 podłoga 350–500; S16 300–500 (min 50 m², mesh+prep incl);
    S13* 250–400 (avg 280–380).
  - `reference_price`: **380 zł/m²** — method: S1 local floor mid 380 coincides with S15 >50 m²
    low bound and S13* avg 280–380; S5 "typical" 450–600 sits higher because it bundles small-area
    and prep-heavy jobs. 380 = the defensible **local standard-floor figure**; the national
    consumer typical is visibly higher (~450–600). Discrepancy documented for 9E.4 (§15).
  - **Confidence: HIGH** — three local/regional floor-specific L+M quotes (S1, S2, S3) + a large
    coherent national floor cluster (S5, S15, S4, S8, S16, S13*, S11*). Note: two local anchors
    are "od" minimums (S2 320, S3 350), which slightly reduces range precision but not
    comparability of the underlying floor system.
- **Source counts**: LOCAL 1 (S1) · REGIONAL 2 (S2, S3) · NATIONAL 7 (S5, S15, S4, S8, S16, S13*,
  S11*).
- **Substrate-prep scope**: S1 floors quoted for prepared substrate (prep listed as separate work
  step + price driver); S16 includes prep + resin primers + **full-surface fiberglass mesh** —
  higher CLI; S5 bills prep separately (szlifowanie+wyrównanie 30–80; warstwa sczepna+siatka
  40–120; pęknięcia 20–50; gruntowanie 10–25). **None of these prep packages is merged into the
  S-range.**
- **Included operations**: base+finish layers, two PU lacquer coats on floors (S18/S5), details
  (cokoły 40–80 zł/mb S15; narożniki; odpływy).
- **VAT**: S1/S2/S3 netto; S15 netto; S5 UNKNOWN (gross); S11 netto+23%; S16 netto (8/23). Mixed —
  flagged.
- **Minimum charge / area tiers**: S3 **min 80 m²**; S16 **min logistyczne 50 m²**; S15
  **<25–30 m² → flat rate (ryczałt)**, per-m² equivalent up to ~1200 zł/m² on tiny areas; S1 tier
  break at 50 m²; S11 small floor ≤30 m² 550–650; S4 tiers ≤30 / 30–100 / >100 (350–450/300–400/
  250–350). All recorded in §13 — none folded into the M2 range.

## 11. CENNIK_MC_SHOWER-01 — Mikrocement — strefa prysznicowa (system z hydroizolacją) (M2, LABOR_AND_MATERIAL)

- **Canonical scope**: shower-zone microcement **incl. membrane (hydroizolacja)**, per m²;
  membrane + fall (spadek) requirements stated. **Prio P2.**
- **Critical distinction** (9E.3D §1): MICROCEMENT APPLICATION ≠ WET-ZONE SYSTEM WITH WATERPROOFING.
  Only sources that include the membrane are row-comparable; application-only prices are context.
- **Market result**:
  - `local_market_min` / `local_market_max`: **450 / 650** zł/m² (L+M) — S1 "Łazienka – ściany
    **450–650 zł/m²**" (Kraków; includes hydroizolacja, substrate prep, base+finish, topcoat,
    details). This is a *bathroom-wall* figure with wet-zone scope and hydro included — the closest
    Kraków local wet-zone system evidence.
  - `supplementary_pl_min` / `supplementary_pl_max`: **380 / 580** zł/m² L+M wet zone (S7 "Strefa
    mokra (prysznic) 380–580" with material 120–200 + labor 260–380); to **720** brutto on the
    inlet-adjusted city band (S12 "380 do 720 zł brutto za metr kwadratowy … w strefie
    prysznicowej", widełki explicit for Warszawa/Kraków/Wrocław).
  - `reference_price`: **550 zł/m²** — method: three independent origins converge near 550: S1 local
    bathroom-wall mid (550), S11 "jedna łazienka ~550" (incl. membrana), S7 wet-zone mid (480).
    550 = the commonly-observed wet-zone L+M system figure (brutto on S12, mixed otherwise).
  - **Confidence: MEDIUM** — 1 local anchor (S1) + 2–3 national wet-zone-specific sources (S7, S12,
    S11*) + material context (S9, S18). Below HIGH because the local source is bathroom-wall rather
    than shower-floor, and scope (membrane/fall/drain) differs across sources.
- **Source counts**: LOCAL 1 (S1) · REGIONAL 1 (S2 — "strefa mokra" price driver only, no split)
  · NATIONAL 5 (S7, S12**kraków, S9, S11*, S20-weak).
- **Waterproofing / fall / sealers — per source**:
  - S1: hydro in wet zones included; shower surcharge + detail (nisze, odpływ, narożniki) + antislip
    topcoat listed as add-ons. No spadek (fall) figure stated.
  - S12: **brutto shower 380–720/m²**, material 35–50% of it; membrane system row "prysznicowy z
    membraną" at **200–250 zł/m² material** (S9) vs sanitmax material-only systems 90–260; walk-in
    brodzik 1,5 m² **2 800–5 400 zł brutto** with explicit splits (wylewka ze spadkiem 600–900;
    hydroizolacja z taśmami 350–500; materiał z lakierem 250–380; robocizna 1 400–2 200; odpływ
    liniowy 200–400); heated floor +15% labor; over-tiles +25% labor.
  - S7: wet-zone sealing +40–80; walk-in membrane +60–90 (nasiąkliwość 0,02%).
  - S9: warning — crews under **70 zł/m²** typically skip the membrane (leak at 8–14 months).
- **Minimum / area**: S11 "jedna łazienka ~550, >100m² protects 300" — small wet jobs priced at
  the high end; S7 <4 m² +20–35%; S3 min 80 m² is floor-oriented and does **not** apply to a
  single bathroom (S1 realizes "małe metraże (np. jedna łazienka)"). Recorded in §13.
- **VAT**: S12 explicitly **brutto**; S1/S2 netto; S7/S9 UNKNOWN; S11 netto typical. **Brutto vs
  netto split OBLIGATORY in the range** — the 380–580 supplementary band is net-leaning, the
  380–720 city band is brutto; 9E.4 must not merge them (§15).

## 12. CENNIK_MC_STAIRS-01 — Mikrocement na schody (unit: M2 canonical; per step recorded separately)

- **Canonical scope**: stair microcement, record basis (m² or per step). **Prio P3.** OWN_PRICE
  candidate per catalog §13 — see verdict below.
- **UNIT PROBLEM (documented, not resolved)**: the market prices stairs **three ways** and no
  conversion is attempted (catalog §15):
  - **per m²**: S1 Kraków **750–950** (stopnica + podstopnica, L+M); S4 400–600; S7 350–550;
    S8 600–900, with risers+cheeks (podstopnice/policzki) even **850–1100**;
  - **per step (stopień/schodek, = tread + riser)**: S15 400–600 netto; S16 **750–1300 netto
    /stopień**; S13* ~400/stopień; S19 900–1500/schodek;
  - **per flight (bieg)**: S13* 9 000–13 000 zł / bieg (17–19 steps).
  m² and per-step are **different bases** — a 0,3 m² typical step at 400–600 zł/step implies
  ~1300–2000 zł/m², which must NOT be conflated with the 350–950 zł/m² m² band.
- **Market result**:
  - `local_market_min` / `local_market_max` (M2, L+M): **750 / 950** — S1 (Kraków, stopnica +
    podstopnica; no prep-upcharge split; L+M).
  - `supplementary_pl_min` / `supplementary_pl_max`: M² (L+M) **350 / 900** (S7 350–550; S4
    400–600; S8 600–900, complex 850–1100); **per step (L+M) 400 / 1300** (S15 400–600 netto; S16
    750–1300 netto; S13* ~400; S19 900–1500). Recorded **without conversion**.
  - `reference_price`: **null** — no single defensible value while the unit model is open.
  - **Confidence: LOW** — many sources but scope/unit heterogeneity is decisive (rubric LOW =
    "significant scope ambiguity"); only S1 is local.
- **Source counts**: LOCAL 1 (S1) · REGIONAL 0 · NATIONAL 7 (S13*, S15, S16, S4, S7/S8, S10
  robocizna 220–300/m² stair labor, S19).
- **Included / excluded work — per source**: S1 includes stopnica+podstopnica (edges/side not
  stated); S16 includes prep + mesh + PU sealer and warns stairs quoted together with flooring are
  cheaper than separate jobs; S15 notes no ready-made baseboards exist (cokol 40–80 zł/mb);
  S13* stair pricing "leveling, repair, precision"; S10 stair labor +40% over walls. Substrate
  prep on stairs is universally up-charged and **not** included in any band.
- **OWN_PRICE verdict**: **BORDERLINE — market evidence EXISTS (contra the pure OWN_PRICE default).**
  This item is not a "no market" case like Batch C's REV_PAINT_LM; it is a **unit-model decision**
  (M2 vs per step vs per flight) plus scope definition (tread/riser/edge/nosing/prep). The
  catalog records unit "M2 (or per step — record basis)" — 9E.4 must pick one basis and rebuild
  the range on it. If the owner prefers M2: local 750–950 (S1) + national 350–900; if per step:
  400–1300 L+M. **No owner price assigned in 9E.3D.**

---

## 13. Minimum job / small-area + mobilization findings (commercial context, NOT M2 rates)

| Source | Minimum / tier / surcharge |
|---|---|
| S3 JAK Chemia | **min. projekt ~80 m²** ("realizujemy projekty od ok. 80 m²"); small bathrooms NOT typical |
| S16 Technodecor | **minimum logistyczne 50 m²** for floors/walls (bathrooms & stairs exempt) |
| S15 Vnetrze | **<25–30 m² → ryczałt** (flat rate), per-m² equivalent up to ~**1200 zł/m²** on tiny areas |
| S1 Monolite | floor tier ≤50 m² 400 vs >50 m² 360–380; no stated minimum; small bathroom work is normal |
| S11 Topciment | small floor / one bathroom ≤30 m² **550–650**; medium 50–100 ~400; >100 od 300 |
| S7 profesorbudownictwa | **<4 m² +20–35%** (mobilization); 3 m² łazienka 450–600 vs 15 m² 280–380 |
| S4 adrem | area tiers ≤30 350–450 · 30–100 300–400 · >100 250–350 (L+M) |
| S10 poilerobocizna | small projects higher rates; **>100 m² −15–25%**; >300 m² hourly negotiation |
| S13 Festfloor | "Niektórzy wykonawcy specjalizują się tylko w większych metrażach" |

No minimum-job figure has been converted into a normal M2 rate.

---

## 14. Bathroom / wet-zone example context (NON-COMPARABLE project contexts)

| Source | Bathroom area / scope | Waterproofing | Materials | Labor | Total price | Why not directly comparable to M2 catalog rate |
|---|---|---|---|---|---|---|
| S1 Monolite | 6 m² łazienka (walls+floor, walk-in shower) | incl. (wet zone) | incl. system | incl. | **3 000–4 800 zł** execution; TCO 5 lat 3 270–5 340 | whole-bathroom package incl. fixed costs, details (nisze, odpływ, narożniki), hydro — not a m² application rate |
| S1 Monolite | taras 12 m² (UV+antislip) | — | incl. | incl. | 5 000–6 500 zł | exterior system (UV lacquer, spadki) — different scope |
| S7 profesorbudownictwa | typowa łazienka 6–10 m² | +40–80 wet zone | 90–160 | 220–340 | **2 500–5 000 zł** | whole-job incl. fixed costs; own per-m² rows exist separately (used instead) |
| S7 | łazienka 5 m² walk-in → **1 800–2 800 zł**; 12 m² → 4 200–6 500 zł | membrana | incl. | incl. | per m² equivalently derived by the SOURCE itself (610 zł/m² at 8 m²) | source-derived m² (S8) used as such — the total-only rows kept as projects |
| S9 abcremontu | 5 m² łazienka z prysznicem → **4 500–7 000 zł**; 6–8 m² walk-in → **3 200–5 800 zł** | prysznic system with membrane | incl. | incl. | project totals | whole bathroom incl. skuwanie/removal, planning, hydraulics-adjacent — not a m² rate |
| S9 | zestaw systemowy 15–20 m² (ściany+podłoga) | membrane +400–600 zł (separate) | system 1 800–3 200 zł | — | kit material only | material kit, DIY-ready; not installed |
| S4 adrem | FAQ łazienka 5 m² → 1 500–2 500 zł | — | incl. | incl. | contradicts its own 300–500 zł/m² rows (5 m² × 300–500 = 1 500–2 500) | **internal inconsistency flagged** — used as context only |
| S12 sanitmax | brodzik walk-in 1,5 m² → **2 800–5 400 zł brutto** | hydro+taśmy 350–500 | 250–380 | 1 400–2 200 | incl. odpływ liniowy 200–400; wylewka ze spadkiem 600–900 | per-piece (brodzik) pricing — not per m² of shower wall |

No M2 catalog rate has been reverse-engineered from these totals.

---

## 15. MICRO-CEMENT SCOPE MATRIX (for 9E.4 normalization)

YES / NO / UNKNOWN; prices verbatim.

| Source | Wall/Floor/Shower/Stairs | Labor | Material | Primer | Mesh | Substrate prep | Waterproofing | Microcement | Sealer | VAT | Unit | Price (verbatim) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1 Monolite | Wall+Floor+Stairs | YES | YES | YES | UNKNOWN | YES (szlifowanie/wyrównanie) | YES (wet zones) | YES | YES (topcoat) | NETTO | M2 | wnętrza 250–400; posadzki ≤50 m² 400, >50 360–380; łazienka ściany 450–650; schody 750–950; blaty 500–650 |
| S2 Zement pracowniabetonu.pl | Wall+Floor+Shower (unified) | YES | YES | YES (gruntowanie) | UNKNOWN | YES (przygotowanie i gruntowanie) | UNKNOWN (strefa mokra listed as cost driver) | YES | YES (zabezpieczenie) | NETTO | M2 | od 320 netto (posadzki, ściany, łazienki, tarasy) |
| S3 JAK Chemia | Wall+Floor | YES | YES | YES | UNKNOWN | YES (szlifowanie, wyrównanie, gruntowanie) | UNKNOWN | YES | YES (impregnat i lakier) | NETTO | M2 | od 350 netto all-in; min 80 m² |
| S4 adrem | Wall+Floor+Stairs | YES | YES | YES (przygotowanie) | UNKNOWN | YES | UNKNOWN | YES | YES (versealowanie) | UNKNOWN | M2 | ściany 250–400; podłogi 300–500; schody 400–600; blaty 500–800 |
| S5 murator | Floor | YES | YES | YES (gruntowanie 10–25) | YES (sczepna+siatka 40–120) | YES (szlifowanie/wyrównanie 30–80; pęknięcia 20–50) | UNKNOWN | YES | YES (lakier PU 2×) | UNKNOWN (gross) | M2 | posadzka 350–500 typical / 300–750 overall; materiał 120–250; robocizna 180–400 |
| S6 prof. ściana | Wall | YES | YES | YES (grunt) | UNKNOWN | YES (wyrównanie incl.) | YES (łazienka +50–80 / mat. 110–120) | YES | YES (lakier 30–40) | UNKNOWN | M2 | ściana 250–400; robocizna od 150; mat. system ~90–100 |
| S7 prof. łazienka | Wall+Floor+Shower+Stairs | YES | YES | YES | UNKNOWN | YES (dane) | YES (strefa mokra +40–80; membrana +60–90) | YES | YES (lakier/impregnacja) | UNKNOWN | M2 | podłoga 300–450; ściany suche 250–400; strefa mokra 380–580; obudowa wanny 340–540; schody 350–550 |
| S8 prof. koszt 2026 | Wall+Floor+Shower+Stairs | YES | YES | YES (gruntowanie 12–22) | YES (mata 25–45) | YES (samopoziomująca 35–55; epoksyd 40–70; utylizacja 60–90) | UNKNOWN | YES | YES (lakier PU +18–30) | UNKNOWN | M2 | ściana 280–380 (mat 25–30%); podłoga 350–500 (mat 35–40%); schody 600–900 (850–1100 z podstopnicami); łazienka 8 m² ~610 |
| S9 abcremontu | Wall+Floor+Shower | YES (80–160 apl.) | YES (system 90–250; prysznic z membraną 200–250; premium 240–280) | YES | UNKNOWN | YES (wyrównanie/gruntowanie +25–45; płytki +30–50; ogrzewanie +20–35) | YES (prysznic membrane system) | YES | YES (lakier PU) | UNKNOWN | M2 | aplikacja 80–160 (miasta 120–160, małe 80–110) |
| S10 poilerobocizna | Wall+Floor+Stairs | YES only | NO | YES (inside labor %) | NO | YES (20–30% robocizny) | NO | YES | YES (lakier inside labor) | UNKNOWN | M2 | ściany 100–160/120–180; podłogi 180–250 (220@50m², 170@200m²); schody 220–300; godz. 80–120 |
| S11 Topciment | Wall+Floor+Shower | YES | YES | YES | UNKNOWN | YES (stan podłoża driver) | YES (łazienka incl. membrana) | YES | YES (lakier) | NETTO (typ. +23%) | M2 | 300–650 typical 350–550; jedna łazienka ~550; ≥100 od 300; ≤30 550–650 |
| S12 sanitmax | Shower | YES | YES | YES | UNKNOWN | YES (wylewka ze spadkiem) | YES (hydro+taśmy) | YES | YES (lakier PU spray) | BRUTTO | M2 | strefa prysznicowa 380–720 brutto (mat 35–50%); brodzik 1,5 m² 2 800–5 400 brutto |
| S13 Festfloor | Wall+Floor+Stairs | YES (L+M rows) | YES | YES (GO! basic) | YES (exterior/strengthening) | YES (zestaw wzmacniający 24–35) | UNKNOWN (HYDROFEST exists, unpriced) | YES | YES (PU FEST 2K) | UNKNOWN | M2 / STEP / BIEG | mat: posadzka 49,5; ściana 34,5; GO! 60; ext 100,95; 50–100; L+M posadzka 250–400 (280–380 średnio); schody ~400/stopień, 9 000–13 000/bieg |
| S14 ekipazlecenia | Wall | YES | YES | UNKNOWN | UNKNOWN | YES (wycena indywidualna — excluded) | UNKNOWN | YES | YES (impregnacja/lakier w cenie) | UNKNOWN | M2 | ściana kompleksowo od 326 zł/m² |
| S15 vnetrze | Floor+Stairs | YES | YES | YES (grunt) | UNKNOWN | UNKNOWN (extra) | UNKNOWN | YES | YES (lakier; lepszy PU +50) | NETTO | M2 / STEP | >50 m² 350–550 netto; cokol 40–80/mb; schody 400–600 netto/stopień |
| S16 Technodecor | Wall+Floor+Stairs | YES | YES | YES (żywiczne) | YES (mata na całą powierzchnię) | YES (ocena+przygotowanie) | YES (strefy mokre) | YES | YES (Remmers PU) | NETTO (8/23) | M2 / STEP | podłogi i ściany 300–500; łazienki od 280; schody 750–1300 netto/stopień; min 50 m² |
| S17 Conbar (sklep) | Wall+Floor+Shower+Stairs (set) | NO | YES only | YES (CONGRUNT) | YES (siatka prod.) | NO | YES (Waterproof variants) | YES | YES (CONPU/CONTOP/CONCOVER) | UNKNOWN | M2 (set/10 m²) | ściany zestaw 10 m² 680–745 (68–74,5/m²); epoksydowa posadzka 1 940 (194/m²); zewnątrz 1 595–1 640 (159,5–164/m²); lakier CONPU 2K 1,2 kg 170 |
| S18 cementibeton | Wall+Floor+Shower | NO | YES only | YES (in system) | NO | NO | YES (bathroom system) | YES | YES (lakier najdroższy elem.) | UNKNOWN | M2 | materiał: ściany 80–150; podłogi 120–250; łazienka/strefa mokra 150–300; blaty 200–400; zewnątrz 250–500 |
| S19 Pracownia Betonu (Warszawa) | Wall+Floor+Stairs | YES | YES | YES (gruntowanie) | UNKNOWN | YES (szlifowanie, matowienie) | NO (not mentioned) | YES | YES (zabezpieczenia) | UNKNOWN | M2 / STEP | 350–500 średnio; ściany 450–600; podłogi 350–500; schody 900–1500/schodek; robocizna 200–350 |

Matrix reading notes for 9E.4: walls peel "substrate prep — included/free" (S1/S2/S3/S16) vs
"billed extra" (S5/S14/S8); waterproofing is IN at 8 sources for wet zones (S1 S6 S7 S9 S11 S12
S16 S17) and NOT price-separated at S2/S3/S5; per-step pricing exists at 4 sources; **netto/brutto
split is mandatory** (S12 is gross, S9/S4/S6/S7/S8 unknown, S1/S2/S3/S15/S16 netto).

---

## 16. MATERIAL SYSTEM CONTEXT (manufacturer / store evidence — NOT labor)

**Documented PLN/m² material context** (only where the source states quantities or pack÷coverage):

| Product / system | Source | Package → coverage | Derived PLN/m² | Method |
|---|---|---|---|---|
| Festfloor Life — posadzka set | S13 | 495 zł / 10 m² | **49,5** | pack/coverage (source-stated) |
| Festwall — ściana set | S13 | 517 zł / 15 m² | **34,5** | pack/coverage (source-stated) |
| Festfloor GO! BASIC (gotowy+lacquer+primer) | S13 | 600 zł / 10 m² | **60** | pack/coverage (source-stated) |
| Festfloor GO! exterior set | S13 | 1 095 zł / 10 m² | **100,95** | pack/coverage (source-stated) |
| Festfloor general material band | S13 | — | **50–100** | source-stated band |
| Festfloor substrate-strengthening set | S13 | 240–350 zł / set | **24–35** | source-stated m² |
| Conbar CONONE ściany set 10 m² | S17 | 680–745 zł / 10 m² | **68–74,5** | pack/coverage |
| Conbar epoxy posadzka set 10 m² | S17 | 1 940 zł / 10 m² | **194** | pack/coverage |
| Conbar exterior set 10 m² | S17 | 1 595–1 640 zł / 10 m² | **159,5–164** | pack/coverage |
| Generic complete system — walls | S6/S9/S18/S20 | — | **80–150** (ścienny 90–130; system ~90–100) | source-stated material bands |
| Generic complete system — floors | S18/S9/S12 | — | **120–250** (łazienkowy 150–190; posadzkowy z kwarcem 180–260) | source-stated material bands |
| Wet-zone system (membrane) | S9/S18 | — | **150–300** (prysznicowy z membraną 200–250) | source-stated material bands |
| Premium systems (PU/anti-bacterial/satin) | S9 | — | **240–280** | source-stated band |

**Completeness checks**: the S13 GO!/BASIC figures explicitly include lacquer+primer (full wall/floor
system). The S17 wall set is "Jednolity Efekt" decorative system — whether primer/lacquer are inside
is **UNKNOWN → partial material evidence** (lacquer CONPU 2K 1,2 kg sold separately at 170 zł is
excluded from the 68–74,5 band). S16/S5 prep+mesh packages (sczepna+siatka 40–120; mata 25–45;
gruntowanie 10–25/12–22) are **separate rows**, not folded into system materials.

**Derived material context is NOT a contractor market quote** (9E.1 §7): all cells above feed only
the future material-side estimate, never a labor-market claim.

## 17. FESTFLOOR CONTEXT (manufacturer; one system reference, NOT "the market")

- URL: https://www.festfloor.pl/mikrocement-cena/ (plus shop: https://festfloor.pl — packs).
  Checked: **2026-09-14**. Company NIP 7011180788.
- Systems priced on the page: **Festfloor Life, Festfloor GO!, Festwall**, plus lakier **PU FEST 2K**.
- Material (verbatim): posadzka Life 10 m² set **495 zł → 49,5 zł/m²**; Festwall 15 m² set
  **517 zł → 34,5 zł/m²**; GO! BASIC (wymieszany+zabarwiony, z lakierem i gruntem) 10 m²
  **600 zł → 60 zł/m²**; GO! exterior 10 m² **1 095 zł → 100,95 zł/m²**; "materiały … 50–100 zł/m²";
  wzmacnianie podłoża **240–350 zł / 24–35 zł/m²**.
- L+M contractor-scale rows on the same manufacturer page (label: manufacturer-context, not firm
  quote): posadzka L+M **250–400 zł/m²** ("średnia 280–380"); schody **~400 zł/stopień**, **9 000–
  13 000 zł/bieg** (17–19 stopni).
- HYDROFEST (membrane system) is listed in the site menu but **not priced** on this page.
- Festfloor figures are **not weighted** into the general market ranges of §6 — recorded as one
  system reference (§18 of the contract).

## 18. NORMALIZATION_REVIEW_NOTE (Batch A/B/C issues preserved + new Batch D issues, for 9E.4)

Preserved from 9E.3A / 9E.3B / 9E.3C (not fixed here — **Batch A/B/C numbers untouched**):
1. **SKIM_PKG-01 vs SKIM_1L-01 / SKIM_2L-01** — package band 35–70 vs component equivalent 65–91;
   decide package scope at 9E.4.
2. **Painting coat-count** — 2-coat PAINT_2K default; no double-count of PRIM_PAINT/SKIM;
   re-verify the inconsistent cennikremontow 1-coat row.
3. **betonizm.pl Q4** — main-table 60–80 vs chart 110 conflict; re-check at 9E.4.
4. **GK_JOINT unit model** — M2 vs LM (mb) evidence family; confirm unit at 9E.4.
5. **Kraków "Montaż narożników" cell** — 22–30 zł/m² for a linear service; unit mismatch.
6. **Reveal unit model** — M2 component rows (REV_PREP/SKIM/SAND/PAINT) have no standalone market
   pricing; market prices reveals per mb (30–110 labor) or per window/door; 9E.4 decides strategy.
7. **M2 complete-bundle vs component (reveals)** — 80–120/m² and nowabudowa 113/m² are complete
   obróbka, not component rates.
8. **"Szpaleta" dual scope** — prefab profile systems ≠ tynkowa obróbka.
9. **Kraków-zone LM evidence** — only o-okna metropolis zone mapping positions Kraków for reveals.

New issues exposed by Batch D:
10. **Labor-only microcement is a national-guide construct only (NEW)** — no Kraków/Małopolskie
    firm prices MC labor separately; local labor-only rows (WALL_L, FLOOR_L) are empty and must be
    OWN_PRICE or regional-coefficient-derived at 9E.4 (Kraków premium +20–30% per S10/S12/S5
    documented).
11. **"od" anchors masquerading as ranges (NEW)** — S2 od 320, S3 od 350, S14 od 326 are
    minimums; the FLOOR_S/WALL_S ranges built on them need an explicit min-vs-range handling
    decision (a min-only anchor lowers range precision).
12. **Netto/Brutto split (NEW)** — S12 is explicit brutto (380–720); S1/S2/S3/S15 netto; S5 gross-
    consumer; S4/S6/S7/S8/S9/S10 unknown. The shower supplementary band **must not** silently mix
    brutto and netto origins.
13. **Wet-zone scope is not "application" (NEW)** — membrane+fall+drain+junction details push
    wet-zone per-m² well above standard wall L+M (+30–80% over dry walls). 9E.4 should seed
    SHOWER-01 either as a *system* (L+M, membrane incl.) or keep application + separate
    hydroizolacja rows — the current catalog row is the former.
14. **Stairs unit model (NEW)** — M2 vs per-step vs per-flight all exist; 350–950 zł/m² (m² basis)
    and 400–1300 zł/step (step basis) are NOT convertible without geometry. 9E.4 picks the seed
    unit and scope (tread/riser/edge/nosing/prep).
15. **Manufacturer material cost ≠ contractor price (NEW)** — Festfloor/Conbar pack÷coverage
    (34,5–100,95/m²) vs contractor L+M (250–650/m²) and vs national material echelons
    (80–300/m²): three different layers that seeding must keep apart; material side is a future
    Stage 10 estimate input, not a PriceBook price row.
16. **Substrate-prep inclusion is inconsistent across sources (NEW)** — S1/S2/S3/S16 fold prep+mesh
    into the quote; S5/S14/S8 bill it separately (prep packages 10–120 zł/m² depending on
    severity). Any seeded L+M microcement row must declare a prep assumption (e.g. "substrate
    ready, leveling excluded").
17. **Minimum-m² / mobilization is structural (NEW)** — JAK 80 m², Technodecor 50 m², Vnetrze
    <25–30 m² ryczałt, Monolite ≤50 m² tier, S11 ≤30 m² premium, S7 <4 m² +20–35%. Small
    bathrooms are the primary local sales case, yet carry the highest unit price; 9E.4 should
    consider a small-area surcharge or minimum-price logic rather than a flat M2 seed alone.
18. **Regional city-unified vs Kraków-specific (NEW)** — three local/regional L+M anchors
    (S1 Kraków, S2 Małopolska+Śląsk, S3 Kraków/Libiąż) presently define WALL_S/FLOOR_S local
    ranges; only S1 splits walls/floors. 9E.4 must decide whether to keep unified L+M wall+floor
    seeds or demand per-surface seeds (the catalog already separates them — the market barely
    does).
19. **Festfloor-family content flag (NEW)** — cementibeton.pl (S18) is Festfloor-affiliated;
    sanitmax (S12) explicit-Kraków city mapping is a national calculator, not a Kraków firm; both
    carry caveats for weight at 9E.4.

## 19. Research summary (for `docs/development-progress.md`)

- Items researched: **6 / 6** Batch D items.
- Sources: **22 referenced pages** used (19 weighted + 3 flag-only), of which **1 is a strict
  Kraków-local price anchor (Monolite)**, **2 are Małopolskie/regional L+M anchors (Zement
  pracowniabetonu.pl serving Kraków; JAK Chemia Kraków showroom/Libiąż)**, **2 Kraków-adjacent
  producers with material evidence (Conbar Mirzec-marketing-Kraków; Festfloor national)**, and the
  rest Poland-wide/manufacturer-market overviews. A further **8 negative/local-audit pages**
  (conbar landing, mikrobet landing, Oferteo Kraków+Wieliczka, cennikibudowlane Kraków,
  remonty-inplus Kraków, loftsurface Kraków realize 404, OLX Kraków dynamic) contain **no**
  usable per-m² price rows.
- Confidence distribution: **HIGH 1** (FLOOR_S) · **MEDIUM 4** (WALL_L, WALL_S, FLOOR_L, SHOWER) ·
  **LOW 1** (STAIRS) · **INSUFFICIENT 0**.
- OWN_PRICE candidates: **0 pure** (all six canonical items have some market evidence). **STAIRS**
  keeps the strongest OWN_PRICE/default-unit pressure but is really a **unit-model
  + scope-normalization case** (m² vs per step vs per flight), not an absence-of-market case.
  WALL_L / FLOOR_L (labor-only) have **no local basis** → candidates for OWN_PRICE or
  regional-coefficient derivation at 9E.4.
- Festfloor / material context: **recorded** (§16, §17) — material PLN/m² 34,5–194; contractor
  L+M 250–650; national material echelons 80–300; three layers kept apart.
- Minimum-job findings: **recorded** (§13) — 50–80 m² floors minimums, <25–30 m² flat-rating,
  small-area premiums; none converted to M2 rates.

## 20. CROSS-CHECK (9E.3D §27)

- **All 6 canonical items researched** — yes; codes verbatim from catalog §10.
- **Every numeric claim traceable** — each figure carries source, URL, type, region,
  `checked_at 2026-09-14`; quotes read from the opened page (or curl-rendered text where the page
  is dynamic — OLX excluded).
- **Exact URLs present** — §5 index + item sections + matrix.
- **Local vs PL separated** — LOCAL 1 (Monolite) / REGIONAL 2 (Zement, JAK) / NATIONAL per item in
  §4; no local claims for labor-only rows (documented negative §4.1).
- **Labor vs L+M vs material separated** — LABOR rows (WALL_L, FLOOR_L) use only labor-only
  origins; L+M bands use only complete-system origins; manufacturer/store material evidence kept
  in §16/§17; matrix columns separate them per source.
- **Walls/floors not silently mixed** — where sources give unified rates (S2/S3) it is stated
  explicitly; wall vs floor rows carry separate bands; S1's floor vs bathroom-wall prices kept in
  their own rows.
- **Waterproofing explicit** — hydro included (S1/S6/S7/S9/S11/S12/S16/S17), separate (S7 +40–80,
  S12 hydro+taśmy row), not stated (S2/S3/S5) — per source. Shower row = system-with-membrane;
  application-only prices are context, not row evidence.
- **Substrate preparation explicit** — included vs billed-extra per source (§15 matrix); prep
  packages (S5 10–120/m²; S8 hidden costs) recorded, never merged into bands.
- **Stairs units not converted** — M2, per-step, per-flight recorded separately with a no-conversion
  note (§12).
- **Minimum charges excluded from normal M2 ranges** — §13 records them as context only.
- **Manufacturer prices not treated as labor** — §16/§17 labeled MATERIAL/MANUFACTURER; Festfloor
  L+M rows kept separate from the material pack context and flagged.
- **Derived material calculations show formula** — pack/coverage written on every derived cell
  (`pack ÷ coverage`).
- **No guessed consumption** — all derivations use source-stated pack coverage; no component
  subtractions performed (no labor-from-complete, no material-from-complete).
- **No invented prices** — every figure is a quoted/derived-from-quoted value; jak-wykonac.fun
  (S21) excluded from independent counting.

## 21. Source archival & exclusion notes

- SANITMAX (S12), Oferteo, Topciment (S11), Festfloor (S13) and ekipazlecenia (S14) pages may
  drift/rotate; re-verify before seeding (9E.5/9E.7).
- Oferteo Kraków/Wieliczka were server-rendered text only; per-firm pages carry "Zapytaj o ofertę"
  and no price lists — marketplace evidence remains a future verification channel.
- OLX Kraków/national microcement lists are JS-rendered; **not extractable** at check time (noted,
  not scored).
- Unreachable/blocked at check time: pytania https://www.topciment.com (403 on fetch engine; got
  full text via UA-rendered fetch — retained), dk7-krakow-libertow.pl (403 — excluded),
  loftsurface Kraków realize (404 — excluded), plus the content-network clones listed in §5.
- **Distinct companies confirmed**: pracowniabetonu.pl (Zement, Śląsk/Małopolska) vs
  pracowniabetonu.eu (Pracownia Betonu, Warszawa) — both use Resistone, both kept, neither merged.
- **Term caution**: "beton ciré" in Kraków search = concrete-cutting/ready-mix vendors, not a
  microcement service cluster (§2); "beton architektoniczny" as thick-cast ≠ thin-layer system.

## 22. Checked-at note

All `checked_at` values in this file: **2026-09-14**.