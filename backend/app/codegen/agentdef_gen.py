"""Agent-definition generation: gap + connector spec -> agent.yaml.

The model produces the operational spec (system prompt, workflow steps, test
scenarios); we assemble the YAML with `yaml.safe_dump` so the output is always
valid YAML (tool bindings are derived deterministically from the connector spec).
"""
from __future__ import annotations

import re

import yaml

from ..llm.router import LLMRouter
from ..observability import RunLedger
from ..schemas.artifacts import AgentDefSpec, ConnectorSpec, GeneratedFile
from ..schemas.gaps import IntegrationGap

AGENTDEF_SYSTEM = """You design automation agents. Given an integration gap and the
connector available for the destination system, write the agent definition that
executes the end-to-end workflow (read from the source system, transform, write to
the destination). Provide:
- agent_name and a one-line description,
- a concrete, operational system_prompt,
- ordered workflow_steps that actually accomplish the integration,
- test_scenarios including error and edge cases (auth failure, pagination, retries,
  partial data)."""


def _snake(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_")
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", s)
    return re.sub(r"_+", "_", s).lower() or "resource"


def generate_agent_def(gap: IntegrationGap, spec: ConnectorSpec, router: LLMRouter,
                       ledger: RunLedger | None = None) -> GeneratedFile:
    prompt = (
        f"Integration: {gap.integration_name}\nDescription: {gap.description}\n"
        f"Source system: {gap.source_system}\nDestination system: {gap.destination_system}\n"
        f"Destination connector class: {spec.class_name} "
        f"(entities: {', '.join(e.name for e in spec.entities)})\n\n"
        f"Write the AgentDefSpec to automate this integration."
    )
    definition = router.structured(task="codegen", schema=AgentDefSpec, prompt=prompt,
                                   system=AGENTDEF_SYSTEM)
    if not isinstance(definition, AgentDefSpec):
        definition = AgentDefSpec(
            agent_name=f"{gap.integration_name} agent",
            description=gap.description,
            system_prompt=f"You automate the {gap.integration_name} integration.",
            workflow_steps=[f"Read from {gap.source_system}", f"Write to {gap.destination_system}"],
            test_scenarios=["auth failure", "pagination", "retry on rate limit"],
        )

    operations: list[str] = []
    for e in spec.entities:
        m = _snake(e.name)
        operations += [f"list_{m}", f"get_{m}", f"create_{m}", f"update_{m}", f"delete_{m}"]

    agent_doc = {
        "agent": {
            "name": definition.agent_name,
            "description": definition.description,
            "model": "<configure: e.g. gemini-2.5-flash, llama-3.3-70b-versatile, or claude-opus-4-8>",
            "system_prompt": definition.system_prompt,
            "tools": [{
                "connector": spec.class_name,
                "module": f"{spec.package_name}.connector",
                "operations": operations,
            }],
            "workflow": [{"step": i, "action": step}
                         for i, step in enumerate(definition.workflow_steps, start=1)],
            "test_scenarios": definition.test_scenarios,
        }
    }
    content = yaml.safe_dump(agent_doc, sort_keys=False, default_flow_style=False, width=100)
    if ledger:
        ledger.event("agent_def", gap=gap.id, name=definition.agent_name,
                     steps=len(definition.workflow_steps))
    return GeneratedFile(path=f"{spec.package_name}/agent.yaml", language="yaml", content=content)
