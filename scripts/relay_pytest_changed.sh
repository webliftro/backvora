#!/usr/bin/env bash
set -euo pipefail

main_branch="${MAIN_BRANCH:-master}"
base="$(git merge-base HEAD "$main_branch")"

if git diff --quiet "$base"...HEAD -- '*.py' 'backend/**' 'tests/**'; then
  echo "pytest skipped: no Python/backend/tests changes since $main_branch ($base)"
  exit 0
fi

# Resolve a python that actually has the test deps: repo venv first, then the
# main worktree's venv (drive worktrees don't carry the untracked venv/), then
# plain python3.
PY="python3"
common_root="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)"
for cand in "venv/bin/python" "$common_root/venv/bin/python"; do
  if [ -x "$cand" ] && "$cand" -c "import pytest" >/dev/null 2>&1; then
    PY="$cand"
    break
  fi
done

# Accepted baseline: tests already failing on pristine master for reasons
# unrelated to relay tasks (order-status naming drift, article-writer prompt
# drift). Deselected so the gate measures regressions, mirroring
# relay_lint_baseline.sh. Remove entries once the underlying tests are fixed
# (a deselect for a passing/absent test is ignored by pytest).
BASELINE_FAILURES=(
  "tests/test_lifecycle_e2e.py::TestFullLifecycle::test_happy_path"
  "tests/test_link_monitor.py::TestVerifyLiveUrl::test_verified_all_good"
  "tests/test_todays_changes.py::TestArticleWriterBannedPhrasing::test_recommendation_guidance_in_prompt"
)
deselect_args=()
for t in "${BASELINE_FAILURES[@]}"; do
  deselect_args+=(--deselect "$t")
done
echo "pytest baseline: deselecting ${#BASELINE_FAILURES[@]} known pre-existing failures (see script header)"

"$PY" -m pytest tests "${deselect_args[@]}"
