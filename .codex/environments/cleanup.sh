#!/bin/sh
set -eu
set -f

: "${CODEX_WORKTREE_PATH:?}"
if [ "$(basename "$CODEX_WORKTREE_PATH")" != lzug ] ||
   [ "$(dirname "$(dirname "$CODEX_WORKTREE_PATH")")" != "$HOME/.codex/worktrees" ]; then
  echo "Not a managed lzug worktree: $CODEX_WORKTREE_PATH" >&2
  exit 1
fi

scope=$(basename "$(dirname "$CODEX_WORKTREE_PATH")")
case "$scope" in
  ''|*[!a-z0-9-]*) echo "Invalid worktree name: $scope" >&2; exit 1 ;;
esac

# Only resources with this label and the expected name may be removed.
# Persistent volumes intentionally lack the worktree label.
if ! command -v docker >/dev/null 2>&1; then
  exit 0
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker is unavailable; start it and retry worktree cleanup." >&2
  exit 1
fi

container_ids=$(docker ps -aq --filter "label=lzug-codex-$scope")
for id in $container_ids; do
  name=$(docker inspect --format '{{.Name}}' "$id")
  name=${name#/}
  case "$name" in
    "lzug-codex-$scope"-*)
      docker rm -f "$id"
    ;;
  esac
done

image_tags=$(docker image ls --format '{{.Repository}}:{{.Tag}}' --filter "label=lzug-codex-$scope")
for tag in $image_tags; do
  case "$tag" in
    "lzug-codex-$scope"-*)
      docker image rm "$tag"
    ;;
  esac
done

network_ids=$(docker network ls -q --filter "label=lzug-codex-$scope")
for id in $network_ids; do
  name=$(docker network inspect --format '{{.Name}}' "$id")
  case "$name" in
    "lzug-codex-$scope"-*)
      docker network rm "$id"
    ;;
  esac
done

volume_names=$(docker volume ls -q --filter "label=lzug-codex-$scope")
for name in $volume_names; do
  case "$name" in
    "lzug-codex-$scope"-*)
      docker volume rm "$name"
    ;;
  esac
done
