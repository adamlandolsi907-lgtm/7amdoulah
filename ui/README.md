# ADWYA Energy Intelligence — UI

Frontend for the NRTF Phase 2 energy document pipeline. Built for the **Re·Tech Fusion hackathon (INSAT)** — pharmaceutical factory energy audit, document extraction, CO₂ estimation, and knowledge graph visualization for **Société ADWYA, Sidi Daoud, Tunisia**.

---

## Quick Start

```bash
cd "C:\Projects\NRTF\Phase 2\ui"
npm install
npm run dev        # → http://localhost:3000
npm run build      # production build check
```

The app runs fully without a backend — all data is loaded from `lib/mock-data.ts`.

---

## What This Is

A document intelligence workstation heavily inspired by **Selecao-QDesign** (located at `../Selecao-QDesign/`), adapted from a biological research platform to an industrial energy audit tool. The same visual language (dark green theme, floating windows, three-mode workspace, @xyflow graph) is repurposed for STEG invoices, Excel energy reports, and the ADWYA factory knowledge graph.

**Tech stack** (identical to QDesign):

| Layer | Choice |
|---|---|
| Framework | Next.js 16 (App Router, Turbopack) |
| UI | React 19 + TypeScript |
| Styling | Tailwind CSS 4 + Radix UI primitives |
| State | Zustand 5 |
| Graph | @xyflow/react 12 |
| Components | Custom shadcn-style (no shadcn dependency) |

---

## File Structure

```
ui/
├── app/
│   ├── globals.css            # Dark green theme, scrollbar, react-flow overrides
│   ├── layout.tsx             # Root layout (metadata, body)
│   ├── page.tsx               # Root redirect → /workspace
│   └── workspace/
│       └── page.tsx           # Main workspace — header + mode switcher + floating windows
│
├── components/
│   ├── ui/                    # Base components (Radix-backed, green-themed)
│   │   ├── button.tsx         # 6 variants: default/destructive/outline/secondary/ghost/link
│   │   ├── badge.tsx          # 7 variants incl. success/warning/critical
│   │   ├── dialog.tsx         # Radix Dialog with dark overlay
│   │   ├── input.tsx          # Dark-themed text input
│   │   ├── label.tsx          # Radix Label
│   │   ├── scroll-area.tsx    # Radix ScrollArea with green thumb
│   │   ├── select.tsx         # Native <select> with dark styling
│   │   └── tooltip.tsx        # Radix Tooltip
│   │
│   ├── viewers/               # Floating window system
│   │   ├── FloatingWindow.tsx # Draggable + resizable + minimizable window shell
│   │   ├── InsightPanel.tsx   # Document insights (extracted fields, anomalies, CO₂, power factor)
│   │   ├── ImageViewer.tsx    # Base64 or URL image display (for STEG bill photos)
│   │   └── index.tsx          # Barrel export
│   │
│   └── workspace/             # The three main mode panels
│       ├── DocumentPool.tsx   # Document cards grid + anomaly sidebar + stats bar
│       ├── EnergyGraph.tsx    # @xyflow interactive knowledge graph
│       ├── AnalysisPanel.tsx  # KPI cards + collapsible analysis findings
│       └── index.ts           # Barrel export
│
└── lib/
    ├── types.ts               # All TypeScript types for the energy domain
    ├── mock-data.ts           # Static mock documents, graph, analysis, KPIs
    ├── stores.ts              # Zustand store (mode, documents, graph, viewers)
    └── utils.ts               # Formatters (kWh, TND, dates, labels, colors)
```

---

## The Three Modes

The workspace has a mode switcher in the header with arrows between modes (same pattern as QDesign's Pool → Graph → Co-Scientist flow):

```
[ Documents ] → [ Graphe Énergétique ] → [ Analyse & KPI ]
```

### Mode 1 — Documents (DocumentPool)

A card grid of all extracted energy documents. Each card shows:
- Document type badge (Facture STEG / Relevé Compteur / Rapport Excel / etc.)
- Period (month/year, formatted in French)
- Energy quantity in kWh (auto-scaled to MWh/GWh)
- Amount in TND (for invoices)
- CO₂ in tonnes (for billed electricity)
- Extraction confidence % with color-coded dot (green ≥90%, amber ≥70%, red <70%)
- Anomaly badge (red, count) or OK badge (green)

**Right sidebar** (visible on xl screens): live list of all RECONCILIATION anomalies with delta % — clickable to open the relevant document.

**Stats bar** at top: total kWh across all docs, total TND, anomaly count, average confidence.

**Filters**: by document type (select dropdown) and anomaly-only toggle button.

**Clicking a card** opens a floating InsightPanel window for that document.

### Mode 2 — Graphe Énergétique (EnergyGraph)

An interactive @xyflow/react knowledge graph of the ADWYA factory energy system. Full pan/zoom/minimap.

**Node types** (color-coded):

| Type | Color | Represents |
|---|---|---|
| `site` | Amber | ADWYA factory |
| `zone` | Blue | Alpha / Beta / Gamma production zones |
| `equipment` | Green | Tri-gen, absorption machine, compressors, boilers, GEGs |
| `meter` | Purple | STEG purchase meter, GN meters (incl. shared Beta/Munters) |
| `document` | Red | Extracted documents (linked to actual EnergyDocument records) |
| `anomaly` | Bright red + pulse animation | Flagged issues (reconciliation, underperformance, oversizing) |
| `supplier` | Gray | STEG |
| `reading` | Cyan | Individual meter readings |

**Edge types** (style-coded):

| Type | Style | Represents |
|---|---|---|
| `supplies` / `feeds` | Solid green, animated | Energy flow |
| `part_of` | Solid blue | Zone → Site hierarchy |
| `located_in` | Solid gray | Equipment → Zone |
| `measured_by` | Solid purple | Document → Meter |
| `extracted_from` | Solid amber | Document → Source |
| `discrepancy` | Dashed red | Anomaly → affected entity |
| `not_connected_to` | Long-dash red | Steam meters NOT wired to GTE |
| `shared_with` | Dashed orange | Shared GN meter (Beta + Munters) |

**Hovering a node** shows a tooltip with full description (equipment specs, measured values, audit findings).

**Clicking a document node** opens the InsightPanel floating window for that document.

**Legend** is always visible at bottom-left.

**Audit-driven anomaly nodes** embedded in the graph (from `rapport_audit.pdf`):
- Absorbeur THERMAX: 261 kW measured vs 802 kW nominal (32%)
- Compresseur D132RS-8A: 39% load average, 87% of hours at <20% charge
- Zone Beta: no tri-gen heat recovery despite 1 270 kW available
- Shared GN meter Beta+Munters: data impossible to disaggregate
- Steam meters Alpha + Gamma: installed but NOT connected to GTE

### Mode 3 — Analyse & KPI (AnalysisPanel)

**KPI grid** (ISO 50001 standard indicators, color-coded by status):

| KPI | Formula | Threshold |
|---|---|---|
| Facteur de Puissance | kWh / √(kWh² + kVArh²) | >0.90 (STEG penalizes below) |
| Auto-suffisance | tri-gen production / total consumption | higher = better |
| Dépendance Réseau | STEG net / total | lower = better |
| CO₂ net | Scope 1 + Scope 2 − injection credit | — |
| Intensité CO₂ | kgCO₂ / kWh_total | lower = better |
| EnPI | actual / baseline (12-month rolling) | <1.0 = improvement |
| Absorbeur THERMAX | % of nominal capacity | >70% expected |
| Charge Compresseur | average load % | >60% expected |

**Analysis findings** grouped by severity (Critique → Attention → Bilans & Insights), each collapsible:

| ID | Type | Topic |
|---|---|---|
| an_001 | reconciliation | Excel 19 100 vs STEG 18 634 kWh — +2.5% écart octobre 2025 |
| an_002 | anomaly | Absorbeur à 32% nominal — 541 kW froid non récupérés |
| an_003 | anomaly | Compresseur surdimensionné — 39% charge, 87% du temps <20% |
| an_004 | anomaly | Zone Beta — aucune récupération tri-gen, compteur GN partagé |
| an_005 | anomaly | Compteurs vapeur non branchés au GTE — angle mort |
| an_006 | co2_estimate | Bilan CO₂ octobre 2025: 24 402 kgCO₂ net (Scope 1 + 2) |
| an_007 | kpi | ISO 50001 KPIs: cos φ = 0.968, auto-suffisance 31.7% |

---

## The Floating Window System

The core UX pattern. Any document can be opened in a draggable, resizable, minimizable window that floats above the workspace — identical to QDesign's FloatingWindow for PDB/PDF/sequence viewers.

### How it works

**Opening:** Clicking a document card (in pool mode) or a document node (in graph mode) calls `store.openViewer(doc)`. The store checks if that document is already open — if yes, it un-minimizes it; if no, it adds a new viewer entry with a cascading offset position.

**State:** All viewer positions, sizes, and minimize states live in Zustand (`useWorkspaceStore.activeViewers`). This means switching between modes doesn't close open windows — they persist across the whole workspace.

**Stacking:** Multiple windows can be open simultaneously. Minimized windows collapse to a taskbar at the bottom-right, stacked horizontally with 200px spacing.

**InsightPanel content:** The window's body is always an `InsightPanel` component displaying:
1. Document type + confidence score
2. Summary KPI tiles (kWh, TND, CO₂, power factor if applicable)
3. Anomaly cards (if any) — with observed vs expected values
4. Extracted fields table — all OCR'd fields with units and per-field confidence dots
5. Extraction metadata (method, zone, energy type)
6. Related documents — other docs from the same month (auto-linked by date)

### Adding a new viewer type

To show something other than InsightPanel inside a FloatingWindow (e.g. a PDF renderer or chart), add it in `app/workspace/page.tsx` inside the `activeViewers.map()`:

```tsx
<FloatingWindow key={viewer.id} ...props>
  {viewer.type === "pdf" && <PDFViewer content={doc.content} />}
  {viewer.type === "image" && <ImageViewer content={doc.content} />}
  {/* default: */}
  <InsightPanel document={doc} relatedDocuments={relatedDocs} />
</FloatingWindow>
```

---

## Data Layer

### Mock data (`lib/mock-data.ts`)

Contains three exports used directly by the Zustand store:

- **`MOCK_DOCUMENTS`** — 6 `EnergyDocument` records (2 STEG bills, 1 meter reading, 2 Excel reports, 1 PDF)
- **`MOCK_GRAPH`** — `EnergyGraph` with 21 nodes and 25 edges representing the full ADWYA energy system
- **`MOCK_ANALYSIS`** — 7 `AnalysisResult` records (reconciliation, anomalies, CO₂ bilan, KPI summary)
- **`MOCK_KPIS`** — 8 `EnergyKPI` records for the ISO 50001 KPI grid

### Connecting to the real FastAPI backend

The UI is intentionally disconnected. To wire it up:

**1. Create `lib/api.ts`:**
```typescript
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function fetchDocuments(): Promise<EnergyDocument[]> {
  const res = await fetch(`${API}/unified`);
  return res.json();
}
export async function fetchGraph(): Promise<EnergyGraph> {
  const res = await fetch(`${API}/graph`);
  return res.json();
}
export async function fetchAnalysis(): Promise<AnalysisResult[]> {
  const res = await fetch(`${API}/anomalies`);
  return res.json();
}
export async function fetchKPIs(): Promise<EnergyKPI[]> {
  const res = await fetch(`${API}/kpis`);
  return res.json();
}
```

**2. Update `lib/stores.ts`** — replace the static imports with React Query fetches or add `useEffect` initialization calls in `app/workspace/page.tsx`.

**3. The FastAPI routes to implement** (from `7amdoulah/AGENT_BRIEF.md`):
```
GET /unified     → list[EnergyDocument]
GET /graph       → { nodes, edges }
GET /anomalies   → list[Anomaly]
GET /kpis        → dict[KPI]
GET /co2         → list[CO2Estimate]
```

The type contracts in `lib/types.ts` already match what the backend should return — especially `EnergyDocument`, `EnergyGraph`, `AnalysisResult`, and `EnergyKPI`.

---

## Type Reference (`lib/types.ts`)

### `EnergyDocument`

The core document record. Produced by the extraction pipeline for each source file.

```typescript
interface EnergyDocument {
  id: string;
  name: string;
  doc_type: "steg_bill" | "steg_meter_reading" | "excel_report" | "pdf_report" | "image_invoice";
  date: string;                    // "YYYY-MM"
  zone: "alpha" | "beta" | "gamma" | "global";
  energy_type: "electricity" | "gas" | "steam" | "hot_water" | "chilled_water" | "compressed_air";
  quantity_kwh: number | null;     // normalized to kWh
  unit_raw: string;                // original unit before normalization
  quantity_raw: number | null;     // original value
  amount_tnd: number | null;       // invoice amount (TND), null for non-invoices
  supplier?: string;               // "STEG" for electricity/gas bills
  facture_number?: string;         // "69105258R" — STEG invoice ref
  extraction_confidence: number;   // 0.0–1.0
  extraction_method: "claude_vision" | "pdfplumber" | "pandas_excel" | "manual";
  fields: ExtractedField[];        // individual OCR'd fields with labels and units
  anomalies: AnomalyFlag[];        // detected issues (RECONCILIATION, SPIKE, DROPOUT, DRIFT)
  co2_kg: number | null;           // estimated kgCO₂ for this document's energy
  co2_scope: "scope1" | "scope2" | null;
  source_file: string;             // original filename
  added_at: string;                // ISO timestamp
  content?: string;                // base64 content for image/PDF viewing
}
```

### `EnergyNode` / `EnergyEdge`

Graph entities. Positions are absolute pixel coordinates for @xyflow.

```typescript
interface EnergyNode {
  id: string;
  type: "site" | "zone" | "equipment" | "meter" | "document" | "anomaly" | "supplier" | "reading";
  label: string;
  description?: string;            // shown in hover tooltip
  position: { x: number; y: number };
  metadata?: Record<string, unknown>;
  documentId?: string;             // links to an EnergyDocument (enables click-to-open)
  anomaly?: boolean;               // triggers pulse animation
  severity?: "ok" | "warning" | "critical";
}

interface EnergyEdge {
  id: string;
  source: string;                  // node id
  target: string;                  // node id
  label?: string;                  // displayed on edge
  type: "supplies" | "part_of" | "located_in" | "measured_by" | "extracted_from"
      | "reconciles_with" | "discrepancy" | "feeds" | "not_connected_to" | "shared_with";
  strength?: number;               // 0–1, not currently visualized
}
```

### `AnalysisResult`

An analysis finding (anomaly detection output, CO₂ bilan, KPI summary, etc.).

```typescript
interface AnalysisResult {
  id: string;
  type: "reconciliation" | "anomaly" | "co2_estimate" | "kpi" | "forecast" | "insight";
  title: string;
  content: string;                 // full text, whitespace-preserved, supports multiline
  severity?: "ok" | "warning" | "critical";
  date?: string;                   // "YYYY-MM"
  value?: number;                  // headline number (delta %, kgCO₂, cos φ, etc.)
  unit?: string;
  document_ids?: string[];         // EnergyDocument ids this result refers to
  created_at: string;
}
```

---

## Zustand Store (`lib/stores.ts`)

Single store `useWorkspaceStore` covering all UI state:

```typescript
// Mode
mode: WorkspaceMode             // "pool" | "graph" | "analysis"
setMode(mode)

// Data (currently static mock)
documents: EnergyDocument[]
graph: EnergyGraph
analysis: AnalysisResult[]
kpis: EnergyKPI[]

// Floating viewer windows
activeViewers: ViewerEntry[]
openViewer(doc)                 // opens or un-minimizes
closeViewer(id)
minimizeViewer(id)
restoreViewer(id)
updateViewerPosition(id, pos)
updateViewerSize(id, size)

// Graph selection
selectedNodeId: string | null
setSelectedNode(id)

// Document filters
filterDocType: string           // "all" or doc_type value
filterDate: string
filterAnomaly: boolean
setFilter(key, value)
```

---

## Styling Notes

The theme is derived directly from QDesign's dark biology theme, repurposed for energy:

- **Background:** `#0a0f0a` (very dark green-black)
- **Surface:** `gray-900`, `gray-950`
- **Accent:** `green-600` (#22c55e) for buttons, highlights, handles
- **Text:** `green-100` for headings, `gray-300` for body, `gray-400`/`gray-500` for labels
- **Anomaly:** `red-400` / `red-950` backgrounds
- **Warning:** `amber-400` / `amber-950` backgrounds

Energy-specific semantic colors overlaid on the base theme:
- **Electricity:** amber (kWh values)
- **TND amounts:** blue
- **CO₂:** green (Leaf icon)
- **Reactive power:** purple
- **Anomaly:** red with AlertTriangle icon

All Radix UI components are unstyled primitives wrapped with Tailwind — no shadcn/ui dependency, no CVA, just `cn()` (clsx + tailwind-merge).

---

## Relation to QDesign

| QDesign concept | Energy UI equivalent |
|---|---|
| `DataPoolItem` (PDB/PDF/image/sequence) | `EnergyDocument` (steg_bill/excel_report/etc.) |
| `DataPool.tsx` | `DocumentPool.tsx` |
| `KnowledgeGraph.tsx` | `EnergyGraph.tsx` |
| `CoScientistPanel.tsx` | `AnalysisPanel.tsx` |
| `FloatingWindow.tsx` | `FloatingWindow.tsx` (copied directly) |
| `PDBViewer`, `PDFViewer`, etc. | `InsightPanel.tsx` (energy-specific) |
| `GraphNode` types (pdb/pdf/sequence) | `EnergyNode` types (site/zone/equipment/meter) |
| `GraphEdge` correlation types | `EnergyEdge` energy flow types |
| `CoScientistStep` (reasoning/evidence/hypothesis) | `AnalysisResult` (reconciliation/anomaly/co2_estimate/kpi) |
| MongoDB + NestJS backend | FastAPI + SQLite (not yet connected) |
| Socket.io real-time | Not implemented (single-user hackathon) |

The `FloatingWindow.tsx` component is a near-exact copy of QDesign's version. The three-mode workspace page structure, mode switcher with arrows, and Zustand store patterns are all direct adaptations.

---

## Factory Context (for graph/data understanding)

**Site:** Société ADWYA — Sidi Daoud, Tunisia — pharmaceutical (human medicines)  
**STEG district:** KRAM — Client REF: 226570 — Tarif HTA 30kV, 1300 kVA subscribed  
**Three production zones:** Alpha (fabrication), Beta (conditioning), Gamma (storage)

**Energy vectors in the knowledge graph:**

| Vector | System | Rated |
|---|---|---|
| Grid electricity | STEG HTA 30kV, 2 independent lines | 1 300 kVA |
| Self-generation | Tri-gen gas engine + alternator | 1 200 kW |
| Natural gas | STEG BP2, double-ramp station | 6 000 th/h subscribed |
| Steam | 2× MANGAZZINI boilers (Alpha + Gamma) | 1 840 kW total |
| Hot water | 3 gas boilers + 3 tri-gen heat exchangers | 1 140 + 1 270 kW |
| Chilled water | 6× Carrier GEG electric + THERMAX absorption | 2 650 + 802 kW |
| Compressed air | 2× oil-free screw compressors | 41.18 m³/min |

**Key audit findings embedded in the graph** (from `7amdoulah/rapport_audit.pdf`):
1. Absorption machine at 32% of nominal capacity
2. Compressor at 39% average load (oversized by ~2.5×)
3. Zone Beta has zero tri-gen heat recovery
4. Steam meters installed but not connected to GTE management system
5. Beta boiler + Munters share one gas meter — consumption impossible to disaggregate
