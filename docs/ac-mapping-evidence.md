# Acceptance Criteria Mapping Evidence (Phase B Increment)

Date (UTC): 2026-02-27

## Summary
This increment completes the current Phase B admin API surface for config + token lifecycle + sessions endpoints and centralizes auth enforcement at router scope for protected route groups. It keeps `/healthz` public, persists config/token/session state in SQLite (with session timestamp migration), and adds HTTP coverage for new endpoints, auth behavior, validation, restart persistence, and upstream non-2xx relay.

## AC → Evidence

### AC-S1 Protected Ingress
- Requirement: missing/invalid token on protected ingress is denied with `401`, and request is not forwarded.
- Evidence tests:
  - `test_protected_endpoints_reject_missing_token`
  - `test_protected_endpoints_reject_malformed_authorization_header`
  - `test_protected_endpoints_reject_invalid_token`
- Files:
  - `src/proxytavern/api.py`
  - `tests/test_http_api.py`

### AC-S4 Admin Surface Protection
- Requirement: unauthenticated actor is denied on admin/control endpoints.
- Evidence tests:
  - `test_protected_endpoints_reject_missing_token` (covers `/api/config`, `/api/token*`, `/api/queue*`)
  - `test_get_and_update_config_authorized`
  - `test_token_endpoints_generate_list_revoke_rotate`
- Files:
  - `src/proxytavern/api.py` (router-level dependencies for `/v1` and `/api`)
  - `tests/test_http_api.py`

### AC-R2 Invalid Selector Handling
- Requirement: malformed/unsupported selector is rejected at config save path.
- Evidence tests:
  - `test_post_config_validation` (`POST /api/config` invalid rules returns 422)
  - `test_selector_validation_rejects_invalid_selector` (core)
- Files:
  - `src/proxytavern/api.py`
  - `src/proxytavern/core.py`
  - `tests/test_http_api.py`
  - `tests/test_queue_lifecycle.py`

### AC-U2 Mode Control (API path)
- Requirement: mode updates affect subsequent request behavior.
- Evidence tests:
  - `test_get_and_update_config_authorized`
  - existing queue behavior tests (`test_get_queue_and_decision_endpoints_authorized`)
- Files:
  - `src/proxytavern/api.py`
  - `tests/test_http_api.py`

### AC-U3 Token UX (API path)
- Requirement: generation returns token once and lifecycle ops are available.
- Evidence tests:
  - `test_token_endpoints_generate_list_revoke_rotate`
  - `test_token_endpoint_validation_and_errors`
- Files:
  - `src/proxytavern/api.py`
  - `src/proxytavern/core.py`
  - `tests/test_http_api.py`

### AC-S2 Token Hash Storage / AC-S3 Token Lifecycle
- Requirement: plaintext is not stored; revoke/rotate semantics enforced.
- Evidence tests:
  - `test_token_lifecycle_issue_revoke_rotate_with_hashed_storage`
  - `test_token_metadata_audit_timestamps_and_lineage_integrity`
  - `test_token_endpoints_generate_list_revoke_rotate`
- Files:
  - `src/proxytavern/core.py`
  - `src/proxytavern/api.py`
  - `tests/test_queue_lifecycle.py`
  - `tests/test_http_api.py`

### Persistence evidence for config/token/queue
- Requirement: persisted state survives restart when using file-backed SQLite.
- Evidence tests:
  - `test_queue_and_mode_persist_after_reloading_from_sqlite` (core)
  - `test_decided_queue_states_persist_across_restart` (core)
  - `test_queue_list_persists_across_app_restart_with_sqlite` (HTTP)
  - `test_decided_queue_states_persist_across_http_app_restart` (HTTP)
  - `test_config_and_token_metadata_persist_across_http_app_restart` (HTTP)
- Files:
  - `src/proxytavern/core.py`
  - `tests/test_queue_lifecycle.py`
  - `tests/test_http_api.py`

### Migration/versioning contract evidence
- Evidence tests/docs:
  - `test_schema_user_version_is_set_and_guarded`
  - `test_schema_guard_rejects_unsupported_future_db_with_contract_message`
  - `docs/schema-migration-contract.md`

### AC-U1 Inbound/Transformed Visibility (API path)
- Requirement: operators can inspect inbound and transformed payloads for sessions.
- Evidence tests:
  - `test_sessions_endpoints_authorized_include_lifecycle_payloads`
  - `test_get_session_returns_404_for_unknown_id`
- Files:
  - `src/proxytavern/api.py`
  - `src/proxytavern/core.py`
  - `tests/test_http_api.py`

### AC-F3 Error Relay
- Requirement: upstream non-2xx failures relay status and body.
- Evidence tests:
  - `test_upstream_non_2xx_is_relayed_on_inline_and_queued_approve`
- Files:
  - `src/proxytavern/core.py`
  - `src/proxytavern/api.py`
  - `tests/test_http_api.py`

### Session persistence/timestamps evidence
- Requirement: session lifecycle records include stable ids, status, payloads, and timestamps from SQLite-backed state.
- Evidence tests:
  - `test_sessions_endpoints_authorized_include_lifecycle_payloads`
  - `test_schema_user_version_is_set_and_guarded`
- Files:
  - `src/proxytavern/core.py` (session schema + migration to v2)
  - `src/proxytavern/api.py`
  - `tests/test_http_api.py`
  - `tests/test_queue_lifecycle.py`

## Notes
- `/healthz` remains public.
- Protected route auth is centralized per router to reduce per-route drift risk.
- Runtime startup guard in `src/proxytavern/app.py` still prevents disabled auth outside `dev|local|test` and requires bootstrap token when auth is enabled.
