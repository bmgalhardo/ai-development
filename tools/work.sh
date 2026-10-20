#!/usr/bin/env bash
# Run the latest cycle's issues with independent workers: one fresh
# Codex or Claude worker per ready issue, one at a time, until no
# issue is ready. The state lives in the issue files, so it can be stopped
# and started again. The build issue runs last; then type /publish in an
# interactive session (headless sessions can't publish artifacts).
#
# Run it from the project's root; the project is the git repo of the
# current directory, and this script stays in the workflow repo:
#
#   ../game-development/tools/work.sh                       # Codex (default)
#   WORK_AGENT=claude ../game-development/tools/work.sh      # Claude
#   WORK_BUDGET_USD=25 WORK_AGENT=claude ../game-development/tools/work.sh
#
# A worker that hits the usage limit is retried at the reported reset time
# when available, or after WORK_WAIT seconds; other failures stop after two tries.
set -uo pipefail
NEXT_ISSUE="$(dirname "$(readlink -f "$0")")/next_issue.py"
cd "$(git rev-parse --show-toplevel)" || exit 1

WAIT="${WORK_WAIT:-1800}"
WORKER="${WORK_AGENT:-codex}"
BUDGET="${WORK_BUDGET_USD:-15}"
case "$WORKER" in
    codex|claude) ;;
    *) echo "WORK_AGENT must be codex or claude." >&2; exit 1 ;;
esac
if ! command -v "$WORKER" >/dev/null 2>&1; then
    echo "$WORKER is not installed or not on PATH." >&2
    exit 1
fi
LOG_DIR="artifacts/work"
mkdir -p "$LOG_DIR"

if [ -n "$(git status --porcelain)" ] && [ -z "$(python3 "$NEXT_ISSUE" --status | grep 'in progress')" ]; then
    echo "The working tree has changes and no issue is in progress: commit or stash them first." >&2
    exit 1
fi

failures=0
last=""
while :; do
    issue="$(python3 "$NEXT_ISSUE")"
    if [ -z "$issue" ]; then
        echo "No issue is ready."
        python3 "$NEXT_ISSUE" --status
        exit 0
    fi
    if [ "$issue" != "$last" ]; then failures=0; last="$issue"; fi
    log="$LOG_DIR/$(basename "$issue" .md)-$(date +%Y%m%d-%H%M%S).log"
    echo "$(date +%H:%M) $issue (log: $log)"
    case "$WORKER" in
        codex)
            codex exec --sandbox danger-full-access -c approval_policy='"never"' \
                --color never \
                "Read .agents/skills/implement/SKILL.md and follow it to implement $issue. Work on this issue only, without asking the user questions." \
                > "$log" 2>&1
            code=$?
            ;;
        claude)
            claude -p "/implement $issue" --permission-mode auto --max-budget-usd "$BUDGET" \
                --output-format text > "$log" 2>&1
            code=$?
            ;;
    esac
    status="$(python3 "$NEXT_ISSUE" --status | grep " $(basename "$issue")\$" | awk '{$1=""; $NF=""; print}' | xargs)"
    case "$status" in
        done|blocked) continue ;;
    esac
    if grep -qiE "usage limit|session limit|weekly limit|rate.?limit|429" "$log"; then
        delay="$(python3 - "$log" "$WAIT" <<'PY'
from datetime import datetime, timedelta
from pathlib import Path
import re
import sys

log, fallback = sys.argv[1], int(sys.argv[2])
text = Path(log).read_text(errors="replace")
now = datetime.now().astimezone()
patterns = (
    r"try again at ([A-Z][a-z]{2} \d{1,2}(?:st|nd|rd|th)?, \d{4} \d{1,2}:\d{2} [AP]M)",
    r"resets (\d{1,2}(?::\d{2})?\s*[AP]M?) \([A-Za-z_/]+\)",
)
reset = None
match = re.search(patterns[0], text, re.I)
if match:
    value = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", match.group(1), flags=re.I)
    reset = datetime.strptime(value, "%b %d, %Y %I:%M %p").replace(tzinfo=now.tzinfo)
else:
    match = re.search(patterns[1], text, re.I)
    if match:
        value = match.group(1).strip().upper().replace(" ", "")
        fmt = "%I:%M%p" if ":" in value else "%I%p"
        reset = now.replace(hour=datetime.strptime(value, fmt).hour,
                            minute=datetime.strptime(value, fmt).minute,
                            second=0, microsecond=0)
        if reset <= now:
            reset += timedelta(days=1)
if reset and reset > now:
    print(max(1, int((reset - now).total_seconds()) + 30))
else:
    print(fallback)
PY
)"
        echo "$(date +%H:%M) usage limit; waiting ${delay}s"
        sleep "$delay"
        continue
    fi
    failures=$((failures + 1))
    echo "$(date +%H:%M) worker stopped (exit $code) with $issue $status ($failures)"
    if [ "$failures" -ge 2 ]; then
        echo "Stopping: $issue failed twice. See $log." >&2
        exit 1
    fi
done
