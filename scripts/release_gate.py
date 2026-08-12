#!/usr/bin/env python3
"""Create and authorize immutable lzug release candidates through GitHub."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.build_metadata import COMMIT_SHA, SEMVER_TAG  # noqa: E402

MARKER = "<!-- lzug-release-candidate:v1 -->"
TAG_MARKER = "lzug-release-candidate:v1"
RELEASE_LABEL = "type: release"
REQUIRED_CHECKS = (
    "Quality / Backend",
    "Quality / Frontend",
    "Quality / Operator CLI",
    "Quality / OCI",
    "Quality / Documentation",
    "Quality / Security",
    "Quality / Overall",
)
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
FIELD = re.compile(r"^<!-- ([a-z-]+): ([^\n]+) -->$", re.MULTILINE)


class GateError(RuntimeError):
    """A release gate failed closed."""


@dataclass(frozen=True)
class Candidate:
    """Machine-readable identity of one immutable release candidate."""

    tag: str
    sha: str
    source_issue: int

    @property
    def version(self) -> str:
        """Return the release identity without the Git tag prefix."""

        return self.tag.removeprefix("v")


class GitHub:
    """Minimal GitHub REST client with fail-closed error handling."""

    def __init__(self, repository: str, token: str) -> None:
        if REPOSITORY.fullmatch(repository) is None:
            raise GateError("repository must have the form owner/name")
        if not token:
            raise GateError("GH_TOKEN is required")
        self.repository = repository
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        allow_missing: bool = False,
    ) -> Any:
        """Send one authenticated JSON request to the GitHub REST API."""

        url = f"https://api.github.com{path}"
        data = None if payload is None else json.dumps(payload).encode()
        request = Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "lzug-release-gate",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310
                body = response.read()
        except HTTPError as error:
            if allow_missing and error.code == 404:
                return None
            detail = error.read().decode(errors="replace")
            raise GateError(f"GitHub API {method} {path} failed: {error.code} {detail}") from error
        if not body:
            return None
        return json.loads(body)

    def repo(self, path: str = "") -> str:
        """Return an escaped repository API path."""

        owner, name = self.repository.split("/", 1)
        return f"/repos/{quote(owner)}/{quote(name)}{path}"

    def pages(self, path: str) -> list[Any]:
        """Read a conventional per-page GitHub collection completely."""

        separator = "&" if "?" in path else "?"
        result: list[Any] = []
        for page in range(1, 101):
            payload = self.request("GET", f"{path}{separator}per_page=100&page={page}")
            values = payload.get("check_runs", []) if isinstance(payload, dict) else payload
            if not isinstance(values, list):
                raise GateError("GitHub collection response is not a list")
            result.extend(values)
            if len(values) < 100:
                return result
        raise GateError("GitHub collection exceeded the supported pagination limit")


def parse_candidate(body: str) -> Candidate:
    """Parse exactly one trusted candidate marker block from an issue body."""

    if body.count(MARKER) != 1:
        raise GateError("release issue must contain exactly one candidate marker")
    fields: dict[str, str] = {}
    for key, value in FIELD.findall(body):
        if key in fields:
            raise GateError(f"release issue contains duplicate machine field {key}")
        fields[key] = value
    expected = {"release-tag", "candidate-sha", "source-issue"}
    if set(fields) != expected:
        raise GateError("release issue machine fields are incomplete or unknown")
    tag = fields["release-tag"]
    sha = fields["candidate-sha"]
    source = fields["source-issue"]
    if SEMVER_TAG.fullmatch(tag) is None:
        raise GateError("release tag must be supported SemVer")
    if COMMIT_SHA.fullmatch(sha) is None:
        raise GateError("candidate SHA must contain exactly 40 lowercase hex characters")
    if not source.isdecimal() or int(source) < 1:
        raise GateError("source issue must be a positive integer")
    return Candidate(tag, sha, int(source))


def render_candidate(candidate: Candidate, repository: str) -> str:
    """Render the versioned automatic release gate equivalent to the Issue Form."""

    issue_url = f"https://github.com/{repository}/issues/{candidate.source_issue}"
    return f"""{MARKER}
<!-- release-tag: {candidate.tag} -->
<!-- candidate-sha: {candidate.sha} -->
<!-- source-issue: {candidate.source_issue} -->

## Unveränderlicher Kandidat

- Geplanter annotierter Tag: `{candidate.tag}`
- Kandidat-Commit: `{candidate.sha}`
- Auslösendes letztes reguläres Milestone-Issue: [#{candidate.source_issue}]({issue_url})

Dieses Issue ist das einzige Freigabe-Gate für genau diesen Kandidaten. Der
Milestone dient ausschließlich der Vollständigkeitsprüfung. Erst der vom
Workflow am Kandidat-Commit erzeugte annotierte Tag wird technische
Versionsquelle. Wird nach diesem Zeitpunkt eine Korrektur erforderlich, muss
sie über ein reguläres Milestone-Issue erfolgen; die Automation setzt dieses
Gate anschließend auf den neuen geprüften Kandidaten zurück.

## Kandidat und Zielmenge

- [ ] Der Release-Milestone heißt exakt wie `{candidate.tag}`.
- [ ] Alle regulären Milestone-Issues sind geschlossen; dieses Issue ist das einzige offene Gate.
- [ ] Der Umfang ist eingefroren; zusätzliche Funktionen sind später geplant.
- [ ] Der Kandidat ist auf `master` erreichbar und seit der Prüfung unverändert.
- [ ] Für die Version existieren weder ein Tag noch ein veröffentlichter GitHub Release.
- [ ] Version, Milestone, Changelog-Abschnitt und geplanter Tag stimmen exakt überein.

## Freigegebener Umfang

Enthalten:

- <!-- kuratierbaren Umfang ergänzen -->

Nicht enthalten:

- <!-- bewusste Abgrenzung ergänzen -->

Vorgänger, erprobter RC oder begründete Nichtanwendbarkeit:

- <!-- Link oder Begründung ergänzen -->

## CI- und Qualitätsnachweise

- [ ] `Quality / Backend` ist für `{candidate.sha}` erfolgreich.
- [ ] `Quality / Frontend` ist für `{candidate.sha}` erfolgreich.
- [ ] `Quality / Operator CLI` ist für `{candidate.sha}` erfolgreich.
- [ ] `Quality / OCI` ist für `{candidate.sha}` erfolgreich.
- [ ] `Quality / Documentation` ist für `{candidate.sha}` erfolgreich.
- [ ] `Quality / Security` ist für `{candidate.sha}` erfolgreich.
- [ ] `Quality / Overall` ist für `{candidate.sha}` erfolgreich.
- [ ] Browser-E2E und Accessibility sind erfolgreich.
- [ ] Dokumentation und öffentliche Statusaussagen sind geprüft.

Nachweise:

- <!-- exakte Workflow-Läufe verlinken -->

## Security und Lieferkette

- [ ] CodeQL, Secret- und Misconfiguration-Scans sind erfolgreich.
- [ ] Backend-, Frontend-, Actions- und Container-Abhängigkeiten sind geprüft.
- [ ] Kein release-blockierender Security- oder Scanning-Befund ist offen.
- [ ] CycloneDX-SBOM und Provenance werden aus dem Kandidaten erzeugt.
- [ ] Artefakte werden ausschließlich durch den vertrauenswürdigen Workflow gebaut und attestiert.
- [ ] Akzeptierte Restrisiken besitzen eine dokumentierte Maintainer-Entscheidung.

Nachweise und Restrisiken:

- <!-- Security-, SBOM- und Provenance-Nachweise ergänzen -->

## Betrieb, Daten und Wiederherstellung

- [ ] Neuinstallation und Healthcheck mit der Referenzkonfiguration sind erfolgreich.
- [ ] Upgrade vom unterstützten Vorgänger ist erfolgreich oder beim ersten
  Release ausdrücklich nicht anwendbar.
- [ ] Backup und Restore sind mit Integritätsprüfung erfolgreich oder für den
  beanspruchten Umfang abgegrenzt.
- [ ] Der Rollback-Pfad ist geprüft oder seine begründete Grenze akzeptiert.
- [ ] Persistenz, Berechtigungen, Secrets, Healthcheck und
  Ressourcenanforderungen sind dokumentiert.

Nachweise:

- <!-- Installation, Upgrade, Backup/Restore und Rollback verlinken -->

## Pilot und Befunde

- [ ] Alle Befunde sind erfasst, klassifiziert und verlinkt oder begründet nicht anwendbar.
- [ ] Kein release-blockierender Befund ist offen.
- [ ] Nachgelagerte Befunde besitzen Issue, Priorität und Releasezuordnung oder
  bewusste Nichtzuordnung.

Erprobter RC, Befunde und Einschränkungen:

- <!-- Links oder Nichtanwendbarkeit ergänzen -->

## Releaseinformationen

- [ ] Der versionsbezogene Changelog-Abschnitt ist eindeutig, vollständig und frei von Platzhaltern.
- [ ] Breaking Changes, Migrationen, Upgrade-/Rollback-Grenzen und bekannte
  Einschränkungen sind hervorgehoben.
- [ ] Lizenz-, Drittanbieter- und Datenschutzangaben sind geprüft.
- [ ] Die kuratierten Release Notes verweisen auf SBOM, Provenance, Artefakte
  und Betriebsdokumentation.

Release Notes und Kommunikation:

- <!-- Changelog, Hinweise und Kommunikationsplan verlinken -->

## Verbindliche Freigabe

- [ ] Die freigebende Maintainer-Person hat alle Nachweise auf denselben Kandidaten geprüft.
- [ ] Die dokumentierte Entscheidung ist `GO`; bei `NO-GO` bleibt das Issue offen.
- [ ] Das Schließen ist die ausdrückliche Freigabe für die erneute serverseitige Validierung.
- [ ] Der Publish-Job benötigt danach zusätzlich die Freigabe des GitHub-Environments `release`.
- [ ] Tags, GitHub Release, OCI-Image und spätere CLI-Artefakte werden nicht
  manuell erzeugt oder überschrieben.

Entscheidung, freigebende Person, Datum und Restrisiken:

- <!-- GO erst nach vollständiger Abnahme dokumentieren -->

Ein fehlgeschlagener oder unvollständiger Lauf gilt nicht als veröffentlichter
Release. Die Automation veröffentlicht zuletzt den vollständigen GitHub Release
und dokumentiert Tag, Digest, SBOM, Attestations und Workflow-Lauf hier.
"""


def labels(issue: dict[str, Any]) -> set[str]:
    """Return normalized label names from a GitHub issue response."""

    return {label["name"] for label in issue.get("labels", []) if isinstance(label, dict)}


def required_checks_pass(check_runs: list[dict[str, Any]], sha: str) -> None:
    """Require the latest completed result for every stable quality gate."""

    latest: dict[str, dict[str, Any]] = {}
    for run in check_runs:
        name = run.get("name")
        if name not in REQUIRED_CHECKS or run.get("head_sha") != sha:
            continue
        timestamp = run.get("completed_at") or run.get("started_at") or ""
        previous = latest.get(name)
        previous_timestamp = (
            (previous.get("completed_at") or previous.get("started_at") or "") if previous else ""
        )
        if previous is None or timestamp > previous_timestamp:
            latest[name] = run
    missing = [name for name in REQUIRED_CHECKS if name not in latest]
    failed = [
        name
        for name in REQUIRED_CHECKS
        if name in latest and latest[name].get("conclusion") != "success"
    ]
    if missing or failed:
        raise GateError(f"required checks are not successful; missing={missing}, failed={failed}")


def protected_by_required_ruleset(client: GitHub) -> None:
    """Require an active, bypass-free default-branch ruleset with all stable gates."""

    summaries = client.request("GET", client.repo("/rulesets"))
    for summary in summaries:
        detail = client.request("GET", client.repo(f"/rulesets/{summary['id']}"))
        if detail.get("enforcement") != "active" or detail.get("target") != "branch":
            continue
        included = detail.get("conditions", {}).get("ref_name", {}).get("include", [])
        if "~DEFAULT_BRANCH" not in included or detail.get("bypass_actors"):
            continue
        for rule in detail.get("rules", []):
            if rule.get("type") != "required_status_checks":
                continue
            parameters = rule.get("parameters", {})
            names = {check.get("context") for check in parameters.get("required_status_checks", [])}
            if (
                parameters.get("strict_required_status_checks_policy")
                and set(REQUIRED_CHECKS) <= names
            ):
                return
    raise GateError("default branch lacks the strict bypass-free required-check ruleset")


def milestone_issues(client: GitHub, milestone_number: int) -> list[dict[str, Any]]:
    """Return every issue and pull request assigned to one milestone."""

    return client.pages(client.repo(f"/issues?milestone={milestone_number}&state=all"))


def check_runs(client: GitHub, sha: str) -> list[dict[str, Any]]:
    """Return all check runs for one exact commit."""

    return client.pages(client.repo(f"/commits/{sha}/check-runs?filter=latest"))


def comment(client: GitHub, issue_number: int, body: str) -> None:
    """Add one safe, server-side issue comment."""

    client.request("POST", client.repo(f"/issues/{issue_number}/comments"), {"body": body})


def create_candidate(client: GitHub, issue_number: int, candidate_sha: str) -> None:
    """Create or reset the sole release gate after the last regular issue closes."""

    issue = client.request("GET", client.repo(f"/issues/{issue_number}"))
    milestone = issue.get("milestone")
    if issue.get("state") != "closed" or milestone is None or RELEASE_LABEL in labels(issue):
        return
    tag = milestone.get("title", "")
    if SEMVER_TAG.fullmatch(tag) is None:
        return

    repository = client.request("GET", client.repo())
    if repository.get("default_branch") != "master":
        raise GateError("release automation requires master as default branch")
    if COMMIT_SHA.fullmatch(candidate_sha) is None:
        raise GateError("candidate SHA must contain exactly 40 lowercase hex characters")
    comparison = client.request("GET", client.repo(f"/compare/{candidate_sha}...master"))
    if comparison.get("status") not in {"ahead", "identical"}:
        raise GateError("pinned candidate is not reachable from master")

    issues = milestone_issues(client, milestone["number"])
    open_regular = [
        item["number"]
        for item in issues
        if item.get("state") == "open" and RELEASE_LABEL not in labels(item)
    ]
    if open_regular:
        return
    gates = [item for item in issues if RELEASE_LABEL in labels(item)]
    open_gates = [item for item in gates if item.get("state") == "open"]
    closed_gates = [item for item in gates if item.get("state") == "closed"]
    if closed_gates and not open_gates:
        return
    if len(open_gates) > 1:
        raise GateError("milestone contains more than one open release gate")

    protected_by_required_ruleset(client)
    required_checks_pass(check_runs(client, candidate_sha), candidate_sha)

    candidate = Candidate(tag, candidate_sha, issue_number)
    body = render_candidate(candidate, client.repository)
    assignees = [entry["login"] for entry in issue.get("assignees", [])]
    payload = {
        "title": f"Release: {tag}",
        "body": body,
        "milestone": milestone["number"],
        "labels": [RELEASE_LABEL, "review:operations", "review:code-quality"],
        "assignees": assignees,
    }
    if open_gates:
        gate = open_gates[0]
        if gate.get("user", {}).get("login") != "github-actions[bot]":
            raise GateError("existing release gate was not created by GitHub Actions")
        parse_candidate(gate.get("body") or "")
        release_issue = client.request("PATCH", client.repo(f"/issues/{gate['number']}"), payload)
        action = "zurückgesetzt"
    else:
        release_issue = client.request("POST", client.repo("/issues"), payload)
        action = "erzeugt"
    comment(
        client,
        issue_number,
        f"Release-Gate #{release_issue['number']} wurde für `{tag}` {action}. "
        f"Der unveränderliche Kandidat ist `{candidate_sha}`.",
    )


def validate_tag_state(client: GitHub, candidate: Candidate, issue_number: int) -> None:
    """Allow no tag, or the exact annotated tag left by a retryable prior attempt."""

    encoded_tag = quote(candidate.tag, safe="")
    reference = client.request(
        "GET", client.repo(f"/git/ref/tags/{encoded_tag}"), allow_missing=True
    )
    if reference is None:
        return
    obj = reference.get("object", {})
    if obj.get("type") != "tag":
        raise GateError("existing release tag is not annotated")
    tag_object = client.request("GET", client.repo(f"/git/tags/{obj.get('sha', '')}"))
    expected_marker = f"{TAG_MARKER} issue={issue_number} candidate={candidate.sha}"
    if (
        tag_object.get("tag") != candidate.tag
        or tag_object.get("object", {}).get("type") != "commit"
        or tag_object.get("object", {}).get("sha") != candidate.sha
        or expected_marker not in tag_object.get("message", "")
    ):
        raise GateError("existing annotated tag does not match this candidate gate")


def authorize(client: GitHub, issue_number: int, output: Path) -> bool:
    """Authorize one bot-created, maintainer-closed candidate for qualification."""

    issue = client.request("GET", client.repo(f"/issues/{issue_number}"))
    body = issue.get("body") or ""
    if RELEASE_LABEL not in labels(issue) or MARKER not in body:
        output.write_text("eligible=false\n", encoding="utf-8")
        return False
    candidate = parse_candidate(body)
    milestone = issue.get("milestone") or {}
    if issue.get("state") != "closed":
        raise GateError("release gate must be closed")
    if issue.get("user", {}).get("login") != "github-actions[bot]":
        raise GateError("release gate must be created by github-actions[bot]")
    if issue.get("title") != f"Release: {candidate.tag}":
        raise GateError("release gate title does not match its machine identity")
    if milestone.get("title") != candidate.tag:
        raise GateError("release gate milestone does not match its machine identity")

    closer = issue.get("closed_by", {}).get("login")
    if not closer:
        raise GateError("release gate has no closing actor")
    permission = client.request(
        "GET", client.repo(f"/collaborators/{quote(closer)}/permission")
    ).get("permission")
    if permission not in {"maintain", "admin"}:
        raise GateError("closing actor must have maintain or admin permission")

    repository = client.request("GET", client.repo())
    if repository.get("default_branch") != "master":
        raise GateError("release automation requires master as default branch")
    comparison = client.request("GET", client.repo(f"/compare/{candidate.sha}...master"))
    if comparison.get("status") not in {"ahead", "identical"}:
        raise GateError("candidate is no longer reachable from master")
    protected_by_required_ruleset(client)
    required_checks_pass(check_runs(client, candidate.sha), candidate.sha)

    issues = milestone_issues(client, milestone["number"])
    open_items = [item["number"] for item in issues if item.get("state") == "open"]
    if open_items:
        raise GateError(f"milestone still contains open items: {open_items}")
    matching_gates = [item for item in issues if RELEASE_LABEL in labels(item)]
    if [item["number"] for item in matching_gates] != [issue_number]:
        raise GateError("milestone does not contain exactly this one release gate")

    validate_tag_state(client, candidate, issue_number)
    release = client.request(
        "GET", client.repo(f"/releases/tags/{quote(candidate.tag, safe='')}"), allow_missing=True
    )
    if release is not None and not release.get("draft"):
        raise GateError("a published GitHub Release already exists for this version")

    image = f"ghcr.io/{client.repository.lower()}"
    values = {
        "eligible": "true",
        "tag": candidate.tag,
        "version": candidate.version,
        "sha": candidate.sha,
        "image": image,
        "canonical_ref": f"{image}:{candidate.version}",
        "issue_number": str(issue_number),
        "issue_url": issue["html_url"],
    }
    with output.open("w", encoding="utf-8") as stream:
        for key, value in values.items():
            stream.write(f"{key}={value}\n")
    return True


def create_annotated_tag(client: GitHub, issue_number: int, output: Path) -> None:
    """Create the exact annotated tag after repeating all authorization checks."""

    temporary = output.with_suffix(".authorization")
    authorize(client, issue_number, temporary)
    values = dict(line.split("=", 1) for line in temporary.read_text(encoding="utf-8").splitlines())
    temporary.unlink()
    candidate = Candidate(values["tag"], values["sha"], 1)
    encoded_tag = quote(candidate.tag, safe="")
    existing = client.request(
        "GET", client.repo(f"/git/ref/tags/{encoded_tag}"), allow_missing=True
    )
    if existing is None:
        marker = f"{TAG_MARKER} issue={issue_number} candidate={candidate.sha}"
        tag_object = client.request(
            "POST",
            client.repo("/git/tags"),
            {
                "tag": candidate.tag,
                "message": f"Release {candidate.tag}\n\n{marker}",
                "object": candidate.sha,
                "type": "commit",
            },
        )
        client.request(
            "POST",
            client.repo("/git/refs"),
            {"ref": f"refs/tags/{candidate.tag}", "sha": tag_object["sha"]},
        )
    validate_tag_state(client, candidate, issue_number)
    output.write_text(f"tag={candidate.tag}\nsha={candidate.sha}\n", encoding="utf-8")


def report_failure(client: GitHub, issue_number: int, run_url: str) -> None:
    """Reopen a failed release gate and leave an actionable recovery record."""

    issue = client.request("GET", client.repo(f"/issues/{issue_number}"))
    if issue.get("state") == "closed":
        client.request("PATCH", client.repo(f"/issues/{issue_number}"), {"state": "open"})
    comment(
        client,
        issue_number,
        "Die Veröffentlichung ist unvollständig und gilt nicht als Release. "
        f"Das Gate wurde für Ursachenklärung und erneute Freigabe geöffnet: {run_url}",
    )


def parser() -> argparse.ArgumentParser:
    """Create the release-gate command-line interface."""

    root = argparse.ArgumentParser()
    root.add_argument("--repository", required=True)
    root.add_argument("--token", default=os.environ.get("GH_TOKEN", ""))
    commands = root.add_subparsers(dest="command", required=True)

    candidate = commands.add_parser("candidate")
    candidate.add_argument("--issue", required=True, type=int)
    candidate.add_argument("--sha", required=True)

    authorization = commands.add_parser("authorize")
    authorization.add_argument("--issue", required=True, type=int)
    authorization.add_argument("--github-output", required=True, type=Path)

    tag = commands.add_parser("create-tag")
    tag.add_argument("--issue", required=True, type=int)
    tag.add_argument("--github-output", required=True, type=Path)

    failure = commands.add_parser("report-failure")
    failure.add_argument("--issue", required=True, type=int)
    failure.add_argument("--run-url", required=True)
    return root


def main() -> None:
    """Run the requested GitHub release-gate operation."""

    args = parser().parse_args()
    client = GitHub(args.repository, args.token)
    try:
        if args.command == "candidate":
            create_candidate(client, args.issue, args.sha)
        elif args.command == "authorize":
            authorize(client, args.issue, args.github_output)
        elif args.command == "create-tag":
            create_annotated_tag(client, args.issue, args.github_output)
        else:
            report_failure(client, args.issue, args.run_url)
    except GateError as error:
        if args.command == "authorize":
            try:
                issue = client.request("GET", client.repo(f"/issues/{args.issue}"))
                if MARKER in (issue.get("body") or ""):
                    comment(
                        client,
                        args.issue,
                        "Die Release-Autorisierung wurde serverseitig abgelehnt: "
                        f"`{error}`. Es wurden keine Veröffentlichungsrechte verwendet.",
                    )
            except GateError:
                pass
        print(f"release gate rejected: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
