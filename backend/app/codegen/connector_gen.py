"""Connector generation: gap -> ConnectorSpec (LLM) -> rendered files (templates).

The structural concerns (auth, pagination, rate limiting, retries, error handling)
live in the Jinja2 templates and are therefore guaranteed correct and importable.
The model's job is to supply the API-specific *spec* (base path, auth type, entity
resource paths, pagination style) for the integration's destination system.
"""
from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ..llm.router import LLMRouter
from ..observability import RunLedger
from ..schemas.artifacts import ConnectorSpec, EntitySpec, GeneratedFile
from ..schemas.gaps import IntegrationGap

TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES)),
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)

CONNECTOR_SYSTEM = """You are an API integration engineer. Given an integration gap
(source system -> destination system), produce a ConnectorSpec for the DESTINATION
system so we can generate a reusable client for it.

Use your knowledge of the real API:
- class_name: PascalCase, e.g. 'NetSuiteConnector'.
- package_name: snake_case, e.g. 'netsuite_connector'.
- base_url_env: an UPPER_SNAKE env var name for the base URL.
- auth.type: one of oauth2_client_credentials | api_key_bearer | basic | custom_header
  (pick what the real API uses).
- entities: 1-3 representative resources relevant to THIS integration, each with a
  realistic resource_path, id_field, list_path (array key in list responses), and a
  pagination style (cursor | offset | page | none).
Be realistic and specific; do not invent a fake product."""


def _snake(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_")
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", s)
    return re.sub(r"_+", "_", s).lower() or "resource"


def _pascal(name: str) -> str:
    return "".join(p.capitalize() for p in re.split(r"[^0-9a-zA-Z]+", name) if p) or "Connector"


def generate_connector_spec(gap: IntegrationGap, router: LLMRouter,
                            ledger: RunLedger | None = None) -> ConnectorSpec:
    prompt = (
        f"Integration gap:\n- source: {gap.source_system}\n"
        f"- destination: {gap.destination_system}\n- name: {gap.integration_name}\n"
        f"- description: {gap.description}\n\n"
        f"Produce the ConnectorSpec for the destination system "
        f"('{gap.destination_system}')."
    )
    spec = router.structured(task="codegen", schema=ConnectorSpec, prompt=prompt,
                             system=CONNECTOR_SYSTEM)
    if not isinstance(spec, ConnectorSpec):
        spec = ConnectorSpec(system_name=gap.destination_system, class_name="Connector",
                             package_name="connector", base_url_env="API_BASE_URL")
    _normalize_spec(spec, gap)
    if ledger:
        ledger.event("connector_spec", gap=gap.id, system=spec.system_name,
                     entities=[e.name for e in spec.entities], auth=spec.auth.type)
    return spec


def _normalize_spec(spec: ConnectorSpec, gap: IntegrationGap) -> None:
    spec.system_name = spec.system_name or gap.destination_system
    spec.class_name = _pascal(spec.class_name or f"{spec.system_name}Connector")
    if not spec.class_name.endswith("Connector"):
        spec.class_name += "Connector"
    spec.package_name = _snake(spec.package_name or f"{spec.system_name}_connector")
    spec.base_url_env = re.sub(r"[^0-9A-Za-z]+", "_", spec.base_url_env or
                               f"{spec.package_name}_base_url").upper()
    if not spec.entities:
        spec.entities = [EntitySpec(name="Record", resource_path="/records",
                                    id_field="id", list_path="data", pagination="cursor",
                                    page_param="next")]
    for e in spec.entities:
        if not e.resource_path.startswith("/") and not e.resource_path.startswith("http"):
            e.resource_path = "/" + e.resource_path
        e.resource_path = e.resource_path.rstrip("/")


def _context(spec: ConnectorSpec, gap: IntegrationGap) -> dict:
    return {
        "system_name": spec.system_name,
        "class_name": spec.class_name,
        "package_name": spec.package_name,
        "base_url_env": spec.base_url_env,
        "env_prefix": re.sub(r"[^0-9A-Za-z]+", "_", spec.package_name).upper(),
        "auth": spec.auth.model_dump(),
        "rate_limit_per_sec": spec.rate_limit_per_sec,
        "entities": [
            {**e.model_dump(), "method": _snake(e.name)} for e in spec.entities
        ],
        "notes": spec.notes,
        "integration_name": gap.integration_name,
        "description": gap.description,
    }


def render_connector_files(spec: ConnectorSpec, gap: IntegrationGap) -> list[GeneratedFile]:
    ctx = _context(spec, gap)
    pkg = spec.package_name
    return [
        GeneratedFile(path=f"{pkg}/connector.py", language="python",
                      content=_env.get_template("connector.py.j2").render(**ctx)),
        GeneratedFile(path=f"{pkg}/test_connector.py", language="python",
                      content=_env.get_template("test_connector.py.j2").render(**ctx)),
        GeneratedFile(path=f"{pkg}/README.md", language="markdown",
                      content=_env.get_template("README.md.j2").render(**ctx)),
        GeneratedFile(path=f"{pkg}/requirements.txt", language="text",
                      content=_env.get_template("requirements.txt.j2").render(**ctx)),
    ]
