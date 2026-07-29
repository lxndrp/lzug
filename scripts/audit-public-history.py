#!/usr/bin/env python3
"""Create a sanitized audit summary for every object reachable from Git refs.

The script deliberately never writes matched values, names, email addresses,
domains, or repository paths to its report. Sensitive comparison values must
be supplied through a separate protected file with one value per line.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])"
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
)
PHONE_PATTERN = re.compile(
    r"(?<![\w.])(?:\+49|0049|0)[\s/-]*(?:\(?\d{2,5}\)?[\s/-]*)" r"(?:\d[\s/-]*){5,12}(?![\w.])"
)
POSTAL_ADDRESS_PATTERN = re.compile(
    r"\b[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]*(?:straße|strasse|str\.|weg|platz|allee|gasse)"
    r"\s+\d{1,4}[A-Za-z]?\b",
    re.IGNORECASE,
)
ORGANIZATION_PATTERN = re.compile(
    r"\b(?:[A-ZÄÖÜ][\wÄÖÜäöüß&.-]*\s+){1,6}" r"(?:GmbH|AG|KG|OHG|UG|e\.?\s*V\.?)\b"
)
PATTERNS = {
    "email_address": EMAIL_PATTERN,
    "phone_number": PHONE_PATTERN,
    "postal_address": POSTAL_ADDRESS_PATTERN,
    "organization_legal_name": ORGANIZATION_PATTERN,
}
ALLOWED_EXTENSIONS = {
    "",
    ".cjs",
    ".css",
    ".html",
    ".ico",
    ".ini",
    ".js",
    ".json",
    ".lock",
    ".md",
    ".mjs",
    ".py",
    ".scss",
    ".sh",
    ".sql",
    ".svg",
    ".toml",
    ".ts",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
RESERVED_DOMAIN_SUFFIXES = (
    ".example",
    ".example.com",
    ".invalid",
    ".localhost",
    ".test",
)
PUBLIC_EMAIL_PROVIDERS = {
    "gmail.com",
    "googlemail.com",
    "icloud.com",
    "outlook.com",
    "proton.me",
    "protonmail.com",
    "web.de",
    "yahoo.com",
}


def git(git_dir: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    """Run Git against the audit mirror and return stdout."""
    result = subprocess.run(
        ["git", f"--git-dir={git_dir}", *args],
        check=True,
        input=input_bytes,
        capture_output=True,
    )
    return result.stdout


def component(path: str) -> str:
    """Return a stable, non-sensitive top-level location."""
    if not path:
        return "<root>"
    first = path.split("/", 1)[0]
    known_components = {"backend", "db", "docs", "frontend", "prototypes", "scripts"}
    return first if first in known_components else "<other>"


def extension(path: str) -> str:
    """Return only the normalized file extension."""
    suffix = Path(path).suffix.lower()
    return suffix if suffix else "<none>"


def domain_class(domain: str) -> str:
    """Classify an email domain without preserving the domain itself."""
    normalized = domain.lower().rstrip(".")
    if normalized == "users.noreply.github.com":
        return "code_hosting_noreply"
    if normalized == "example.com" or normalized.endswith(RESERVED_DOMAIN_SUFFIXES):
        return "reserved_or_non_routable"
    if normalized in PUBLIC_EMAIL_PROVIDERS:
        return "public_email_provider"
    return "custom_or_organization"


def identity_class(name: str) -> str:
    """Classify a commit identity without preserving its name."""
    normalized = name.casefold()
    if "[bot]" in normalized or "copilot" in normalized or "dependabot" in normalized:
        return "automation"
    return "human_or_unclassified"


def text_content(data: bytes) -> str | None:
    """Decode probable text blobs and reject binary content."""
    if b"\0" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def binary_strings(data: bytes) -> str:
    """Recover printable strings from binary content for PII matching."""
    decoded = data.decode("utf-8", "ignore")
    printable = "".join(
        character if character.isprintable() or character in "\n\t" else "\n"
        for character in decoded
    )
    return "\n".join(line for line in printable.splitlines() if len(line.strip()) >= 4)


def parse_objects(git_dir: Path) -> tuple[dict[str, set[str]], dict[str, tuple[str, int]]]:
    """Return object paths plus type and size metadata."""
    lines = git(git_dir, "rev-list", "--objects", "--all").decode("utf-8", "surrogateescape")
    paths_by_oid: dict[str, set[str]] = collections.defaultdict(set)
    for line in lines.splitlines():
        oid, separator, path = line.partition(" ")
        if separator:
            paths_by_oid[oid].add(path)
        else:
            paths_by_oid.setdefault(oid, set())

    ordered_oids = sorted(paths_by_oid)
    query = ("\n".join(ordered_oids) + "\n").encode()
    metadata_output = git(
        git_dir,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_bytes=query,
    ).decode()
    metadata: dict[str, tuple[str, int]] = {}
    for line in metadata_output.splitlines():
        oid, object_type, object_size = line.split()
        metadata[oid] = (object_type, int(object_size))
    return paths_by_oid, metadata


class FindingCounter:
    """Aggregate findings without retaining matched data or full paths."""

    def __init__(self) -> None:
        self.occurrences: collections.Counter[str] = collections.Counter()
        self.blobs: dict[str, set[str]] = collections.defaultdict(set)
        self.components: dict[str, collections.Counter[str]] = collections.defaultdict(
            collections.Counter
        )
        self.known_value_ids: set[int] = set()

    def add(self, category: str, oid: str, paths: Iterable[str], count: int = 1) -> None:
        self.occurrences[category] += count
        self.blobs[category].add(oid)
        locations = {component(path) for path in paths} or {"<unknown>"}
        for location in locations:
            self.components[category][location] += 1

    def report(self) -> dict[str, object]:
        categories = sorted(self.occurrences)
        return {
            category: {
                "occurrences": self.occurrences[category],
                "unique_blobs": len(self.blobs[category]),
                "components": dict(sorted(self.components[category].items())),
            }
            for category in categories
        }


def scan_text(
    text: str,
    oid: str,
    paths: Iterable[str],
    known_values: list[str],
    findings: FindingCounter,
) -> collections.Counter[str]:
    """Scan text while returning only email-domain classifications."""
    domain_classes: collections.Counter[str] = collections.Counter()
    for category, pattern in PATTERNS.items():
        matches = list(pattern.finditer(text))
        if matches:
            findings.add(category, oid, paths, len(matches))
        if category == "email_address":
            for match in matches:
                domain_classes[domain_class(match.group(0).rsplit("@", 1)[1])] += 1

    folded = text.casefold()
    for index, value in enumerate(known_values):
        count = folded.count(value.casefold())
        if count:
            findings.known_value_ids.add(index)
            findings.add("known_readiness_value", oid, paths, count)
    return domain_classes


def scan_diff(
    git_dir: Path, known_values: list[str]
) -> tuple[int, dict[str, int], collections.Counter[str]]:
    """Scan changed lines from every diff without retaining their contents."""
    output = git(
        git_dir,
        "log",
        "--all",
        "--full-history",
        "--no-renames",
        "--format=",
        "--patch",
        "--no-color",
    ).decode("utf-8", "replace")
    changed_lines = 0
    occurrences: collections.Counter[str] = collections.Counter()
    matched_known_ids: set[int] = set()
    for line in output.splitlines():
        if not line.startswith(("+", "-")) or line.startswith(("+++", "---")):
            continue
        changed_lines += 1
        content = line[1:]
        for category, pattern in PATTERNS.items():
            occurrences[category] += len(list(pattern.finditer(content)))
        folded = content.casefold()
        for index, value in enumerate(known_values):
            count = folded.count(value.casefold())
            if count:
                matched_known_ids.add(index)
                occurrences["known_readiness_value"] += count
    return (
        changed_lines,
        dict(sorted(occurrences.items())),
        collections.Counter({"distinct_known_values": len(matched_known_ids)}),
    )


def deleted_file_summary(git_dir: Path) -> dict[str, object]:
    """Aggregate deleted historical paths by top-level component."""
    output = git(
        git_dir,
        "log",
        "--all",
        "--full-history",
        "--diff-filter=D",
        "--name-only",
        "--format=",
    ).decode("utf-8", "surrogateescape")
    paths = {line for line in output.splitlines() if line}
    locations = collections.Counter(component(path) for path in paths)
    return {"unique_paths": len(paths), "components": dict(sorted(locations.items()))}


def commit_identity_summary(git_dir: Path) -> dict[str, object]:
    """Aggregate author and committer identity categories."""
    output = git(
        git_dir,
        "log",
        "--all",
        "--format=%aN%x00%aE%x00%cN%x00%cE",
    ).decode("utf-8", "replace")
    author_pairs: set[tuple[str, str]] = set()
    committer_pairs: set[tuple[str, str]] = set()
    names: set[str] = set()
    emails: set[str] = set()
    domains: set[str] = set()
    name_classes: collections.Counter[str] = collections.Counter()
    domain_classes: collections.Counter[str] = collections.Counter()
    for line in output.splitlines():
        parts = line.split("\0")
        if len(parts) != 4:
            continue
        author_name, author_email, committer_name, committer_email = parts
        author_pairs.add((author_name, author_email))
        committer_pairs.add((committer_name, committer_email))
        names.update((author_name, committer_name))
        emails.update((author_email, committer_email))
    for name in names:
        name_classes[identity_class(name)] += 1
    for email in emails:
        domain = email.rsplit("@", 1)[1] if "@" in email else ""
        domains.add(domain)
    for domain in domains:
        domain_classes[domain_class(domain)] += 1
    return {
        "unique_author_pairs": len(author_pairs),
        "unique_committer_pairs": len(committer_pairs),
        "unique_names": len(names),
        "unique_emails": len(emails),
        "unique_email_domains": len(domains),
        "name_classes": dict(sorted(name_classes.items())),
        "email_domain_classes": dict(sorted(domain_classes.items())),
    }


def ref_summary(git_dir: Path) -> dict[str, object]:
    """Count the explicitly audited ref classes."""
    output = git(git_dir, "for-each-ref", "--format=%(refname)").decode()
    refs = [line for line in output.splitlines() if line]
    counts = collections.Counter(
        {"heads": 0, "tags": 0, "pull_heads": 0, "pull_merges": 0, "pull_other": 0, "other": 0}
    )
    for ref in refs:
        counts[ref_class(ref)] += 1
    return {"counts": dict(sorted(counts.items())), "total": len(refs)}


def ref_class(ref: str) -> str:
    """Classify a ref without preserving its full name."""
    if ref.startswith("refs/heads/"):
        return "heads"
    if ref.startswith("refs/tags/"):
        return "tags"
    if re.fullmatch(r"refs/pull/\d+/head", ref):
        return "pull_heads"
    if re.fullmatch(r"refs/pull/\d+/merge", ref):
        return "pull_merges"
    if ref.startswith("refs/pull/"):
        return "pull_other"
    return "other"


def affected_ref_summary(
    git_dir: Path, findings: FindingCounter, unexpected_binary_oids: set[str]
) -> dict[str, object]:
    """Count refs that can reach each sanitized finding category."""
    targets = {category: set(oids) for category, oids in findings.blobs.items()}
    targets["unexpected_binary"] = unexpected_binary_oids
    counts: dict[str, collections.Counter[str]] = {
        category: collections.Counter() for category in targets
    }
    refs = git(git_dir, "for-each-ref", "--format=%(refname)").decode().splitlines()
    for ref in refs:
        reachable_output = git(git_dir, "rev-list", "--objects", ref).decode(
            "utf-8", "surrogateescape"
        )
        reachable = {line.partition(" ")[0] for line in reachable_output.splitlines()}
        category = ref_class(ref)
        for finding_category, oids in targets.items():
            if reachable.intersection(oids):
                counts[finding_category][category] += 1
    return {
        category: dict(sorted(class_counts.items()))
        for category, class_counts in sorted(counts.items())
    }


def load_known_values(path: Path | None) -> list[str]:
    """Read protected comparison values without exposing them."""
    if path is None:
        return []
    values = {line.strip() for line in path.read_text().splitlines() if len(line.strip()) >= 4}
    return sorted(values, key=str.casefold)


def audit(git_dir: Path, known_values_path: Path | None) -> dict[str, object]:
    """Run the complete sanitized audit."""
    git(git_dir, "fsck", "--full", "--strict", "--no-dangling")
    known_values = load_known_values(known_values_path)
    paths_by_oid, metadata = parse_objects(git_dir)

    findings = FindingCounter()
    binary_findings = FindingCounter()
    content_domain_classes: collections.Counter[str] = collections.Counter()
    binary_extensions: collections.Counter[str] = collections.Counter()
    unexpected_extensions: collections.Counter[str] = collections.Counter()
    unexpected_binary_oids: set[str] = set()
    object_types: collections.Counter[str] = collections.Counter()
    object_bytes: collections.Counter[str] = collections.Counter()
    large_blobs = {"at_least_100_kib": 0, "at_least_1_mib": 0}
    text_blobs = 0
    binary_blobs = 0

    for oid, (object_type, size) in metadata.items():
        object_types[object_type] += 1
        object_bytes[object_type] += size
        if object_type != "blob":
            continue
        paths = paths_by_oid[oid]
        if size >= 100 * 1024:
            large_blobs["at_least_100_kib"] += 1
        if size >= 1024 * 1024:
            large_blobs["at_least_1_mib"] += 1
        for path in paths:
            suffix = extension(path)
            if suffix not in ALLOWED_EXTENSIONS and suffix != "<none>":
                unexpected_extensions[suffix] += 1

        data = git(git_dir, "cat-file", "blob", oid)
        text = text_content(data)
        if text is None:
            binary_blobs += 1
            suffixes = {extension(path) for path in paths} or {"<none>"}
            for suffix in suffixes:
                binary_extensions[suffix] += 1
                if suffix not in ALLOWED_EXTENSIONS and suffix != "<none>":
                    unexpected_binary_oids.add(oid)
            recovered_text = binary_strings(data)
            content_domain_classes.update(
                scan_text(recovered_text, oid, paths, known_values, findings)
            )
            scan_text(recovered_text, oid, paths, known_values, binary_findings)
            continue
        text_blobs += 1
        content_domain_classes.update(scan_text(text, oid, paths, known_values, findings))

    changed_lines, diff_findings, diff_known = scan_diff(git_dir, known_values)
    master_sha = git(git_dir, "rev-parse", "refs/heads/master").decode().strip()
    return {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "candidate_sha": master_sha,
        "rules": {
            "content_patterns": sorted(PATTERNS),
            "known_values_supplied": len(known_values),
            "minimum_known_value_length": 4,
            "large_blob_thresholds": ["100 KiB", "1 MiB"],
            "report_contains_match_values": False,
        },
        "refs": ref_summary(git_dir),
        "objects": {
            "counts": dict(sorted(object_types.items())),
            "bytes": dict(sorted(object_bytes.items())),
            "text_blobs": text_blobs,
            "binary_blobs": binary_blobs,
            "large_blobs": large_blobs,
            "binary_extensions": dict(sorted(binary_extensions.items())),
            "unexpected_extensions": dict(sorted(unexpected_extensions.items())),
        },
        "content_findings": findings.report(),
        "binary_content_findings": binary_findings.report(),
        "content_email_domain_classes": dict(sorted(content_domain_classes.items())),
        "known_readiness_values_matched": len(findings.known_value_ids),
        "affected_refs": affected_ref_summary(git_dir, findings, unexpected_binary_oids),
        "diff_scan": {
            "changed_lines": changed_lines,
            "findings": diff_findings,
            "distinct_known_values_matched": diff_known["distinct_known_values"],
        },
        "deleted_files": deleted_file_summary(git_dir),
        "commit_identities": commit_identity_summary(git_dir),
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--git-dir", type=Path, required=True, help="Bare mirror to audit")
    parser.add_argument(
        "--known-values",
        type=Path,
        help="Protected file with one sensitive comparison value per line",
    )
    parser.add_argument("--output", type=Path, required=True, help="Sanitized JSON report")
    return parser.parse_args()


def main() -> None:
    """Run the audit and write only the sanitized JSON report."""
    args = parse_args()
    result = audit(args.git_dir.resolve(), args.known_values)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
