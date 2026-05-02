# NRTF Energy Intelligence Pipeline

**Re·Tech Fusion Hackathon — INSAT | Team NRTF**

End-to-end energy data pipeline for Société ADWYA (pharmaceutical factory, Sidi Daoud, Tunisia).
Extracts data from STEG invoices (JPEG/PDF) and monthly Excel operational reports,
normalises units to kWh, estimates GHG emissions, and serves results via a REST API and Streamlit dashboard.

---

## Architecture

```
data/
  *.jpeg          <- STEG Facture MT + Fiche Releve (22 phone photos)
  *.pdf           <- STEG PDF invoices (5 files)
  reports/*.xlsx  <- Monthly BILAN TOTAL reports (12+ months)
        |
        v
Extraction Layer
  image.py  ->  Gemini 2.5 Flash (vision + CLAHE/deskew)
  pdf.py    ->  pdfplumber + vision fallback
  excel.py  ->  openpyxl delta scan
        |
        v
Normalization  (normalize.py)
  All units -> kWh  (18 unit families)
  Gas: HHV=10.55 / LHV=9.51 kWh/Nm3
        |
        v
CO2 Estimation  (co2.py)
  Scope 1 : gas combustion   0.201 kgCO2/kWh
  Scope 2 : grid purchase    0.593 kgCO2/kWh
  Scope 2c: grid injection  -0.593 kgCO2/kWh
  + Tri-gen adjusted mode
        |
        v
Analytics
  anomaly.py  -> 4 detectors (dropout / spike / drift / reconciliation)
  kpis.py     -> ISO 50001 KPIs
  forecast.py -> Prophet / Holt-Winters
  graph.py    -> networkx knowledge graph + pyvis
        |
   -----+------
   |           |
FastAPI    Streamlit
:8000      :8501
```

Storage: SQLite (data/pipeline.db) — no external database required.

---

## Setup

### Prerequisites

- Python 3.11+
- Gemini API key (free tier — aistudio.google.com)

### Install

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=your_key_here
```

### Run the extraction pipeline

```bash
python -m scripts.run_pipeline
# Optional: custom data directory
python -m scripts.run_pipeline --data-dir /path/to/data
```

Processes all JPEGs, PDFs, and Excel files, normalises units, estimates CO2,
runs anomaly detection, and writes everything to data/pipeline.db.

---

## Run the API

```bash
uvicorn app.main:app --reload --port 8000
```

Swagger UI: http://localhost:8000/docs

| Method | Route                  | Description                       |
|--------|------------------------|-----------------------------------|
| GET    | /health                | Service health check              |
| POST   | /extract               | Extract from base64-encoded file  |
| GET    | /unified               | All energy records (filterable)   |
| GET    | /co2                   | CO2 estimates by scope / date     |
| GET    | /anomalies?recompute=1 | Anomaly detection results         |
| GET    | /forecast?horizon=3    | 3-month ahead forecast            |
| GET    | /kpis                  | ISO 50001 KPIs                    |
| GET    | /graph                 | Knowledge graph JSON              |
| POST   | /submit                | Full submission payload           |

---

## Run the Dashboard

```bash
streamlit run app/dashboard.py
```

Open http://localhost:8501

Sections:
- ISO 50001 KPI cards (EnPI, self-sufficiency, grid dependency, power factor, CO2 intensity)
- Monthly energy chart (filterable by energy type)
- CO2 scope breakdown with Simple vs Tri-gen Adjusted toggle
- Anomaly table with re-run button
- 3-month forecast (Prophet -> Holt-Winters fallback)
- Interactive knowledge graph (pyvis)

---

## Run with Docker

```bash
cp .env.example .env   # set GEMINI_API_KEY
docker compose up --build
```

- API: http://localhost:8000/docs
- Dashboard: http://localhost:8501

---

## Run Tests

```bash
pytest tests/ -v
# Pure-Python tests (no external deps):
pytest tests/test_anomaly.py tests/test_normalize.py tests/test_co2.py -v
```

| Module                   | Tests | Requires          |
|--------------------------|-------|-------------------|
| test_normalize.py        |  26   | none              |
| test_co2.py              |  19   | none              |
| test_anomaly.py          |  19   | none              |
| test_excel_extractor.py  |   ?   | openpyxl          |
| test_image_extractor.py  |   ?   | opencv, Gemini    |
| test_pdf_extractor.py    |   ?   | pdfplumber, fitz  |

---

## Emission Factors & Assumptions

| Factor                  | Value             | Source             |
|-------------------------|-------------------|--------------------|
| STEG grid electricity   | 0.593 kgCO2/kWh   | ANME Tunisia 2023  |
| Natural gas (LHV)       | 0.201 kgCO2/kWh   | IPCC AR6           |
| Gas HHV (STEG billing)  | 10.55 kWh/Nm3     | STEG PCS           |
| Gas LHV (CO2 calc)      | 9.51 kWh/Nm3      | combustion basis   |
| Steam (5 bar saturated) | 681 kWh/T         | h=2748 kJ/kg       |
| Scope 3                 | Not included      | upstream gas, etc. |

**CO2 modes:**
- *Simple*: per-record — Scope 1 (gas combustion) or Scope 2 (grid electricity). Direct and auditable.
- *Tri-gen Adjusted*: gross combustion CO2 minus avoided emissions from electricity produced,
  heat recovered, and cooling displaced. The factory may be CO2-net-negative on electricity
  if tri-gen export exceeds grid import.

**Forecast caveat:** ~12 monthly data points limits seasonal accuracy. Confidence intervals
are intentionally wide — do not use for financial planning.

**Reconciliation anomaly:** compares Excel BILAN TOTAL grid_import delta vs STEG bill active
energy for the same month. A >2% discrepancy triggers a RECONCILIATION flag.

---

## Project Structure

```
nrtf_claude/
|-- app/
|   |-- main.py            FastAPI application (9 routes + Swagger)
|   |-- dashboard.py       Streamlit dashboard
|   |-- extractors/
|   |   |-- image.py       Gemini vision + CLAHE/deskew preprocessing
|   |   |-- pdf.py         pdfplumber + vision fallback
|   |   `-- excel.py       openpyxl delta scan (BILAN TOTAL sheets)
|   |-- pipeline/
|   |   |-- normalize.py   Unit -> kWh (18 families, HHV/LHV gas)
|   |   |-- co2.py         GHG Protocol Scope 1/2 estimation
|   |   |-- anomaly.py     4 detectors (dropout/spike/drift/reconciliation)
|   |   |-- kpis.py        ISO 50001 KPIs
|   |   |-- forecast.py    Prophet / Holt-Winters forecasting
|   |   `-- graph.py       networkx knowledge graph + pyvis rendering
|   |-- models/schemas.py  Pydantic data models
|   `-- db/store.py        SQLite CRUD
|-- data/                  Input documents + pipeline.db (auto-created)
|-- scripts/
|   `-- run_pipeline.py    Full batch extraction runner
|-- tests/                 Test suite (58+ pure-Python tests)
|-- Dockerfile
|-- docker-compose.yml
`-- requirements.txt
```
