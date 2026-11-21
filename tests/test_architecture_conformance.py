"""Dependency rules. A package may not import a package it is not allowed to reach."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from architecture import COMPONENTS, CONTROL_PATHS, FORBIDDEN_IMPORTS, READ_ONLY_SERVICES

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
PACKAGES = set(FORBIDDEN_IMPORTS)


def _module_name(path: Path) -> str:
    relative = path.relative_to(BACKEND).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


class ConformanceTests(unittest.TestCase):
    def test_every_component_is_a_package_module_or_service(self) -> None:
        for component, kind, location in COMPONENTS:
            self.assertIn(kind, {"package", "module", "service"}, component)
            for name in location.split(", "):
                path = (REPO / name) if name.startswith("SCADAPROJECT/") else (BACKEND / name)
                if kind == "package" and path.suffix == "":
                    self.assertTrue(path.is_dir(), f"{component} missing package {path}")
                else:
                    self.assertTrue(path.is_file(), f"{component} missing {path}")

    def test_packages_do_not_import_forbidden_packages(self) -> None:
        violations: list[str] = []
        for package in PACKAGES:
            banned = FORBIDDEN_IMPORTS[package]
            for path in (BACKEND / package).rglob("*.py"):
                module = _module_name(path)
                if not module.startswith(package):
                    continue
                for imported in _imports(path):
                    root = imported.split(".")[0]
                    if root in banned:
                        violations.append(f"{path.name} imports {imported}")
        self.assertEqual(violations, [])

    def test_read_only_services_have_no_control_path(self) -> None:
        for name in READ_ONLY_SERVICES:
            path = REPO / name if name.startswith("SCADAPROJECT/") else BACKEND / name
            text = path.read_text(encoding="utf-8")
            for control in CONTROL_PATHS:
                self.assertNotIn(control, text, f"{name} references {control}")


if __name__ == "__main__":
    unittest.main()
