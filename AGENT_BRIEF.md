# Phase 2 — Agent Implementation Brief
## Re·Tech Fusion Hackathon — INSAT
## Version 2 — Full Feature Map with Decisions

---

## 0. Strategic Directive

> **"Prioritize depth over covering all features. The core is document extraction, unit normalization, and CO2 estimation."** — Challenge spec

Build in this order: extraction → normalization → CO2 → dashboard → Docker → anomalies → KG innovation. Stop at the depth that earns full points on each layer before moving to the next.

**Scoring:**

| Criterion | Points | Build order |
|---|---|---|
| Document extraction accuracy | 40 | #1 |
| Unit normalization accuracy | 25 | #2 |
| Dashboard quality | 20 | #3 |
| Dockerized pipeline | 20 | #4 |
| CO2 estimation quality | 15 | #5 |
| Bonus: Anomaly detection | +15 | #6 |
| Bonus: Innovation (KG + ISO KPIs) | +25 | #7 |
| **Max total** | **160** | |

---

## 1. Factory Context (rapport_audit.pdf)

**Site:** Pharmaceutical — Société ADWYA, founded 1984, Sidi Daoud, Tunisia  
**STEG district:** KRAM | **Client REF:** 226570  
**3 production zones:** Alpha, Beta, Gamma

### Energy vectors (for knowledge graph Equipment nodes):
| Vector | Production system | Rated power |
|---|---|---|
| Electricity (grid) | STEG HTA 30kV, 2 independent lines | 1300 kVA subscribed |
| Electricity (self) | Tri-generation gas engine + alternator | 1200 kW, 42-44% eff. |
| Natural gas | STEG BP2 tariff, double-ramp station | 6000 th/h subscribed |
| Steam | 2x MANGAZZINI boilers (Alpha+Gamma) | 1840 kW total (1240+600) |
| Hot water | 3 gas boilers + 3 tri-gen heat exchangers | 1140 kW boilers + 1270 kW recovery |
| Chilled water | 6x Carrier GEG electric + THERMAX absorption | 2650 kW + 802 kW |
| Compressed air | 2x oil-free screw compressors | 41.18 m³/min |
| Lighting | Various (LED, fluorescent, industrial) | 61.41 kW, 371,134 kWh/an |

### Tri-generation key numbers:
- GN consumed: 1860 kW thermal (273 Nm³/h)
- Electricity produced: 1200 kW
- Heat recovered (hot water): 1270 kW — measured avg 161 kWh/h (6 months 2024)
- Absorption cooling: 802 kW nominal, 635 kW real, 261 kW measured avg 2025
- Absorption COP: 74%
- Exhaust heat exchanger (Air/Water): 575 kW
- Cooling water heat exchanger (Water/Water): 652 kW

### Meter infrastructure:
- **3 MT meters:** STEG purchase (CTR 3738835), STEG sale/injection, internal factory production
- **GN meters:** general + sub-meters per boiler (Alpha, Gamma) + shared (Beta+Munters)
- **Steam meters** per boiler — NOTE: not yet connected to GTE (management system)

---

## 2. Data Inventory (`data/`)

### 2.1 JPEG images — 22 files

**All from company Société ADWYA (pharmaceutical factory)**. Phone-photographed, bilingual Arabic (RTL) + French (LTR). Two subtypes:

#### Type A — Facture Moyenne Tension (STEG electricity bill)
**Fields to extract:**

| Field | Location on document | Type | Notes |
|---|---|---|---|
| `date` | "Mois" + year in header | MM/YYYY | Billing month |
| `active_energy_kwh` | "Consommation à facturer kWh" | Float | Already kWh — no conversion |
| `reactive_energy_kvarh` | "Réactif" / "Énergie réactive" | Float | DO NOT convert to kWh |
| `power_subscribed_kva` | "Puissance souscrite" | Float | 1300 kVA for ADWYA |
| `facture_number` | "N° Facture" | String | e.g. 69105258R |
| `amount_tnd` | "NET À PAYER" | Float | Tunisian Dinars |
| `supplier` | Header logo/text | String | "STEG" |
| `site` | "Consommateur" | String | "SOCIÉTÉ ADWYA" |
| `district` | "District" | String | "KRAM" |

#### Type B — Fiche Relevé Énergie Achat et Vente (meter reading sheet)
**Fields to extract:**

| Field | Notes |
|---|---|
| `month_year` | "MOIS: février-25" format |
| `client_ref` | "REF: 226570" |
| `purchase_jour_kwh` | Code 1.8.3 — Nouveau - Ancien |
| `purchase_pointe_kwh` | Code 1.8.2 |
| `purchase_nuit_kwh` | Code 1.8.1 |
| `purchase_soir_kwh` | Code 1.8.4 |
| `purchase_reactive_kvarh` | Code 5.8.0 |
| `injection_jour_kwh` | Code 2.8.3 — energy SOLD back to grid |
| `injection_pointe_kwh` | Code 2.8.2 |
| `injection_nuit_kwh` | Code 2.8.1 |
| `injection_soir_kwh` | Code 2.8.4 |
| `production_index_old` | CTR Production ancien |
| `production_index_new` | CTR Production nouveau |
| `net_consumption_kwh` | SUM(purchase slots) — SUM(injection slots) |
| `max_demand_j_kva` | IMax J |
| `max_demand_p_kva` | IMax P |
| `max_demand_s_kva` | IMax S |

**Key formula:** `net_consumption_kwh = purchase_total - injection_total`
This is what gets billed. The injection represents tri-generation export to the STEG grid.

### 2.2 PDF files — 5 files
Files: `data 2.0.pdf`, `sxada.pdf`, `fiche releve donne .pdf`, `doc 2.pdf`, `data faxtuees.pdf`

Strategy (in order):
1. Try `pdfplumber` text extraction → if ≥1 recognizable table found, parse it
2. Check for Arabic text indicators → bilingual invoice likely
3. Fallback: render page as PNG → Claude vision extraction with invoice prompt
4. Record extraction method used per file in metadata

### 2.3 Excel reports — ~20 files in `data/reports/`
Naming: `{month}-report{N}_{DDMMYYYY}.xlsx`
Date range: FIN AOUT 2025 → juillet 2026 (12+ months)

**Structural challenges to handle:**
- Variable header row position → scan first 10 rows for HEADER_KEYWORDS
- Merged cells for zone headers → `ffill()` after reading
- Units embedded in column headers ("Energie [kWh]", "GN [Nm³]")
- French month names in date cells
- Multiple sheets — iterate all, attempt extraction from each

**Header detection:**
```python
HEADER_KEYWORDS = {"date", "mois", "kwh", "energie", "consommation",
                   "zone", "compteur", "gaz", "vapeur", "electrique"}
```

---

## 3. Layer 0 — Image Preprocessing (CRITICAL — do before OCR)

Phone photos have perspective distortion, rotation, shadows. Without preprocessing, extraction F1 drops ~35%.

```python
# Pipeline per JPEG
def preprocess_invoice_image(img_path):
    img = cv2.imread(img_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # 1. CLAHE contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(gray)
    # 2. Deskew
    coords = np.column_stack(np.where(enhanced < 200))
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45: angle += 90
    M = cv2.getRotationMatrix2D(center, -angle, 1.0)
    rotated = cv2.warpAffine(enhanced, M, (w, h))
    # 3. Return as base64 PNG for vision API
    return encode_image(rotated)
```

---

## 4. Extraction Engine

### 4.1 Vision extraction (primary for JPEGs)

Use **Claude claude-sonnet-4-6** with vision. Include factory context in system prompt.

```python
EXTRACTION_PROMPT = """
You are extracting data from a STEG (Tunisia electricity utility) document.
The document is bilingual: French (left-to-right) and Arabic (right-to-left).

Return ONLY valid JSON matching this schema. Use null for any field you cannot read.

For STEG electricity bills (Facture Moyenne Tension):
{
  "document_type": "steg_bill",
  "date": "YYYY-MM",
  "facture_number": "string",
  "active_energy_kwh": float,
  "reactive_energy_kvarh": float,
  "power_subscribed_kva": float,
  "amount_tnd": float,
  "supplier": "STEG",
  "site": "string",
  "confidence": 0.0-1.0
}

For meter reading sheets (Fiche Relevé Énergie Achat et Vente):
{
  "document_type": "steg_meter_reading",
  "date": "YYYY-MM",
  "client_ref": "string",
  "purchase_jour_kwh": float,
  "purchase_pointe_kwh": float,
  "purchase_nuit_kwh": float,
  "purchase_soir_kwh": float,
  "purchase_reactive_kvarh": float,
  "injection_jour_kwh": float,
  "injection_pointe_kwh": float,
  "injection_nuit_kwh": float,
  "injection_soir_kwh": float,
  "net_consumption_kwh": float,
  "confidence": 0.0-1.0
}
"""
```

### 4.2 PDF text extraction (primary for PDFs)

```python
import pdfplumber  # v0.9.0+

def extract_pdf(path):
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if tables:
                return parse_invoice_table(tables)
        # No tables found — fall back to vision
        return extract_with_vision(render_pdf_page(path))
```

### 4.3 Excel extraction

```python
import pandas as pd

def extract_excel(path):
    xl = pd.ExcelFile(path)
    records = []
    for sheet in xl.sheet_names:
        df = xl.parse(sheet, header=None)
        header_row = find_header_row(df, HEADER_KEYWORDS)
        if header_row is not None:
            df.columns = df.iloc[header_row]
            df = df.iloc[header_row+1:].reset_index(drop=True)
            records.extend(parse_energy_rows(df, sheet))
    return records
```

---

## 5. Unit Normalization

Canonical unit: **kWh**

| Input unit | Multiplier | LHV/HHV note |
|---|---|---|
| kWh | 1.0 | identity |
| MWh | 1000.0 | — |
| GJ | 277.778 | exact (1 GJ / 3.6 MJ/kWh) |
| Gcal | 1163.0 | 1 Gcal = 1000 kcal × 1.163 kWh/kcal |
| th (thermie) | 1.163 | 1 th = 1 Mcal |
| BTU | 0.000293071 | NIST exact |
| toe | 11630.0 | IEA: 1 toe = 10 Gcal HHV |
| Nm³ (gas, Tunisia) | 10.55 | STEG PCS (HHV) ≈ 10.55 kWh/Nm³ |
| Nm³ (gas, LHV) | 9.51 | for CO2 combustion calculation |
| T vapeur (sat. 5 bar) | 681.0 | enthalpy 5 bar = 2748 kJ/kg |
| kVArh | ❌ null | NOT convertible — store as-is |

**IMPORTANT:** Store both `quantity_kwh_hhv` and `quantity_kwh_lhv` for gas. The organizer ground truth may use either. Explicitly document which is used in CO2 calculation (use LHV for combustion).

**Per-record normalization schema:**
```json
{
  "document_id": "img_38",
  "document_type": "steg_bill",
  "source_file": "WhatsApp Image ... (38).jpeg",
  "date": "2025-10",
  "supplier": "STEG",
  "site": "ADWYA",
  "zone": "global",
  "energy_type": "electricity",
  "quantity_raw": 18634.0,
  "unit_raw": "kWh",
  "quantity_kwh": 18634.0,
  "conversion_factor": 1.0,
  "conversion_formula": "identity",
  "extraction_confidence": 0.97,
  "extraction_method": "claude_vision"
}
```

---

## 6. CO2 Estimation

### Emission factors

| Energy input | Scope | kgCO2/kWh | Source |
|---|---|---|---|
| STEG grid electricity purchased | Scope 2 (market) | 0.593 | ANME Tunisia ~2023 |
| Natural gas (tri-gen engine) | Scope 1 | 0.201 | IPCC AR6, LHV basis |
| Natural gas (boilers) | Scope 1 | 0.201 | IPCC AR6 |
| Natural gas (Munters) | Scope 1 | 0.201 | IPCC AR6 |
| Electricity sold to grid (credit) | Scope 2 negative | −0.593 | Avoided emissions |

### Simple CO2 calculation
```python
CO2_total_kg = (
    electricity_purchased_kwh * 0.593      # Scope 2
  + gas_trigeneration_kwh    * 0.201       # Scope 1
  + gas_boilers_kwh          * 0.201       # Scope 1
  + gas_munters_kwh          * 0.201       # Scope 1
  - electricity_sold_kwh     * 0.593       # Scope 2 credit
)
```

### Advanced CO2 calculation — tri-generation net benefit
The tri-gen burns gas but avoids grid purchase AND avoids boiler gas:
```python
CO2_trigeneration_gross = gas_consumed_kwh * 0.201

CO2_avoided_from_electricity = electricity_produced_kwh * 0.593
CO2_avoided_from_heat = heat_recovered_kwh * 0.201         # replaces boiler
CO2_avoided_from_cooling = cooling_produced_kwh / 3.2 * 0.593  # COP_equiv ~3.2

CO2_trigeneration_net = (
    CO2_trigeneration_gross
  - CO2_avoided_from_electricity
  - CO2_avoided_from_heat
  - CO2_avoided_from_cooling
)
```

**Dashboard toggle:** "Simple" vs "Tri-gen Adjusted" CO2 display.  
**Document both in README.** Show jury the factory is likely CO2-negative on electricity.

### GHG Protocol Scope labeling (for jury recognition)
- **Scope 1:** All on-site combustion (gas engine, boilers, Munters)
- **Scope 2:** Net grid electricity (purchased - sold)
- **Scope 3:** Not included (upstream gas extraction, etc.) — mention in README

---

## 7. Knowledge Graph

### Stack: networkx + pyvis + FastAPI JSON export

```python
import networkx as nx
from pyvis.network import Network

G = nx.DiGraph()

# Node types (use 'type' attribute)
G.add_node("ADWYA", type="Site", address="Sidi Daoud", sector="pharma")
G.add_node("Zone_Alpha", type="Zone")
G.add_node("Zone_Beta", type="Zone")
G.add_node("Zone_Gamma", type="Zone")
G.add_node("STEG", type="Supplier", energy_type="electricity+gas")
G.add_node("Trigeneration", type="Equipment", power_kw=1200, zone="global")
G.add_node("GEG1_Alpha", type="Equipment", power_kw=391, eer=3.11)
# ... all equipment from rapport_audit ...

# Edges
G.add_edge("STEG", "ADWYA", rel="SUPPLIES", energy_type="electricity")
G.add_edge("Zone_Alpha", "ADWYA", rel="PART_OF")
G.add_edge("GEG1_Alpha", "Zone_Alpha", rel="LOCATED_IN")
G.add_edge("EnergyReading_001", "Meter_CTR3738835", rel="MEASURED_BY")
G.add_edge("EnergyReading_001", "Document_img38", rel="EXTRACTED_FROM")
G.add_edge("EmissionEstimate_001", "EnergyReading_001", rel="COMPUTED_FROM")
```

### Graph-powered queries for dashboard:
1. "Total electricity net consumption per month" — filter STEG SUPPLIES → aggregate readings
2. "CO2 by zone per month" — traverse Zone → Equipment → EnergyReading → EmissionEstimate
3. "Self-sufficiency ratio" — tri-gen production / total consumption
4. "Which months had injection to grid?" — injection_kwh > 0 filter

### pyvis visualization (Streamlit)
```python
def render_knowledge_graph(G):
    net = Network(height="500px", directed=True)
    net.from_nx(G)
    net.save_graph("graph.html")
    with open("graph.html") as f:
        components.html(f.read(), height=500)
```

---

## 8. ISO 50001 Energy Performance Indicators (dashboard KPIs)

These are standard industrial KPIs — industry judges will recognize them immediately.

| KPI | Formula | Unit | Description |
|---|---|---|---|
| **EnPI** | actual / baseline | ratio | Energy Performance Index (>1 = worse than baseline) |
| **SEI** | total_kwh / production_units | kWh/batch | Specific Energy Intensity |
| **EnB** | rolling 12-month avg kWh | kWh/month | Energy Baseline |
| **Grid dependency** | steg_net / total_consumed | % | How much comes from grid |
| **Self-sufficiency** | trigeneration_kwh / total | % | On-site production fraction |
| **Power factor** | kWh / √(kWh²+kVArh²) | — | Target >0.9 (STEG penalizes below) |
| **CO2 intensity** | kgCO2 / kWh_total | kgCO2/kWh | Carbon efficiency |
| **Specific CO2** | kgCO2 / production_unit | kgCO2/batch | Carbon per product unit |

Note: production_units not available from documents — use kWh as denominator or leave as total.

---

## 9. Anomaly Detection (+15 pts)

### Four detectors:

#### Detector 1 — Reconciliation anomaly (most valuable, unique)
```python
# Compare Excel report to STEG bill for same month
delta_pct = abs(excel_kwh - steg_bill_kwh) / steg_bill_kwh
if delta_pct > 0.02:  # >2% discrepancy
    flag("RECONCILIATION", confidence=1-delta_pct)
```
This catches: meter misread, typo in report, billing error, measurement lag.

#### Detector 2 — Spike (Z-score)
```python
z = (value - rolling_mean(window=3)) / rolling_std(window=3)
if abs(z) > 3.0:
    flag("SPIKE", confidence=min(abs(z)/5, 1.0))
```

#### Detector 3 — Dropout
```python
if value is None or value == 0.0:
    flag("DROPOUT", confidence=1.0)
```

#### Detector 4 — Trend drift
```python
slope, _, r, _, _ = scipy.stats.linregress(range(N), last_6_months)
pct_change_per_month = slope / mean_value
if abs(pct_change_per_month) > 0.10:  # >10%/month drift
    flag("DRIFT", confidence=abs(r))
```

### Anomaly output schema:
```json
{
  "anomaly_id": "anom_001",
  "type": "RECONCILIATION | SPIKE | DROPOUT | DRIFT",
  "timestamp": "2025-10",
  "meter_or_site": "CTR_3738835 | Zone_Alpha",
  "value_observed": 25000.0,
  "value_expected": 18600.0,
  "delta_pct": 34.4,
  "confidence_score": 0.95,
  "document_source": "img_38",
  "description": "Excel report shows 25,000 kWh vs STEG bill 18,634 kWh (+34%)"
}
```

---

## 10. Forecasting

**Honest assessment:** ~20 monthly data points (Aug 2025 → Jul 2026) is the minimum for seasonal models.

**Recommended: Prophet 1.1+**
```python
from prophet import Prophet

df = pd.DataFrame({'ds': dates, 'y': kwh_values})
model = Prophet(
    yearly_seasonality=True,
    interval_width=0.90,  # 90% confidence interval
    seasonality_mode='multiplicative'
)
model.fit(df)
future = model.make_future_dataframe(periods=3, freq='MS')  # next 3 months
forecast = model.predict(future)
```

**Fallback: Holt-Winters** if Prophet not available:
```python
from statsmodels.tsa.holtwinters import ExponentialSmoothing
model = ExponentialSmoothing(data, trend='add', seasonal='add', seasonal_periods=12)
```

**Caveat to document:** Clearly state in README that forecast confidence is limited by dataset length. Don't present narrow bands.

---

## 11. API Design (FastAPI)

```
GET  /health
POST /extract          body: {file_b64, file_type}   → extraction record
GET  /unified          ?from=2025-08&to=2026-07       → list[EnergyRecord]
GET  /co2              ?scope=1,2&from=...&to=...     → list[CO2Estimate]
GET  /anomalies        ?type=all                       → list[Anomaly]
GET  /forecast         ?horizon=3&zone=global          → ForecastResult
GET  /kpis             ?from=...&to=...                → dict[KPI]
GET  /graph            → {nodes: [...], edges: [...]}
POST /submit           → formats and POSTs to challenge platform
GET  /docs             (auto-generated Swagger — satisfies "API documented")
```

---

## 12. Docker Architecture

```yaml
# docker-compose.yml
version: '3.9'
services:
  api:
    build: .
    ports: ["8000:8000"]
    volumes: ["./data:/app/data:ro", "./db:/app/db"]
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}

  dashboard:
    build: .
    ports: ["8501:8501"]
    volumes: ["./data:/app/data:ro"]
    command: streamlit run app/dashboard.py --server.port 8501 --server.address 0.0.0.0
    environment:
      - API_URL=http://api:8000

  # SQLite database in shared volume — no separate DB container needed
```

**Cold start test:** `docker compose up --build` must work with only `ANTHROPIC_API_KEY` set.

---

## 13. Tech Stack (final decisions)

| Component | Choice | Version | Reason |
|---|---|---|---|
| Image preprocessing | OpenCV | 4.9+ | Deskew, CLAHE, perspective |
| Invoice OCR (JPEG) | Claude API vision | claude-sonnet-4-6 | Best bilingual AR/FR accuracy |
| PDF extraction | pdfplumber | 0.9.0+ | Best for invoice table structure |
| Excel parsing | pandas + openpyxl | 2.0+ | Standard, handles merged cells |
| Knowledge graph | networkx | 3.x | Zero infra, sufficient for 1000 nodes |
| Graph visualization | pyvis | 0.3.x | Renders in Streamlit via HTML |
| CO2 + normalization | Pure Python | — | Deterministic, auditable |
| Anomaly detection | scipy + pandas | — | Lightweight, interpretable |
| Forecasting | Prophet | 1.1+ | Handles 20 data points, seasonality |
| API | FastAPI | 0.100+ | Auto-docs, async-ready |
| Dashboard | Streamlit | 1.28+ | Fastest UI for hackathon |
| Storage | SQLite | — | Zero infra, persistent, portable |
| Container | Docker + compose | — | Required for 20 pts |

### NOT using:
- ❌ Neo4j — overkill, adds infra complexity
- ❌ LangChain / RAG — unnecessary abstraction
- ❌ PostgreSQL — SQLite is sufficient
- ❌ Tesseract — poor AR/FR accuracy vs Claude vision
- ❌ LSTM/deep learning — 20 data points, will overfit

---

## 14. Project Structure

```
phase2/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example          # ANTHROPIC_API_KEY=...
├── app/
│   ├── main.py           # FastAPI app + routers
│   ├── dashboard.py      # Streamlit app
│   ├── extractors/
│   │   ├── image.py      # Claude vision extraction + preprocessing
│   │   ├── pdf.py        # pdfplumber + vision fallback
│   │   └── excel.py      # pandas extraction
│   ├── pipeline/
│   │   ├── normalize.py  # Unit conversion engine
│   │   ├── co2.py        # CO2 estimation (simple + tri-gen adjusted)
│   │   ├── anomaly.py    # 4 anomaly detectors
│   │   ├── forecast.py   # Prophet wrapper
│   │   └── graph.py      # networkx KG builder + queries
│   ├── models/
│   │   └── schemas.py    # Pydantic models for all records
│   └── db/
│       └── store.py      # SQLite read/write
├── data/                 # Input documents (mounted as volume)
│   ├── *.jpeg
│   ├── *.pdf
│   └── reports/*.xlsx
├── tests/
│   ├── test_normalize.py # Unit test every conversion factor
│   └── test_extract.py   # Smoke test per document type
└── README.md             # Required for submission
```

---

## 15. Submission Checklist

- [ ] GitHub repo with README, code, demo screenshots
- [ ] `docker compose up` works from cold start
- [ ] `/docs` Swagger UI is accessible
- [ ] All 22 JPEGs extracted with >90% field accuracy
- [ ] All Excel reports parsed
- [ ] All PDFs attempted (even partial extraction is scored)
- [ ] Unit normalization covers kWh, MWh, GJ, Gcal, BTU, toe, Nm³
- [ ] CO2 estimate for every record (with scope label)
- [ ] Anomaly report posted to platform
- [ ] Dashboard live-accessible (or screenshots)
- [ ] Knowledge graph visible in dashboard
- [ ] ISO KPIs shown (EnPI, self-sufficiency, power factor)

---

## 16. Key Extraction Prompts

### STEG bill / meter reading prompt (include in all vision calls):
```
Context: This is a STEG (Société Tunisienne de l'Électricité et du Gaz) document for 
SOCIÉTÉ ADWYA (pharmaceutical factory, KRAM district, client REF 226570).
Language: Bilingual French (LTR) + Arabic (RTL).
- "Consommation à facturer kWh" = active energy in kWh (THE main number)
- "Réactif" = reactive energy in kVArh (DO NOT convert to kWh)
- "OII Jour/Nuit/Pointe/Soir" = energy injection indices (sold back to grid from tri-gen)
- "CTR Production" = internal tri-generation production meter
- Time-of-use slots: Pointe (peak), Jour (day), Nuit (night), Soir (evening)
- Monetary values are in TND (Tunisian Dinar) — extract but do not confuse with kWh
- Index delta (Nouveau - Ancien) = energy consumed/injected this period in kWh
```

### For Excel reports:
```
This is a monthly energy report for a pharmaceutical factory with 3 zones:
Alpha, Beta, Gamma. Energy types present: electricity (kWh), natural gas (Nm³ or th),
steam (T or kWh), chilled water (kWh), hot water (kWh), compressed air (Nm³).
Extract: date, zone, energy_type, quantity, unit for each row.
```
