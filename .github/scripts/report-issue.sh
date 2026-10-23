#!/usr/bin/env bash
# Open the refresh-failure issue, or comment on the open one. Idempotent: a body carrying the same KEY is never posted twice
# (a re-run of the same job, or the same stale source on the next run, adds nothing).
# usage: report-issue.sh KEY TITLE BODY      needs GH_TOKEN and issues: write
set -euo pipefail
key="$1"; title="$2"; body="$3"
marker="<!-- report-key:${key} -->"
labels="$(gh label list --json name --jq '.[].name')"
case "$labels" in
  *refresh-failure*) ;;
  *) gh label create refresh-failure --color B60205 --description "data refresh failed or went stale" ;;
esac
num="$(gh issue list --label refresh-failure --state open --json number --jq '.[0].number // empty')"
if [ -n "$num" ]; then
  seen="$(gh issue view "$num" --json body,comments --jq '[.body, (.comments[].body)] | join("\n")')"
  case "$seen" in
    *"$marker"*) echo "already reported on #$num"; exit 0 ;;
  esac
  gh issue comment "$num" --body "${body}

${marker}"
else
  gh issue create --title "$title" --label refresh-failure --body "${body}

${marker}"
fi
