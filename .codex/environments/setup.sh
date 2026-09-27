#!/bin/sh
set -eu

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

cd "$CODEX_WORKTREE_PATH"
mkdir -p .mise/conf.d
printf '[env]\nLZUG_DEVELOPMENT_RESOURCE_SCOPE = "%s"\n' "$scope" > .mise/conf.d/codex-resource-scope.toml

mise install
mise exec -- task setup
mise exec -- task doctor
