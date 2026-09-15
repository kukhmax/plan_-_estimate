# Stage 9E.3E — Kraków Market Research — Batch E: Decorative Finishes / Venetian Plaster

**Evidence file — web research + documentation ONLY. No prices implemented. No `PriceItem.price` modified. No seeds. No migrations. No backend/frontend changes.**
`checked_at` policy: **2026-09-14** for every source (re-fetched fresh during this sub-stage, unless a page was archived at time of check).

**Canonical rows researched (catalog §11, verbatim codes):**
| Code | PL name | RU name | Cat. | Unit | Scope | Prio |
|---|---|---|---|---|---|---|
| CENNIK_DEC_VEN-01 | Stiuk wenecki — klasyczny | Венецианская штукатурка — классическая | DECORATIVE | M2 | LABOR | P1 |
| CENNIK_DEC_VEN_MAR-01 | Stiuk wenecki — efekt marmuru z żyłkowaniem | Венецианская штукатурка — мраморный эффект с прожилками | DECORATIVE | M2 | LABOR | P2 |
| CENNIK_DEC_CONC-01 | Efekt betonu / beton architektoniczny | Эффект бетона / архитектурный бетон | DECORATIVE | M2 | LABOR | P2 |
| CENNIK_DEC_GENERIC-01 | Tynk dekoracyjny — ogólny | Декоративная штукатурка — общая | DECORATIVE | M2 | LABOR | P2 |

**User story that matters for our business (Stage 5F/9E/10 intent):** the classic Venetian (P1) and concrete-effect (P2) rows carry our primary exposure; the veined-marble row (P2) is a workshop-grade **custom/artistic** service where published labor pricing is rare by market structure.

---

## 1. Purpose — technology classification before price

The decorative-finish market clusters **very different technologies under overlapping words** (`stiuk wenecki`, `marmoryzacja`, `tynk dekoracyjny`, `beton architektoniczny`, `mikrocement`). This file records:

1. the **exact terminology** each source used (task §3),
2. the **technology family** each price belongs to (classic Venetian / veined marble / concrete-effect / generic structural / **excluded**: microcement, decorative panels, resin floors),
3. scope classification **LABOR / MATERIAL / LABOR_AND_MATERIAL / UNKNOWN** (task §8),
4. layer count / polishing / wax where stated (task §10),
5. substrate assumption and prep inclusion (task §9),
6. complexity grade STANDARD / ENHANCED / ARTISTIC / UNKNOWN (task §11),
7. VAT basis where stated (task §15).

**Guard rule (same as Batch D):** we never derive a labor figure by subtracting a guessed material cost from a complete-system figure, and we never convert a decorative retail product price into a contractor labor rate.

---

## 2. Terminology research — actual market wording

| Term | Frequency in search results | Technology the term maps to | Price relevance |
|---|---|---|---|
| `stiuk wenecki` | very high | classic Venetian plaster (lime/gypsum-lime, marble dust, multi-layer, polished/waxed) | classic row PP1 |
| `efekt marmuru` / `marmoryzacja` / `żyłkowanie` | medium | marble-look with veining (artistic) | veined row PP2 |
| `stiuk marmurowy` / `mikrokruszywo` | medium | marble-effect (may be generic, not necessarily veined) | veined surrogate / generic |
| `tynk dekoracyjny` | very high | umbrella term covering structural, stone, glaze, travertine, venetian | generic row + technology discriminator |
| `efekt betonu` / `beton architektoniczny` / `imitacja betonu` | high | thin-layer decorative concrete-effect coating (1,5–3 mm) | concrete row |
| `beton dekoracyjny` | high | same thin-layer coatings + **floor** scope (watch out) | concrete row / exclusion |
| `trawertyn` / `efekt skały` / `tadelakt` / `Ottocento` | medium | separate stone-effect systems | NOT canonical rows — generic context |
| `mikrocement` / `mikrobeton` | high | microcement (Batch D) | **excluded from Batch E rows** |
| `przecierka` / `wychmurzenia` (R3) | low | lime-wash / pale-body on plaster | generic context only |

**Terminology caution 1 — `beton ciré` / `beton architektoniczny` vs microcement:** in Kraków searches `beton ciré` collides with concrete-cutting/ready-mix vendors (same finding as Batch D §2). In virtual market terms `beton architektoniczny` almost always means a **thin-layer decorative coating** (1,5–3 mm, per konkret-beton and abc-tynki), NOT cast architectural concrete. `płyty betonowe / panel betonowy` (prefab panels) is a **separate scope** (including on the concrete-effect page of bursatm: 200–400 zł/m² panels) and must never enter the thin-layer row.

**Terminology caution 2 — `stiuk syntetyczny`:** several sources (muratordom/Jeger, poilerobocizna) explicitly contrast acrylic `stiuk syntetyczny` (30–46 zł/m² material) with natural lime/venetian systems (59–83 zł/m² material). They are **not the same system or the same labor scope**; cheap "stiuk wenecki za 60–70 zł/m²" offers (flagged by ewyposazenie) are almost always synthetic single-layer substitutes.

---

## 3. System / brand recording

Where a source states a product/system, it is recorded:
- **VIAN "Venezia"** marble system (viandekor.pl) — polymer-bound, marble-dust veneer, multi-layer + veining + hot polish + wax. L+M.
- **Dekor Lux "Marmorinus"** Venetian/marmorino (dekor-lux.pl) — 4–6 layers, polishing on hot steel trowel, wax. L+M ~313 zł/m².
- **Mikrocement "Betonus"** (dekor-lux calculator) — microcement system; excluded from Batch E concrete row (Batch D row FLOOR_S).
- **"Travertinus"", "Ottocento Velvetus", "Sahara", "Alkantara" (zamsz)** (dekor-lux family) — other stone/textile systems; generic context only.
- **Jeger / Magnat Stiuk Wenecki** (muratordom, dekoratorniatv) — retail Venetian materials; material context only. Magnat: 140–220 zł / 5 kg → ~10 m² (DERIVED 14–22 zł/m²).
- **Jeger lime/gypsum-lime Venetian + acrylic structural** (muratordom): natural 59–83 zł/m² material, synthetic-set 30–46 zł/m² (DERIVED, formula shown).

---

## 4. Geographic priority — source counts

- **Strict Kraków-local (priced):** **0** (audited: dflhome.pl — Kraków Kliny, beton architektoniczny/imitacja betonu + tynk wapienny/marmorino Kraków, but *"wycena indywidualna — nie ma jednej ceny dla wszystkich efektów"* — no published M2 price; dekormarmo.pl — Kraków decorative specialist, portfolio-only site, last activity ~2013, no prices; cenauslug.pl stiuk-wenecki/Kraków — HTTP 410 dead, consistent with Batch C).
- **Kraków-local marketplace anchor:** **1 (weighted as flag/anchor)** — OLX listing "TynkDeko — tynki dekoracyjne, Marmorino, beton dekoracyjny, złocenia — Kraków i okolice, cena od 100 zł/m², wycena indywidualna" (checked 2026-09-14; JS-rendered page, text served after render).
- **Regional serving Kraków:** **2** — VIAN (viandekor.pl; Silesia + Małopolska; marble page quotes "właściciele premium nieruchomości w Krakowie...", concrete page lists "Kraków, Katowice, Gliwice, Knurów, Chorzów, Rybnik, Zabrze" service cities; publishes L+M prices); KB.pl stiuk wenecki **Kraków row 405 zł/m²** (national portal city-mapping, min 10 m², kompletna usługa).
- **Patrz also:** itynki.pl national + regional table explicitly maps **Kraków into the "+20% big-city premium"** band (text: +15–25% vs national average) — regional *transform* evidence, not a Kraków firm quote.
- **Poland supplementary:** ~16 numeric pages (see §5 index).

---

## 5. Source evidence index (16 weighted + 6 flag/exclusion; exact URLs preserved — future `PriceSource` candidates)

| # | Source name | URL | Type | Region | Checked |
|---|---|---|---|---|---|
| S1 | KB.pl — Cennik stiuku weneckiego 2026 (city rows) | https://kb.pl/cenniki/stiuk-wenecki/ | NATIONAL portal (per-city rows) | PL incl. Kraków/Małopolskie | 2026-09-14 |
| S2 | itynki.pl — Ile kosztuje robocizna przy tynku dekoracyjnym | https://itynki.pl/tynki-dekoracyjne-cena-robocizny | INDUSTRY guide (labor) | PL + Kraków premium map | 2026-09-14 |
| S3 | ewyposazenie.pl — Tynk dekoracyjny cena za m2 robocizny | https://ewyposazenie.pl/tynk-dekoracyjny-cena-za-m2-robocizny/ | INDUSTRY guide (labor+material tables) | PL | 2026-09-14 |
| S4 | adrem.org.pl — Stiuk wenecki cena za m2 robocizny | https://adrem.org.pl/stiuk-wenecki-cena-za-m2-robocizny/ | CONTRACTOR_PRICE_LIST (Warszawa firm page) | Warszawa + PL service | 2026-09-14 |
| S5 | jakietynki.pl — Tynk dekoracyjny cena za m2 robocizny | https://jakietynki.pl/tynk-dekoracyjny-cena-za-m2-robocizny | INDUSTRY guide (labor ladder) | PL | 2026-09-14 |
| S6 | wistalex.pl — Stiuk wenecki cena za m2 robocizny 2026 | https://wistalex.pl/stiuk-wenecki-cena-robocizny/ | INDUSTRY guide (labor + total) | PL | 2026-09-14 |
| S7 | poilerobocizna.pl — Tynk dekoracyjny cena za m2 robocizny | https://poilerobocizna.pl/tynk-dekoracyjny-cena-za-m2-robocizny | INDUSTRY guide (mixing caveat) | PL | 2026-09-14 |
| S8 | poilerobocizna.pl — Beton architektoniczny cena robocizny | https://poilerobocizna.pl/beton-architektoniczny-cena-robocizny | INDUSTRY guide (labor, incl. panels) | PL | 2026-09-14 |
| S9 | abc-tynki.pl — Tynk beton architektoniczny: cena robocizny | https://abc-tynki.pl/tynk-beton-architektoniczny-cena-robocizny | INDUSTRY guide (labor) | PL | 2026-09-14 |
| S10 | bursatm.pl — Beton architektoniczny cena robocizny | https://bursatm.pl/beton-architektoniczny-cena-robocizny | INDUSTRY guide (labor + L+M) | PL | 2026-09-14 |
| S11 | konkret-beton.pl — Cena położenia betonu dekoracyjnego 2026 | https://konkret-beton.pl/cena-polozenia-betonu-dekoracyjnego | INDUSTRY guide (labor+material+sample) | PL | 2026-09-14 |
| S12 | VIAN Dekor — Efekt marmuru na ścianie (nakładanie) | https://viandekor.pl/efekt-marmuru-na-scianie-nakladanie/ | CONTRACTOR_PRICE_LIST (company) | Śląsk + Małopolska (serves Kraków) | 2026-09-14 |
| S13 | VIAN Dekor — Nakładanie tynku — efekt betonu | https://viandekor.pl/nakladanie-dekoracyjnego-tynku-betonowego/ | CONTRACTOR_PRICE_LIST (company) | Śląsk + Małopolska (serves Kraków) | 2026-09-14 |
| S14 | Dekor Lux — Marmur na ścianie — efekt prawdziwego kamienia | https://www.dekor-lux.pl/blog/marmur-na-scianie-efekt | CONTRACTOR_PRICE_LIST (Warszawa firm blog w/ prices) | Warszawa + PL service | 2026-09-14 |
| S15 | ekipazlecenia.pl — Cennik stiuk wenecki 2026 | https://ekipazlecenia.pl/cennik/cennik-stiuk-wenecki | INDUSTRY portal (network) | PL | 2026-09-14 |
| S16 | muratordom.pl — Stiuk wenecki od matu po wysoki połysk | https://muratordom.pl/wnetrza/prace-wykonczeniowe/stiuk-wenecki-od-matu-po-wysoki-polysk-efekt-marmuru-na-scianie-aa-fzDR-KY2Q-LghX.html | INDUSTRY/MEDIA article (L+M + material), brand: Jeger | PL | 2026-09-14 |
| S17 | dekoratorniatv.pl — Stiuk wenecki marmur cena / m2 | https://dekoratorniatv.pl/materialy-wykonczeniowe/stiuk-wenecki-marmur-cena/ | INDUSTRY article (material context) | PL | 2026-09-14 |
| S18 | OLX Kraków — TynkDeko, tynki dekoracyjne Marmorino / Beton / Kraków | https://www.olx.pl/d/oferta/tynki-dekoracyjne-mikrocement-marmorino-beton-krakow-i-okolice-CID5216-ID1cg830.html | MARKETPLACE (local listing) | Kraków i okolice | 2026-09-14 |

Flag / exclusion:
| S19 | dflhome.pl — Beton architektoniczny Kraków (imitacja betonu) | https://dflhome.pl/beton-architektoniczny-imitacja-betonu-krakow/ | LOCAL firm, no prices | Kraków (Kliny) + Wieliczka | 2026-09-14 |
| S20 | dflhome.pl — Tynk wapienny / marmorino / efekt marmuru Kraków | https://dflhome.pl/tynk-wapienny-wychmurzenia-marmorino-krakow/ | LOCAL firm, no prices | Kraków | 2026-09-14 |
| S21 | dekormarmo.pl — aranżacja wnętrz, tynki dekoracyjne Kraków | http://www.dekormarmo.pl/ | LOCAL firm, portfolio-only (old site) | Kraków (+Katowice, Warszawa, Bielsko-Biała) | 2026-09-14 |
| S22 | cenauslug.pl — nałożenie stiuku weneckiego Kraków | https://cenauslug.pl/budowa-i-remont/nalozenie-stiuku-weneckiego/krakow | NATIONAL portal (dead) | Kraków row — HTTP 410 | 2026-09-14 |
| S23 | cudaarchitektury.pl — stiuk wenecki cena za m2 | https://cudaarchitektury.pl/stiuk-wenecki-cena-za-m2-robocizny-i-co-warto-wiedziec/ | CONTENT-NETWORK small | PL (siblings: mebloweporady.pl, forummeble.pl) — HTTP 403 | 2026-09-14 |
| S24 | KB.pl — Cena tynkowania i gładzi Kraków (city page) | https://kb.pl/cenniki/miejskie/tynkowanie/krakow/ | NATIONAL portal city page — external plaster rows only, no decorative rows | Kraków | 2026-09-14 (negative audit) |

Content-network duplication flags (do NOT count as independent):
- cudaarchitektury.pl / mebloweporady.pl / forummeble.pl share one content network (same article skeleton, `stiuk wenecki cena za m2 robocizny i co warto wiedzieć`) → **count once (none usable: 403)**.
- jakietynki.pl / itynki.pl / t-tynki.pl share a `*tynki` content network (different numbers per site, same structure) → treated as **two independent sets of numbers** but flagged; not 3 independent.
- abc-tynki.pl / bursatm.pl / poilerobocizna.pl / konkret-beton.pl belong to the broader SEO "poradnik" ecosystem; each publishes **differing numbers**, so they are counted as distinct data points with the ecosystem risk documented, never as 4 independent confirmations of one number.

---

## 6. Summary table (Batch E — 4 items)

| Code | PL name | Technology | Unit | Scope | Local range | Suppl. PL range | Reference | Confidence | Local src | Region. src | Nat. src | Checked |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CENNIK_DEC_VEN-01 | Stiuk wenecki — klasyczny | classic Venetian plaster | M2 | LABOR | — (L+M city anchor only: Kraków 405 kompleksowo) | 100–160 (core 120–150; premium to 300) | 140 | MEDIUM | 0 | 1 | 6 | 2026-09-14 |
| CENNIK_DEC_VEN_MAR-01 | Stiuk wenecki — efekt marmuru z żyłkowaniem | marble-look + veining (artistic) | M2 | LABOR | — | surrogate (non-veined) 80–160; explicit veined L+M 350–550 | null | LOW | 0 | 1 | 3 | 2026-09-14 |
| CENNIK_DEC_CONC-01 | Efekt betonu / beton architektoniczny | thin-layer concrete effect | M2 | LABOR | — | 60–150 (core; outer 50–270) | 110 | MEDIUM | 0 | 1 | 5 | 2026-09-14 |
| CENNIK_DEC_GENERIC-01 | Tynk dekoracyjny — ogólny | structural/colored/glaze render (narrow) | M2 | LABOR | — | 40–80 | 60 | MEDIUM | 0 | 0 | 4 | 2026-09-14 |

**No implementation decision yet — research evidence only (9E.3E §6).**
Confidence key: HIGH = 3+ genuinely comparable local/regional sources; MEDIUM = 2+ useful sources or strong local anchor + good supplementary; LOW = single usable source / substantial artistic or scope ambiguity; INSUFFICIENT = no defensible numerical range. Multiple national articles repeating similar values do not by themselves create HIGH confidence.

---

## 7. CENNIK_DEC_VEN-01 — Stiuk wenecki — klasyczny (M2, LABOR)

**Canonical comparability (catalog §11):** classic Venetian plaster application, labor, per m². *Not comparable:* veined marble-look workshop grades; lime-plaster interior coats.

- **Local (Kraków)** — no local firm publishes a Venetian **labor** m² rate (dflhome, dekormarmo: individual quotation; OLX TynkDeko Kraków: `od 100 zł/m² — wycena indywidualna`, scope covers marmorino+beton, so this minimum spans technologies and is **not** a classic-Venetian labor row). Only local **LABOR_AND_MATERIAL** anchor: **KB.pl Kraków row 405 zł/m² kompleksowo**, Małopolskie rows 387–424 (S1), min 10 m², white/gray base, "cena zawiera koszt robocizny i niezbędnych materiałów" → VEN L+M local mapping.
- **Supplementary PL — LABOR (canonical row basis):**
  - itynki.pl (S2): stiuk wenecki robocizna **120–150 zł/m²**, complex/complex-pattern > 200; material extra 30–80 zł/m²; Kraków +15–25% (big-city premium).
  - jakietynki.pl (S5): wysoki stopień skomplikowania (stiuk wenecki) robocizna **120–150 zł/m²**.
  - wistalex.pl (S6): standardowa aplikacja **80–120 zł/m²** (2024; secondary table 90–110), techniki specjalistyczne (wielowarstwowy, marmoryzacja) **120–150 zł/m²**; total L+M 150–250.
  - ewyposazenie.pl (S3): stiuk wenecki robocizna **150–300 zł/m²**; za trudne techniki + materiał → total 250–430 premium; suspicious "stiuk 60–70" = missing layers/quality.
  - adrem.org.pl (S4, Warszawa): robocizna **150–300 zł/m²** (podstawowy 150–200 · średni 200–250 · premium 250–300), **materiał 50–150 osobno** — explicit LABOR row.
- **Supplementary PL — LABOR_AND_MATERIAL (context only):** S15 ekipazlecenia `od 313 zł/m² kompleksowo`; S14 dekor-lux ~313 (4–6 warstw, polerowanie na gorąco, jasny/średni odcień, podłoże gotowe); S16 muratordom 350–480.
- **VAT:** UNKNOWN on all (no explicit netto/brutto on any of S1–S6/S14–S16 quoted rows; S15 "orientacyjny `od`").
- **Record per source (layers / polish / wax):** itynki: min 3 warstwy, każda polerowana; ewyposazenie: 4–6 warstw? (site: "kilka cienkich warstw"; konkret not). dekor-lux/Marmorinus: 4–6 warstw + polerowanie na gorąco + wosk; muratordom: polerowanie stalową pacą + wosk, ewentualnie do pomieszczeń wilgotnych po wosku; wistalex: standard 1–3 h/m², wielowarstwowy droższy.
- **Substrate assumption:** ready smooth/primed wall assumed for L+M system prices (dekor-lux: "podłożu gotowym do pracy"; VIAN: "idealnie gładkiego przygotowania"; muratordom: "podłoże pod stiuk wenecki"). Labor guides: prep billed separately (itynki: leveling robocizna 30–50 + material 25–40; wistalex prep 20–40; poilerobocizna: +15–30 leveling, +25–40 depth fixes).
- **Complexity:** STANDARD (plain white/gray, low-variation) → ENHANCED (tonal/cloud variation) → ARTISTIC (veining = separate row §8). VEN-01 band reflects STANDARD/ENHANCED only.
- **Market result:** `local_min/local_max` **—** (no local LABOR basis); `supplementary_pl_min 100 / max 160` (core 120–150; premium outliers 150–300 documented); `reference 140` (defensive within the 120–150 core cluster of 3 independent guides). **Confidence MEDIUM** (4 independent LABOR guides; no local LABOR row; artistic complexity).

---

## 8. CENNIK_DEC_VEN_MAR-01 — Stiuk wenecki — efekt marmuru z żyłkowaniem (M2, LABOR)

**Canonical comparability (catalog §11):** custom veining/waxing workshop work, labor, per m² — *"substantially higher than classic"*.

- **Direct veined-marble evidence (rare):**
  - **S12 VIAN (viandekor.pl, marble page)** — the only source that prices **actual veining** on a published m² L+M basis: **od 350 zł/m²** (classic light variants, moderate veining) **do 550 zł/m²** (complex multi-color, dark saturated, black marble with contrasting veins). Includes VIAN "Venezia" material + consumables (grunty, pasty, woski, ochronne) + labor. Small objects higher per m²; "cena zależy od złożoności wzoru i nasycenia koloru". Serving **Kraków+Katowice+Śląsk**.
  - **S14 dekor-lux** — direct statement on veining pricing: "czy żyły mają być wyraźnym rysunkiem, czy ledwie wyczuwalnym... **te dwa warianty wyceniamy inaczej**" (individual quotation, no published premium). Also: próbka (A4) shows color/polish but **not** the rytm rysunku — sample limitation.
- **Surrogate ranges (NOT veining-specific — kept separate):** ewyposazenie "efekt trawertynu lub marmuru" labor **80–160**; wistalex "marmoryzacja" labor **120–150**; poilerobocizna "marmurowy (mikrokruszywo)" **140 zł/m²** (marked by source as including material). These describe marble-effect generally and are **surrogate context only** — do not put them in the veined row.
- **VAT:** UNKNOWN (all).
- **Layers / scope:** veining introduced during layers with contrasting material, closed by subsequent passes (dekor-lux: 4–6 warstw, część rysunku ląduje pod spodem, przezroczyste wapno → głębia); VIAN: base toned layer → artystyczne żyłki → multiple depth layers → lustro-polski + wosk.
- **Complexity:** ARTISTIC / custom. Not reproducible 1:1 (dekor-lux) → cost depends on artist time, repetition not guaranteed.
- **Market result:** `local_min/local_max` **—** ; `supplementary_pl_min` — direct veined labor-only row does **not exist** on the Polish market at this check; the only defensible numeric is the **L+M veined band od 350–550 (S12, one regionally-served company)**; `reference` **null**. **Confidence LOW** (scope ambiguity + single explicit veined source + artistic premium undocumented). **Strong OWN_PRICE candidate** pending 9E.4/9E.5 — never invent a "veined premium" %.

---

## 9. CENNIK_DEC_CONC-01 — Efekt betonu / beton architektoniczny (M2, LABOR)

**Canonical comparability (catalog §11):** architectural-concrete **effect** (thin-layer decorative coating), labor, per m².

- **Local:** no Kraków firm with a published concrete-effect LABOR rate (dflhome — individual quotation; OLX TynkDeko Kraków `od 100 zł/m²` general minimum, scope includes "beton dekoracyjny", **not** a dedicated concrete-effect labor row). Regional: VIAN beton-effect **L+M 160 zł/m²** (S13, serves Kraków).
- **Supplementary PL — LABOR (canonical row basis):**
  - ewyposazenie.pl (S3): imitacja betonu architektonicznego robocizna **70–150 zł/m²**.
  - itynki.pl (S2): beton architektoniczny robocizna **100–140 zł/m²** (tabela); text says specialists charge even **140–180 zł/m²** (Robust internal inconsistency — flag).
  - jakietynki.pl (S5): "średnio skomplikowane (struktura betonu)" robocizna **80–120 zł/m²**.
  - konkret-beton.pl (S11): robocizna **50–120 zł/m²** (miasta do 150); below 60 usually excludes impregnation (+20–35); each extra layer **+25–40 zł/m²** (szalunek +35–50%, pores floje do 9500–12000/20 m²).
  - abc-tynki.pl (S9): robocizna **60–270 zł/m²** outer band; total L+M 80–350; material 20–60/m².
  - bursatm.pl (S10): L+M 100–300 (thin-layer); **płyty betonowe 200–400 zł/m² excl. from row**; tynk robocizna "od 60".
  - poilerobocizna beton (S8): robocizna **70–300 zł/m²** (method-dependent: thin-layer vs prefab panels — panels excluded from row).
- **VAT:** UNKNOWN (none explicit; konkret mentions "od 90 zł netto" for a different product — not used).
- **Substrate:** thin-layer (1,5–3 mm, PN-EN 13914-2 tolerance ~2 mm/mb, konkret) → **surface leveling is a separate billed item where wall deviates** (konkret +8–12 zł/m² per correcting mm; itynki prep 30–50 robocizna + 25–40 materiali; poilerobocizna prep +15–30). Record prep as excluded from the labor row unless source states otherwise (VIAN's 160 includes "przygotowanie powierzchni — wyrównanie + grunt" inside L+M).
- **Complexity:** STANDARD (smooth industrial 3 passy) → ENHANCED (szalunek/deska 5–7 warstw, pory, rysy — premium 20–50% or extra layers). Band reflects STANDARD.
- **Microcement guard:** sources that describe **microcement/mikrobeton** (dekor-lux "Betonus", konkret "połyskliwy mikrocement `często mylony z betonem` 220–380 zł/m² material, Batch D FLOOR_S) — excluded from this row. See §11 EXCLUSION LIST.
- **Market result:** `local` **—**; `supplementary_pl_min 60 / max 150` (core of 5 guides; outer 50–270 documented); `reference 110`. **Confidence MEDIUM** (5 independent national guides, no local rate, method spread).

---

## 10. CENNIK_DEC_GENERIC-01 — Tynk dekoracyjny — ogólny (M2, LABOR)

**Canonical comparability (catalog §11):** generic decorative render (stone/sand, glaze effects), labor, per m². Fallback row.

**COMMON_DECORATIVE_CONTEXT (documented):** the category "tynk dekoracyjny ogólny" in the market maps most consistently to the **structural / colored / rustykalny / glaze-render** family: single-layer colored renders (baranek, kornik, strukturalny kolorowy), rustic/rust-effect, thin-layer "pearl/metallic" surfaces at the high end, stone/travertine imitation, stucco wapienne — **a genuinely heterogeneous family.** Per catalog comparability we build this canonical numerical range **only from the structural/colored/glaze sub-family** (scopes comparable within one pass/one color), and document the rest as scope context:

- ewyposazenie.pl (S3): tynk strukturalny (prosty wzór) robocizna **40–70 zł/m²**.
- itynki.pl (S2): strukturalny kolorowy **50–70 zł/m²**, rustykalny/efekt rdzy **60–80 zł/m²** (table); trawertyn **80–110** (outside narrow family — context); effect metaliczny/perłowy 130–180 (context, high end).
- jakietynki.pl (S5): najprostsze modele **60–80 zł/m²**.
- poilerobocizna (S7): strukturalny **40 zł/m²** calculator base / 40–55 na dużych metrażach; (its table claims "robociznę z materiałem" — see §7 mix caveat; the 40 zł structural row aligns with the labor band).
- **substrate:** rough/primed/structured wall standard; glaze single layer; prep extra (S2 30–50; S7 +15–30).
- **VAT:** UNKNOWN.
- **Market result:** `local` **—**; `supplementary_pl_min 40 / max 80`; `reference 60`. **Confidence MEDIUM** (4 independent guides within the narrow structural family; category breadth documented, no local row).

---

## 11. EXCLUSION LIST — concrete vs microcement / panels / resin guard (prevents future research contamination)

| Excluded scope | Evidence encountered | Why excluded from CENNIK_DEC_* rows |
|---|---|---|
| Microcement / mikrobeton (walls+floors, wet zones) | dekor-lux calculator "Betonus"; konkret-beton "połyskliwy mikrocement ... często mylony z betonem 220–380 zł/m² material, 2 warstwy 2–3 mm, szlifowanie"; VIAN mineral concrete/microcement; Batch D evidence | **belongs to CENNIK_MC_* (Batch D)** — different system (cement+polimer+kwarc), different prep (hydroizolacja), different surface (floors/staircases) |
| Architektural-concrete **panels** (prefab, montowane na klej) | bursatm "płyty betonowe 200–400 zł/m²"; poilerobocizna beton page "płyty prefabrykowane" (70–300 shared band) | separate product/installation scope; not a wall-applied thin-layer decorative coating |
| **Raw / cast** concrete (in-situ wylewany) | abc-tynki "in situ ... dłuższy czas schnięcia"; konkret panel context | structural/construction scope, not coating — never decorative-price basis |
| Resin / polished-concrete **floors** | konkret posadzkowe rows (zacieranie betonu cena) | posadzki scope, not wall effect; also covered by MC_FLOOR_S |
| **Limewash / wychmurzenia** (R3 usage) | dekor-lux "Limewash", dflhome "tynk wapienny wychmurzenia" | separate cheap lime-wash technology, NOT classic Venetian; Generic context at most |
| Tadelakt / Tynk japoński / Sahara / Alkantara (zamsz) / efekt skały | dekor-lux calculator; Bursa content | exotic finish family — catalog says *do not over-expand*; recorded as future-proofing notes only |

Also excluded because they are **retail products, not contractor labor**: Jeger/Magnat Venetian kits (S16/S17 material context, DERIVED 14–22 / 30–46 / 59–83 zł/m²), stucco-naturale.com product page, budujto.pl product page, allego listing "Stiuk Marmur", Parametra Kraków store (marmorino material retail).

---

## 12. MINIMUM JOB / SMALL-AREA + MOBILIZATION FINDINGS (commercial context, NOT M2 rates)

- **Minimum m²**: KB.pl Venetian rows quote **min 10 m²** (S1).
- **Small-wall surcharge** (explicit): VIAN marble — "małe obiekty mają wyższą cenę za metr kwadratowy" (causes: no continuous-application technology) (S12); poilerobocizna — `6 m²` łazienka **+30%** per m² vs standard, `>50 m²` **−10–15%** rabat (S7); ekipazlecenia — `>50 m²` negocjujemy stawkę (S15); dekor-lux — `>50 m²` stawka niższa + single-batch tinting (S14).
- **Fixed sample/mock-up cost**: konkret-beton — professional requires **próbka minimum 1 m²** przed zleceniem (S11); dekor-lux — A4 próbka shows color/polish but not veining rhythm (S14). **No flat sample fee found on any Polish page** — recorded as commercial context; a future `CENNIK_DEC_SAMPLE-01`-style item would need 9E.4/9E.5 owner decision (NOT created in research).
- **Mobilization / floor-protection**: not published by decorative sources; poilerobocizna lists narożniki 25–40 zł/mb and folia as context (S7); treated as hidden-cost note identical to Batch A PREP discussion.

None of the above converted into a per-m² rate in the canonical rows.

## 13. Marble / veining complexity — dedicated context (task §22 — important for our intended Venetian work)

- **VIAN** monetizes veining explicitly within its **L+M band**: od 350 (classic light, moderate veining) → 550 (multi-color, dark saturated, black+contrasting veins); "cena zależy od złożoności wzoru i nasycenia koloru — ciemne i kontrastowe warianty wymagają większego mistrzostwa i czasu". That corresponds to a **~57% spread between simple and complex veined finishes** — quoted as a range, not as a percentage surcharge over classic.
- **dekor-lux** (Warszawa): veining variants priced **individually** ("wyceniamy inaczej"); no published premium. Artwork not reproducible 1:1; client must pre-decide vein density/contrast.
- **wistalex**: "marmoryzacja" priced in its specialist column **120–150 zł/m² LABOR** (vs 80–120 standard) — i.e., surrogate ~+0–50% over standard Venetian on a **general marble-effect** (not necessarily hand-veined) basis; flagged because nicht explicit veining.
- **ewyposazenie**: "efekt trawertynu lub marmuru" 80–160 LABOR — same note.
- **No Polish source** publishes a **fixed additive % or fixed zł for veining over classic Venetian** as a professional labor row. Conclusion for 9E.4: the veined row (`VEN_MAR`) has **no defensible standalone LABOR range**; candidate for OWN_PRICE derivation from own workshop man-hours (typical veined Venetian = classic labour + drawing/layers + risk), with S12's 350–550 L+M used only as a **market sanity window**.

---

## 14. Material system context (manufacturer / store / media evidence — NOT labor)

| Source | System/brand | Product | Package price | Coverage/consumption | DERIVED PLN/m² (formula) | Notes |
|---|---|---|---|---|---|---|
| S16 muratordom/Jeger | Włoski stiuk wapienny (natural lime) | 250–285 zł / 5 kg | → 4–5 m² | **50–71 zł/m²** (`250/5` … `285/4`) | natural lime Venetian |
| S16 same | Podkład | 100–130 zł / 1–2 l | → 8–12 m² | **8–16 zł/m²** (`100/12` … `130/8`) | base for natural system |
| S16 same | całkowity zestaw natural (10 m²) | 590–830 zł | 10 m² | **59–83 zł/m²** (`590/10` … `830/10`) | stated by article |
| S16 same | Komplet syntetyczny (akryl, set incl. podkład+stiuk+pigment+wosk) | 300–460 zł | 10 m² | **30–46 zł/m²** (`300/10` … `460/10`) | acrylic single-layer substitute |
| S17 dekoratorniatv | Stiuk Wenecki **Magnat** | 140–220 zł / 5 kg | ~10 m² | **14–22 zł/m²** (`140/10` … `220/10`) | retail kit |
| S14/L Reward market | Mikrocement "Betonus" (dekor-lux calculator family) | — | — | not licenseable labor | microcement excluded |
| S11 konkret | Beton architektoniczny suchy tynk | 18–75 zł / kg | 1 kg → 1,2–1,8 m² @1 mm; 3 warstwy → 4,5–5,5 kg/m² | **95–420 zł/m²** (`4,5×18` … `5,5×75`) | formula shown; binder-cement & acrylic compounds |
| S11 konkret | Lakier/wosk/impregnat | 45–180 zł / l | 0,08–0,12 l/m² @2 warstwy | ~4–22 zł/m² (`0,08×45` … `0,12×180`) | sealing layer |

Every DERIVED cell shows the formula. These are **material/store/retail contexts** — never treated as contractor labor. Wholesale/retail echelons: structural 20–50 (S3), travertine/stone 40–90 (S3), venetian natural 50–150 (S3), concrete thin-layer 95–420 (S11). Manufacturer/store sources: stucco-naturale.com, budujto.pl, oikospaint.materiali, Parametra (Kraków) — listed as product retail, excluded from labor.

---

## 15. TECHNOLOGY COMPARISON MATRIX (normalization input for 9E.4)

| Source | Technology | Classic Venetian | Veining | Concrete effect | Other decorative | Labor | Material | Prep | Primer | Layers | Polish/wax | Unit | Price | VAT |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1 KB.pl (Kraków row) | stiuk wenecki kompleksowo | YES | NO | NO | NO | L+M | YES (incl.) | UNKNOWN | UNKNOWN | n/a (complet) | YES (polerowany stiuk) | M2 | 405 zł/m² (Kraków; Małop. 387–424) | UNKNOWN |
| S2 itynki.pl | tynk dekoracyjny labor (venetti/beton/trawertyn/strukt.) | YES | NO | YES | YES | LABOR | NO (30–80 extra) | quoted separately | YES (grunt before app) | VEN min 3; TRAW 3+ | VEN polished; sealing extra 15–35 | M2 | VEN 120–150 · BETON 100–140 (text: 140–180) · TRAW 80–110 · STRUKT 50–70 · METAL 130–180 | UNKNOWN |
| S3 ewyposazenie.pl | tynk dekoracyjny labor+material | YES | surrogate | YES | YES | LABOR (table) | material table 20–180 | separate | YES | VEN 4–6 (multi) | wax/lacquer separate | M2 | VEN 150–300 · CONC 70–150 · MAR 80–160 · STRUKT 40–70 | UNKNOWN |
| S4 adrem.org.pl | stiuk wenecki (Warszawa) | YES | NO | NO | NO | LABOR | NO (50–150 separate) | separate (grunt/wyrównanie) | YES | 3+ warstwy | polerowanie + wosk | M2 | 150–300 (podst 150–200/środ 200–250/prem 250–300) | UNKNOWN |
| S5 jakietynki.pl | tynk dekoracyjny ladder | YES | NO | YES (struktura betonu) | YES | LABOR | n/a | not stated | UNKNOWN | proste/srednie/wysokie | UNKNOWN | M2 | 60–80 · 80–120 (beton) · 120–150 (venetti) | UNKNOWN |
| S6 wistalex.pl | stiuk wenecki | YES | marmoryzacja separate | NO | NO | LABOR | NO (50–100) | prep 20–40 separate | YES | standard multi-layer | multi-layer/metallic premium | M2 | 80–120 (specj. 120–150); total 150–250 | UNKNOWN |
| S7 poilerobocizna | tynk dekoracyjny (venetti/strukt.) | YES | NO | YES | YES | MIXED — table says robocizna+materiał, intro says robocizna | note | +15–30 wyrównanie | YES | venetti 3+ | polish stages | M2 | intro 80–180 (do 250); calc: STRUKT 40 · STUCCO 70 · WENECKI 130 · BETON 110 · MARMUR 140 | UNKNOWN |
| S8 poilerobocizna beton | beton architektoniczny | NO | NO | YES (thin-layer + panels) | NO | LABOR (70–300 mixes panels) | panels exclude | not stated | YES | layers per method | sealer/lacquer | M2 | 70–300 (method-dependent) | UNKNOWN |
| S9 abc-tynki.pl | beton architektoniczny | NO | NO | YES | NO | LABOR (60–70% of budget) | 20–60 | separate | YES | 2–3 warstwy | sealing incl. (see text) | M2 | labor 60–270; L+M 80–350 | UNKNOWN |
| S10 bursatm.pl | beton architektoniczny | NO | NO | YES (thin-layer) | NO | LABOR (od 60) | yes in L+M 100–300 | UNKNOWN | YES | UNKNOWN | wax | M2 | L+M 100–300; panels 200–400 (excl.) | UNKNOWN |
| S11 konkret-beton | beton dekoracyjny | NO | NO | YES | NO | LABOR | material 95–420 | billed extra (+8–12/mm) | YES (grunt) | 3–7 warstw | lacquer/wax +20–35 | M2 | labor 50–120 (miasta 150); extra layer +25–40 | UNKNOWN (one unrelated "netto" noted) |
| S12 VIAN — marmur | marmorino/stiuk, veining | YES (as classic base) | **YES (explicit veins)** | NO | NO | L+M | YES (incl.) | wall prep to smooth (incl. in L+M per text) | YES base toned | base + veins + depth layers | polerowanie + wosk | M2 | od 350 → 550 (veined; komplexicity-driven) | UNKNOWN (incl. materials) |
| S13 VIAN — beton | tynk beton dekoracyjny | NO | NO | YES | NO | L+M | YES (incl. consumables) | wyrównanie+grunt (incl.) | YES | multi-step blocks | tonowanie + wosk ochronny | M2 | 160 zł/m² (dark colors wyższa) | UNKNOWN (incl. materials) |
| S14 dekor-lux | marmorino / venetti / many effects | YES | YES (separat, wyceniamy inaczej) | NO | YES (travertino, tadelakt, japandi…) | L+M | YES (incl. material) | podłoże "gotowe do pracy" | UNKNOWN | 4–6 warstw | polerowanie na gorąco + wosk | M2 | ~313 (klasyczny jasny/średni); veined = indywidualnie | UNKNOWN |
| S15 ekipazlecenia | stiuk wenecki kompleksowo | YES | NO | NO | NO | L+M | YES | indywidualna wycena | UNKNOWN | UNKNOWN | polish/wax implied | M2 | od 313 zł/m² (base), >50 m² negotiable | UNKNOWN |
| S16 muratordom/Jeger | stiuk wenecki | YES | NO | NO | NO | L+M (system) / MATERIAL (derived) | YES in L+M 350–480; material 30–83 derived | podłoże separate | YES (podkład) | multi-layer synthetic/lime | polerowanie + wosk | M2 / kg | L+M 350–480; material 59–83 natural / 30–46 synt | UNKNOWN |
| S17 dekoratorniatv | stiuk wenecki (Magnat) | YES (material) | NO | NO | NO | MATERIAL | yes (retail kit) | not stated | part of kit | stated ~10 m²/5 kg | polish/wax by contractor | M2 | material 14–22 (derived) | UNKNOWN |
| S18 OLX TynkDeko (Kraków) | tynki dekoracyjne / marmorino / beton / złocenia | YES (mixed offer) | UNKNOWN | YES (mixed offer) | YES (złocenia) | UNKNOWN (od 100 zł/m², wycena indyw.) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | M2 | od 100 zł/m² | UNKNOWN |
| S19/S20 dflhome (Kraków) | imitacja betonu / tynk wapienny / marmorino | YES | YES (efekt marmuru in offer) | YES | YES | UNKNOWN (indywidualna wycena) | — | — | — | — | — | M2 | — | — |
| S21 dekormarmo (Kraków) | stiuk, trawertyn, beton dekoracyjny | YES | NO (stiuk/trawertyn) | YES (beton dekoracyjny) | YES (piaskowiec, welur, skóra…) | UNKNOWN (no prices) | — | — | — | — | — | — | — | — |
| S22 cenauslug (Kraków row) | stiuk wenecki | YES | NO | NO | NO | UNKNOWN | — | — | — | — | — | — | HTTP 410 (dead) | — |
| S23 cudaarchitektury (+siblings) | stiuk wenecki | YES | NO | NO | NO | UNKNOWN | — | — | — | — | — | — | 403; content-network (mebloweporady/forummeble) — not independent | — |

---

## 16. OWN_PRICE / internal items — candidates after research

- **CENNIK_DEC_VEN_MAR-01 (veined marble)** — the **strongest OWN_PRICE candidate** in Batch E: no Polish published veined-LABOR m² row; only L+M 350–550 (one regionally-served firm) + normative "individually quoted" (Warszawa firm). Catalog already flags "(substantially higher than classic)". **Do not assign a market value; derive from own workshop man-hours at 9E.4/9E.5**, keep S12's 350–550 L+M as sanity window, keep classic band 120–150 labor as relative anchor.
- **CENNIK_DEC_CONC-01 / VEN-01 / GENERIC-01** — have defensible national LABOR ranges (S2/S3/S5/S6/S11 in cross-check); **not** OWN_PRICE. Local (Kraków) pricing still individual — 9E.4 decision should set the local coefficient using the itynki +15–25% big-city margin and/or owner's own rate sheet.
- No new catalog rows proposed during research (task §1 — catalog restructuring belongs to 9E.4).

---

## 17. NORMALIZATION_REVIEW_NOTE (Batch A/B/C/D issues preserved + new Batch E issues, for 9E.4)

**Batch A/B issues (1)–(5) preserved untouched** (prep/priming/skim/sanding — see Batch A/B §21).
**Batch C issues (6)–(9) preserved untouched** (reveal unit model etc. — Batch C §16/§21).
**Batch D issues (10)–(19) preserved untouched** (microcement — Batch D §18).

**New Batch E issues (20)–(29):**
1. **(20) Classic vs veined Venetian** — classic LABOR band 120–150 has 3+ independent national guides; veined row has **no standalone LABOR range** (only L+M 350–550 by one firm + individual quotation). Do not merge; VEN_MAR keeps null reference until 9E.5.
2. **(21) `stiuk syntetyczny` vs natural lime** — acrylic single-layer kits (30–46 zł/m² material) must never be priced like natural lime Venetian (59–83 zł/m² material); the classic-LABOR range already implicitly assumes multi-layer natural systems; synthetic "venetian 60–70 zł/m²" offers are a quality flag (ewyposazenie warning).
3. **(22) quoting-mode mixes in national guides (S7 poilerobocizna)** — same page claims "robocizna 80–180" in intro while its price table states "robociznę z materiałem"; S9/S10/S11 likewise mix "robocizna" vs total. Only explicitly-labor rows feed LABOR ranges; L+M figures feed L+M context.
4. **(23) Material-system differences in one floating "tynk dekoracyjny" family** — the generic row is only defensible if restricted to structural/colored/rustykalny (40–80 labor). Travertine 80–110, metallic/pearl 130–180, limewash, tadelakt etc., are separate scopes; document `COMMON_DECORATIVE_CONTEXT`, and **9E.4 must decide whether GENERIC-01 keeps a range at all or becomes OWN_PRICE/reference-only** (catalog comparability allows a labor row; technology breadth documented).
5. **(24) Artistic complexity must not be normalized** — veining, multi-color, szalunek patterns command unquantified premiums (VIAN zolo 350→550; konkret szalunek +35–50%, pory 9500–12000/20m²; dekor-lux individual). No percentage surcharge invented; ENHANCED/ARTISTIC documented as scope notes only.
6. **(25) Substrate-prep inclusion varies** — L+M system prices assume "gotowe podłoże" (dekor-lux, VIAN), labor rows exclude prep (itynki 30–50 robocizna; konkret +8–12/mm levelling; poilerobocizna +15–30). 9E.4 must keep prep out of DEC rows (it belongs to PREP/SKIM rows in Batch A).
7. **(26) Small-job / min-m² pricing** — `min 10 m²` (KB), `6 m² → +30%`, `>50 m² −10–15%` (S7), `>50 m²` negotiable (S14/S15), sample `≥1 m²` (S11). Excluded from unit rows; a future flat-rate/sample item is a 9E.4/9E.5 decision, not research.
8. **(27) Concrete-effect vs microcement contamination** — concrete-effect rows must stay thin-layer-wall-applied (1,5–3 mm decorative coating). Microcement (220–380 zł/m² material; MC_* Batch D), prefab panels (200–400 zł/m²), cast-in-situ concrete and resin floors are **excluded** (§11 list) — this guard is the permanent boundary document for 9E.4/9E.6 seeds.
9. **(28) KR-Based "Kraków 405 zł/m² kompleksowo" portál city-row nature** — S1 KB.pl city rows are national-portal **city-mapped** figures (min 10 m², kompleksowa, white/gray base), not a Kraków firm quote; Małopolskie 387–424 spread is a mapping spread. Useful only as **L+M sanity window for VEN**, not as a labored local row. Same class as Batch C issue (9) (o-okna zone mapping) and Batch D (kb.pl usage).
10. **(29) Content-network duplication** — cudaarchitektury/mebloweporady/forummeble (one skeleton, 403 on primary — S23) and the `*tynki` family (itynki/jakietynki/t-tynki) must not be over-weighted; the concrete-effect/labor guides (abc/bursa/poilerobocizna/konkret) are SEO-poradnik ecosystem — count as 4 differing data points, never 4 confirmations. SANITMAX-type archival note applies (S22 cenauslug HTTP 410, S23 403, S12/S13/S14/S15 pages may drift — re-verify before 9E.5/9E.7 seeding).

---

## 18. Research summary (for `docs/development-progress.md`)

- Items researched: **4 / 4** Batch E items.
- Sources: **23 referenced pages** (16 weighted + 7 flag/exclusion: 2 Kraków firms qualitative, 1 Kraków marketplace anchor, 1 dead portal row, 1 blocked content-network, 1 city-page negative, plus S20 dflhome 2nd page), of which **0 published a Kraków-local m² LABOR rate**, **1 Kraków-local marketplace anchor** (OLX TynkDeko Kraków `od 100 zł/m² — wycena indyw.`), **2 regional serving-Kraków** (VIAN L+M marble 350–550 / concrete 160; KB.pl Kraków-row 405 L+M stiuk), and **~16 Poland-wide/manufacturer-market pages**.
- Confidence distribution: **HIGH 0** · **MEDIUM 3** (VEN, CONC, GENERIC) · **LOW 1** (VEN_MAR veined) · **INSUFFICIENT 0**.
- OWN_PRICE candidates: **VEN_MAR (veined marble)** — strongest (no veined-LABOR market row); local coefficient for VEN/CONC/GENERIC remains an owner/9E.4 decision (big-city +15–25% documented).
- Market structure finding: decorative-finish prices in Poland are split between (a) **national labor guides 40–150/300 zł/m² robocizna** (structural → classic venetian ladder) and (b) **firm-published L+M system prices 160–550 zł/m²** (beton 160; venetian 313–480; veined marble 350–550). Kraków firms publish **no fixed M2 labor rates** — artistic/custom work is individually quoted. Both channels kept separate.

---

## 19. CROSS-CHECK (9E.3E §26)

- **All 4 canonical items researched** — yes; codes verbatim from catalog §11.
- **Exact URLs present** — §5 index + matrix + per-item sections.
- **Local vs PL separated** — LOCAL priced 0 / regional-serving-Kraków 2 (VIAN, KB row) / national ~16; local qualitative firms (dflhome, dekormarmo, OLX) documented, not scored as priced rows.
- **LABOR vs MATERIAL vs L+M separated** — LABOR ranges fed only from labor-labelled rows (itynki, jakietynki, wistalex, adrem, ewyposazenie table, konkret, abc-tynki, poilerobocizna-labor rows); L+M bands fed only from system prices (KB 405, dekor-lux 313, ekipazlecenia 313, muratordom 350–480, VIAN 160/350–550, bursatm 100–300); material context (S16/S17, konkret material) kept in §14. No cross-feeding, no subtraction of material to derive labor.
- **Classic Venetian not mixed with veined** — classic row uses non-veined guides; veining segregated into §8/§13 with surrogate evidence flagged.
- **Concrete effect not mixed with microcement** — §11 exclusion list explicit; VIAN beton (160, thin-layer) counted for CONC, VIAN marble (350–550) not; "Betonus"/konkret-microcement excluded into Batch D.
- **Generic decorative range not fabricated from unrelated technologies** — GENERIC row limited to structural/colored/rustykalny 40–80; travertine/metallic/stone separated as context; `COMMON_DECORATIVE_CONTEXT` documented.
- **Substrate prep documented** — per source (§9, §15 matrix, §17 note 6); no prep-inflated labor rows.
- **Minimum charges excluded from unit ranges** — §12 records min 10 m², small-wall surcharges, sample requirements as context only.
- **Artistic/custom work not normalized** — no invented veining surcharge; VIAN's 350–550 is a quoted band (state it), dekor-lux individual (quote it), no mathematical extrapolation.
- **No invented prices** — every numeric figure is quoted or derived-with-formula from a checked source; content-network clones (S23) counted zero.
- **VAT** — UNKNOWN everywhere except explicitly noted (none in this batch); no automatic conversion between bases.

---

## 20. Source archival & exclusion notes

- S12/S13 (viandekor.pl), S14 (dekor-lux.pl), S15 (ekipazlecenia.pl), S1 (kb.pl) pages may drift/rotate — re-verify before seeding (9E.5/9E.7).
- OLX listing (S18) is a JS-rendered page; the 2 MB render served the text at check time — treated as a marketplace anchor, re-check before 9E.5.
- Dead/blocked at check time: cenauslug.pl stiuk wenecki Kraków **HTTP 410** (consistent with Batch C dead-Kraków-service-row finding); cudaarchitektury.pl **HTTP 403** (content-network sibling mebloweporady.pl mirrors the same article — not counted).
- Local firms audited as qualitative: dflhome.pl (Kraków Kliny; Wieliczka realization images; "nie ma jednej ceny ... wycena indywidualnie"), dekormarmo.pl (Kraków decorative studio, portfolio-only, stale site ~2013). **Neither publishes M2 prices** — recorded for the Kraków negative audit, not as price rows.
- `checked_at` note: all `checked_at` = **2026-09-14**.