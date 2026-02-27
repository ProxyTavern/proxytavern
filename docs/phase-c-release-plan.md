# Phase C Execution Plan (Release Validation + Readiness)

Status: ACTIVE  
Date (UTC): 2026-02-27

## Phase C Objectives
1. Validate release readiness with local-safe regression evidence.
2. Complete operator-facing runbook polish for final handoff.
3. Isolate approval-gated external validations (compose/LAN/ST live) without executing them.
4. Produce concise go/no-go readiness artifacts.

## Acceptance-Criteria Mapping

### Gate C1 — API + Contract Regression (must pass)
- Validate non-regression of `POST /v1/chat/completions` inline flow and upstream relay behavior.
- Validate stable API behaviors for config/token/session/queue endpoints.
- **AC targets:** AC-F1, AC-F2, AC-F3, AC-U1, AC-U2, AC-Q1, AC-Q2, AC-Q3.
- **Evidence source:** `tests/test_http_api.py`, `tests/test_queue_lifecycle.py`.

### Gate C2 — Auth/Security Matrix Verification (must pass)
- Verify protected ingress rejects missing, malformed, and invalid bearer tokens.
- Verify protected admin/operator surfaces enforce auth.
- Verify runtime auth hardening guards (`auth disabled` protections, required token when enabled).
- Verify token lifecycle + hashed storage guarantees.
- **AC targets:** AC-S1, AC-S2, AC-S3, AC-S4.
- **Evidence source:** `tests/test_http_api.py`, `tests/test_runtime_config.py`, `tests/test_queue_lifecycle.py`.

### Gate C3 — Persistence + Migration Sanity (must pass)
- Verify queue/config/token/session persistence across app restarts with SQLite file DB.
- Verify schema version guard (future DB version fails fast with contract error).
- **AC targets:** AC-D1 (local-safe prep), schema migration contract readiness.
- **Evidence source:** `tests/test_http_api.py`, `tests/test_queue_lifecycle.py`, `docs/schema-migration-contract.md`.

### Gate C4 — Operator Runbook Completeness (must pass)
- Final smoke checklist present and executable.
- Rollback and troubleshooting section present.
- Release readiness checklist with go/no-go criteria present.
- **Artifact target:** `docs/operator-playbook.md`.

### Gate C5 — External Approval-Gated Validations (deferred, not executed)
- Docker Compose live bring-up on target host.
- LAN reachability/auth validation from separate LAN client.
- SillyTavern live install/settings verification.
- **AC targets:** AC-D1, AC-D2, AC-ST2 final live proof.
- **Execution policy:** explicit human approval required before any run.

## Exit Criteria (Phase C Sign-off)
- C1/C2/C3/C4 are green with local evidence attached.
- C5 is explicitly tracked as deferred approval-required work.
- Release readiness report published with risks and go/no-go recommendation.
