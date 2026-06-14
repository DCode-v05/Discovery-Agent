"""Offline tests for Level 3 code generation.

No API keys: a fake router returns specs, and we verify the rendered code is
syntactically valid, imports cleanly, has valid agent YAML, and — critically —
its generated pytest suite PASSES (proving the code actually runs). All template
branches (auth types x pagination styles) are exercised.
"""
from __future__ import annotations

import zipfile

import pytest

from backend.app.codegen.connector_gen import render_connector_files
from backend.app.codegen.service import generate_code
from backend.app.codegen.validators import validate_artifact
from backend.app.schemas.artifacts import (
    AgentDefSpec,
    AuthSpec,
    ConnectorSpec,
    EntitySpec,
)
from backend.app.schemas.gaps import EffortLevel, GapStatus, IntegrationGap

AUTH_TYPES = ["api_key_bearer", "oauth2_client_credentials", "basic", "custom_header"]
PAGINATIONS = ["cursor", "offset", "page", "none"]


def _gap(name="Coupa -> NetSuite", dest="NetSuite") -> IntegrationGap:
    return IntegrationGap(
        id="gap-1", source_system="Coupa", destination_system=dest,
        integration_name=name, description="Sync POs into bills.",
        status=GapStatus.missing, effort_level=EffortLevel.medium, effort_days=10,
        business_impact_score=3.0,
    )


def _spec(auth_type: str, pagination: str) -> ConnectorSpec:
    return ConnectorSpec(
        system_name="NetSuite", class_name="NetSuiteConnector",
        package_name="netsuite_connector", base_url_env="NETSUITE_BASE_URL",
        auth=AuthSpec(type=auth_type, token_url="https://x.test/token",
                      scopes=["rest_webservices"], header_name="Authorization"),
        rate_limit_per_sec=5.0,
        entities=[EntitySpec(name="Vendor Bill", resource_path="/record/v1/vendorBill",
                             id_field="id", list_path="items", pagination=pagination,
                             page_param="offset" if pagination == "offset" else "next")],
    )


@pytest.mark.parametrize("auth_type", AUTH_TYPES)
@pytest.mark.parametrize("pagination", PAGINATIONS)
def test_all_template_branches_import(auth_type, pagination):
    spec = _spec(auth_type, pagination)
    files = render_connector_files(spec, _gap())
    # add a minimal valid agent.yaml so YAML check passes
    files.append(type(files[0])(path=f"{spec.package_name}/agent.yaml", language="yaml",
                                content="agent:\n  name: t\n"))
    result = validate_artifact(files, spec.package_name, run_tests=False)
    assert result.syntax_ok, result.issues
    assert result.import_ok, result.issues
    assert result.yaml_ok, result.issues


def test_generated_pytest_suite_passes():
    """The strongest signal: render a connector and run its own tests green."""
    spec = _spec("api_key_bearer", "cursor")
    files = render_connector_files(spec, _gap())
    files.append(type(files[0])(path=f"{spec.package_name}/agent.yaml", language="yaml",
                                content="agent:\n  name: t\n"))
    result = validate_artifact(files, spec.package_name, run_tests=True)
    assert result.passed, result.issues
    assert result.tests_pass is True, result.issues


class FakeRouter:
    """Returns a ConnectorSpec or AgentDefSpec depending on the requested schema."""

    def structured(self, *, task, schema, prompt, system="", images=None, model=None):
        if schema is ConnectorSpec:
            return _spec("oauth2_client_credentials", "cursor")
        if schema is AgentDefSpec:
            return AgentDefSpec(
                agent_name="PO-to-Bill agent", description="Coupa -> NetSuite",
                system_prompt="Automate the Coupa to NetSuite integration.",
                workflow_steps=["List approved POs in Coupa", "Create vendor bills in NetSuite"],
                test_scenarios=["auth failure", "pagination", "retry on 429"],
            )
        raise AssertionError(f"unexpected schema {schema}")

    def text(self, **_):
        return ""


def test_generate_code_end_to_end_with_bundle():
    gaps = [_gap("Coupa -> NetSuite", "NetSuite"), _gap("Okta -> Salesforce", "Salesforce")]
    for i, g in enumerate(gaps, 1):
        g.id = f"gap-{i}"
    result = generate_code(gaps, router=FakeRouter(), top_n=2, run_tests=True, write_bundle=True)

    assert result.artifact_count == 2
    for art in result.artifacts:
        assert art.error is None
        assert art.validation.passed, art.validation.issues
        assert art.validation.tests_pass is True, art.validation.issues
        paths = {f.path.split("/")[-1] for f in art.files}
        assert {"connector.py", "test_connector.py", "agent.yaml",
                "README.md", "requirements.txt"} <= paths

    # bundle zip exists and contains the generated files
    from backend.app.config import PROJECT_ROOT
    bundle = PROJECT_ROOT / result.bundle_path
    assert bundle.exists()
    with zipfile.ZipFile(bundle) as z:
        assert any(n.endswith("connector.py") for n in z.namelist())
