#!/usr/bin/env bash
set -euo pipefail

main_branch="${MAIN_BRANCH:-master}"
base="$(git merge-base HEAD "$main_branch")"

if git diff --quiet "$base"...HEAD -- '*.py' 'backend/**' 'tests/**'; then
  echo "pytest skipped: no Python/backend/tests changes since $main_branch ($base)"
  exit 0
fi

python3 -m pytest tests
