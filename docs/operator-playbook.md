## 0) Git working guardrails (required)
- Always work on **devbox** in `~/proxytavern`.
- Run `scripts/git-preflight.sh` before long implementation runs and again before push/PR.
- Branch naming convention: `<type>/<short-scope>` (examples: `feat/queue-filtering`, `fix/auth-401`, `chore/git-guardrails`).
- Optional remote reachability check: `scripts/git-preflight.sh --check-remote`.
- Before opening a PR, run `scripts/pr-ready.sh` (or `scripts/pr-ready.sh --tests "<test command>"`).

# ProxyTavern Operator Playbook (Phase C)

## 1) Bring-up (Docker Compose)
1. Copy `.env.example` to `.env`.
2. Set a strong `PROXYTAVERN_BEARER_TOKEN`.
3. Keep `PROXYTAVERN_AUTH_ENABLED=true` for LAN/prod.
4. Start service:
   - `docker compose up -d --build`
5. Verify health:
   - `curl http://127.0.0.1:8080/healthz`

## 2) LAN hardening defaults
- Default bind is loopback (`PROXYTAVERN_BIND=127.0.0.1`).
- For LAN access, set explicit host IP (avoid `0.0.0.0` unless intentionally exposed).
- Auth-disable guard: startup fails with `PROXYTAVERN_AUTH_ENABLED=false` unless `PROXYTAVERN_ENV` is `dev|local|test`.
- `PROXYTAVERN_BEARER_TOKEN` is required when auth is enabled.
- Keep token material out of shell history/logging where possible.

## 3) Admin API usage (all endpoints below require bearer auth)
Set helper:
- `export PT="http://127.0.0.1:8080"`
- `export TOKEN="<admin-token>"`

### 3.1 Config endpoints
Get current config:
- `curl -s -H "Authorization: Bearer $TOKEN" "$PT/api/config"`

Update mode + rules:
- `curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$PT/api/config" -d '{"mode":"queued","rules":["$.messages[0].content"]}'`

### 3.2 Token lifecycle endpoints
Generate token (shown once in response):
- `curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$PT/api/token/generate" -d '{"label":"ops"}'`

List token metadata (no plaintext token):
- `curl -s -H "Authorization: Bearer $TOKEN" "$PT/api/token"`

Revoke token:
- `curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$PT/api/token/revoke" -d '{"token_id":"<id>"}'`

Rotate token:
- `curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$PT/api/token/rotate" -d '{"token_id":"<id>","label":"ops-rotated"}'`

### 3.3 Session inspection endpoints
- `GET /api/sessions`
- `GET /api/sessions/<session-id>`

### 3.4 Queue endpoints
- `GET /api/queue`
- `POST /api/queue/{id}/approve`
- `POST /api/queue/{id}/reject`
- `POST /api/queue/{id}/approve-with-edit`

## 4) Final smoke-test checklist (release candidate)
Run all checks against a release-candidate build before go/no-go:

1. **Health check**
   - `GET /healthz` returns `200` and `{"status":"ok"}`.
2. **Auth enforcement matrix**
   - Protected endpoints reject missing token (`401`).
   - Protected endpoints reject malformed auth header (`401`).
   - Protected endpoints reject invalid token (`401`).
3. **Core API regression**
   - Inline mode `POST /v1/chat/completions` returns forwarded result.
   - Upstream non-2xx is relayed with status/body integrity.
4. **Config/rules behavior**
   - `GET /api/config` reflects current mode/rules.
   - `POST /api/config` validates bad payloads with `422`.
5. **Queue lifecycle**
   - Queued mode creates pending queue item.
   - approve / reject / approve-with-edit update state and enforce single-decision rule.
6. **Persistence sanity**
   - Queue/config/token metadata persist after app restart with file-backed SQLite.
   - Decided queue states persist and remain queryable.
7. **Schema contract sanity**
   - Unsupported future schema version fails fast with `SchemaVersionError`.
8. **ST extension package sanity (local-only)**
   - `python scripts/validate_st_extension.py` passes.

## 5) Rollback + troubleshooting

### 5.1 Rollback procedure (local/host level)
1. Stop current app process/container.
2. Restore last known good image/build and `.env`.
3. Restore prior SQLite DB snapshot if schema/content regression is suspected.
4. Start previous version and run smoke checks (health + auth + minimal chat completion).
5. Hold rollout until root cause is documented.

### 5.2 Common troubleshooting map
- **401 on all protected calls**
  - Confirm `Authorization: Bearer <token>` format.
  - Verify token is active (not revoked/rotated out).
- **Startup failure in prod with auth disabled**
  - Expected guardrail behavior; enable auth or switch to approved local/test env.
- **422 on config or queue edit**
  - Validate payload schema (`mode`, JSONPath rule shape, `approve-with-edit` payload object).
- **Schema version startup error**
  - DB `user_version` is newer than supported; use matching app version or planned migration path.
- **Queue decision conflict (409)**
  - Item already decided; inspect queue/session records for existing decision state.

## 6) Release readiness checklist (go / no-go)

### Go criteria (all required)
- [ ] Local release validation suite is green (API/auth/persistence/schema/ST package checks).
- [ ] Operator smoke-test checklist is complete and reproducible.
- [ ] Rollback path is documented and executable.
- [ ] No unresolved P0/P1 defects in proxy core/auth/queue paths.
- [ ] Approval-required external validations are explicitly tracked and pending sign-off.

### No-go triggers (any one)
- [ ] Auth regression (missing/malformed/invalid token not consistently rejected).
- [ ] Non-deterministic transform or queue decision integrity issue.
- [ ] Persistence/schema guard failures without mitigation.
- [ ] Missing rollback artifacts or unknown recovery path.

## 7) Approval-required validations (not run in local Phase C)
- Compose live validation on target environment.
- LAN access + auth validation from external LAN host/client.
- SillyTavern live extension install/settings verification.

## 8) GitHub PR review-reply helper
Use `scripts/gh-review-reply.py` to reply to specific review comments/threads with fallback.

Prereqs:
- `gh` CLI installed/authenticated.
- Run from repo root or pass `--repo owner/name`.

Examples:
- List thread/comment IDs for a PR:
  - `scripts/gh-review-reply.py --pr 123 --target 0 --list --format text`
- Dry-run mapping only (no post):
  - `scripts/gh-review-reply.py --pr 123 --target 456789012 --dry-run --format json`
- Post reply to review comment/thread target:
  - `scripts/gh-review-reply.py --pr 123 --target 456789012 --body "Thanks, fixed in latest commit."`

Target forms accepted:
- Numeric review comment ID (`databaseId`)
- Review comment node ID (`PRRC_...`)
- Review thread node ID (`PRRT_...`)
- Discussion URL containing `discussion_r<id>`

Exit codes:
- `0` success (or dry-run/list success)
- `2` target not found
- `3` inline reply failed, PR-level fallback posted
- `4` inline + fallback both failed
- `5` runtime/auth/query error

## 9) Web UI config workflow (runtime settings editor)

UI path: `/ui`

1. Open **Config** panel.
2. Click **Load** implicitly on page open (current effective config is fetched from `GET /api/config`).
3. Edit runtime-safe fields:
   - mode (`inline|queued`)
   - upstream URL
   - blocked JSONPaths
   - upstream auth flags/header name (token is never shown; env-only)
   - retention/privacy (`maxSessions`, payload storage toggle)
4. Click **Save Config** (calls `POST /api/config`).
   - Validation errors are shown as actionable toast messages.
   - Runtime overrides persist and take precedence over bootstrap env/default values.
5. Click **Reset Overrides** to clear runtime overrides (`POST /api/config/reset`) and fall back to env/default values.
6. Click **Test Connection** (`POST /api/config/test-connection`) to verify upstream reachability.

Security notes:
- `/api/config` responses never include plaintext auth tokens.
- Attempting to set upstream tokens through API is rejected; tokens must come from environment (`UPSTREAM_AUTH_TOKEN`).
