from __future__ import annotations

import sys
from collections.abc import Iterable
from dataclasses import dataclass, fields


@dataclass(frozen=True)
class JobSelection:
    backend: bool = False
    frontend: bool = False
    npm_security: bool = False
    documentation: bool = False
    compose: bool = False
    e2e: bool = False
    a11y: bool = False

    @classmethod
    def full(cls) -> JobSelection:
        return cls(**{field.name: True for field in fields(cls)})

    def merge(self, other: JobSelection) -> JobSelection:
        return JobSelection(
            **{
                field.name: getattr(self, field.name) or getattr(other, field.name)
                for field in fields(self)
            }
        )

    def selected_names(self) -> list[str]:
        return [field.name for field in fields(self) if getattr(self, field.name)]


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
    "README.md",
    "frontend/README.md",
    "frontend/THIRD_PARTY_NOTICES.md",
    "mkdocs.yml",
}
FULL_FILES = {
    ".github/dependabot.yml",
    ".mise.toml",
    ".node-version",
    ".python-version",
    "Taskfile.yml",
    "pyproject.toml",
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
PLAYWRIGHT_FILES = {
    "backend/e2e_server.py",
    "frontend/playwright.config.ts",
}
COMPOSE_FILES = {
    ".env.example",
    "compose.yaml",
    "scripts/validate-compose.sh",
}
EXTERNALLY_CHECKED_FILES = {
    ".dockerignore",
    "Dockerfile",
    "go.mod",
    "scripts/compose-smoke.sh",
    "scripts/container-smoke.sh",
}


def _normalized(path: str) -> str:
    return path.removeprefix("./")


def jobs_for_path(path: str) -> JobSelection:
    normalized = _normalized(path)

    if normalized in PROCESS_FILES or normalized.startswith(PROCESS_PREFIXES):
        return JobSelection()
    if normalized in DOCUMENTATION_FILES or normalized.startswith("docs/"):
        return JobSelection(documentation=True)
    if normalized in FULL_FILES or normalized.startswith(".github/workflows/"):
        return JobSelection.full()

    if normalized == "uv.lock":
        return JobSelection(backend=True, documentation=True, e2e=True, a11y=True)
    if normalized in {"frontend/package.json", "frontend/package-lock.json"}:
        return JobSelection(
            frontend=True,
            npm_security=True,
            documentation=True,
            e2e=True,
            a11y=True,
        )

    if normalized in PLAYWRIGHT_FILES or normalized.startswith("frontend/e2e/"):
        return JobSelection(e2e=True, a11y=True)
    if normalized.startswith("backend/tests/") or normalized.startswith("prototypes/"):
        return JobSelection(backend=True)
    if normalized.startswith("backend/"):
        return JobSelection(backend=True, documentation=True, e2e=True, a11y=True)
    if normalized.startswith(("db/", "fixtures/")):
        return JobSelection(backend=True, documentation=True, e2e=True, a11y=True)
    if normalized == "scripts/generate_synthetic_fixtures.py":
        return JobSelection(backend=True, documentation=True, e2e=True, a11y=True)

    if normalized.startswith("frontend/src/") and normalized.endswith(".spec.ts"):
        return JobSelection(frontend=True)
    if normalized in FRONTEND_ONLY_FILES:
        return JobSelection(frontend=True)
    if normalized in FRONTEND_PRODUCT_FILES or normalized.startswith(
        ("frontend/src/", "frontend/public/")
    ):
        return JobSelection(frontend=True, documentation=True, e2e=True, a11y=True)
    if normalized.startswith("frontend/"):
        return JobSelection.full()

    if normalized in COMPOSE_FILES:
        return JobSelection(compose=True)
    if normalized in EXTERNALLY_CHECKED_FILES or normalized.startswith("cmd/"):
        return JobSelection()

    return JobSelection.full()


def classify_paths(paths: Iterable[str]) -> JobSelection:
    changed_paths = [path for path in paths if path]
    if not changed_paths:
        return JobSelection.full()

    selection = JobSelection()
    for path in changed_paths:
        selection = selection.merge(jobs_for_path(path))
    return selection


def paths_from_stdin() -> list[str]:
    payload = sys.stdin.buffer.read()
    entries = payload.split(b"\0") if b"\0" in payload else payload.splitlines()
    return [entry.decode("utf-8", errors="surrogateescape") for entry in entries if entry]


def main() -> int:
    selection = classify_paths(paths_from_stdin())
    for field in fields(selection):
        print(f"{field.name}={'true' if getattr(selection, field.name) else 'false'}")
    selected = selection.selected_names()
    print("classification=" + (",".join(selected) if selected else "classification-and-gate-only"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
