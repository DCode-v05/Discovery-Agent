---
name: new-connector
description: Extend the Level 3 code generator — add a connector auth type or pagination style, add an LLM provider, or change the generated connector shape. Use when modifying backend/app/codegen/templates or backend/app/llm.
---

# Extend the code generator / provider layer

## Add an auth type or pagination style to generated connectors
The generated connector's structure is hand-written in Jinja2 — that's what guarantees it
imports and its tests pass. To extend it:

1. **Auth:** edit `backend/app/codegen/templates/connector.py.j2`. Add a branch in the
   `{% if auth.type == ... %}` blocks for the `__init__` credentials and the `_auth_headers`
   method. Mirror the constructor branch in `test_connector.py.j2`'s `_make()` helper.
   Add the new literal to `AuthSpec.type` in `backend/app/schemas/artifacts.py`.
2. **Pagination:** add a branch in the `list_{{ e.method }}` section of `connector.py.j2`
   (`{% if e.pagination == ... %}`). Add the literal to `EntitySpec.pagination`.
3. **Always** add the new combination to the parametrized matrix in
   `backend/tests/test_codegen_offline.py` (`AUTH_TYPES` / `PAGINATIONS`) and run
   `pytest backend/tests/test_codegen_offline.py -q`. The generated pytest must stay green —
   that's the contract proving the output runs.

## Add an LLM provider (e.g. paid Anthropic/Claude, OpenRouter)
1. Create `backend/app/llm/<name>_provider.py` subclassing `BaseLLMProvider`; implement
   `_raw_structured` and `_raw_text` (see `gemini_provider.py` / `groq_provider.py`).
2. Register it in `LLMRouter.provider()` and add its key/model/RPM to `config.py` + `.env.example`.
3. Point a route at it via `ROUTE_*` in `.env`. No service code changes — the router abstracts it.

## Conventions to keep
- Templates render via `render_connector_files`; precompute derived fields (snake-case method
  names, env prefixes) in `connector_gen._context`, not in the template.
- The agent definition (`agent.yaml`) is assembled with `yaml.safe_dump` in `agentdef_gen.py`
  (never templated) so it is always valid YAML.
- Every generated artifact must pass `validators.validate_artifact` (syntax + import + yaml +
  optional pytest) before it is bundled.
