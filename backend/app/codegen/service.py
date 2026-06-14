"""Level 3 orchestration: gaps -> per-gap connector + agent definition -> validated bundle.

For each missing integration (top-N by business impact) the agent generates a
connector spec, renders the code, generates the agent definition, validates the
result, and packages everything into a downloadable zip.
"""
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from ..config import PROJECT_ROOT
from ..llm.errors import LLMError
from ..llm.router import LLMRouter
from ..observability import RunLedger
from ..schemas.artifacts import CodegenResult, ConnectorArtifact
from ..schemas.gaps import GapReport, GapStatus, IntegrationGap
from .agentdef_gen import generate_agent_def
from .connector_gen import generate_connector_spec, render_connector_files
from .validators import validate_artifact


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_gaps(path: str | Path) -> list[IntegrationGap]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    report = GapReport.model_validate(data)
    return report.gaps


def select_gaps(gaps: list[IntegrationGap], top_n: int) -> list[IntegrationGap]:
    missing = [g for g in gaps if g.status == GapStatus.missing]
    missing.sort(key=lambda g: -g.business_impact_score)
    return missing[:top_n]


def generate_code(gaps: list[IntegrationGap], ledger: RunLedger | None = None,
                  router: LLMRouter | None = None, top_n: int = 3,
                  run_tests: bool = True, write_bundle: bool = True) -> CodegenResult:
    ledger = ledger or RunLedger(kind="codegen")
    router = router or LLMRouter(ledger=ledger)

    selected = select_gaps(gaps, top_n)
    ledger.event("codegen_started", total_gaps=len(gaps), selected=len(selected),
                 targets=[g.integration_name for g in selected])

    artifacts: list[ConnectorArtifact] = []
    warnings: list[str] = []
    for gap in selected:
        try:
            spec = generate_connector_spec(gap, router, ledger)
            files = render_connector_files(spec, gap)
            files.append(generate_agent_def(gap, spec, router, ledger))
            validation = validate_artifact(files, spec.package_name, run_tests)
            artifacts.append(ConnectorArtifact(
                gap_id=gap.id, system_name=spec.system_name,
                integration_name=gap.integration_name, package_name=spec.package_name,
                files=files, validation=validation, notes=spec.notes))
            ledger.event("artifact_validated", gap=gap.id, package=spec.package_name,
                         syntax=validation.syntax_ok, import_ok=validation.import_ok,
                         yaml_ok=validation.yaml_ok, tests_pass=validation.tests_pass)
        except LLMError as exc:
            warnings.append(f"{gap.integration_name}: {exc.message}")
            artifacts.append(ConnectorArtifact(
                gap_id=gap.id, system_name=gap.destination_system,
                integration_name=gap.integration_name, package_name="",
                error=exc.message))
            ledger.failure(what=f"codegen:{gap.id}", error=exc.message, needs=exc.needs)
        except Exception as exc:  # noqa: BLE001 - never let one gap kill the batch
            warnings.append(f"{gap.integration_name}: {exc}")
            artifacts.append(ConnectorArtifact(
                gap_id=gap.id, system_name=gap.destination_system,
                integration_name=gap.integration_name, package_name="", error=str(exc)))
            ledger.failure(what=f"codegen:{gap.id}", error=str(exc),
                           needs="Unexpected generation error; see logs.")

    bundle_path = None
    if write_bundle and any(a.files for a in artifacts):
        bundle_path = _write_bundle(artifacts, ledger.run_id)

    result = CodegenResult(
        run_id=ledger.run_id, generated_at=_now(), artifact_count=len(artifacts),
        artifacts=artifacts, bundle_path=bundle_path, warnings=warnings,
    )
    ledger.finish(artifacts=len(artifacts),
                  passed=sum(1 for a in artifacts if a.validation.passed),
                  bundle=bundle_path)
    return result


def _write_bundle(artifacts: list[ConnectorArtifact], run_id: str) -> str:
    out_dir = PROJECT_ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    zip_path = out_dir / f"connectors_{run_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for a in artifacts:
            # Namespace each artifact by gap id so two gaps targeting the same
            # destination system don't collide in the archive.
            for f in a.files:
                z.writestr(f"{a.gap_id}/{f.path}", f.content)
    return str(zip_path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def to_markdown(result: CodegenResult) -> str:
    lines = [
        "# Generated Integration Code",
        "",
        f"- **Run:** `{result.run_id}`",
        f"- **Generated:** {result.generated_at}",
        f"- **Artifacts:** {result.artifact_count}",
        f"- **Bundle:** `{result.bundle_path or '(none)'}`",
        "",
    ]
    for a in result.artifacts:
        if a.error:
            lines.append(f"## ❌ {a.integration_name} — {a.error}")
            continue
        v = a.validation
        checks = (f"syntax {'✓' if v.syntax_ok else '✗'} · import {'✓' if v.import_ok else '✗'} · "
                  f"yaml {'✓' if v.yaml_ok else '✗'} · "
                  f"tests {'✓' if v.tests_pass else ('—' if v.tests_pass is None else '✗')}")
        lines.append(f"## {a.system_name} — `{a.package_name}` ({a.integration_name})")
        lines.append(f"- **Validation:** {checks}")
        lines.append(f"- **Files:** {', '.join(f.path for f in a.files)}")
        if v.issues:
            lines.append(f"- **Issues:** {'; '.join(v.issues)}")
        lines.append("")
    if result.warnings:
        lines += ["## Warnings", ""] + [f"- {w}" for w in result.warnings]
    return "\n".join(lines)
