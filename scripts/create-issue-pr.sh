#!/usr/bin/env bash

set -euo pipefail

usage() {
  printf 'Usage: %s <issue-number> --title <title> --body-file <path> [--draft] [--dry-run]\n' "$0" >&2
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

issue_number=$1
shift
title=''
body_file=''
draft=false
dry_run=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --title)
      title=${2:-}
      shift 2
      ;;
    --body-file)
      body_file=${2:-}
      shift 2
      ;;
    --draft)
      draft=true
      shift
      ;;
    --dry-run)
      dry_run=true
      shift
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [[ -z $title || -z $body_file || ! -f $body_file ]]; then
  usage
  exit 2
fi

repository=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
issue=$(gh issue view "$issue_number" --repo "$repository" --json assignees,milestone,projectItems)
project=$(jq -r '.projectItems[] | select(.title == "lzug Roadmap") | .title' <<<"$issue" | head -n 1)
milestone=$(jq -r '.milestone.title // empty' <<<"$issue")
assignees=$(jq -r '[.assignees[].login] | join(",")' <<<"$issue")

if [[ -z $project ]]; then
  printf 'Issue #%s ist dem Project lzug Roadmap nicht zugewiesen.\n' "$issue_number" >&2
  exit 1
fi

body=$(mktemp)
trap 'rm -f "$body"' EXIT
cp "$body_file" "$body"
printf '\n\nCloses #%s\n' "$issue_number" >> "$body"

arguments=(pr create --repo "$repository" --base master --title "$title" --body-file "$body" --project "$project")

if [[ -n $milestone ]]; then
  arguments+=(--milestone "$milestone")
fi

if [[ -n $assignees ]]; then
  arguments+=(--assignee "$assignees")
fi

if [[ $draft == true ]]; then
  arguments+=(--draft)
fi

if [[ $dry_run == true ]]; then
  printf 'Repository: %s\nProject: %s\nMilestone: %s\nAssignees: %s\n' \
    "$repository" "$project" "${milestone:-<none>}" "${assignees:-<none>}"
  printf 'Command: gh'
  printf ' %q' "${arguments[@]}"
  printf '\n'
  exit 0
fi

gh "${arguments[@]}"
