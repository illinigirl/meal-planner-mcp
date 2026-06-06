#!/usr/bin/env bash
# PostToolUse hook: after Claude edits a file, lint the package if the change
# touched Python. Receives the tool-call JSON on stdin; we only act on .py
# edits and degrade gracefully when ruff isn't installed, so the hook is safe
# to ship in a shared repo.
set -euo pipefail

payload="$(cat)"

# Pull the edited file path out of the tool input (Edit/Write/MultiEdit).
file="$(printf '%s' "$payload" \
  | python3 -c 'import sys, json
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))
except Exception:
    print("")' 2>/dev/null || true)"

case "$file" in
  *.py) : ;;          # Python change — fall through and lint
  *)   exit 0 ;;      # anything else — nothing to do
esac

if ! command -v ruff >/dev/null 2>&1; then
  echo "lint-changed: ruff not installed; skipping (pip install ruff)" >&2
  exit 0
fi

# Non-zero exit surfaces the lint errors back to the agent as feedback.
ruff check src/mealplanner tests
