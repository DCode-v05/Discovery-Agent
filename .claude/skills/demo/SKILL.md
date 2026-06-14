---
name: demo
description: Run the Discovery Agent end-to-end (Level 1 → 2 → 3) against the sample knowledge base and launch the web UI. Use to verify the full pipeline or prepare the demo video.
---

# Run the Discovery Agent demo

Use this to exercise the whole pipeline on the bundled sample data and bring up the UI.

## Preconditions
- `.env` exists at the project root with `GEMINI_API_KEY` and `GROQ_API_KEY` set.
  If not, tell the user where to get free keys (aistudio.google.com/apikey, console.groq.com/keys)
  and stop — the agent will otherwise fail clearly with a missing-key message.
- Dependencies installed: `pip install -r backend/requirements.txt` and (for the UI) `cd frontend && npm install`.

## Steps
1. Ensure the sample knowledge base exists; regenerate if missing:
   `python data/generate_kb.py`
2. Run the three levels via the CLI (fast, headless, writes JSON + Markdown to `out/`):
   ```
   python -m backend.cli discover data/kb --out out/inventory.json
   python -m backend.cli gaps --inventory out/inventory.json --use-cases data/use_cases.json --out out/gaps.json
   python -m backend.cli codegen --gaps out/gaps.json --top-n 3
   ```
3. Report: systems discovered + how many flagged for review; missing integrations + top priority;
   generated artifacts + validation status (syntax/import/yaml/pytest) + the bundle zip path.
4. To show the UI, start both servers and point the user to http://localhost:5173:
   - `uvicorn backend.app.main:app --reload --port 8000`
   - `cd frontend && npm run dev`

## Verifying without keys
If keys are absent, run only `python -m backend.cli discover data/kb` and show that every
document loads and then reports a clear missing-key failure (exit 0, no crash) — this
demonstrates the "fails clearly / knows what it cannot access" trait.

## Offline correctness check
`python -m pytest backend/tests -q` runs the full suite with a fake LLM router (no keys),
including the hallucination-guard negative test and execution of generated connector tests.
