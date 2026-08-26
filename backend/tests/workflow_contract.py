from __future__ import annotations

import re
from pathlib import Path


def workflow_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def mapping_block(document: str, key: str, *, indent: int = 0) -> str:
    """Return one YAML mapping entry without depending on sibling order."""

    lines = document.splitlines(keepends=True)
    marker = re.compile(rf"^{' ' * indent}{re.escape(key)}:\s*(?:#.*)?$")
    for start, line in enumerate(lines):
        if not marker.match(line.rstrip("\n")):
            continue
        end = start + 1
        while end < len(lines):
            candidate = lines[end]
            stripped = candidate.lstrip(" ")
            if stripped.strip() and not stripped.startswith("#"):
                candidate_indent = len(candidate) - len(stripped)
                if candidate_indent <= indent:
                    break
            end += 1
        return "".join(lines[start:end])
    raise AssertionError(f"missing YAML mapping key {key!r} at indentation {indent}")


def job_block(workflow: str, job_id: str) -> str:
    return mapping_block(mapping_block(workflow, "jobs"), job_id, indent=2)


def trigger_block(workflow: str) -> str:
    return mapping_block(workflow, "on")


def action_references(workflow: str) -> list[str]:
    return re.findall(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", workflow, re.MULTILINE)


def action_blocks(workflow: str, action: str) -> list[str]:
    """Return sequence items using an action, independent of their step names."""

    lines = workflow.splitlines(keepends=True)
    blocks: list[str] = []
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)-\s+(?:uses:\s*)?", line)
        if not match:
            continue
        indent = len(match.group(1))
        end = index + 1
        while end < len(lines):
            candidate = lines[end]
            stripped = candidate.lstrip(" ")
            if stripped.strip() and not stripped.startswith("#"):
                candidate_indent = len(candidate) - len(stripped)
                if candidate_indent < indent or (
                    candidate_indent == indent and stripped.startswith("-")
                ):
                    break
            end += 1
        block = "".join(lines[index:end])
        if re.search(rf"^\s*(?:-\s*)?uses:\s*{re.escape(action)}@", block, re.MULTILINE):
            blocks.append(block)
    return blocks
