# Discovery Agent

**Turns an unstructured pile of company documents into runnable integration code — discovery, gap analysis, then connectors — and refuses to assert anything it can't trace back to a source.**

![Python](https://img.shields.io/badge/Python_3.11+-3776AB?style=flat&logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white) ![Pydantic](https://img.shields.io/badge/Pydantic_v2-E92063?style=flat&logo=pydantic&logoColor=white) ![Google Gemini](https://img.shields.io/badge/Gemini-8E75B2?style=flat&logo=googlegemini&logoColor=white) ![Groq](https://img.shields.io/badge/Groq_Llama_3.3-F55036?style=flat) ![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat&logo=typescript&logoColor=white) ![React](https://img.shields.io/badge/React_18-20232A?style=flat&logo=react&logoColor=61DAFB) ![Vite](https://img.shields.io/badge/Vite-646CFF?style=flat&logo=vite&logoColor=white) ![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white)

## Overview

Most companies run dozens of systems — CRM, ERP, procurement, a data warehouse, HRIS, ITSM, payments — but the knowledge of *what* they run and *how* it all connects is scattered across architecture PDFs, onboarding wikis, spreadsheets, screenshots, and email threads. Before anyone can automate a workflow, a human has to read all of it, work out which systems actually exist, find where integrations are missing, and then write the connectors.

Discovery Agent automates that whole path. You point it at a folder of mixed documents and it does three things in sequence: discovers the software systems an organization runs (each with a confidence score and the source text that backs it), maps automation use cases onto those systems and surfaces the integration gaps in priority order, and then generates runnable Python connectors plus agent-definition YAML and tests for the highest-impact gaps. The design principle running through all of it is that nothing the agent claims is invented — every assertion traces back to text that actually appears in a document, and anything it can't ground is flagged for human review instead of being passed off as fact.

I built this during my AI engineering internship at September AI (September Platforms). It is the most involved agentic system I've shipped: a full backend, a three-step React front-end, a swappable LLM provider layer, and a test suite that runs fully offline.

## Key Features

- **Multi-format ingestion** — PDFs, screenshots/scans (OCR), spreadsheets, Markdown, and plain text, all normalized to one internal document shape before analysis.
- **Vision-first reading of images** — screenshots and scans go through Gemini vision, with a local Tesseract OCR layer used for grounding when it's available.
- **No silent drops** — an unsupported or unreadable file becomes a reported `SkippedDocument` that says *what's needed* to fix it, rather than vanishing from the run.
- **Three progressive levels** — Discovery (Level 1) → Gap analysis (Level 2) → Code generation (Level 3), each runnable on its own from the API or CLI.
- **Grounding guard** — an anti-hallucination check that requires every evidence quote to be an exact normalized substring of the source, or to share at least 60% of its tokens with it.
- **Confidence policy** — explicit named mentions score 0.95, context-inferred findings 0.70; anything below the inferred threshold gets flagged for review.
- **Deterministic prioritization** — integration gaps are ranked in code (not asked of the model) from frequency, criticality, and how many downstream use cases each gap blocks.
- **Validated codegen** — every generated connector is checked for syntax, passes an import smoke-test, has its agent YAML parsed, and runs its own generated pytest suite before being offered for download.
- **Per-run observability ledger** — every meaningful action (document processed, LLM call, decision, confidence score, failure) is written as a structured JSON event to a per-run `.jsonl` file and streamed to a live panel in the UI.
- **Swappable provider layer** — Gemini and Groq sit behind a router; which provider handles extraction, vision, gap analysis, and codegen is set by config, not hard-coded.
- **Three-step React wizard** with confidence badges, grounded-evidence display, and a live observability sidebar.
- **Scriptable CLI** that mirrors the API, plus a sample knowledge base and a `pytest` suite that needs no API keys.

## How It Works

The agent runs as three levels behind a provider layer. Gemini handles vision, extraction, and reasoning (Levels 1 and 2); Groq's Llama 3.3 70B handles fast code generation (Level 3). All model IDs, routing, thresholds, and rate limits live in `config.py` and `.env` so free-tier model names — which rotate often — never leak into business logic.

### Ingestion and preprocessing

Every document is dispatched to a dedicated loader by type — `pdfplumber`/`pypdf` for PDFs, `pillow` + `pytesseract` for images, `pandas`/`openpyxl` for spreadsheets, and text/Markdown loaders for the rest — and normalized to a single `ExtractedDoc` shape (a text layer plus optional vision images). Page, sheet, and row markers are preserved (`page 2`, `Sheet1!B4`, `line 12`) so that evidence can be cited precisely later. Strict ingest is on by default: an unreadable file is reported, not skipped quietly.

### Level 1 — Discovery

The extractor asks the model to pull out the systems described in the documents, each with a category, auth method, entities, processes, and a criticality tier. The merger reconciles the same system appearing across multiple documents into one record. Then the **grounding guard** (`discovery/grounding.py`) runs: for each evidence quote it normalizes whitespace and case and checks whether the quote is an exact substring of the source, and if not, whether at least 60% of its tokens (longer than two characters) appear in the source. A finding that fails grounding is capped and marked `needs_review` rather than trusted. Confidence is assigned from the policy — 0.95 for explicitly named systems, 0.70 for ones inferred from context — and anything under the inferred threshold is surfaced for a human to confirm.

### Level 2 — Gap analysis

Given the inventory plus a set of automation use cases, the mapper connects each use case to the systems it touches, and the gap detector works out which integrations exist versus which are missing. Prioritization is deliberately deterministic and computed in `prioritizer.py`, so the ranking is reproducible and explainable instead of being a model guess:

```
business_impact_score = max_over_requiring_use_cases(freq_norm * crit_weight)
                        * (1 + 0.5 * (blocks_count - 1))
```

Criticality weights are critical 4.0 / high 3.0 / medium 2.0 / low 1.0, and frequency is normalized against the busiest use case in the run. Each gap is then bucketed by its score *relative to the strongest gap in the run* — critical at ≥ 0.75, high at ≥ 0.5, medium at ≥ 0.25 — so the highest-leverage gap always surfaces first. The level also emits plain-English dependency statements ("Integration X must exist before use case Y can be automated").

### Level 3 — Code generation

For the top-N missing integrations (default 3, ranked by business impact), the service generates a connector spec, renders the connector code from Jinja2 templates — auth, CRUD, pagination, rate limiting, retries, and error handling — generates an agent-definition YAML, and then validates the result. Validation is four gates: Python syntax, an import smoke-test, a YAML parse, and a real `pytest` run of the connector's own generated test file. One gap failing never kills the batch; it's caught, recorded as a warning with *what's needed*, and the run continues. Whatever passes is packaged into a downloadable zip (`out/connectors_<run>.zip`), namespaced by gap ID so two gaps targeting the same system don't collide.

### Observability

A `RunLedger` writes a structured JSON event for every step to `data/runs/<run_id>.jsonl` and to stderr. The React **Observability** panel reads it back through `GET /runs/{run_id}`, so an operator can watch the agent's reasoning unfold in real time — what it decided, why, how confident it was, and exactly what it would need if something failed.

### Web application

The front-end (React 18 + Vite + TypeScript) presents the pipeline as a three-step wizard — Discovery, Gap analysis, Code generation — with a persistent observability sidebar. The Discovery step shows discovered systems with confidence badges and their grounding evidence; the Gap step shows prioritized gaps, data flows, and dependency statements; the Codegen step generates and downloads the validated connector bundle.

## Highlights

- **Grounding rule:** evidence is accepted only as an exact normalized substring or ≥ 60% token overlap with the source — the check that keeps fabricated findings out.
- **Confidence policy:** 0.95 explicit / 0.70 inferred, below-threshold findings auto-flagged for review.
- **Explainable priority:** scored in code (freq × criticality × downstream leverage) with critical/high/medium buckets at 0.75 / 0.5 / 0.25 of the run maximum — no model-guessed rankings.
- **Codegen is verified, not just emitted:** four validation gates including a live `pytest` run of the generated connector's own tests.
- **Free-tier safe:** rate-limited to 10 rpm (Gemini) / 30 rpm (Groq) with up to 5 retries, so the whole thing runs on no-cost API keys.
- **Offline test suite:** the `pytest` suite swaps in a fake LLM router and needs no API keys — it covers ingestion, the grounding guard, the confidence policy, gap reconciliation and prioritization, and codegen across every auth/pagination branch (including running the generated connectors' own tests).
- Code split, by GitHub's language stats: Python ~141 KB, TypeScript ~24 KB, CSS ~22 KB, Jinja ~15 KB.

## Tech Stack

- **Languages:** Python 3.11+, TypeScript
- **Backend / API:** FastAPI, Pydantic v2, `pydantic-settings`, Typer (CLI), Uvicorn, `tenacity` (retries), `rich`
- **LLMs:** Gemini via `google-genai` (vision, extraction, reasoning); Groq Llama 3.3 70B via `groq` (code generation) — behind a config-driven provider router
- **Document ingestion:** `pdfplumber`, `pypdf`, `pillow` + `pytesseract` (OCR), `pandas`, `openpyxl`
- **Code generation:** Jinja2 templates, PyYAML, `ast` / import smoke-tests + `pytest` for validation
- **Frontend:** React 18, Vite, TypeScript
- **Infra / tooling:** Docker + docker-compose, `pytest`

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+ (for the front-end)
- Free API keys: Gemini (https://aistudio.google.com/apikey) and Groq (https://console.groq.com/keys) — no credit card needed
- Optional: Tesseract installed locally if you want the OCR grounding layer for images
- Optional: Docker, to run the whole stack with one command

### Installation

```bash
git clone https://github.com/DCode-v05/Discovery-Agent.git
cd Discovery-Agent

# Backend (run from the project root so `backend` is importable)
pip install -r backend/requirements.txt

# Frontend
cd frontend && npm install && cd ..

# Configure keys
cp .env.example .env   # then set GEMINI_API_KEY and GROQ_API_KEY
```

### Running

```bash
# Option A — Docker (one command)
docker compose up --build
# UI: http://localhost:5173   ·   API docs: http://localhost:8000/docs

# Option B — Local (two terminals)
uvicorn backend.app.main:app --reload --port 8000   # backend
cd frontend && npm run dev                          # frontend -> http://localhost:5173
```

## Usage

**Web UI:** open http://localhost:5173 and walk Discovery → Gap analysis → Code generation, watching the observability sidebar as the agent works.

**CLI** (scriptable, mirrors the API — run from the project root):

```bash
# Level 1 — discover systems from a folder of mixed documents
python -m backend.cli discover data/kb --out out/inventory.json

# Level 2 — map use cases and prioritize integration gaps
python -m backend.cli gaps --inventory out/inventory.json --use-cases data/use_cases.json

# Level 3 — generate connector + agent code for the top gaps
python -m backend.cli codegen --gaps out/gaps.json --top-n 3
# -> writes out/connectors_<run>.zip with validated, runnable connectors
```

Each command prints a `rich` summary table and writes both structured JSON and a Markdown report to `out/`. The repo ships a demo knowledge base in `data/kb/` (a PDF, a PNG, an XLSX, a TXT and a Markdown wiki) and sample use cases in `data/use_cases.json`, so the pipeline runs end-to-end out of the box; `data/generate_kb.py` regenerates that sample set.

**Tests** (fully offline, no API keys):

```bash
python -m pytest backend/tests -q
```

## Project Structure

```
Discovery-Agent/
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
│   │   └── routers/            # FastAPI routers: discovery, gaps, codegen, runs, health
│   ├── tests/                  # offline test suite (fake LLM router)
│   ├── cli.py                  # Typer CLI mirroring the API
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.tsx             # 3-step wizard shell
│   │   ├── api.ts, types.ts    # typed API client + response types
│   │   └── components/         # DiscoveryStep, GapStep, CodegenStep, Observability, ConfidenceBadge
│   ├── package.json, vite.config.ts, tsconfig.json
│   └── Dockerfile
├── data/
│   ├── kb/                     # sample knowledge base (pdf, png, xlsx, txt, md)
│   ├── use_cases.json          # sample automation use cases
│   └── generate_kb.py          # regenerates the demo knowledge base
├── .claude/skills/             # helper skills (demo run, new-connector)
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Contact

<table>
  <tr><td><b>Portfolio:</b> <a href="https://www.denistan.me">Denistan</a></td><td><b>LinkedIn:</b> <a href="https://www.linkedin.com/in/denistanb">denistanb</a></td></tr>
  <tr><td><b>GitHub:</b> <a href="https://github.com/DCode-v05">DCode-v05</a></td><td><b>LeetCode:</b> <a href="https://leetcode.com/u/Denistan_B">Denistan_B</a></td></tr>
  <tr><td colspan="2" align="center"><b>Email:</b> <a href="mailto:denistanb05@gmail.com">denistanb05@gmail.com</a></td></tr>
</table>

Made with ❤️ by **Denistan B**
