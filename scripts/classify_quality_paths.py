from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from dataclasses import dataclass, fields


@dataclass(frozen=True)
class QualitySelection:
    """Selected stable domains and their internal quality details."""

    backend: bool = False
    frontend: bool = False
    operator_cli: bool = False
    oci: bool = False
    documentation: bool = False
    security: bool = False
    overall: bool = False
    npm_security: bool = False
    codeql: bool = False
    image: bool = False
    container: bool = False
    compose: bool = False
    operator_container: bool = False
    e2e: bool = False
    a11y: bool = False

    @classmethod
    def full(cls) -> QualitySelection:
        return cls(**{field.name: True for field in fields(cls)})

    def merge(self, other: QualitySelection) -> QualitySelection:
        return QualitySelection(
            **{
                field.name: getattr(self, field.name) or getattr(other, field.name)
                for field in fields(self)
            }
        )

    def selected_domains(self) -> list[str]:
        return [
            name
            for name in (
                "backend",
                "frontend",
                "operator_cli",
                "oci",
                "documentation",
                "security",
                "overall",
            )
            if getattr(self, name)
        ]


PROCESS_FILES = {
    ".github/copilot-instructions.md",
    ".github/pull_request_template.md",
    "AGENTS.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "SECURITY.md",
    "SUPPORT.md",
    "THIRD_PARTY_NOTICES.md",
}
PROCESS_PREFIXES = (
    ".github/ISSUE_TEMPLATE/",
    ".vscode/",
)
DOCUMENTATION_FILES = {
    "CHANGELOG.md",
    "README.md",
    "frontend/README.md",
    "frontend/THIRD_PARTY_NOTICES.md",
    "mkdocs.yml",
}
DOCUMENTATION_TOOL_FILES = {
    "scripts/check_wiki.py",
    "scripts/test_wiki.py",
}
FULL_FILES = {
    ".github/dependabot.yml",
    ".mise.toml",
    ".node-version",
    ".python-version",
    "Taskfile.yml",
    "backend/build_metadata.py",
    "pyproject.toml",
    "scripts/build-frontend.sh",
    "scripts/build_metadata.py",
    "scripts/classify_quality_paths.py",
    "scripts/release.py",
    "scripts/release_gate.py",
}
FRONTEND_ONLY_FILES = {
    "frontend/.editorconfig",
    "frontend/.gitignore",
    "frontend/.prettierignore",
    "frontend/eslint.config.js",
    "frontend/tsconfig.spec.json",
    "frontend/vitest.config.ts",
}
FRONTEND_PRODUCT_FILES = {
    "frontend/angular.json",
    "frontend/proxy.conf.json",
    "frontend/tsconfig.app.json",
    "frontend/tsconfig.json",
}
OVERALL_BROWSER_FILES = {
    "backend/e2e_server.py",
    "frontend/playwright.config.ts",
}
OVERALL_COMPOSE_FILES = {
    ".env.example",
    "compose.yaml",
    "scripts/compose-smoke.sh",
    "scripts/validate-compose.sh",
}
OCI_FILES = {
    ".dockerignore",
    "Dockerfile",
    "scripts/container-smoke.sh",
}
OPERATOR_PROTOCOL_FILES = {
    "backend/admin.py",
    "backend/admin_service.py",
}
SECURITY_FILES = {
    "scripts/enforce_sarif_security.py",
}


def _normalized(path: str) -> str:
    return path.removeprefix("./")


def _web_product_selection(*, backend: bool = False, frontend: bool = False) -> QualitySelection:
    return QualitySelection(
        backend=backend,
        frontend=frontend,
        oci=True,
        documentation=True,
        security=True,
        overall=True,
        codeql=True,
        image=True,
        container=True,
        e2e=True,
        a11y=True,
    )


def selection_for_path(path: str) -> QualitySelection:
    normalized = _normalized(path)

    if normalized in PROCESS_FILES or normalized.startswith(PROCESS_PREFIXES):
        return QualitySelection()
    if (
        normalized in DOCUMENTATION_FILES
        or normalized in DOCUMENTATION_TOOL_FILES
        or normalized.startswith("docs/")
    ):
        return QualitySelection(documentation=True)
    if normalized in FULL_FILES or normalized.startswith(".github/workflows/"):
        return QualitySelection.full()

    if normalized == "uv.lock":
        return QualitySelection(
            backend=True,
            oci=True,
            documentation=True,
            security=True,
            overall=True,
            image=True,
            container=True,
            e2e=True,
            a11y=True,
        )
    if normalized in {"frontend/package.json", "frontend/package-lock.json"}:
        return QualitySelection(
            frontend=True,
            oci=True,
            documentation=True,
            security=True,
            overall=True,
            npm_security=True,
            image=True,
            container=True,
            e2e=True,
            a11y=True,
        )

    if normalized in OVERALL_BROWSER_FILES or normalized.startswith("frontend/e2e/"):
        return QualitySelection(overall=True, e2e=True, a11y=True)
    if normalized in OVERALL_COMPOSE_FILES:
        return QualitySelection(
            overall=True,
            image=True,
            compose=True,
            operator_container=True,
        )
    if normalized in OCI_FILES:
        return QualitySelection(
            oci=True,
            overall=True,
            image=True,
            container=True,
            operator_container=True,
        )

    if normalized.startswith("backend/tests/") or normalized.startswith("prototypes/"):
        return QualitySelection(backend=True)
    if normalized.startswith("backend/"):
        selection = _web_product_selection(backend=True)
        if normalized in OPERATOR_PROTOCOL_FILES:
            selection = selection.merge(
                QualitySelection(operator_cli=True, operator_container=True)
            )
        return selection
    if normalized.startswith(("db/", "fixtures/")):
        return _web_product_selection(backend=True)

    if normalized.startswith("frontend/src/") and normalized.endswith(".spec.ts"):
        return QualitySelection(frontend=True)
    if normalized in FRONTEND_ONLY_FILES:
        return QualitySelection(frontend=True)
    if normalized in FRONTEND_PRODUCT_FILES or normalized.startswith(
        ("frontend/src/", "frontend/public/")
    ):
        return _web_product_selection(frontend=True)
    if normalized.startswith("frontend/"):
        return QualitySelection.full()

    if normalized == "go.mod" or normalized.startswith("cmd/lzug-admin/"):
        return QualitySelection(operator_cli=True)
    if normalized in SECURITY_FILES:
        return QualitySelection(security=True, codeql=True)

    return QualitySelection.full()


def classify_paths(paths: Iterable[str]) -> QualitySelection:
    changed_paths = [path for path in paths if path]
    if not changed_paths:
        return QualitySelection.full()

    selection = QualitySelection()
    for path in changed_paths:
        selection = selection.merge(selection_for_path(path))
    return selection


def paths_from_stdin() -> list[str]:
    payload = sys.stdin.buffer.read()
    entries = payload.split(b"\0") if b"\0" in payload else payload.splitlines()
    return [entry.decode("utf-8", errors="surrogateescape") for entry in entries if entry]


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify lzug quality domains")
    parser.add_argument(
        "--full-reason",
        help="select every domain and detail for a push, schedule, or manual run",
    )
    args = parser.parse_args()

    selection = QualitySelection.full() if args.full_reason else classify_paths(paths_from_stdin())
    for field in fields(selection):
        print(f"{field.name}={'true' if getattr(selection, field.name) else 'false'}")
    selected = selection.selected_domains()
    classification = args.full_reason or (",".join(selected) if selected else "process-only")
    print(f"classification={classification}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
