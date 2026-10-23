#!/usr/bin/env bash
# Open the refresh-failure issue, or comment on the open one. Idempotent: a body carrying the same KEY is never posted twice
# (a re-run of the same job, or the same stale source on the next run, adds nothing).
# usage: report-issue.sh KEY TITLE BODY [EXTRA_LABEL]      needs GH_TOKEN and issues: write
# EXTRA_LABEL (e.g. refresh-escalated) is created if missing and put on the issue even when the comment itself is a duplicate.
set -euo pipefail
key="$1"; title="$2"; body="$3"; extra="${4:-}"
marker="<!-- report-key:${key} -->"
labels="$(gh label list --json name --jq '.[].name')"
case "$labels" in
  *refresh-failure*) ;;
  *) gh label create refresh-failure --color B60205 --description "data refresh failed or went stale" ;;
esac
if [ -n "$extra" ]; then
  case "$labels" in
    *"$extra"*) ;;
    *) gh label create "$extra" --color D93F0B --description "needs a person: a source has been stale too long" ;;
  esac
fi
num="$(gh issue list --label refresh-failure --state open --json number --jq '.[0].number // empty')"
if [ -n "$num" ]; then
  seen="$(gh issue view "$num" --json body,comments --jq '[.body, (.comments[].body)] | join("\n")')"
  if [ -n "$extra" ]; then gh issue edit "$num" --add-label "$extra"; fi
  case "$seen" in
    *"$marker"*) echo "already reported on #$num"; exit 0 ;;
  esac
  gh issue comment "$num" --body "${body}

${marker}"
else
  gh issue create --title "$title" --label "refresh-failure${extra:+,$extra}" --body "${body}

${marker}"
fi
