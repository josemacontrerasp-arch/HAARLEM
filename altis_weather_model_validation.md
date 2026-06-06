# ALTIS GROEP — Validation of the Weather→Schedule Model

**Scope:** validating the quantitative rain/frost → lost-work relationship inside the 13-week cash-flow forecast for a Dutch roofing (*dakdekkers*) portfolio.
**Bottom line:** the current **linear "days lost per mm of rain + per frost day" form is not defensible.** The Dutch construction sector runs on a **threshold / binary "unworkable day" (onwerkbare dag)** model with legally-defined triggers. Switch to that form, calibrate intensities **per calendar quarter** off KNMI De Bilt norms, and add a roofing-specific severity uplift.

---

## 1. Recommendation on the functional form

**Replace the linear per-unit model with a threshold "unworkable-day" model**, because that is exactly how Dutch labour law, construction contracts, and the academic literature all treat weather.

**Why linear-per-mm fails.** Rain stoppage is governed by *occurrence and duration during working hours*, not total depth. A steady 4 mm drizzle across the whole working day stops membrane/adhesive roofing; a 30 mm overnight cloudburst that clears before 07:00 may cost nothing. A coefficient that scales with millimetres mis-allocates losses across quarters (it over-weights heavy-downpour quarters that can still be workable and under-weights drizzle-heavy quarters). Likewise, frost impact is not proportional to "frost days" defined as Tmin ≤ 0 °C — most such nights are followed by perfectly workable days.

**The form that maps to the Dutch rules.** Two layers, both binary/threshold, applied per workday and summed over the 13-week horizon:

- **Rain.** A workday is *unworkable* if it rains for **≥ 300 minutes (5 hours) between 07:00 and 19:00** in the work postcode (CAO Onwerkbaar weer Bouw & Infra). This dovetails with the contract standard (UAV 2012 §42 / AVA 2013 / Woningborg): a day is *onwerkbaar* if, for reasons outside the contractor's control, **the majority of workers/machines cannot work for ≥ 5 hours**.
- **Frost/cold.** A workday is *unworkable* if **any** CAO frost norm is met (window 1 Nov – 31 Mar): overnight (00:00–07:00) temperature was **below −3 °C**; or measured temperature at 07:00 **and** 09:00 was **≤ −0.5 °C**; or temperature at 09:00 was **≤ −1.5 °C**; or **feels-like (gevoelstemperatuur) at 09:30 was ≤ −6.0 °C**. Note this is *not* "Tmin ≤ 0 °C".

**Optional refinement (academic best practice).** El-Rayes & Moselhi distinguish **complete work stoppage** (binary, above threshold) from **partial productivity loss** (a decrement on marginal days). For roofing, stoppage dominates because adhesives/membranes simply cannot be applied to a wet or icy deck, so the binary layer carries ~90% of the signal; a small partial-loss decrement can be layered on "marginal" days if you want precision. This keeps the model both legally anchored and technically faithful.

**Net:** keep a *number-of-unworkable-days* output (which is what feeds milestone slippage → billing → cash), but generate it from thresholds, not from a per-mm slope.

---

## 2. Parameter table

| Parameter | Our value | Recommended value | Functional form | Source | Confidence |
|---|---|---|---|---|---|
| Rain → lost work | 0.04 days lost per mm | **Day lost if ≥ 300 min (5 h) of rain in 07:00–19:00** (CAO); contract test = work impossible ≥ 5 h (UAV 2012 §42) | **Threshold/binary day**, not linear | CAO Onwerkbaar weer Bouw & Infra (Bouwend Nederland; ESPEQ); UAV 2012 §42 (Kienhuis, FDJ) | **STRONG** |
| Rain — roofing-specific deck threshold | n/a | **Membrane/adhesive work lost on essentially any measurable rain wetting the deck (~≥ 1 mm)**, *plus* 1–several "drying/lingering" days after significant rain | Threshold + lingering-day add-on | Roofing-practice sources (EPDM dry-substrate rule; deck stays damp days after rain); El-Rayes & Moselhi "lingering days" | **MODERATE** |
| Frost definition | Tmin ≤ 0 °C | **CAO frost norms** (overnight < −3 °C, or ≤ −0.5 °C at 07:00 & 09:00, or ≤ −1.5 °C at 09:00, or feels-like ≤ −6 °C at 09:30) for *unworkability*; keep KNMI *vorstdag* (Tmin < 0 °C) only as climate label | Threshold/binary day | CAO Onwerkbaar weer Bouw & Infra (Aannemersfederatie; HZC); KNMI definitions | **STRONG** |
| Frost → lost work | 0.8 days per "frost day" | **Day lost only if CAO frost norm met** (≈ a *fraction* of KNMI vorstdagen; severe-frost "strenge vorst" days are the clearest stoppages) | Threshold/binary day | CAO; KNMI (strenge vorst = Tmin ≤ −10 °C) | **MODERATE** |
| Frost season | implicitly year-round | **Restrict to 1 Nov – 31 Mar; ≈ 0 in Apr–Oct** | Calendar gate | CAO winter season; KNMI seasonal frost distribution | **STRONG** |
| Wind / storm | not modelled | **Day lost if KNMI code-red warning for the work postcode** (CAO storm trigger); roofing also halts in high wind on safety grounds well below code red | Threshold/binary day | CAO Onwerkbaar weer (Bouwend Nederland) | **MODERATE** |
| Half-days | implied (fractional) | **Count whole unworkable days** (arbitration treats half-days as not deductible under UAV) | Whole-day | Raad van Arbitrage voor de Bouw, 1 Jul 2020, nr. 81.669 (Kienhuis) | **MODERATE** |
| Roofing vs general construction | 1× (implicit) | **≈ 1.5–2× more unworkable days** than general construction (estimate — no published Vebidak multiplier found) | Multiplier on day count | Inferred from roofing technical constraints + "type of work" factor (El-Rayes & Moselhi) | **WEAK** |

---

## 3. Corrected base/wet/dry quarterly intensities (KNMI De Bilt, 1991–2020)

**Anchors (citable):** KNMI normal annual precipitation **≈ 851 mm**; De Bilt **≈ 53 frost days (vorstdagen, Tmin < 0 °C) per year**, down from ~75; ~185 days/year with ≥ 0.1 mm precipitation.

**The single biggest error in the current scenarios is that they are season-agnostic.** Rain is fairly evenly spread (so a flat number is *roughly* OK), but **frost is almost entirely a Q1/Q4 phenomenon** — a flat "4 frost days per normal quarter" is wildly wrong for a winter quarter and wrong (too high) for summer.

Approximate KNMI De Bilt 1991–2020 normals by **calendar quarter** (precip from monthly normals; frost days indicative — pull exact values from the KNMI Klimaatviewer station table):

| Calendar quarter | Precipitation (mm) | Frost days (Tmin < 0 °C) | Comment |
|---|---|---|---|
| Q1 (Jan–Mar) | ≈ 185 | ≈ 30 | Cold + the frost-driven quarter |
| Q2 (Apr–Jun) | ≈ 175 | ≈ 3 | Driest, mildest |
| Q3 (Jul–Sep) | ≈ 240 | ≈ 0 | Wet (convective), no frost |
| Q4 (Oct–Dec) | ≈ 245 | ≈ 12 | Wet + onset of frost |
| **Year** | **≈ 851** | **≈ 45–53** | |

**Verdict on the model's scenarios:**

- **"Normal" 180 mm** — only correct for a spring-type quarter; a true central quarter is **~210 mm**, and Q3/Q4 run **~240 mm**. Raise and make season-dependent.
- **"Wet" 320 mm** — *plausible* as a wet winter/autumn extreme (≈ P90). Keep.
- **"Dry" 90 mm** — *plausible* as a dry-spring extreme (≈ P10; cf. dry springs 2011/2020). Keep.
- **Frost 4 / 9 / 1 (normal/wet/dry)** — **the real defect.** These ignore seasonality *and* use the wrong (Tmin ≤ 0) definition. Replace with a calendar-quarter frost profile (≈ 30 / 3 / 0 / 12 KNMI vorstdagen for Q1/Q2/Q3/Q4), **then translate to unworkable days** via the CAO threshold (the CAO count is much lower than the vorstdag count — many vorstdagen are workable by midday).

**How the model should pick a scenario.** The 13-week horizon's weather profile is driven by **which calendar quarter it covers**. Recommended approach: (1) tag the horizon by quarter; (2) load that quarter's KNMI base precipitation and frost-day profile; (3) apply the threshold rules to convert to expected unworkable days; (4) run wet/dry as P90/P10 deviations *of that quarter*, not a single global wet/dry. A roll-up's billing seasonality (slow Q1, busy Q2–Q3) then falls out naturally.

> **Caveat on frost counts:** KNMI *vorstdagen* (Tmin < 0 °C) overstate unworkable days. The genuinely unworkable frost days under the CAO norms are far fewer and vary enormously year-to-year (mild winters ≈ near zero). Derive the unworkable-frost count either from KNMI **hourly** station data tested against the CAO thresholds, or from **UWV vorst-WW historical declarations** for the relevant postcodes. Treat any single fixed number as MODERATE/WEAK.

---

## 4. How to defend this to a CFO or a judge

Anchor the entire weather module to **one authoritative, externally-defined standard** so it reads as a regulated input, not a guess:

> *"Unworkable days are defined exactly as in the **CAO Onwerkbaar weer Bouw & Infra** and the **UAV 2012 (§42)** — a workday is lost when it rains ≥ 5 hours in the 07:00–19:00 window, when the CAO frost/wind-chill norms are met, or when ≥ 5 hours of work is impossible. Expected frequencies are calibrated to **KNMI De Bilt 1991–2020 climate normals** by calendar quarter, and verified the same way **UWV** verifies a Vorst-WW claim — against the KNMI station for the work's postcode."*

That sentence does three things a finance committee or arbitrator respects: (i) the thresholds are **someone else's** (a CAO and a standard-form contract that the company's own payroll and contracts already use); (ii) the climatology is the **national meteorological authority's** published norm; and (iii) it mirrors the **exact verification mechanism** the regulator (UWV) and the construction arbitration body (Raad van Arbitrage voor de Bouw, e.g. ruling nr. 81.669) actually apply — including that they prefer real KNMI data over generic averages and count whole days only. By contrast, a "0.04 days per mm" slope has no source in law, contract, or the productivity literature and is the first thing a hostile reviewer would pull on. El-Rayes & Moselhi's list of the seven contested factors in weather claims (definition of *normal* weather, thresholds, type of work, lingering days, criteria for lost days, productivity-equivalent days, workdays vs calendar days) is a useful self-audit checklist to show the model addresses each explicitly.

---

## 5. Roofing vs general construction (severity uplift)

Roofing is **more** weather-exposed than average construction on both axes, which justifies a multiplier on the unworkable-day count (estimate ≈ **1.5–2×**; no published Vebidak figure was located, so treat as WEAK and refine against the OpCos' own site logs):

- **Rain.** Bonded membranes (EPDM, bitumen, PVC) need a **clean, dry substrate**; gluing/torching in rain, mist or high humidity is explicitly advised against because moisture ruins adhesion (blistering, lifting). General groundwork/structure tolerates light rain; membrane roofing does not — so roofing loses a *larger share* of rain days.
- **Lingering days.** After meaningful rain a deck (especially existing bitumen) **stays damp for several days**, so roofing work cannot resume the instant rain stops. This adds "drying days" beyond the raw rain days — a documented dispute factor in weather claims.
- **Cold.** Adhesives/primers generally need **> ~5 °C** and bitumen becomes brittle in hard frost, so roofing's *technical* workability fails at temperatures **above** the CAO's −6 °C feels-like stop. Practically, roofing is constrained earlier than the labour-law frost trigger.

**Recommendation:** model roofing unworkable days as the general-construction threshold result **× a roofing severity factor**, plus an explicit **lingering-days** term after significant rain. Calibrate both from the four OpCos' historical site/works logs (Andijk, Brunssum, Heeze, Winschoten) against the matching KNMI postcode stations — that turns the WEAK multiplier into a company-specific, defensible figure.

---

## References (with links)

### A. Dutch unworkable-weather framework (CAO Onwerkbaar weer / Regeling onwerkbaar weer / UWV)
- Bouwend Nederland — *Onwerkbaar weer* (rain ≥ 300 min trigger; waiting days; storm = KNMI code red; 19 rain waiting days/yr): https://www.bouwendnederland.nl/kennis/arbeidsomstandigheden/onwerkbaar-weer
- ESPEQ — *Regeling onwerkbaar weer* (full rain + frost thresholds, postcode/KNMI verification): https://www.espeq.nl/bedrijven/onwerkbaar-weer/
- Aannemersfederatie Nederland — *Onwerkbaar weer* (exact frost norms): https://www.aannemersfederatie.nl/nieuws/onwerkbaar-weer
- Aannemersfederatie Nederland — *Heeft u te maken met onwerkbaar weer?*: https://www.aannemersfederatie.nl/nieuws/heeft-u-te-maken-met-onwerkbaar-weer
- Aannemersfederatie Nederland — *UWV Regeling onwerkbaar weer bouwnijverheid: regenverlet* (UAV-based rain-hour norm): https://www.aannemersfederatie.nl/index.php/nieuws12/afnl-nieuws/286-uwv-regeling-onwerkbaar-weer-bouwnijverheid-regenverlet
- Vakvereniging HZC — *Onwerkbaar weer – vorst (Bouw en Infra)* (frost norms): https://www.hzc.nl/onwerkbaar-weer-vorst-bouw-infra/
- Arbeidsveiligheid.net — *Onwerkbaar weer: vrij bij te lage gevoelstemperatuur* (−6 °C, 07:00/09:00 measurements): https://www.arbeidsveiligheid.net/veiligheidsartikelen/fysische-factoren/onwerkbaar-weer-vrij-bij-te-lage-gevoelstemperatuur
- Personeelsnet — *WW bij onwerkbaar weer: vangnet met strikte spelregels* (300 min rain; UWV procedure): https://www.personeelsnet.nl/bericht/ww-bij-onwerkbaar-weer-vangnet-mt-strikte-spelregels
- weerverlet.nl — *CAO Onwerkbaar weer Bouw & Infra, art. 12 (Weerverlet)* (≤ −6 °C → max 4×1.5 h work): https://www.weerverlet.nl/cao-artikel-73-2/
- ScabAdvies — *Het vriest! Wat zegt de cao Onwerkbaar weer Bouw & Infra?* (2 frost waiting days; winter season 1 Nov–31 Mar; daily UWV report before 10:00): https://www.scabadvies.nl/het-vriest-wat-zegt-de-cao-onwerkbaar-weer-bouw-infra/
- Persaldi — *Onwerkbaar weer – winter WW*: https://persaldi.nl/arbeidsrecht/onwerkbaar-weer-winter-ww/
- Bouw en Uitvoering — *Vorstverlet en onwerkbaar weer regeling*: https://bouwenuitvoering.nl/varia/vorstverlet-kou-onwerkbaar-weer-vriezen-weer-temperatuur-werk-arbeidsomstandigheden-bouw-infra-cao/

### B. Contract standard — "werkbare werkdagen" / UAV 2012
- Kienhuis Legal — *Werkbare werkdagen* (UAV 2012 ≥ 5-hour definition; Misset ~180 werkbare dagen/jr; Raad van Arbitrage 1 Jul 2020 nr. 81.669; whole-day rule): https://www.kienhuislegal.nl/artikelen/werkbare-werkdagen
- IJzer Advocaten — *Werkbare dagen in een aannemingsovereenkomst* (UAV ≥ 5-hour; burden of proof on contractor): https://ijzeradvocaten.nl/werkbare-dagen-in-een-aannemingsovereenkomst/
- FDJ Advocaten — *Onwerkbare werkdagen op grond van UAV 2012* (§42 korting/penalty mechanism): https://fdjadvocaten.nl/onwerkbare-werkdagen-op-grond-van-uav-2012/
- DocPlayer — *Bouwtijd, werkbare dagen en boete; bewijs (on)werkbare werkdagen* (arbitration preferring KNMI data over the generic 180-day average): https://docplayer.nl/18679359-Bouwtijd-werkbare-dagen-en-boete-bewijs-on-werkbare-werkdagen.html

### C. KNMI climate norms & definitions (De Bilt, 1991–2020)
- KNMI — *Klimaatnormalen 1991–2020* (definitions; ijsdag = freezing all day): https://www.knmi.nl/kennis-en-datacentrum/uitleg/klimaatnormalen-1991-2020
- KNMI — *De staat van ons klimaat 2023* (normal annual precipitation 851 mm, 1991–2020): https://www.knmi.nl/over-het-knmi/nieuws/de-staat-van-ons-klimaat-2023-warmste-en-natste-jaar-ooit-gemeten
- KNMI — *Klimaatviewer* (station tables / frequency tables 1991–2020 — source for exact monthly precip & frost-day counts): https://www.knmi.nl/klimaat-viewer
- KNMI — *Maand- en jaarwaarden* (homogenised De Bilt series): https://www.knmi.nl/nederland-nu/klimatologie/maandgegevens
- Informatiepunt Leefomgeving (IPLO) — *Monitoring klimaatverandering* (De Bilt 53 vorstdagen/yr 1991–2020; vorstdag = Tmin < 0 °C, ijsdag = Tmax < 0 °C): https://iplo.nl/thema/klimaatverandering/klimaatmonitoring/monitoring-klimaatverandering/
- Compendium voor de Leefomgeving (CLO) — *Meteorologische gegevens 1990–2020*: https://www.clo.nl/indicatoren/nl000423-meteorologische-gegevens-1990-2020
- klimaatinfo.nl — *Het klimaat van De Bilt* (53 vorstdagen, ~850 mm, ~185 dagen ≥ 0,1 mm): https://klimaatinfo.nl/klimaat/nederland/de-bilt/

### D. Academic functional-form literature (rain/weather → productivity)
- El-Rayes, K. & Moselhi, O. (2001), *Impact of Rainfall on the Productivity of Highway Construction*, ASCE J. Constr. Eng. Manag. 127(2):125–131: https://www.researchgate.net/publication/237510351_Impact_of_Rainfall_on_the_Productivity_of_Highway_Construction
- Moselhi, O., Gong, D. & El-Rayes, K. (1997), *Estimating weather impact on the duration of construction activities*, Can. J. Civ. Eng. 24(3):359–366 (the "WEATHER" DSS; partial loss vs complete stoppage): https://experts.illinois.edu/en/publications/estimating-weather-impact-on-the-duration-of-construction-activit/
- Moselhi, O. & El-Rayes, K. (2002), *Analyzing weather-related construction claims* (the seven contested factors: normal weather, thresholds, type of work, lingering days, lost-day criteria, productivity-equivalent days, workdays vs calendar days): https://www.researchgate.net/publication/288544010_Analyzing_weather-related_construction_claims
- Ballesteros-Pérez, P. et al. (2018), *Incorporating the effect of weather in construction scheduling and management with sine wave curves: application in the UK*, Construction Management and Economics: https://www.tandfonline.com/doi/full/10.1080/01446193.2018.1478109
- *Understanding and Quantifying the Impact of Adverse Weather on Construction Productivity* (2025), Applied Sciences (MDPI) — recent literature review and method: https://www.mdpi.com/2076-3417/15/19/10759

### E. Roofing-specific technical constraints (dry substrate / lingering / cold)
- Sleiderink kennisbank — *EPDM dakbedekking aanbrengen op een plat dak* (clean dry substrate; not in rain; > 5 °C): https://www.sleiderink.nl/kennisbank/epdm-dakbedekking-aanbrengen-op-een-plat-dak
- EPDMXL — *EPDM aanbrengen op bitumen dakbedekking* (substrate stays damp several days after rain): https://www.epdmxl.nl/blog/epdm-aanbengen-op-bitumen-dakbedekking
- Dakenmarkt — *EPDM over bitumen is niet altijd de beste oplossing* (moisture/condensation ruins adhesion): https://dakenmarkt.nl/epdm-info/epdm-over-bitumen-is-niet-altijd-de-beste-oplossing/

> **Notes & gaps:** (1) No published **Vebidak/Bouwend Nederland** *numeric* roofing-vs-general weather multiplier was found — the 1.5–2× uplift is an engineering estimate to be replaced with the OpCos' own site logs. (2) Monthly De Bilt precip and frost splits above are indicative; pull exact figures from the KNMI Klimaatviewer station table. (3) The exact "unworkable frost days per year" is highly weather-dependent; derive from KNMI hourly data against the CAO thresholds or from UWV Vorst-WW history for the relevant postcodes.
