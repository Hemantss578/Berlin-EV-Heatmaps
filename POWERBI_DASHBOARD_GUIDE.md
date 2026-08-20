# Power BI Dashboard Build Guide — Berlin EV Charging Analytics

This is your step-by-step build guide for the Power BI companion dashboard to
your Streamlit app. It's written against the **real columns in your actual
data files** (`datasets/Ladesaeulenregister.csv` and
`datasets/plz_einwohner.csv`), so you can follow it directly in Power BI
Desktop.

---

## 1. Reframing the metrics in business language

Recruiters scanning for BI/product-analytics skills read "EV charging
station" and think niche hobby project. Read "utilisation," "coverage,"
"growth," "underserved segments" and they think performance analytics. Same
data, different vocabulary — here's the mapping:

| Business/product KPI | What it actually is | Real column(s) it comes from |
|---|---|---|
| **Total capacity deployed** | Total number of charge points installed | `SUM(Anzahl Ladepunkte)` |
| **Coverage rate** | Charge points per 10,000 residents, per postal code | `Anzahl Ladepunkte` ÷ `Einwohner` × 10,000 |
| **Underserved segments (count)** | Postal codes where residents-per-charge-point exceeds a threshold | `Einwohner` ÷ `Anzahl Ladepunkte`, thresholded |
| **Growth (MoM / cumulative)** | New charge points commissioned over time | `Inbetriebnahmedatum` (commissioning date) |
| **Top/bottom performing regions** | Postal codes ranked by charge points or coverage rate | `Postleitzahl` + `Anzahl Ladepunkte` |
| **Product/channel mix** | Share of standard (AC) vs. fast (DC) charging capacity | `Art der Ladeeinrichtung` and `Nennleistung Ladeeinrichtung [kW]` |
| **KPI vs. target** | Coverage rate vs. a defined service-level target | Coverage rate measure vs. a fixed target value |

This is exactly the language of a retail-coverage or store-network
dashboard — "how many locations do we have, where are we underserved, is
utilisation trending up, are we hitting target." That's not a stretch; the
underlying analytical shape (locations × population × capacity × time) is
identical to real BI use cases (retail footprint, branch coverage,
telecom network planning).

**One honest note for your README/interview:** `Inbetriebnahmedatum` is a
genuinely real field (when each charger went live), so the growth trend is
real historical data, not synthetic. The "target" KPI, though, needs a
number you define yourself (there's no official per-postal-code target in
the register) — be upfront that the target is illustrative/self-set (e.g.,
"1 charge point per 1,000 residents") when you present it.

---

## 2. Data prep in Power Query

Both source files need real cleanup — this is good, because "cleaned messy
government data in Power Query" is a much stronger interview story than "the
CSV was already clean."

### Import `Ladesaeulenregister.csv`

1. **Get Data → Text/CSV** → select `Ladesaeulenregister.csv`.
2. In the import preview, set **File Origin** to `1252: Western European
   (Windows)` (the file is Windows-1252 encoded — you'll see broken
   characters like `Lades�ulenregister` if you leave it as UTF-8). Click
   **Transform Data** to open Power Query instead of loading directly.
3. **Remove top rows:** the real header isn't row 1 — there are ~10 metadata
   rows first ("Ladesäulenregister Bundesnetzagentur", update-date notice,
   etc.). Use **Home → Remove Rows → Remove Top Rows** and remove the rows
   above the one starting with `Ladeeinrichtungs-ID;Betreiber;...`. Then
   **Use First Row as Headers**.
4. **Remove columns you don't need for this dashboard:** keep it to one row
   per station, so remove the six repeated per-connector column groups
   (`Steckertypen1..6`, `Nennleistung Stecker1..6`, `EVSE-ID1..6`,
   `Public Key1..6`) and the opening-hours/payment columns — right-click the
   first column to keep → **Remove Other Columns**, keeping:
   `Ladeeinrichtungs-ID`, `Betreiber`, `Status`, `Art der Ladeeinrichtung`,
   `Anzahl Ladepunkte`, `Nennleistung Ladeeinrichtung [kW]`,
   `Inbetriebnahmedatum`, `Postleitzahl`, `Ort`, `Bundesland`, `Breitengrad`,
   `Längengrad`.
5. **Fix data types:**
   - `Anzahl Ladepunkte` → Whole Number
   - `Nennleistung Ladeeinrichtung [kW]` → Decimal Number. If it errors,
     first **Replace Values**: `,` → `.` (German decimal comma), then set
     the type.
   - `Breitengrad` / `Längengrad` → same comma-to-period fix, then Decimal
     Number.
   - `Inbetriebnahmedatum` → the format is `DD.MM.YYYY` (German). Power
     Query will often misread this as MM/DD. Use **Change Type → Using
     Locale…** and pick `German (Germany)` as the source locale, target type
     Date. This is the single most common bug in this dataset — check a few
     January-vs-not-January dates after conversion to confirm it didn't
     swap day/month.
   - `Postleitzahl` → keep as **Text**, not a number (postal codes with
     leading behaviour and joins work more reliably as text; you'll also
     join it to a text `PLZ` column in the residents table).
6. **Handle nulls:** filter `Status` to keep only `In Betrieb` (currently
   active/operational chargers) so the dashboard reflects live
   infrastructure, not planned-but-not-built entries. Filter out rows with
   blank `Postleitzahl`, `Breitengrad`, or `Längengrad` (can't be mapped or
   assigned to a region).
7. **Filter to Berlin:** this file is nationwide (Germany), and your
   dashboard is Berlin-scoped. Filter `Postleitzahl` to postal codes
   `10115`–`14199` (Berlin's range), e.g. add a custom column
   `Text.From(Number.From([Postleitzahl])) ` check or simply use **Filter →
   Number Filters → Between** after temporarily converting to a duplicate
   numeric column for the filter.
8. **Rename columns** to clean, dashboard-friendly names: `StationID`,
   `Operator`, `Status`, `ChargerType`, `ChargePoints`, `NominalPowerKW`,
   `CommissionDate`, `PostalCode`, `City`, `State`, `Latitude`, `Longitude`.
9. **Add a calculated column for power class** (mirrors the bins your
   Streamlit app already uses, for a consistent story across both
   projects): **Add Column → Conditional Column** → `PowerClass` = `"AC
   normal (≤22kW)"` if `NominalPowerKW <= 22`, `"Fast (23–49kW)"` if `<= 49`,
   `"DC fast (50–149kW)"` if `<= 149`, else `"HPC ultra-fast (≥150kW)"`.
10. **Rename the query** itself to `Stations`.

### Import `plz_einwohner.csv`

1. **Get Data → Text/CSV** → this one is UTF-8, comma-delimited, so the
   default import usually works.
2. Columns are `plz, note, einwohner, qkm, lat, lon`. Rename to
   `PostalCode`, `AreaNote`, `Residents`, `AreaKm2`, `Latitude`, `Longitude`.
3. Set `PostalCode` to **Text** (must match the type in `Stations` for the
   relationship to work), `Residents` and `AreaKm2` to numeric types.
4. **Filter to Berlin:** same range, `10115`–`14199`.
5. Rename the query to `Residents`.
6. **Close & Apply.**

---

## 3. Data model + Date table

You have two real tables (`Stations`, `Residents`) plus a Date table you'll
add — a clean small star schema, which is exactly what you want to show you
understand modelling (not just one flat sheet).

1. **Model view → New Table**, and create:
   ```
   DateTable =
   CALENDAR ( MIN ( Stations[CommissionDate] ), MAX ( Stations[CommissionDate] ) )
   ```
2. Add supporting columns to `DateTable`:
   ```
   Year = YEAR ( DateTable[Date] )
   MonthNum = MONTH ( DateTable[Date] )
   MonthName = FORMAT ( DateTable[Date], "MMM" )
   MonthYear = FORMAT ( DateTable[Date], "MMM YYYY" )
   ```
3. Select `DateTable` → **Table tools → Mark as Date Table** → pick the
   `Date` column. This tells Power BI it can trust this table for
   time-intelligence functions (the MoM DAX below depends on this being set
   correctly).
4. **Relationships** (Model view, drag to connect):
   - `DateTable[Date]` (1) → `Stations[CommissionDate]` (many)
   - `Residents[PostalCode]` (1) → `Stations[PostalCode]` (many)

   Both should auto-detect as **one-to-many, single direction, cardinality
   1:***. `Residents` acts as your postal-code dimension table (one row per
   PLZ) even though it's a "real" data file, not a synthetic lookup table —
   that's a legitimate and common modelling pattern (a fact table + a
   dimension table that happens to also carry a measure like population).

This gives you a proper star schema: `Stations` (fact) surrounded by
`DateTable` and `Residents` (dimensions) — worth stating explicitly in your
README and being ready to sketch in an interview.

---

## 4. DAX measures

Create these as a new **Measures table** (Model view → New Table → just
type `Measures = {}` for an empty holder table, then add measures to it) so
they're not scattered inside `Stations`.

**1. Total capacity deployed (sum KPI)**
```
Total Charge Points = SUM ( Stations[ChargePoints] )
```
Plain English: adds up every station's charge-point count. This is your
headline "how much infrastructure exists" number.

**2. Month-over-month growth %**
```
MoM Growth % =
VAR CurrentPoints = [Total Charge Points]
VAR PriorMonthPoints =
    CALCULATE (
        [Total Charge Points],
        DATEADD ( DateTable[Date], -1, MONTH )
    )
RETURN
    DIVIDE ( CurrentPoints - PriorMonthPoints, PriorMonthPoints )
```
Plain English: takes this month's cumulative charge-point total, compares it
to the same measure one month back (`DATEADD` shifts the whole date filter
back a month), and expresses the change as a %. `DIVIDE` instead of `/` so
it returns blank instead of erroring when the prior month is 0. You'll want
this measure plotted against a **running total** of `Total Charge Points`
by month (not the raw per-month count) for it to read as network growth.

**3. Average/ratio metric — residents per charge point**
```
Residents per Charge Point =
DIVIDE ( SUM ( Residents[Residents] ), [Total Charge Points] )
```
Plain English: this is your core "coverage" ratio — how many people are
effectively sharing one charge point in a given postal code (or across the
whole filtered selection). Lower is better (more infrastructure per
resident). This is the direct BI-language equivalent of what your Streamlit
app's gap-analysis table already calls "residents per station."

**4. KPI vs. target**
```
Coverage Target (per 10k) = 5   -- illustrative target, edit freely

Coverage Rate (per 10k) =
DIVIDE ( [Total Charge Points], SUM ( Residents[Residents] ) ) * 10000

Coverage vs Target % =
DIVIDE ( [Coverage Rate (per 10k)], [Coverage Target (per 10k)] )
```
Plain English: `Coverage Target (per 10k)` is a fixed number you set (a
placeholder — pick something defensible, like a round number or one derived
from comparing Berlin's current average to a denser district). `Coverage
Rate` is the actual measured charge points per 10,000 residents.
`Coverage vs Target %` divides one by the other so you can show "we're at
78% of target" with a gauge or KPI visual with a target line. **Be ready to
say in an interview that the target itself is a self-defined benchmark, not
an official figure** — that's a strength (you understood you needed a
target and set one transparently), not a weakness, as long as you're
upfront about it.

---

## 5. Building the visuals (single page)

Layout, top to bottom:

**Row 1 — Title band.** A text box: *"Berlin EV Charging Coverage —
identifying underserved postal codes for charging infrastructure
investment."* Small subtitle underneath: *"Data: Bundesnetzagentur
Ladesäulenregister & postal-code population, filtered to Berlin (10115–14199)."*

**Row 2 — KPI card row (4 cards, equal width).**
`Total Charge Points` · `Coverage Rate (per 10k)` · `Residents per Charge
Point` · `MoM Growth %`. Use the **Card** visual (not multi-row card) for a
clean look; a Power BI "KPI" visual works too if you want the built-in
trend arrow.

**Row 3, left two-thirds — Trend line.** Line chart: X-axis
`DateTable[MonthYear]` (sorted by `DateTable[Date]`), Y-axis a **running
total** of `Total Charge Points` (add a small `Cumulative Charge Points`
measure using `CALCULATE([Total Charge Points], FILTER(ALL(DateTable),
DateTable[Date] <= MAX(DateTable[Date])))` if you want true cumulative
growth rather than per-month counts). Title: "Charging network growth over
time."

**Row 3, right third — Ranked bar.** Horizontal bar chart: Y-axis
`Stations[PostalCode]`, X-axis `Total Charge Points`, sorted descending,
**Top N filter = 10**. Title: "Top 10 postal codes by charge points."
Duplicate this as a second small visual sorted ascending (bottom 10) if you
have room, or use a bookmark toggle between top/bottom.

**Row 4, left half — Category breakdown.** Donut or 100%-stacked bar of
`ChargerType` (or `PowerClass` for the more granular version) by
`Total Charge Points`. Title: "Charging network mix by power class."

**Row 4, right half — Detail matrix.** Matrix visual: rows =
`Stations[PostalCode]`, values = `Total Charge Points`, `SUM(Residents)`,
`Residents per Charge Point`, `Coverage vs Target %`. Apply **conditional
formatting** (background color scale, red→green) on `Residents per Charge
Point` so the most underserved postal codes visibly stand out in red. This
single visual is your "here's the underserved-region answer" moment —
make sure it's not squeezed.

**Slicers** (top-right corner or a thin left rail): a date-range slicer on
`DateTable[Date]`, a dropdown slicer on `Stations[PostalCode]`, and a
dropdown on `PowerClass`. Sync them across the page (there's only one page,
so this is automatic).

**Layout discipline:** align every visual to a grid — use **View →
Gridlines and Snap to Grid**. Keep consistent padding between tiles (Power
BI default margins are fine, just don't let visuals touch). Four KPI cards
of identical size in a row read as "designed"; four different sizes read as
"thrown together."

---

## 6. Polish

- **Colour theme:** View → **Themes → Browse for themes**, or build a
  simple custom theme JSON with 2–3 core colours (e.g., a teal/green for
  "good coverage," amber/red reserved only for the conditional-formatting
  alert colours — don't scatter random accent colours across unrelated
  visuals).
- **Number formatting:** right-click each measure → Format →
  `Coverage Rate` and `Residents per Charge Point` as whole numbers with
  thousands separators; `MoM Growth %` and `Coverage vs Target %` as
  Percentage with 1 decimal.
- **Titles:** every visual gets a short, specific title (not the default
  "Sum of ChargePoints by PostalCode") — write titles as the question the
  visual answers, e.g. "Which postal codes are most underserved?"
- **Page title/subtitle:** a one-line pitch at the top stating exactly what
  the dashboard answers (see Row 1 above) — this is what a recruiter reads
  in the first 3 seconds.
- **Remove default Power BI clutter:** turn off visual-level "..." menus
  where not needed, hide the Filters pane if you're not using it
  interactively, and remove any unused fields from tooltips.

---

## 7. Publish + share a public link

1. **File → Publish → Publish to Power BI** (requires a free Power BI
   account — sign up with any email at
   [app.powerbi.com](https://app.powerbi.com) if you don't have one; a work
   or edu email sometimes unlocks extra features but a free personal
   account is enough for this).
2. Pick a workspace (your personal "My workspace" is fine for a portfolio
   piece).
3. Once published, open the report in the Power BI Service (browser) →
   **File → Embed report → Publish to web (public)**.
4. Read the warning carefully: **Publish to web makes the report visible to
   anyone with the link, with no login required — do not use this for any
   real personal, sensitive, or paid-tier work data.** Your dataset here
   (public government charging register + public population stats) is
   fine for this.
5. Confirm, and Power BI gives you two things: an `<iframe>` embed snippet
   and a direct URL. **Copy the direct URL** — that's the link you put on
   your CV and in your README.
6. Test the link in a private/incognito browser window to confirm it loads
   without you being logged in.

---

## Files this dashboard is built from

| File | What it is |
|---|---|
| `datasets/Ladesaeulenregister.csv` | Bundesnetzagentur public charging-station register (nationwide; filter to Berlin PLZ 10115–14199) |
| `datasets/plz_einwohner.csv` | Population per German postal code (suche-postleitzahl.org) |

Both are real, publicly sourced files already in this repo's `datasets/`
folder — nothing here is synthetic. The only illustrative element is the
`Coverage Target (per 10k)` benchmark value in DAX measure #4, which is a
self-defined target rather than an official figure (see Section 4).
