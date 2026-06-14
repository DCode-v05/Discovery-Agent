"""Discovery Agent CLI — scriptable mirror of the API.

Run from the project root:
    python -m backend.cli discover data/kb --out out/inventory.json
    python -m backend.cli gaps --inventory out/inventory.json --use-cases data/use_cases.json
    python -m backend.cli codegen --gaps out/gaps.json --out out/
"""
from __future__ import annotations

import sys
from pathlib import Path

import typer

# Windows consoles default to cp1252 when stdout is piped; force UTF-8 so rich
# tables (✓, ⚠, box-drawing glyphs) never crash on non-ASCII output.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
from rich.console import Console
from rich.table import Table

from .app.discovery.service import run_discovery, to_markdown
from .app.gapanalysis.service import (
    load_inventory,
    load_use_cases,
    run_gap_analysis,
)
from .app.gapanalysis.service import to_markdown as gaps_to_markdown
from .app.codegen.service import generate_code, load_gaps
from .app.codegen.service import to_markdown as codegen_to_markdown
from .app.llm.errors import LLMError

app = typer.Typer(add_completion=False, help="Discovery Agent — systems discovery, gap analysis, code generation.")
console = Console()


@app.callback()
def _main() -> None:
    """Discovery Agent. Use a subcommand: discover | gaps | codegen."""


def _fail(exc: LLMError) -> None:
    console.print(f"[bold red]Failed:[/bold red] {exc.message}")
    if exc.needs:
        console.print(f"[yellow]What you need to do:[/yellow] {exc.needs}")
    raise typer.Exit(code=1)


@app.command()
def discover(
    source: str = typer.Argument(..., help="A document, or a directory of documents."),
    out: str = typer.Option("out/inventory.json", help="Where to write the inventory JSON."),
    md: str = typer.Option("out/inventory.md", help="Where to write the Markdown report."),
) -> None:
    """Level 1 — discover the systems described in a document collection."""
    try:
        inv = run_discovery(source)
    except LLMError as exc:
        _fail(exc)

    out_path, md_path = Path(out), Path(md)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(inv.model_dump_json(indent=2), encoding="utf-8")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(to_markdown(inv), encoding="utf-8")

    table = Table(title=f"Discovered systems  (run {inv.run_id})")
    for col in ("System", "Category", "Conf", "Tier", "Auth", "Review"):
        table.add_column(col)
    for s in inv.systems:
        table.add_row(
            s.name, s.category, f"{s.confidence:.0%}", s.confidence_tier.value,
            s.auth_method, "⚠" if s.needs_review else "",
        )
    console.print(table)
    console.print(
        f"[green]{inv.systems_count} systems[/green] from {inv.document_count} documents · "
        f"{sum(1 for s in inv.systems if s.needs_review)} flagged for review · "
        f"{len(inv.skipped_documents)} skipped")
    if inv.skipped_documents:
        for sk in inv.skipped_documents:
            console.print(f"  [yellow]skipped[/yellow] {sk.document}: {sk.reason}")
    console.print(f"Wrote [cyan]{out_path}[/cyan] and [cyan]{md_path}[/cyan]")


@app.command()
def gaps(
    inventory: str = typer.Option("out/inventory.json", help="Inventory JSON from `discover`."),
    use_cases: str = typer.Option("data/use_cases.json", help="Automation use-cases JSON."),
    out: str = typer.Option("out/gaps.json", help="Where to write the gap report JSON."),
    md: str = typer.Option("out/gaps.md", help="Where to write the Markdown report."),
) -> None:
    """Level 2 — map use cases to systems and prioritize integration gaps."""
    inv = load_inventory(inventory)
    ucs = load_use_cases(use_cases)
    try:
        report = run_gap_analysis(inv, ucs)
    except LLMError as exc:
        _fail(exc)

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(report.model_dump_json(indent=2), encoding="utf-8")
    Path(md).parent.mkdir(parents=True, exist_ok=True)
    Path(md).write_text(gaps_to_markdown(report), encoding="utf-8")

    table = Table(title=f"Integration gaps  (run {report.run_id})")
    for col in ("Priority", "Integration", "Status", "Effort", "Impact", "Blocks"):
        table.add_column(col)
    for g in report.gaps:
        table.add_row(g.priority.value, g.integration_name, g.status.value,
                      f"{g.effort_level.value} ~{g.effort_days}d",
                      str(g.business_impact_score), str(len(g.blocks_use_cases)))
    console.print(table)
    console.print(f"[green]{report.summary}[/green]")
    for s in report.dependency_statements:
        console.print(f"  [cyan]dep[/cyan] {s}")
    console.print(f"Wrote [cyan]{out}[/cyan] and [cyan]{md}[/cyan]")


@app.command()
def codegen(
    gaps: str = typer.Option("out/gaps.json", help="Gap report JSON from `gaps`."),
    out: str = typer.Option("out", help="Directory for the bundle + report."),
    top_n: int = typer.Option(3, help="How many top missing integrations to generate."),
    run_tests: bool = typer.Option(True, help="Run the generated pytest suites as a check."),
) -> None:
    """Level 3 — generate connector + agent-definition code for the top gaps."""
    gap_list = load_gaps(gaps)
    try:
        result = generate_code(gap_list, top_n=top_n, run_tests=run_tests)
    except LLMError as exc:
        _fail(exc)

    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "codegen.md").write_text(codegen_to_markdown(result), encoding="utf-8")

    table = Table(title=f"Generated connectors  (run {result.run_id})")
    for col in ("Integration", "Package", "Syntax", "Import", "YAML", "Tests"):
        table.add_column(col)
    for a in result.artifacts:
        if a.error:
            table.add_row(a.integration_name, "—", "—", "—", "—", f"[red]{a.error[:30]}[/red]")
            continue
        v = a.validation
        mark = lambda b: "✓" if b else ("—" if b is None else "✗")  # noqa: E731
        table.add_row(a.integration_name, a.package_name, mark(v.syntax_ok),
                      mark(v.import_ok), mark(v.yaml_ok), mark(v.tests_pass))
    console.print(table)
    if result.bundle_path:
        console.print(f"[green]Bundle:[/green] [cyan]{result.bundle_path}[/cyan]")
    for w in result.warnings:
        console.print(f"  [yellow]warn[/yellow] {w}")


if __name__ == "__main__":
    app()
