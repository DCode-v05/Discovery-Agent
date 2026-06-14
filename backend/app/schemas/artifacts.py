"""Level 3 schemas — generated integration code & agent definitions.

LLM-facing models carry raw generated source (`LLMConnectorCode`, etc.); domain
models describe the validated artifact bundle returned to the caller.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# LLM-facing generation spec (the model fills this; templates render it)       #
# --------------------------------------------------------------------------- #
class EntitySpec(BaseModel):
    """One CRUD-able resource on the target system."""

    name: str = Field(description="Entity/object name, singular, PascalCase e.g. 'Invoice'.")
    resource_path: str = Field(description="API path for the collection, e.g. '/services/data/v60.0/sobjects/Invoice'.")
    id_field: str = Field(default="id", description="Name of the unique id field in responses.")
    list_path: str = Field(default="", description="Dotted path to the array in a list response (e.g. 'records' or 'data'); empty if the response IS the array.")
    pagination: Literal["cursor", "offset", "page", "none"] = Field(default="cursor")
    page_param: str = Field(default="cursor", description="Query/body param or response field used for paging (e.g. 'nextRecordsUrl', 'offset', 'page').")


class AuthSpec(BaseModel):
    type: Literal["oauth2_client_credentials", "api_key_bearer", "basic", "custom_header"] = "api_key_bearer"
    token_url: str = Field(default="", description="OAuth token endpoint (oauth2 only).")
    scopes: list[str] = Field(default_factory=list)
    header_name: str = Field(default="Authorization", description="Header to carry the credential (custom_header/api_key).")


class ConnectorSpec(BaseModel):
    """Everything the templates need to emit a complete connector for ONE system."""

    system_name: str
    class_name: str = Field(description="PascalCase class name, e.g. 'NetSuiteConnector'.")
    package_name: str = Field(description="snake_case module/package name, e.g. 'netsuite_connector'.")
    base_url_env: str = Field(description="Env var holding the API base URL, e.g. 'NETSUITE_BASE_URL'.")
    auth: AuthSpec = Field(default_factory=AuthSpec)
    rate_limit_per_sec: float = Field(default=5.0, ge=0.1, le=100.0)
    entities: list[EntitySpec] = Field(default_factory=list, description="1-4 representative entities for this integration.")
    notes: str = ""


class AgentDefSpec(BaseModel):
    """Spec for the agent definition that orchestrates the end-to-end workflow."""

    agent_name: str
    description: str
    system_prompt: str = Field(description="The agent's system prompt — concrete and operational.")
    workflow_steps: list[str] = Field(description="Ordered, concrete steps to execute the integration end to end.")
    test_scenarios: list[str] = Field(description="Scenarios that should be tested, incl. error/edge cases.")


# --------------------------------------------------------------------------- #
# LLM-facing generation output                                                #
# --------------------------------------------------------------------------- #
class LLMConnectorCode(BaseModel):
    """The model's generated connector body (Python)."""

    code: str = Field(description="Complete, importable Python module source for the connector. No markdown fences.")
    base_url_env: str = Field(default="", description="Name of the env var holding the API base URL, if applicable.")
    notes: str = Field(default="", description="Anything an engineer should know before deploying.")


class LLMTestCode(BaseModel):
    code: str = Field(description="Complete pytest module source testing auth, CRUD, error and edge cases. No markdown fences.")


class LLMAgentDefinition(BaseModel):
    yaml: str = Field(description="Agent definition as YAML text: system_prompt, tools, workflow steps, test scenarios. No markdown fences.")


# --------------------------------------------------------------------------- #
# Domain output                                                               #
# --------------------------------------------------------------------------- #
class ValidationResult(BaseModel):
    syntax_ok: bool = False
    import_ok: bool = False
    yaml_ok: bool = False
    tests_pass: bool | None = None  # None = not run
    issues: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.syntax_ok and self.import_ok and self.yaml_ok


class GeneratedFile(BaseModel):
    path: str = Field(description="Path relative to the artifact bundle root.")
    content: str
    language: str = Field(description="python | yaml | markdown | text")


class ConnectorArtifact(BaseModel):
    gap_id: str
    system_name: str
    integration_name: str
    package_name: str
    files: list[GeneratedFile] = Field(default_factory=list)
    validation: ValidationResult = Field(default_factory=ValidationResult)
    notes: str = ""
    error: str | None = None


class CodegenResult(BaseModel):
    run_id: str
    generated_at: str
    artifact_count: int
    artifacts: list[ConnectorArtifact] = Field(default_factory=list)
    bundle_path: str | None = None
    warnings: list[str] = Field(default_factory=list)
