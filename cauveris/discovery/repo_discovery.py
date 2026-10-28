"""
Dynamic Repository Discovery for Cauveris.
When source is included in an incident bundle:
- detect languages (Python, C/C++, Rust, Go, JS/TS, Java, Shell)
- detect build systems (CMake, Make, Cargo, Maven, Gradle, setuptools, poetry, npm/yarn)
- detect test frameworks (pytest, unittest, ctest, cargo test, junit, jest)
- identify configuration roots
- identify executable entry points
- locate deployment manifests (Kubernetes, Docker Compose, Helm charts)

Safety policy:
Does NOT execute any discovered commands automatically without explicit allowlist clearance.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredRepository:
    root_path: str
    detected_languages: List[str] = field(default_factory=list)
    build_systems: List[str] = field(default_factory=list)
    test_frameworks: List[str] = field(default_factory=list)
    configuration_roots: List[str] = field(default_factory=list)
    executable_entry_points: List[str] = field(default_factory=list)
    deployment_manifests: List[str] = field(default_factory=list)
    is_safe_to_execute: bool = False
    execution_policy_violations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RepositoryDiscovery:
    """Discovers source repository components safely without execution."""

    SAFE_EXECUTABLES = {"pytest", "python -m pytest", "cargo test", "ctest", "make test"}

    def __init__(self, root_dir: Path):
        self.root_dir = Path(root_dir)

    def discover(self) -> DiscoveredRepository:
        repo = DiscoveredRepository(root_path=str(self.root_dir).replace("\\", "/"))
        if not self.root_dir.exists() or not self.root_dir.is_dir():
            return repo

        languages: Set[str] = set()
        build_systems: Set[str] = set()
        test_frameworks: Set[str] = set()
        config_roots: Set[str] = set()
        entry_points: List[str] = []
        deploy_manifests: List[str] = []

        for p in self.root_dir.rglob("*"):
            if not p.is_file():
                continue
            rel = str(p.relative_to(self.root_dir)).replace("\\", "/")
            name_lower = p.name.lower()
            suffix = p.suffix.lower()

            # 1. Languages
            if suffix == ".py":
                languages.add("python")
            elif suffix in (".cpp", ".cc", ".cxx", ".h", ".hpp"):
                languages.add("cpp")
            elif suffix == ".c":
                languages.add("c")
            elif suffix == ".rs":
                languages.add("rust")
            elif suffix == ".go":
                languages.add("go")
            elif suffix in (".js", ".jsx"):
                languages.add("javascript")
            elif suffix in (".ts", ".tsx"):
                languages.add("typescript")
            elif suffix == ".java":
                languages.add("java")
            elif suffix in (".sh", ".bash"):
                languages.add("shell")

            # 2. Build systems
            if name_lower == "cmakelists.txt":
                build_systems.add("cmake")
            elif name_lower in ("makefile", "gnumakefile"):
                build_systems.add("make")
            elif name_lower == "cargo.toml":
                build_systems.add("cargo")
            elif name_lower == "pom.xml":
                build_systems.add("maven")
            elif name_lower in ("build.gradle", "build.gradle.kts"):
                build_systems.add("gradle")
            elif name_lower in ("pyproject.toml", "setup.py", "setup.cfg"):
                build_systems.add("python-build")
            elif name_lower == "package.json":
                build_systems.add("npm/yarn")

            # 3. Test frameworks
            if "test" in rel.lower():
                if suffix == ".py":
                    test_frameworks.add("pytest")
                elif suffix == ".rs":
                    test_frameworks.add("cargo-test")
                elif suffix in (".cpp", ".cc"):
                    test_frameworks.add("gtest/ctest")
                elif suffix == ".java":
                    test_frameworks.add("junit")
                elif suffix in (".js", ".ts"):
                    test_frameworks.add("jest/mocha")

            # 4. Configuration roots
            if any(cfg in rel.lower() for cfg in ("config", "conf", "etc", "settings")):
                config_roots.add(str(p.parent.relative_to(self.root_dir)).replace("\\", "/"))

            # 5. Entry points
            if name_lower in ("main.py", "app.py", "server.py", "main.cpp", "main.rs", "index.js", "index.ts"):
                entry_points.append(rel)

            # 6. Deployment manifests
            if name_lower in ("docker-compose.yaml", "docker-compose.yml", "compose.yaml", "compose.yml"):
                deploy_manifests.append(rel)
            elif suffix in (".yaml", ".yml") and any(d in rel.lower() for d in ("k8s", "deploy", "helm", "chart")):
                deploy_manifests.append(rel)

        # Allowlisted policy check: automatic execution disabled unless explicitly cleared
        violations: List[str] = []
        violations.append("Untrusted uploaded source code execution requires manual verification permit")

        repo.detected_languages = sorted(languages)
        repo.build_systems = sorted(build_systems)
        repo.test_frameworks = sorted(test_frameworks)
        repo.configuration_roots = sorted(config_roots)
        repo.executable_entry_points = sorted(entry_points)
        repo.deployment_manifests = sorted(deploy_manifests)
        repo.is_safe_to_execute = False
        repo.execution_policy_violations = violations

        return repo
