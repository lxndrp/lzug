"""Deploy and verify one immutable lzug demo artifact pair in Azure Container Apps."""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, overload
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

API_VERSION = "2025-07-01"
APP_IMAGE_PATTERN = re.compile(r"^ghcr\.io/lxndrp/lzug-demo-app@sha256:[0-9a-f]{64}$")
SEED_IMAGE_PATTERN = re.compile(r"^ghcr\.io/lxndrp/lzug-demo-seed@sha256:[0-9a-f]{64}$")
PRODUCT_TAG_PATTERN = re.compile(
    r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)" r"(?:-rc\.(0|[1-9][0-9]*))?$"
)
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
AZURE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.()-]{0,89}$")
REVISION_SUFFIX_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,62}[a-z0-9]$")


class DeploymentError(RuntimeError):
    """Signal a failed or unsafe demo deployment operation."""


@dataclass(frozen=True)
class ArtifactPair:
    app_image: str
    seed_image: str
    product_tag: str
    product_commit: str
    schema_fingerprint: str
    seed_revision: str

    def validate(self) -> None:
        checks = (
            (APP_IMAGE_PATTERN, self.app_image, "app_image"),
            (SEED_IMAGE_PATTERN, self.seed_image, "seed_image"),
            (PRODUCT_TAG_PATTERN, self.product_tag, "product_tag"),
            (COMMIT_PATTERN, self.product_commit, "product_commit"),
            (DIGEST_PATTERN, self.schema_fingerprint, "schema_fingerprint"),
            (DIGEST_PATTERN, self.seed_revision, "seed_revision"),
        )
        for pattern, value, label in checks:
            if pattern.fullmatch(value) is None:
                raise DeploymentError(f"Invalid immutable demo pair field: {label}")


@dataclass(frozen=True)
class AzureTarget:
    subscription_id: str
    resource_group: str
    container_app: str

    def validate(self) -> None:
        if (
            re.fullmatch(
                r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                self.subscription_id,
            )
            is None
        ):
            raise DeploymentError("subscription_id must be a UUID")
        for value, label in (
            (self.resource_group, "resource_group"),
            (self.container_app, "container_app"),
        ):
            if AZURE_NAME_PATTERN.fullmatch(value) is None:
                raise DeploymentError(f"Invalid Azure {label}")

    @property
    def resource_uri(self) -> str:
        return (
            "https://management.azure.com/subscriptions/"
            f"{self.subscription_id}/resourceGroups/{self.resource_group}"
            f"/providers/Microsoft.App/containerApps/{self.container_app}"
            f"?api-version={API_VERSION}"
        )


def validate_demo_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise DeploymentError("demo_url must be an HTTPS origin without credentials or path")
    return value.rstrip("/") + "/"


def _named_entry(entries: Any, expected_name: str, label: str) -> dict[str, Any]:
    if not isinstance(entries, list):
        raise DeploymentError(f"Azure template is missing {label}")
    matches = [entry for entry in entries if entry.get("name") == expected_name]
    if len(matches) != 1:
        raise DeploymentError(
            f"Azure template must contain exactly one {label} named {expected_name}"
        )
    return matches[0]


def _template(resource: dict[str, Any]) -> dict[str, Any]:
    try:
        template = resource["properties"]["template"]
    except (KeyError, TypeError) as error:
        raise DeploymentError("Azure response does not contain a revision template") from error
    if not isinstance(template, dict):
        raise DeploymentError("Azure revision template has an invalid shape")
    return template


def artifact_pair_from_resource(resource: dict[str, Any]) -> dict[str, str]:
    template = _template(resource)
    app = _named_entry(template.get("containers"), "lzug-demo-app", "app container")
    seed = _named_entry(template.get("initContainers"), "lzug-demo-seed", "seed init container")
    return {"app_image": str(app.get("image", "")), "seed_image": str(seed.get("image", ""))}


def deployment_body(
    resource: dict[str, Any], pair: ArtifactPair, revision_suffix: str
) -> tuple[dict[str, Any], dict[str, str]]:
    pair.validate()
    if REVISION_SUFFIX_PATTERN.fullmatch(revision_suffix) is None:
        raise DeploymentError("revision_suffix must be a valid lowercase ACA revision suffix")
    if (
        resource.get("properties", {}).get("configuration", {}).get("activeRevisionsMode")
        != "Single"
    ):
        raise DeploymentError("The demo Container App must remain in Single revision mode")

    template = copy.deepcopy(_template(resource))
    app = _named_entry(template.get("containers"), "lzug-demo-app", "app container")
    seed = _named_entry(template.get("initContainers"), "lzug-demo-seed", "seed init container")
    previous = {"app_image": str(app.get("image", "")), "seed_image": str(seed.get("image", ""))}
    if APP_IMAGE_PATTERN.fullmatch(previous["app_image"]) is None:
        raise DeploymentError(
            "The currently deployed app image is not an immutable canonical digest"
        )
    if SEED_IMAGE_PATTERN.fullmatch(previous["seed_image"]) is None:
        raise DeploymentError(
            "The currently deployed seed image is not an immutable canonical digest"
        )

    app["image"] = pair.app_image
    seed["image"] = pair.seed_image
    template["revisionSuffix"] = revision_suffix
    return {"properties": {"template": template}}, previous


def readiness_observation(
    resource: dict[str, Any], pair: ArtifactPair, revision_suffix: str
) -> tuple[bool, dict[str, Any]]:
    properties = resource.get("properties", {})
    latest = properties.get("latestRevisionName")
    ready = properties.get("latestReadyRevisionName")
    observed_pair = artifact_pair_from_resource(resource)
    observation = {
        "provisioning_state": properties.get("provisioningState"),
        "running_status": properties.get("runningStatus"),
        "latest_revision": latest,
        "latest_ready_revision": ready,
        **observed_pair,
    }
    is_ready = (
        properties.get("provisioningState") == "Succeeded"
        and isinstance(latest, str)
        and latest.endswith(f"--{revision_suffix}")
        and ready == latest
        and observed_pair["app_image"] == pair.app_image
        and observed_pair["seed_image"] == pair.seed_image
    )
    return is_ready, observation


def validate_health(payload: Any, pair: ArtifactPair) -> None:
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise DeploymentError("Health endpoint did not report status=ok")
    if payload.get("revision") != pair.product_commit:
        raise DeploymentError("Health endpoint reported an unexpected product commit")


def validate_demo_status(payload: Any, pair: ArtifactPair) -> None:
    expected = {
        "product_version": pair.product_tag.removeprefix("v"),
        "product_commit": pair.product_commit,
        "schema_fingerprint": pair.schema_fingerprint,
        "seed_revision": pair.seed_revision,
        "initialized": True,
        "initialization_status": "ready",
        "reset_timezone": "Europe/Berlin",
    }
    if not isinstance(payload, dict):
        raise DeploymentError("Demo API returned a non-object status document")
    for field, value in expected.items():
        if payload.get(field) != value:
            raise DeploymentError(f"Demo API reported an unexpected {field}")


@overload
def _az_rest(
    method: str,
    uri: str,
    body: dict[str, Any] | None = None,
    *,
    expect_json: Literal[True] = True,
) -> dict[str, Any]: ...


@overload
def _az_rest(
    method: str,
    uri: str,
    body: dict[str, Any] | None = None,
    *,
    expect_json: Literal[False],
) -> None: ...


def _az_rest(
    method: str,
    uri: str,
    body: dict[str, Any] | None = None,
    *,
    expect_json: bool = True,
) -> dict[str, Any] | None:
    """Run an Azure REST request and parse only responses with a JSON contract."""
    command = [
        "az",
        "rest",
        "--only-show-errors",
        "--method",
        method,
        "--uri",
        uri,
        "--output",
        "json" if expect_json else "none",
    ]
    if body is not None:
        command.extend(("--body", json.dumps(body, separators=(",", ":"))))
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode:
        detail = result.stderr.strip() or "Azure REST request failed without details"
        raise DeploymentError(detail)
    if not expect_json:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise DeploymentError("Azure REST request returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise DeploymentError("Azure REST request returned a non-object JSON response")
    return payload


def _http_get(url: str, *, expect_json: bool) -> tuple[Any, str]:
    request = Request(url, headers={"User-Agent": "lzug-demo-deployment/1"})
    try:
        with urlopen(request, timeout=20) as response:
            content_type = response.headers.get_content_type()
            body = response.read().decode("utf-8")
    except HTTPError as error:
        raise DeploymentError(f"GET {url} returned HTTP {error.code}") from error
    except (URLError, TimeoutError) as error:
        detail = getattr(error, "reason", str(error))
        raise DeploymentError(f"GET {url} failed: {detail}") from error
    if expect_json:
        try:
            return json.loads(body), content_type
        except json.JSONDecodeError as error:
            raise DeploymentError(f"GET {url} returned invalid JSON") from error
    return body, content_type


def deploy(target: AzureTarget, pair: ArtifactPair, revision_suffix: str, record: Path) -> None:
    target.validate()
    current = _az_rest("get", target.resource_uri)
    body, previous = deployment_body(current, pair, revision_suffix)
    _az_rest("patch", target.resource_uri, body, expect_json=False)
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(
        json.dumps(
            {
                "previous": previous,
                "target": asdict(pair),
                "revision_suffix": revision_suffix,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def wait_for_readiness(
    target: AzureTarget, pair: ArtifactPair, revision_suffix: str, timeout_seconds: int
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        resource = _az_rest("get", target.resource_uri)
        ready, last = readiness_observation(resource, pair, revision_suffix)
        if ready:
            return last
        time.sleep(10)
    raise DeploymentError(
        "Azure readiness timed out. Last observation: "
        + json.dumps(last, sort_keys=True, separators=(",", ":"))
    )


def wait_for_health(demo_url: str, pair: ArtifactPair, timeout_seconds: int) -> None:
    root = validate_demo_url(demo_url)
    deadline = time.monotonic() + timeout_seconds
    last_error = "health endpoint was not requested"
    while time.monotonic() < deadline:
        try:
            payload, _content_type = _http_get(urljoin(root, "api/health"), expect_json=True)
            validate_health(payload, pair)
            return
        except DeploymentError as error:
            last_error = str(error)
            time.sleep(10)
    raise DeploymentError(f"Health wait timed out: {last_error}")


def smoke(demo_url: str, pair: ArtifactPair) -> None:
    root = validate_demo_url(demo_url)
    health, _ = _http_get(urljoin(root, "api/health"), expect_json=True)
    validate_health(health, pair)
    status, _ = _http_get(urljoin(root, "api/demo/status"), expect_json=True)
    validate_demo_status(status, pair)
    openapi, _ = _http_get(urljoin(root, "api/openapi.json"), expect_json=True)
    if not isinstance(openapi, dict) or not str(openapi.get("openapi", "")).startswith("3."):
        raise DeploymentError("Central API route did not return the OpenAPI 3 contract")
    frontend, content_type = _http_get(root, expect_json=False)
    if content_type != "text/html" or "<app-root" not in frontend:
        raise DeploymentError("Central frontend route did not return the Angular application shell")


def diagnostics(target: AzureTarget) -> None:
    target.validate()
    resource = _az_rest("get", target.resource_uri)
    properties = resource.get("properties", {})
    report = {
        "provisioning_state": properties.get("provisioningState"),
        "running_status": properties.get("runningStatus"),
        "latest_revision": properties.get("latestRevisionName"),
        "latest_ready_revision": properties.get("latestReadyRevisionName"),
        **artifact_pair_from_resource(resource),
    }
    print(json.dumps(report, indent=2, sort_keys=True))


def _pair_from_args(args: argparse.Namespace) -> ArtifactPair:
    pair = ArtifactPair(
        app_image=args.app_image,
        seed_image=args.seed_image,
        product_tag=args.product_tag,
        product_commit=args.product_commit,
        schema_fingerprint=args.schema_fingerprint,
        seed_revision=args.seed_revision,
    )
    pair.validate()
    return pair


def _target_from_args(args: argparse.Namespace) -> AzureTarget:
    target = AzureTarget(args.subscription_id, args.resource_group, args.container_app)
    target.validate()
    return target


def _add_pair(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--app-image", required=True)
    parser.add_argument("--seed-image", required=True)
    parser.add_argument("--product-tag", required=True)
    parser.add_argument("--product-commit", required=True)
    parser.add_argument("--schema-fingerprint", required=True)
    parser.add_argument("--seed-revision", required=True)


def _add_target(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--subscription-id", required=True)
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--container-app", required=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-inputs")
    _add_pair(validate)
    validate.add_argument("--demo-url", required=True)

    deploy_parser = commands.add_parser("deploy")
    _add_pair(deploy_parser)
    _add_target(deploy_parser)
    deploy_parser.add_argument("--revision-suffix", required=True)
    deploy_parser.add_argument("--record", type=Path, required=True)

    readiness = commands.add_parser("wait-readiness")
    _add_pair(readiness)
    _add_target(readiness)
    readiness.add_argument("--revision-suffix", required=True)
    readiness.add_argument("--timeout-seconds", type=int, default=600)

    health = commands.add_parser("wait-health")
    _add_pair(health)
    health.add_argument("--demo-url", required=True)
    health.add_argument("--timeout-seconds", type=int, default=600)

    smoke_parser = commands.add_parser("smoke")
    _add_pair(smoke_parser)
    smoke_parser.add_argument("--demo-url", required=True)

    diagnostic = commands.add_parser("diagnostics")
    _add_target(diagnostic)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        if args.command == "validate-inputs":
            _pair_from_args(args)
            validate_demo_url(args.demo_url)
        elif args.command == "deploy":
            deploy(
                _target_from_args(args),
                _pair_from_args(args),
                args.revision_suffix,
                args.record,
            )
        elif args.command == "wait-readiness":
            observation = wait_for_readiness(
                _target_from_args(args),
                _pair_from_args(args),
                args.revision_suffix,
                args.timeout_seconds,
            )
            print(json.dumps(observation, indent=2, sort_keys=True))
        elif args.command == "wait-health":
            wait_for_health(args.demo_url, _pair_from_args(args), args.timeout_seconds)
        elif args.command == "smoke":
            smoke(args.demo_url, _pair_from_args(args))
        else:
            diagnostics(_target_from_args(args))
    except DeploymentError as error:
        print(f"demo deployment failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
