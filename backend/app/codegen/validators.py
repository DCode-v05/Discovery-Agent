"""Validate generated artifacts before offering them for download.

Checks (in order): Python syntax (`ast.parse`), import smoke-test (the connector
imports cleanly), YAML validity (the agent definition parses), and — best effort —
runs the generated pytest suite to prove the code actually works.
"""
from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import yaml

from ..schemas.artifacts import GeneratedFile, ValidationResult


def _check_syntax(code: str, label: str) -> str | None:
    try:
        ast.parse(code)
        return None
    except SyntaxError as exc:
        return f"{label}: syntax error line {exc.lineno}: {exc.msg}"


def _import_smoke(code: str) -> str | None:
    """Write the connector to a temp file and import it in-process."""
    tmp = Path(tempfile.gettempdir()) / f"conn_{uuid.uuid4().hex[:8]}.py"
    tmp.write_text(code, encoding="utf-8")
    mod_name = f"_genconn_{uuid.uuid4().hex[:8]}"
    try:
        spec = importlib.util.spec_from_file_location(mod_name, tmp)
        if spec is None or spec.loader is None:
            return "import: could not create module spec"
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        return None
    except Exception as exc:  # noqa: BLE001 - any import failure is a finding
        return f"import: {type(exc).__name__}: {exc}"
    finally:
        sys.modules.pop(mod_name, None)
        tmp.unlink(missing_ok=True)


def _check_yaml(text: str) -> str | None:
    try:
        yaml.safe_load(text)
        return None
    except yaml.YAMLError as exc:
        return f"agent.yaml: invalid YAML: {exc}"


def _run_pytest(files: list[GeneratedFile], package_name: str) -> tuple[bool | None, str | None]:
    """Materialize the bundle in a temp dir and run its pytest suite."""
    with tempfile.TemporaryDirectory(prefix="codegen_") as tmp:
        root = Path(tmp)
        for f in files:
            dest = root / f.path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(f.content, encoding="utf-8")
        pkg_dir = root / package_name
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "test_connector.py"],
                cwd=str(pkg_dir), capture_output=True, text=True, timeout=90,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return None, f"pytest could not run: {exc}"
        if proc.returncode == 0:
            return True, None
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-8:]
        return False, "pytest failed:\n" + "\n".join(tail)


def validate_artifact(files: list[GeneratedFile], package_name: str,
                      run_tests: bool = True) -> ValidationResult:
    connector = next((f for f in files if f.path.endswith("connector.py")
                      and "test" not in f.path), None)
    test = next((f for f in files if f.path.endswith("test_connector.py")), None)
    agent = next((f for f in files if f.path.endswith("agent.yaml")), None)

    issues: list[str] = []
    syntax_ok = True
    for f in (connector, test):
        if f is None:
            issues.append("missing expected python file")
            syntax_ok = False
            continue
        err = _check_syntax(f.content, f.path)
        if err:
            issues.append(err)
            syntax_ok = False

    import_ok = False
    if connector is not None:
        err = _import_smoke(connector.content)
        import_ok = err is None
        if err:
            issues.append(err)

    yaml_ok = False
    if agent is not None:
        err = _check_yaml(agent.content)
        yaml_ok = err is None
        if err:
            issues.append(err)

    tests_pass: bool | None = None
    if run_tests and syntax_ok and import_ok:
        tests_pass, err = _run_pytest(files, package_name)
        if err:
            issues.append(err)

    return ValidationResult(syntax_ok=syntax_ok, import_ok=import_ok, yaml_ok=yaml_ok,
                            tests_pass=tests_pass, issues=issues)
