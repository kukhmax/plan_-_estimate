# Polish Construction & Finishing Domain Rules

## 1. Domain Overview & Central Entity: OBIEKT
In the Polish interior finishing and renovation sector (*prace wykończeniowe i remontowe*), every operation is tied to a physical building site or residential unit: the **OBIEKT** (Project / Work Site).

All data structures, inspections, measurements, and contractual artifacts derive from this aggregate root.

## 2. Core Domains & Domain Responsibilities

1. **Clients (`Klienci`)**: Private individuals (B2C) or commercial investors (B2B). Contact details, tax IDs (NIP/PESEL), communication preferences.
2. **Projects (`Obiekty / Projekty`)**: The renovation site. Address, development stage (stan deweloperski, rynek wtórny, kamienica, dom jednorodzinny), floor, access conditions.
3. **Rooms (`Pomieszczenia`)**: Living room (salon), bedroom (sypialnia), bathroom (łazienka), hallway (korytarz), kitchen (kuchnia), etc.
4. **Surfaces (`Ściany i Sufity / Płaszczyzny`)**: Individual walls, ceilings, partition walls, slants (skosy poddasza), architectural niches (wnęki).
5. **Measurements (`Pomiary`)**: Length, width, height, net wall area, ceiling area, subtraction of window/door openings (*otwory okienne i drzwiowe*).
6. **Substrate Inspections (`Badania Podłoża`)**: On-site technical diagnostics before work commencement (humidity, absorption, cohesion, flatness).
7. **Photos (`Zdjęcia`)**: Visual evidence of existing conditions, defects, progress milestones, and concealed works (*roboty zanikające*).
8. **Risks (`Ryzyka`)**: Deterministic technical warnings, risk score, and required mitigation steps (e.g., priming, fiber fleece, mesh reinforcement).
9. **Quality Levels (`Klasy Jakości`)**: Explicit standards agreed with the client (S1-S4, Q1-Q4 / PSG1-PSG4).
10. **Price Book (`Katalog Cen / Baza Cenowa`)**: Contractor's base rates for labor, materials, equipment, and difficulty surcharges.
11. **Estimates (`Kosztorysy`)**: Detailed line-item calculations based on surface areas, substrates, and chosen quality levels.
12. **Contracts (`Umowy`)**: Binding legal agreement between contractor and client, defining scope, timeline, stages, payments, and warranties.
13. **Technical Protocols (`Protokoły Techniczne`)**: Handover of site (*protokół przekazania terenu*), acceptance of concealed works (*odbiór robót ulegających zakryciu*), and final acceptance (*protokół odbioru końcowego*).
14. **Work Execution (`Realizacja Prac`)**: Stage completion tracking, checklist verification, deviation notes.
15. **Legal Knowledge (`Baza Wiedzy Prawnej i Normatywnej`)**: Polish Building Law (*Prawo Budowlane*), ITB technical conditions, Polish Norms (PN-B, PN-EN).
16. **Client Phrases (`Zwroty i Komunikacja`)**: Professional Polish/Russian phrases for explaining technical requirements, delays, extra works, and risk refusals to clients.
17. **Scheduling (`Harmonogramowanie`)**: Drying times, technological breaks (*przerwy technologiczne*), stage dates.

## 3. Work Types (Technologie Prac)

- **Szpachlowanie / Gładź**:
  - Gładzie gipsowe, polimerowe, cementowe.
  - Ręczne oraz maszynowe (agregat hydrodynamiczny).
  - Szlifowanie bezpyłowe z oświetleniem smugowym.
- **Włóknina Szklana (Welon Szklany)**:
  - Wklejanie welonu szklanego o gramaturze 40-50 g/m² przeciw mikropęknięciom na sufitach i ścianach.
  - Zastosowanie na łączeniach płyt g-k oraz na tynkach w nowym budownictwie podlegającym osiadaniu.
- **Malowanie**:
  - Malowanie gruntujące, podkładowe, nawierzchniowe.
  - Metody: natrysk hydrodynamiczny (airless) oraz wałek mikrofibra.
  - Klasy odporności na szorowanie (Klasa 1 wg PN-EN 13300).
- **Mikrocement**:
  - Systemy cienkowarstwowe polimerowo-cementowe na posadzki, ściany, kabiny prysznicowe bez brodzika.
  - Wymóg specjalnego przygotowania podłoża (żywica epoksydowa z piaskiem kwarcowym, hydroizolacja).
- **Stiuk Wenecki i Tynki Dekoracyjne**:
  - Szlachetne tynki wapienne, akrylowe, efekty welwetu, betonu architektonicznego.
  - Wysokie wymagania odnośnie równości podłoża.

## 4. Substrates (Podłoża)

All inspections and works must classify the substrate into:
1. **Beton**: Prefabrykat, żelbet monolityczny, stropy Vector/Filigran.
2. **Tynk gipsowy**: Maszynowy lekki lub twardy, zatarty na ostro lub gładko.
3. **Tynk cementowo-wapienny**: Tradycyjny, porowaty, o wysokiej chłonności i szorstkości.
4. **Płyta g-k / sucha zabudowa**: Ściany działowe, sufity podwieszane, zabudowy stelażowe GK.
5. **Stara gładź (Old skim coat)**: Istniejące warstwy gipsowe/kredowe o niepewnej nośności.
6. **Stara farba (Old paint)**: Dyspersyjna, emulsyjna, lateksowa, olejna (lamperia), klejowa.
7. **Płytki ceramiczne (Tile)**: Podłoże pod mikrocement lub szpachlowanie renowacyjne.
8. **Inne (Other)**: Gazobeton, ceramika poryzowana, silikat.

## 5. Quality Standards & Levels

### A. Tynki tradycyjne i beton: Klasy S1 – S4
- **S1 (Podstawowa)**: Powierzchnia zgrubna, dopuszczalne widoczne ziarno i drobne nierówności, pod okładziny ceramiczne lub tapety strukturalne.
- **S2 (Standardowa)**: Standard deweloperski, szpachlowanie jedno- lub dwuwarstwowe, dopuszczalne drobne ślady narzędzi widoczne pod światło boczne.
- **S3 (Podwyższona)**: Powierzchnia gładka, wielowarstwowa, szlifowana pod oświetlenie rozproszone, pod farby matowe.
- **S4 (Najwyższa / Luksusowa)**: Powierzchnia idealnie gładka, sprawdzana lampą smugową (np. Festool Syslite / Smuga), pod farby satynowe, połysk, oświetlenie ledowe przypodłogowe lub sufitowe.

### B. Sucha zabudowa (Płyty G-K): Klasy Q1 – Q4 (PSG1 – PSG4)
- **Q1 / PSG1**: Podstawowe spoinowanie połączeń płyt g-k z wtopieniem taśmy zbrojącej (papierowej lub z włókna szklanego).
- **Q2 / PSG2**: Standardowe szpachlowanie spoin z łagodnym przejściem do powierzchni płyty; pod tapety o grubej strukturze lub tynki strukturalne.
- **Q3 / PSG3**: Podwyższone szpachlowanie: spoinowanie Q2 + szerokie szpachlowanie spoin oraz cienkowarstwowe przeciągnięcie gładzią całej powierzchni w celu ujednolicenia chłonności i faktury.
- **Q4 / PSG4**: Całopowierzchniowe szpachlowanie powłoką o grubości min. 1 mm na całej powierzchni płyty; pod oświetlenie smugowe, farby półmatowe/błyszczące, mikrocement.

## 6. Deterministic Technical Risk Engine
The risk engine must evaluate combinations of:
- `(Substrate, SubstrateCondition, PlannedFinish, QualityLevel, EnvironmentalFactors)`
and return deterministic rules:
- **Moisture Check**: If humidity > 3% CM for concrete or > 1% for gypsum plaster -> **BLOCK** skim coating/painting, flag `CRITICAL_MOISTURE_RISK`.
- **Oil Paint Lamperia**: If old oil paint detected -> requires mechanical scratch, sanding, or quartz primer (kontakt-grunt) before skim coat.
- **Drywall Q4 with Side Light**: If ceiling with LED strip + drywall -> mandatory fiberglass fleece (*włóknina szklana*) or Q4 protocol to prevent visible board seams.
- **Warranty Disclaimer**: If client refuses recommended primer or reinforcement, generate formal protocol clause: *Wyłączenie odpowiedzialności wykonawcy za spękania na żądanie inwestora*.
