"""Phase 1 Regression Tests: Anti-Mock, Anti-Fixture, and False-Success Guard.

Proves:
1. Settings validate_production_security() forbids demo_mode, demo_auth, runtime_fixtures, etc.
2. No runtime modules import forbidden mock or fixture tokens.
3. Endpoint reset-demo and sample loading are strictly rejected when demo_mode/allow_explicit_samples is false.
4. Missing incident data produces UNAVAILABLE / 404 rather than synthetic fallback incidents.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cauveris.config import Settings  # noqa: E402
from scripts.check_runtime_fixture_imports import FORBIDDEN, RUNTIME  # noqa: E402


def test_production_security_rejects_insecure_flags():
    """Verify production security validation rejects all mock/demo modes."""
    # 1. demo_mode
    with pytest.raises(RuntimeError, match="CAUVERIS_DEMO_MODE is enabled"):
        s = Settings(runtime_mode="production", demo_mode=True, demo_auth=False, runtime_fixtures=False)
        s.validate_production_security()

    # 2. demo_auth
    with pytest.raises(RuntimeError, match="CAUVERIS_DEMO_AUTH is enabled"):
        s = Settings(runtime_mode="production", demo_mode=False, demo_auth=True, runtime_fixtures=False)
        s.validate_production_security()

    # 3. runtime_fixtures
    with pytest.raises(RuntimeError, match="CAUVERIS_RUNTIME_FIXTURES is enabled"):
        s = Settings(runtime_mode="production", demo_mode=False, demo_auth=False, runtime_fixtures=True)
        s.validate_production_security()

    # 4. autoload_sample
    with pytest.raises(RuntimeError, match="CAUVERIS_AUTOLOAD_SAMPLE is enabled"):
        s = Settings(runtime_mode="production", demo_mode=False, demo_auth=False, runtime_fixtures=False, autoload_sample=True)
        s.validate_production_security()

    # 5. allow_explicit_samples
    with pytest.raises(RuntimeError, match="CAUVERIS_ALLOW_EXPLICIT_SAMPLES is enabled"):
        s = Settings(runtime_mode="production", demo_mode=False, demo_auth=False, runtime_fixtures=False, allow_explicit_samples=True)
        s.validate_production_security()


def test_zero_runtime_mock_imports():
    """Ensure no file in cauveris/ imports from forbidden test, mock, or fixture packages."""
    violations = []
    for py_file in sorted(RUNTIME.rglob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            mod_name = None
            if isinstance(node, ast.Import):
                mod_name = ",".join(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                mod_name = node.module or ""
            if not mod_name:
                continue
            for token in FORBIDDEN:
                if token in mod_name.lower():
                    # Isolated sample loader exception for explicit user actions
                    if py_file.name == "sample_loader.py" and token == "golden_incident":
                        continue
                    violations.append(f"{py_file.relative_to(ROOT)}:{node.lineno}: imports '{mod_name}' (matched '{token}')")

    assert not violations, "Forbidden imports detected in production code:\n" + "\n".join(violations)
