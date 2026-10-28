"""CI guard: production code must not quietly import test/sample results."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "cauveris"
FORBIDDEN = ("mocks", "fixtures", "__tests__", "golden_incident", "sample_results")
EXPLICIT_SAMPLE_LOADER = RUNTIME / "api" / "sample_loader.py"


def main() -> int:
    violations: list[str] = []
    for path in sorted(RUNTIME.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            violations.append(f"{path}: syntax error: {exc}")
            continue
        for node in ast.walk(tree):
            module = None
            if isinstance(node, ast.Import):
                module = ",".join(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
            if not module or not any(token in module.lower() for token in FORBIDDEN):
                continue
            if path == EXPLICIT_SAMPLE_LOADER and "golden_incident" in module.lower():
                continue
            violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: {module}")
    if violations:
        print("Runtime fixture/sample imports are forbidden:", file=sys.stderr)
        print("\n".join(violations), file=sys.stderr)
        return 1
    print("Runtime fixture import guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
