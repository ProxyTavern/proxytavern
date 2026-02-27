#!/usr/bin/env bash
set -euo pipefail

CANONICAL_ORIGIN="https://github.com/ProxyTavern/proxytavern.git"
CHECK_REMOTE=false

usage() {
  cat <<USAGE
Usage: scripts/git-preflight.sh [--check-remote]

Checks:
  - inside a git work tree
  - origin remote exists
  - origin URL matches ${CANONICAL_ORIGIN}
  - current branch is not detached
  - prints working tree summary
Optional:
  --check-remote   run git ls-remote origin to verify remote reachability
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check-remote)
      CHECK_REMOTE=true
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

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[FAIL] Not inside a git repository." >&2
  exit 1
fi

echo "[OK] Git repository: $(git rev-parse --show-toplevel)"

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "[FAIL] Missing origin remote. Configure origin=${CANONICAL_ORIGIN}" >&2
  exit 1
fi

origin_url="$(git remote get-url origin)"
if [[ "$origin_url" != "$CANONICAL_ORIGIN" ]]; then
  echo "[FAIL] origin URL mismatch." >&2
  echo "       expected: ${CANONICAL_ORIGIN}" >&2
  echo "       actual:   ${origin_url}" >&2
  exit 1
fi

echo "[OK] origin: ${origin_url}"

branch="$(git symbolic-ref --quiet --short HEAD || true)"
if [[ -z "$branch" ]]; then
  echo "[FAIL] Detached HEAD. Check out a branch before push/PR." >&2
  exit 1
fi

echo "[OK] branch: ${branch}"

echo "[INFO] Working tree summary:"
git status --short --branch

if [[ "$CHECK_REMOTE" == "true" ]]; then
  echo "[INFO] Checking remote reachability (git ls-remote origin)..."
  if ! git ls-remote --exit-code origin >/dev/null 2>&1; then
    echo "[FAIL] Cannot reach origin via git ls-remote." >&2
    exit 1
  fi
  echo "[OK] origin reachable"
fi

echo "[PASS] Git preflight checks complete."
