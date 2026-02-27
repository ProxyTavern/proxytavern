# Spec: Contained SillyTavern + ProxyTavern UI Config + Auto-Generated Blocking Rules

Status: Draft for implementation  
Owner: ProxyTavern maintainers  
Last Updated (UTC): 2026-02-27

---

## 1) Problem Statement

Current setup requires operators to manually edit env/config files, manually discover payload fields to block, and manually align trust/auth between ProxyTavern (PT) and SillyTavern (ST). This creates avoidable failures (notably PT→ST 403), slows onboarding, and weakens reproducibility when routing OpenCode (or similar clients) through PT.

This spec defines an implementation-ready flow where:
- ST extension exposes and confirms ST endpoint information in-product.
- PT web UI provides a first-class Config pane for runtime settings (no manual env editing for normal operation).
- PT automatically derives candidate blocked JSONPaths from observed incoming payload structure, allowing operator checkbox toggles before forwarding.
- PT→ST trust/auth is hardened and testable.
- OpenCode→PT routing can be proven deterministically.
- Safe compatibility improvements (streaming mode behavior, cache semantics, transport headers) are included.

---

## 2) Product Goals and Non-Goals

### Goals
1. First-run success within 10 minutes without shell/env edits.
2. Deterministic, inspectable routing from OpenCode → PT → ST.
3. Operator-controlled field filtering via auto-suggested JSONPath rules.
4. Eliminate known PT→ST 403 trust mismatch class.
5. Maintain backward-compatible API behavior for existing PT clients where possible.

### Non-Goals
1. Full ST plugin marketplace automation.
2. Model-specific prompt optimization logic.
3. Historical analytics/dashboarding beyond config + inspection needs.
4. Arbitrary expression language for transforms (JSONPath toggles only in this phase).

---

## 3) End-to-End UX Flow

## 3.1 First-Run Wizard (Happy Path)

### Step 0: Preconditions
- User has ST reachable on LAN/host.
- User deploys PT via Docker/Compose.

### Step 1: Install ST Extension
- User installs PT ST extension in ST Extensions manager.
- Extension panel appears in ST Extensions pane.

### Step 2: Extension Displays ST Endpoint
- Extension reads ST runtime origin + effective API path/port.
- Panel displays:
  - `Detected ST Endpoint URL`
  - `Copy Endpoint` action
  - `Connectivity check` status (optional ping)

### Step 3: Install/Run PT
- User starts PT container stack.
- User opens PT web UI (`/ui`).

### Step 4: PT First-Run Wizard
Wizard stages:
1. **Endpoint Pairing**: paste or auto-import ST endpoint from extension.
2. **Trust/Auth Setup**: choose PT→ST auth mode (none/header/token as supported), verify handshake.
3. **Runtime Config**: set PT listen host/port, upstream timeout, queue mode/inline mode.
4. **Rule Bootstrapping**: enable “Observe payload structure for N requests”, preview generated JSONPaths.
5. **Review + Apply**: persist config, run end-to-end probe.

### Step 5: Validation Screen
- Shows deterministic route proof:
  - inbound request id
  - PT decision mode
  - transformed payload hash
  - ST response status
- Shows pass/fail and recommended remediation.

## 3.2 Normal Operations

1. Operator opens PT Config pane any time.
2. Changes values in UI form (not raw env file).
3. PT validates, writes config store, and applies hot-reload or restart-required markers.
4. Auto-rule engine keeps learning new payload fields in observe mode.
5. Operator toggles candidate blocked fields via checkbox list and saves active rule set.
6. Session inspector shows raw vs transformed payload + which rules fired.

---

## 4) Architecture and Component Responsibilities

## 4.1 ST Extension
Responsibilities:
- Detect and display local ST endpoint URL/port/path.
- Provide copy/export action for endpoint metadata.
- (Optional) expose one-click deep-link to PT wizard with prefilled params.
- Show trust mode guidance for PT connection expectations.

Out of scope:
- Managing PT runtime directly.

## 4.2 PT API Service
Responsibilities:
- Own effective runtime config state (not env file as source of truth after first run).
- Serve config CRUD + validation APIs.
- Maintain auth/trust policy for PT→ST and UI/admin endpoints.
- Process incoming prompt requests; apply active block rules.
- Generate/refresh candidate JSONPaths from observed payloads.
- Emit deterministic trace metadata for routing proofability.

## 4.3 PT Web UI
Responsibilities:
- First-run wizard orchestration.
- Config pane with typed fields, validation errors, and restart-impact labels.
- Rule management UI with:
  - auto-generated candidates
  - checkbox enable/disable
  - preview of path impact
- Connection test + route proof UI.

## 4.4 Config Persistence Layer
Responsibilities:
- Persist runtime config revisions and rule sets in DB.
- Track active revision, audit metadata (`updated_by`, timestamp, source).
- Store generated-rule observations separately from active enforcement rules.

---

## 5) Detailed Requirements by Feature

## 5.1 ST Endpoint Visibility in Extension

Functional requirements:
1. Extension panel MUST display ST endpoint URL and port currently in effect.
2. Extension MUST allow copy-to-clipboard for endpoint value.
3. Extension SHOULD indicate if endpoint is not externally reachable (local-only bind warning).

Acceptance-level constraints:
- Endpoint string format must be canonicalized (`scheme://host:port/basePath`).
- If ST runs behind reverse proxy, extension should display effective configured external URL when available.

## 5.2 PT Config Pane (No Manual Env Editing)

Functional requirements:
1. PT UI MUST expose editable fields for at least:
   - ST endpoint URL
   - PT listen host/port (or published port metadata)
   - request timeout
   - mode (inline/queued)
   - streaming compatibility mode
   - cache-control behavior
   - PT→ST auth/trust settings
2. Save action MUST validate all fields server-side.
3. Config updates MUST be persisted as revisioned state.
4. UI MUST indicate whether each field is hot-reloadable or restart-required.
5. Runtime config precedence is explicit: UI/API runtime config overrides bootstrap env values after first successful save; env remains bootstrap-only fallback.

## 5.3 Auto-Generated JSONPath Blocking Rules

Functional requirements:
1. PT MUST observe incoming payloads and build a field-path inventory.
2. PT MUST propose candidate JSONPaths from observed structure using safe JSONPath-lite subset.
3. UI MUST render candidate list with per-path checkbox (enabled/disabled).
4. Operator MUST be able to promote candidates into active blocking rules.
5. PT MUST record rule provenance (`auto-generated`, `manual`, `imported`).
6. PT MUST show rule-hit telemetry in session details.

Algorithm constraints:
- Deduplicate structurally equivalent paths.
- Cap candidate explosion with configurable limits (depth, count per request, total pool).
- Default policy is permissive: no protected-field denylist is enforced automatically; operators opt into blocking via candidate activation.

## 5.4 PT→ST Auth/Trust Hardening (403 Remediation)

Functional requirements:
1. PT MUST implement Option A auth scope now: static bearer token plus optional custom header/value pair for ST outbound calls.
2. PT MUST send configured auth material deterministically on every forwarded request.
3. PT MUST offer handshake test endpoint/action that validates outbound auth against ST and reports concrete failure reason.
4. PT MUST fail closed if configured auth mode is invalid/incomplete.

Operational requirements:
- Provide clear mismatch diagnostics (missing header, token invalid, host mismatch, protocol mismatch).

## 5.5 OpenCode→PT Routing Proofability + Deterministic Provider Guidance

Functional requirements:
1. PT MUST expose route proof record keyed by request/session id containing:
   - client source metadata (safe subset)
   - matched PT config revision id
   - rule-set revision id
   - upstream target endpoint
   - request/transform checksum
2. UI MUST provide “Copy deterministic provider config” snippets for common clients (OpenCode baseline).
3. PT MUST include “last mile” verification API returning whether current config can accept expected OpenAI-compatible calls.

## 5.6 Compatibility Improvements

Required improvements:
1. Streaming under transform constraints is strict-fail:
   - passthrough when no blocking transform is required mid-stream
   - when transform enforcement requires full-body access and client requests stream=true, return deterministic failure (no implicit buffered fallback)
2. Cache headers on control/config endpoints:
   - `Cache-Control: no-store` for sensitive config/status endpoints.
3. Forwarding headers hygiene:
   - preserve necessary correlation ids
   - strip hop-by-hop headers
   - optional `X-ProxyTavern-Trace-Id` injection for diagnostics.

---

## 6) API Contract Changes

## 6.1 New/Updated Endpoints

1. `GET /api/config/effective`
   - Returns active runtime config + revision metadata + restart flags.

2. `PUT /api/config/effective`
   - Replaces effective config (validated).
   - Response includes `applied`, `restartRequired`, `revisionId`.

3. `POST /api/config/test-upstream`
   - Runs PT→ST connectivity/auth handshake test.
   - Returns structured diagnostics.

4. `GET /api/rules/candidates`
   - Returns auto-discovered JSONPath candidates with observed counts and last-seen timestamp.

5. `PUT /api/rules/active`
   - Sets active blocking rules (from candidates and/or manual entries).

6. `POST /api/rules/observe/reset` (admin)
   - Clears candidate observation pool.

7. `GET /api/routes/proof/:sessionId`
   - Returns deterministic route proof record.

## 6.2 Contract Notes
- Existing `GET/POST /api/config` may remain as compatibility aliases for one release cycle.
- All new admin endpoints require existing PT auth policy.
- Error payloads must be normalized (`code`, `message`, `details`).

---

## 7) Data Model Changes

## 7.1 New Tables/Entities

1. `config_revisions`
   - `id` (pk)
   - `config_json` (json)
   - `created_at`
   - `created_by`
   - `source` (`wizard|ui|api|migration`)
   - `is_active` (bool)

2. `rule_candidates`
   - `id`
   - `jsonpath`
   - `first_seen_at`
   - `last_seen_at`
   - `seen_count`
   - `sample_context_json` (optional scrubbed)
   - `status` (`candidate|accepted|ignored`)

3. `rule_revisions`
   - `id`
   - `rules_json`
   - `created_at`
   - `created_by`
   - `is_active`

4. `route_proofs`
   - `session_id` (pk/fk)
   - `config_revision_id`
   - `rule_revision_id`
   - `upstream_url`
   - `request_hash`
   - `transform_hash`
   - `outbound_status`
   - `created_at`

## 7.2 Modified Entities
- `request_sessions` add optional `config_revision_id`, `rule_revision_id`, `trace_id`.
- `config_state` may be deprecated to view over `config_revisions` active row.

## 7.3 Migration Strategy
- Forward migration creates new tables and backfills active rows from legacy config/rules.
- Keep legacy reads for one version; write-through to new tables only.

---

## 8) Security

## 8.1 Threat Vector: PT→ST auth mismatch causes fallback misconfiguration or unauthorized retries
1. **Threat Vector:** Incorrect/missing outbound auth header/token between PT and ST leading to 403 and repeated insecure experimentation.
2. **Risk Level:** High
3. **Recommended Fix:** Explicit outbound auth mode model + handshake test + fail-closed validation.
4. **What the Fix Solves:** Removes ambiguity; prevents silent unauthenticated forwarding attempts.
5. **Residual Risk:** Token rotation drift still possible without rotation automation.

## 8.2 Threat Vector: UI config tampering / unauthorized changes
1. **Threat Vector:** Unauthorized actor modifies endpoint/rules via PT admin APIs.
2. **Risk Level:** High
3. **Recommended Fix:** Enforce auth on all admin endpoints, audit revision metadata, optional IP allowlist.
4. **What the Fix Solves:** Restricts config mutation and enables forensic attribution.
5. **Residual Risk:** Stolen admin token remains a risk until revoked.

## 8.3 Threat Vector: Overblocking or critical field removal from auto-generated rules
1. **Threat Vector:** Auto-generated rules disable required protocol fields causing breakage/semantic drift.
2. **Risk Level:** Medium
3. **Recommended Fix:** Candidate-only default + explicit operator activation + protected allowlist + pre-save simulation.
4. **What the Fix Solves:** Prevents unintended enforcement from passive observation.
5. **Residual Risk:** Human misconfiguration still possible.

## 8.4 Threat Vector: Sensitive payload data leakage in rule-candidate sampling
1. **Threat Vector:** Candidate generation stores sensitive content in example context.
2. **Risk Level:** High
3. **Recommended Fix:** High-privacy retention defaults: store structural metadata only, scrub values, keep short TTL windows (e.g., route proofs 7d, rule-candidate observations 24h) unless explicitly extended by operator policy.
4. **What the Fix Solves:** Reduces data-at-rest exposure from prompt content and limits blast radius if storage is exposed.
5. **Residual Risk:** Metadata may still reveal usage patterns.

## 8.5 Threat Vector: Route proof spoofing / incomplete trace chain
1. **Threat Vector:** Inability to verify that a client request used intended config and reached intended upstream.
2. **Risk Level:** Medium
3. **Recommended Fix:** Persist signed/hash-linked proof tuple (session, config rev, rule rev, request/transform hashes).
4. **What the Fix Solves:** Improves non-repudiation and deterministic troubleshooting.
5. **Residual Risk:** Hashes prove consistency, not correctness of initial config intent.

---

## 9) Acceptance Criteria (Given / When / Then)

1. **First-run pairing**
- Given ST extension is installed and detects endpoint
- When user opens PT first-run wizard
- Then endpoint is prefilled or easily pasted, validated, and persisted without env edit.

2. **Config management in UI**
- Given PT is running
- When operator edits ST endpoint and timeout in Config pane and clicks Save
- Then PT validates server-side, creates config revision, and marks restart/hot-reload requirements.

3. **Auto-rule discovery**
- Given observe mode is enabled
- When PT processes inbound prompt payloads
- Then candidate JSONPaths appear in Rules UI with seen counts and are disabled by default.

4. **Rule activation**
- Given candidate paths exist
- When operator enables specific checkboxes and saves active rules
- Then subsequent requests apply those block rules and session details show fired paths.

5. **PT→ST hardening**
- Given outbound auth mode is configured
- When operator runs upstream test
- Then PT returns pass/fail with concrete reason and avoids ambiguous 403 handling.

6. **Deterministic route proof**
- Given a proxied request completes
- When operator opens route proof by session id
- Then proof includes config revision, rule revision, upstream URL, request/transform hashes, and status.

7. **Compatibility behavior**
- Given streaming mode is requested by client
- When active rules require full-body transform
- Then PT applies documented fallback behavior and reports mode used.

---

## 10) Test Matrix

## 10.1 Unit Tests
- Config schema validation (valid/invalid/restart-required flags).
- JSONPath candidate extraction (dedupe, limits, protected paths).
- Rule activation merge logic.
- Outbound auth header composition by mode.
- Cache-control/header policy helpers.

## 10.2 Integration Tests
- API config CRUD with revision persistence.
- Observe payload → candidate list population.
- Candidate activation → transform enforcement path.
- Upstream handshake diagnostics for auth success/failure modes.
- Route proof creation after successful and failed forwards.

## 10.3 End-to-End Tests
- ST extension endpoint display + PT wizard ingestion flow.
- OpenCode-compatible request through PT to ST with proof retrieval.
- Streaming compatibility scenarios (passthrough vs buffered fallback).

## 10.4 Manual/Operator Tests
- Docker first-run in clean environment.
- UI-only reconfiguration (no shell edits) of key runtime settings.
- 403 remediation checklist validation against misconfigured ST auth.
- Rollback to previous config/rule revision.

---

## 11) Migration and Rollout Plan

Phase rollout:
1. **Schema-first deploy**: add new tables/endpoints behind feature flags.
2. **Dual-read compatibility**: UI reads new effective endpoints; old endpoints aliased.
3. **Wizard beta**: enable first-run wizard + config pane for internal operators.
4. **Auto-rule observe-only launch**: candidate generation on, enforcement unchanged.
5. **Rule activation GA**: checkbox-driven enforcement enabled for all.
6. **Legacy deprecation**: remove dependence on direct env mutation for routine config.

Operational safeguards:
- Backup DB before migrations.
- Support one-click revert to previous config/rule revision.
- Telemetry gate: watch 4xx/5xx and transform error rates before broad enablement.

---

## 12) Implementation Slices (Strict Order)

1. **Slice 1: Config revision data model + migration scaffolding**
2. **Slice 2: Effective config API (`/api/config/effective`) with validation and restart metadata**
3. **Slice 3: PT→ST outbound auth mode model + handshake test endpoint**
4. **Slice 4: PT UI Config pane wired to effective config API**
5. **Slice 5: Rule-candidate observation pipeline (observe-only, no enforcement changes)**
6. **Slice 6: Rules UI candidate checkboxes + active rule revision API**
7. **Slice 7: Request pipeline integration for active rule revisions + telemetry in sessions**
8. **Slice 8: Route proof persistence + retrieval API + UI panel**
9. **Slice 9: Streaming/cache/header compatibility hardening**
10. **Slice 10: ST extension endpoint display/prefill integration with PT wizard**
11. **Slice 11: Full e2e + migration + rollback documentation and release checklist update**

No slice may begin until prior slice acceptance criteria are green.

---

## 13) Definition of Done

Done when all are true:
1. Spec sections in this document are implemented with matching endpoint and data contracts.
2. First-run wizard completes full pairing/config/rule-bootstrap without manual env edits.
3. PT→ST auth handshake test prevents unresolved 403 ambiguity.
4. Auto-generated JSONPath candidates are available and operator-toggleable with safe defaults.
5. Route proof is available per session and usable for deterministic troubleshooting.
6. Test matrix has passing automated coverage for critical paths plus manual checklist sign-off.
7. Migration + rollback steps are documented and validated in a clean Docker deployment.

---

## 14) Finalized Decisions (Locked)

The following decisions are approved and must be treated as implementation constraints for this spec:

1. **Config precedence:** runtime override.
   - Effective runtime config from UI/API is authoritative after first save.
2. **Rule policy baseline:** permissive defaults.
   - Auto-generated candidates are non-enforcing until explicitly activated by operators.
3. **PT→ST auth scope:** Option A now.
   - Support static bearer plus optional custom header/value pair; defer mTLS and broader auth expansion.
4. **Streaming under constraints:** strict fail.
   - If requested transform requires full-body buffering, reject `stream=true` deterministically (no silent fallback).
5. **Retention policy:** High Privacy tier.
   - Minimize stored sensitive material and enforce short default retention windows with explicit operator override only.
6. **ST extension/PT coupling:** passive.
   - Keep copy/paste + optional deep-link flow; no active push coupling from extension to PT in this phase.
