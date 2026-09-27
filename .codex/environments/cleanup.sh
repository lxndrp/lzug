#!/usr/bin/env bash
set -euo pipefail

: "${CODEX_WORKTREE_PATH:?}"
if [[ "$(basename "$CODEX_WORKTREE_PATH")" != lzug ||
      "$(dirname "$(dirname "$CODEX_WORKTREE_PATH")")" != "$HOME/.codex/worktrees" ]]; then
  echo "Not a managed lzug worktree: $CODEX_WORKTREE_PATH" >&2
  exit 1
fi

scope=$(basename "$(dirname "$CODEX_WORKTREE_PATH")")
case "$scope" in
  ''|*[!a-z0-9-]*) echo "Invalid worktree name: $scope" >&2; exit 1 ;;
esac

prefix="lzug-codex-$scope-"
scope_label="org.lzug.development.scope=$scope"
ephemeral_label='org.lzug.development.lifecycle=ephemeral'

# Only resources with both labels and the expected name belong to this worktree.
# Persistent volumes intentionally lack the ephemeral lifecycle label.
if ! command -v docker >/dev/null 2>&1; then
  exit 0
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker is unavailable; start it and retry worktree cleanup." >&2
  exit 1
fi

docker ps -aq --filter "label=$scope_label" --filter "label=$ephemeral_label" |
while IFS= read -r id; do
  [[ -n "$id" ]] || continue
  name=$(docker inspect --format '{{.Name}}' "$id")
  name=${name#/}
  if [[ "$name" == "$prefix"* ]]; then
    docker rm -f "$id"
  fi
done

docker image ls --format '{{.Repository}}:{{.Tag}}' --filter "label=$scope_label" --filter "label=$ephemeral_label" |
while IFS= read -r tag; do
  if [[ "$tag" == "$prefix"* ]]; then
    docker image rm "$tag"
  fi
done

docker network ls -q --filter "label=$scope_label" --filter "label=$ephemeral_label" |
while IFS= read -r id; do
  [[ -n "$id" ]] || continue
  name=$(docker network inspect --format '{{.Name}}' "$id")
  if [[ "$name" == "$prefix"* ]]; then
    docker network rm "$id"
  fi
done

docker volume ls -q --filter "label=$scope_label" --filter "label=$ephemeral_label" |
while IFS= read -r name; do
  if [[ "$name" == "$prefix"* ]]; then
    docker volume rm "$name"
  fi
done
