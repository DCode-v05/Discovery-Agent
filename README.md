# Discovery Agent

## Project Description
Discovery Agent is a production-grade autonomous agent that turns an unstructured pile of company documents into working integration code. It reads a mixed-format knowledge base (PDFs, screenshots, spreadsheets, wikis, email threads), **discovers the software systems** an organization runs — each with a confidence score and grounded source evidence — then **maps automation use cases to those systems, traces the data flows, and surfaces the integration gaps**, and finally **generates runnable Python connectors, agent-definition YAML, and tests** for the highest-impact gaps. It is built around five principles: it makes decisions from context, validates aggressively (no hallucinations), fails clearly, stays inside guard rails, and logs every decision to an observable run ledger.

---

## Project Details

### Problem Statement
Enterprises run dozens of systems (CRM, ERP, procurement, data warehouse, HRIS, ITSM, payments), but the knowledge of *what* they run and *how* it connects is scattered across architecture docs, onboarding wikis, spreadsheets, screenshots, and email threads. Before any automation can be built, someone has to read all of it, figure out which systems exist, find where integrations are missing, and then build the connectors. Discovery Agent automates that entire path — discovery → gap analysis → code generation — while guaranteeing that nothing it asserts is invented: every claim traces back to text that actually appears in a source document.

### Document Ingestion & Preprocessing
Every document is normalized to a single `ExtractedDoc` shape (a text layer plus optional vision images) before analysis:
- **Dispatch by type** — PDF (`pdfplumber`/`pypdf`), image (`pillow` + `pytesseract` OCR), spreadsheet (`pandas`/`openpyxl`), Markdown, and plain text each have a dedicated loader.
- **Vision-first for images** — screenshots/scans are read by Gemini vision; a local Tesseract OCR fallback supplies a text layer for self-grounding when available.
- **Location markers** — page/sheet/row markers are preserved so evidence can be cited precisely (`page 2`, `Sheet1!B4`, `line 12`).
- **No silent drops** — an unsupported or unreadable file becomes a reported `SkippedDocument` (with *what's needed* to fix it), never a silent omission.

### Agent Pipeline & Levels
The agent runs as three progressive levels behind a swappable LLM provider layer (Gemini for vision/extraction/reasoning, Groq/Llama for fast code generation):

| Level | Input | Output | Key guarantee |
|---|---|---|---|
| **1 — Discovery** | PDF, image, spreadsheet, Markdown, text | System inventory: name, category, auth, entities, processes, criticality, **confidence**, **source evidence** | **No hallucinations** — every claim is grounded against source text; uncertain findings are flagged for review |
| **2 — Gap analysis** | Inventory + automation use cases | Use-case → system mappings, data flows, **prioritized integration gaps**, dependency statements | Priority is computed deterministically (frequency × criticality × downstream blocked) — explainable, not model-guessed |
| **3 — Code generation** | Gaps | Per gap: connector (auth, CRUD, pagination, rate limiting, retries, errors) + agent-definition YAML + unit tests + README, bundled as a zip | Generated code is **validated** (syntax + import smoke-test + YAML parse + a real `pytest` run) before it is offered for download |

The **grounding guard** (`discovery/grounding.py`) is the heart of the anti-hallucination policy: an evidence quote must appear in the source as an exact normalized substring or with ≥60% token overlap, otherwise the finding is capped and flagged for human review.

### Configuration & Thresholds
Model IDs, task routing, confidence thresholds, and rate limits are config-driven (free-tier model names rotate, so they never live in business logic). Tune everything from `.env`:
```
GEMINI_MODEL=gemini-2.5-flash        # vision + extraction + reasoning (L1, L2)
GROQ_CODE_MODEL=llama-3.3-70b-versatile   # fast code generation (L3)
ROUTE_EXTRACTION=gemini              # which provider handles each task
ROUTE_VISION=gemini
ROUTE_GAP_ANALYSIS=gemini
ROUTE_CODEGEN=groq
CONFIDENCE_EXPLICIT=0.95             # >= explicit named mention
CONFIDENCE_INFERRED=0.70             # reasoned from context; below this -> flagged for review
GEMINI_RPM=10                        # free-tier-safe rate limits
GROQ_RPM=30
```

### Observability
Every meaningful action — document processed, LLM call, context-driven decision, confidence score, failure — is emitted as a structured JSON event to a per-run ledger at `data/runs/<run_id>.jsonl` and to stderr. The React **Observability** panel reads the ledger via `GET /runs/{run_id}` so an operator can watch the agent's reasoning unfold: what it decided, why, how confident it was, and exactly what it would need if something failed.

### Web Application
A React + Vite + TypeScript front-end presents the pipeline as a three-step wizard:
- **Discovery** — upload documents (or point at a server-side path) and see the discovered systems with confidence badges and grounded evidence.
- **Gap analysis** — review prioritized integration gaps, data flows, and dependency statements.
- **Code generation** — generate and download the validated connector bundle for the top gaps.
- **Observability sidebar** — a live feed of the agent's decisions and confidence scores for the active run.

---

## Tech Stack
- **Backend:** Python 3.11+, FastAPI, Pydantic v2, `typer` CLI, `uvicorn`
- **LLMs (free tier):** Gemini (`google-genai`) for vision/extraction/reasoning; Groq (`groq`, Llama) for code generation — behind a swappable provider layer
- **Document ingestion:** `pdfplumber`, `pypdf`, `pillow` + `pytesseract` (OCR), `pandas`, `openpyxl`
- **Code generation:** `jinja2` templates, `pyyaml`, `ast` / import smoke-tests for validation
- **Frontend:** React 18, Vite, TypeScript
- **Tooling:** `pytest` (fully offline test suite), Docker + docker-compose

---

## Getting Started

### 1. Clone the repository
```
git clone https://github.com/DCode-v05/Discovery-Agent.git
cd Discovery-Agent
```

### 2. Install dependencies
```
# Backend (run from the project root so `backend` is importable)
pip install -r backend/requirements.txt

# Frontend
cd frontend && npm install && cd ..

# Configure API keys (free, no credit card)
cp .env.example .env   # then set GEMINI_API_KEY and GROQ_API_KEY
```
Get free keys: **Gemini** → https://aistudio.google.com/apikey · **Groq** → https://console.groq.com/keys

### 3. Run the application
```
# Option A — Docker (one command)
docker compose up --build
# UI: http://localhost:5173   ·   API docs: http://localhost:8000/docs

# Option B — Local (two terminals)
uvicorn backend.app.main:app --reload --port 8000   # backend
cd frontend && npm run dev                           # frontend -> http://localhost:5173
```

---

## Usage

**Web UI:** open http://localhost:5173 and walk the Discovery → Gap analysis → Code generation steps, watching the Observability sidebar.

**CLI (scriptable, mirrors the API):** run from the project root.
```
# Level 1 — discover systems from a folder of mixed documents
python -m backend.cli discover data/kb --out out/inventory.json

# Level 2 — map use cases and prioritize integration gaps
python -m backend.cli gaps --inventory out/inventory.json --use-cases data/use_cases.json

# Level 3 — generate connector + agent code for the top gaps
python -m backend.cli codegen --gaps out/gaps.json --top-n 3
# -> writes out/connectors_<run>.zip with validated, runnable connectors
```
The CLI prints rich summaries; full structured JSON + Markdown reports are written to `out/`.

**Tests (fully offline — no API keys):**
```
python -m pytest backend/tests -q
```
The suite uses a fake LLM router and covers multi-format ingestion, the hallucination/grounding guard, the confidence policy, gap reconciliation + prioritization, and code generation across every auth/pagination branch — including running the generated connectors' own pytest suites to prove they work.

---

## Project Structure
```
Discovery-Agent/
│
├── backend/
│   ├── app/
│   │   ├── config.py            # single source of truth: keys, models, routing, thresholds
│   │   ├── observability.py     # structured logging + per-run ledger (data/runs/<id>.jsonl)
│   │   ├── main.py              # FastAPI application entry point
│   │   ├── schemas/             # Pydantic contracts: inventory (L1), gaps (L2), artifacts (L3)
│   │   ├── llm/                 # provider layer: base, gemini_provider, groq_provider, router, errors
│   │   ├── ingest/              # loaders: pdf, image (OCR), spreadsheet, text -> ExtractedDoc
│   │   ├── discovery/           # Level 1: extractor, merger, grounding, service
│   │   ├── gapanalysis/         # Level 2: mapper, gap_detector, prioritizer, service
│   │   ├── codegen/             # Level 3: connector_gen, agentdef_gen, validators, templates/, service
│   │   └── routers/             # FastAPI routers: discovery, gaps, codegen, runs, health
│   ├── tests/                   # offline test suite (fake LLM router)
│   ├── cli.py                   # typer CLI (mirrors the API)
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # 3-step wizard shell
│   │   ├── api.ts, types.ts     # typed API client + response types
│   │   └── components/          # DiscoveryStep, GapStep, CodegenStep, Observability, ConfidenceBadge
│   ├── package.json, vite.config.ts, tsconfig.json
│   └── Dockerfile
│
├── data/
│   ├── kb/                      # sample knowledge base (pdf, png, xlsx, txt, md)
│   ├── use_cases.json          # sample automation use cases
│   ├── runs/                   # per-run observability ledgers (generated)
│   └── generate_kb.py          # regenerates the demo knowledge base
│
├── out/                        # generated inventories, gap reports, connector bundles
├── docker-compose.yml
├── .env.example
├── CLAUDE.md                   # full architecture map & conventions
└── README.md
```

---

## Contributing

Contributions are welcome! To contribute:
1. Fork the repository
2. Create a new branch:
   ```bash
   git checkout -b feature/your-feature
   ```
3. Commit your changes:
   ```bash
   git commit -m "Add your feature"
   ```
4. Push to your branch:
   ```bash
   git push origin feature/your-feature
   ```
5. Open a pull request describing your changes.

---

## Contact
- **GitHub:** [DCode-v05](https://github.com/DCode-v05)
- **Email:** denistanb05@gmail.com
