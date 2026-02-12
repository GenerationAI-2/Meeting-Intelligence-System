#!/bin/bash
set -euo pipefail

# =============================================================================
# audit.sh — Pre-deployment vulnerability scan
# =============================================================================
#
# Usage:
#   ./infra/audit.sh                # Full audit (blocks on HIGH/CRITICAL)
#   ./infra/audit.sh --skip-audit   # Skip audit entirely
#   ./infra/audit.sh --warn-only    # Report but don't block deployment
#
# Scans:
#   1. Python dependencies (pip-audit via uvx)
#   2. npm dependencies (npm audit)
#   3. Filesystem scan (trivy, if installed)
#
# Exit codes:
#   0 = No HIGH/CRITICAL vulnerabilities found (or --skip-audit/--warn-only)
#   1 = HIGH/CRITICAL vulnerabilities found

SKIP_AUDIT=false
WARN_ONLY=false
FAILURES=0

for arg in "$@"; do
    case $arg in
        --skip-audit) SKIP_AUDIT=true ;;
        --warn-only) WARN_ONLY=true ;;
    esac
done

if [ "$SKIP_AUDIT" = true ]; then
    echo "Audit skipped via --skip-audit flag"
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Vulnerability Audit ==="
echo ""

# --- Python Dependencies ---
echo "--- [1/3] Python dependencies (pip-audit) ---"
if command -v uv &> /dev/null; then
    # Scan the project's virtual environment directly (avoids ensurepip issues)
    if (cd "$REPO_ROOT/server" && uv run pip-audit --desc 2>&1); then
        echo "PASS: No known Python vulnerabilities"
    else
        echo "FAIL: Python vulnerabilities found"
        FAILURES=$((FAILURES + 1))
    fi
else
    echo "SKIP: uv not installed"
fi
echo ""

# --- npm Dependencies ---
echo "--- [2/3] npm dependencies (npm audit) ---"
if command -v npm &> /dev/null && [ -f "$REPO_ROOT/web/package-lock.json" ]; then
    if npm audit --prefix "$REPO_ROOT/web" --omit=dev --audit-level=high 2>&1; then
        echo "PASS: No HIGH/CRITICAL npm vulnerabilities"
    else
        echo "FAIL: npm vulnerabilities found (HIGH or CRITICAL)"
        FAILURES=$((FAILURES + 1))
    fi
else
    echo "SKIP: npm not installed or no package-lock.json"
fi
echo ""

# --- Filesystem scan (optional, requires trivy) ---
echo "--- [3/3] Filesystem scan (trivy) ---"
if command -v trivy &> /dev/null; then
    if trivy fs "$REPO_ROOT" \
        --severity HIGH,CRITICAL \
        --exit-code 1 \
        --skip-dirs .git,node_modules \
        --quiet 2>&1; then
        echo "PASS: No HIGH/CRITICAL vulnerabilities (trivy fs)"
    else
        echo "FAIL: trivy found HIGH/CRITICAL vulnerabilities"
        FAILURES=$((FAILURES + 1))
    fi
else
    echo "SKIP: trivy not installed (install with: brew install trivy)"
fi
echo ""

# --- Summary ---
echo "=== Audit Summary ==="
if [ $FAILURES -gt 0 ]; then
    echo "RESULT: $FAILURES check(s) failed"
    if [ "$WARN_ONLY" = true ]; then
        echo "WARNING: Proceeding due to --warn-only flag"
        exit 0
    else
        echo "Deployment blocked. Fix vulnerabilities or re-run with --warn-only"
        exit 1
    fi
else
    echo "RESULT: All checks passed"
    exit 0
fi
