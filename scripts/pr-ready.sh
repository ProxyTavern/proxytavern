#!/usr/bin/env bash
set -euo pipefail

TEST_CMD=""
CHECK_REMOTE=false
SKIP_TESTS=false

usage() {
  cat <<USAGE
Usage: scripts/pr-ready.sh [--tests "<command>"] [--check-remote] [--skip-tests]

Runs:
  1) scripts/git-preflight.sh
  2) test command (default: .venv/bin/pytest -q if present, else pytest -q)
Then prints next commands for push + PR.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tests)
      TEST_CMD="${2:-}"
      shift
      ;;
    --check-remote)
      CHECK_REMOTE=true
      ;;
    --skip-tests)
      SKIP_TESTS=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[FAIL] Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

PREFLIGHT_ARGS=()
if [[ "$CHECK_REMOTE" == "true" ]]; then
  PREFLIGHT_ARGS+=(--check-remote)
fi

scripts/git-preflight.sh "${PREFLIGHT_ARGS[@]}"

run_default_tests() {
  if [[ -x .venv/bin/pytest ]]; then
    echo "[INFO] Running tests: .venv/bin/pytest -q"
    .venv/bin/pytest -q
  elif command -v pytest >/dev/null 2>&1; then
    echo "[INFO] Running tests: pytest -q"
    pytest -q
  else
    echo "[FAIL] No pytest found (.venv/bin/pytest or PATH)." >&2
    return 1
  fi
}

if [[ "$SKIP_TESTS" == "true" ]]; then
  echo "[WARN] Skipping tests by request (--skip-tests)."
else
  if [[ -n "$TEST_CMD" ]]; then
    echo "[INFO] Running tests: ${TEST_CMD}"
    eval "$TEST_CMD"
  else
    run_default_tests
  fi
  echo "[OK] Tests passed"
fi

branch="$(git rev-parse --abbrev-ref HEAD)"

echo

echo "Next commands:"
echo "  git push -u origin ${branch}"
echo "  gh pr create --base main --head ${branch} --fill"
