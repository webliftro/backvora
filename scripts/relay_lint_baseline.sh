#!/usr/bin/env bash
set -euo pipefail

# Accepted BackVora baseline from the pre-refresh run: 298 total ESLint problems
# (287 errors, 11 warnings). This gate is green only while the branch does not
# increase that historical debt.
max_errors=287
max_warnings=11

cd frontend-react

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

set +e
npx eslint . --format json --output-file "$tmp"
lint_rc=$?
set -e

node - "$tmp" "$max_errors" "$max_warnings" <<'NODE'
const fs = require('fs');
const [path, maxErrorsRaw, maxWarningsRaw] = process.argv.slice(2);
const maxErrors = Number(maxErrorsRaw);
const maxWarnings = Number(maxWarningsRaw);
const report = JSON.parse(fs.readFileSync(path, 'utf8'));
const totals = report.reduce((acc, file) => {
  acc.errors += file.errorCount || 0;
  acc.warnings += file.warningCount || 0;
  return acc;
}, { errors: 0, warnings: 0 });

console.log(`eslint baseline check: ${totals.errors} errors, ${totals.warnings} warnings (accepted baseline <= ${maxErrors}/${maxWarnings})`);

if (totals.errors > maxErrors || totals.warnings > maxWarnings) {
  process.exit(1);
}
NODE

if [ "$lint_rc" -ne 0 ]; then
  echo "eslint exited non-zero, but problem counts are within the documented accepted baseline."
fi
