# ProxyTavern Implementation Spec: Streaming + Prompt Visibility UI + Token UX

Status: Draft for implementation  
Owner: ProxyTavern engineering  
Target file: `docs/spec-streaming-ui-token.md`  
Last updated (UTC): 2026-02-27

---

## 1) Problem Statement

ProxyTavern currently has three gaps that block production-grade operator and client workflows:

1. **No OpenAI-compatible streaming support** on `POST /v1/chat/completions`, forcing non-streaming-only clients.
2. **Insufficient prompt visibility in UI**: operators can configure blocked JSONPaths but cannot reliably inspect full inbound prompt payload vs transformed outbound payload for a selected session.
3. **Token generation UX gap**: UI generate-token action does not display the returned token inline, causing copy/verification friction and operational mistakes.

This spec defines implementation-ready requirements to close all three gaps while preserving compatibility, security, and operator safety.

---

## 2) Scope

### In Scope
- Add `stream=true` support to chat completions endpoint using OpenAI-compatible SSE framing.
- Define streaming behavior by mode (`inline` vs `queued`), including fallback/error behavior.
- Add/adjust admin API contracts needed for session payload visibility at scale.
- Add UI session detail views for full inbound/transformed payload inspection.
- Add token generation UI that displays token once, supports copy, and supports masked/unmasked visibility toggle.
- Add tests (unit/integration/e2e/manual) and rollout/migration guidance.

### Out of Scope
- WebSocket streaming transport.
- Full historical replay/search engine for payload internals.
- Changing auth model beyond required hardening for new endpoints.
- Reworking queue architecture to support deferred server-push streaming after human approval.
- Multi-user RBAC redesign (assume current admin trust model remains).

---

## 3) Detailed Requirements by Feature

## 3.1 Feature A — API Streaming Support

### A.1 Functional Behavior
1. `POST /v1/chat/completions` must accept `stream: true` and return `Content-Type: text/event-stream` in supported mode.
2. In **inline mode**, ProxyTavern must:
   - authenticate,
   - normalize + apply rules,
   - forward upstream with streaming enabled,
   - relay SSE frames to client with minimal transformation.
3. In **queued mode**, `stream: true` is not supported for pending moderation path. Proxy must reject deterministically (see A.4).
4. `stream: false` (or missing `stream`) behavior remains unchanged.

### A.2 SSE Protocol and Chunk Shape
Proxy output must be OpenAI-compatible SSE:
- Each event line format: `data: {JSON}\n\n`
- Final sentinel: `data: [DONE]\n\n`
- No custom event names required.

Expected JSON chunk shape (pass-through compatible):
- `id` (string)
- `object` (e.g., `chat.completion.chunk`)
- `created` (unix seconds)
- `model` (string)
- `choices` array with partial deltas:
  - `index`
  - `delta` object (content/tool_calls/role fragments)
  - `finish_reason` only in terminating chunk for a choice

Proxy may preserve upstream chunk payload exactly except where safety requires sanitization of internal metadata.

### A.3 Compatibility Rules
- If upstream already emits OpenAI-compatible SSE, Proxy relays raw chunk payloads (after optional guard filtering).
- If upstream does not stream despite `stream=true` and returns single JSON completion:
  - Proxy may buffer and emit a synthetic single chunk + `[DONE]` **only when** config `STREAM_SYNTHETIC_FALLBACK=true`.
  - Default is `false`; if false, return `502` with explicit error code `upstream_stream_unavailable`.
- HTTP status for successful streaming initiation must be `200`.

### A.4 Queue-Mode Constraint (Required)
When global mode is `queued` and request has `stream=true`:
- Return `409 Conflict` JSON error:
  - `error.type = "queue_mode_streaming_unsupported"`
  - `error.message` explains streaming cannot be held while awaiting approval.
  - `error.hint` suggests retry with `stream=false` or switch mode to `inline`.
- Must not create a long-lived hanging connection.
- Must still record session event for audit (`received` + rejection reason).

### A.5 Error Handling / Termination
- Auth failures: standard `401` JSON error (non-SSE).
- Validation failures: `400` JSON error (non-SSE).
- Upstream connect failure before first chunk: `502` JSON error.
- Mid-stream upstream failure after chunks started:
  - Emit terminal SSE error chunk:
    - `data: {"error":{"type":"upstream_stream_error","message":"..."}}\n\n`
  - Then close stream (no further chunks).
  - If feasible, emit `[DONE]` only when semantics remain valid; otherwise close directly.
- Client disconnect should cancel upstream stream promptly and mark session event `client_disconnected`.

### A.6 Observability Requirements
- Metrics:
  - `stream_requests_total{result,mode}`
  - `stream_duration_ms`
  - `stream_chunks_relayed_total`
  - `stream_disconnects_total{side=client|upstream}`
- Structured logs must not include raw token secrets and must obey payload redaction rules.

---

## 3.2 Feature B — PT UI Prompt Visibility Improvements

### B.1 UX Objective
For any selected session, operator can inspect:
1. Full inbound request payload (pre-rule transform).
2. Full transformed/outgoing payload (post-rule transform, pre-forward).
3. Clear indication if payload is truncated/redacted.

### B.2 UI Additions
In Session Detail view add a **Prompt Payloads** panel:
- Tab 1: `Inbound Payload`
- Tab 2: `Transformed Payload`
- Shared controls:
  - Pretty/Raw toggle
  - Copy JSON button
  - Download JSON button (admin only)
  - Search-in-payload field (client-side within loaded slice)
- Metadata strip above payload:
  - payload byte size,
  - redaction count,
  - truncation status,
  - capture timestamp.

### B.3 Data Source API Requirements
#### New/Adjusted endpoints
1. `GET /api/sessions?cursor=<>&limit=<>`
   - Must return session summaries only (no full payload blobs).
   - Include flags: `has_inbound_payload`, `has_transformed_payload`, `payload_truncated`.
2. `GET /api/sessions/:id/payloads`
   - Returns metadata and first page/slice:
   - `{ inbound: {json, bytes, redacted_fields, truncated, next_cursor}, transformed: {...} }`
3. `GET /api/sessions/:id/payloads/:kind?cursor=<>&max_bytes=<>`
   - `kind in {inbound, transformed}`
   - Returns additional serialized slice if payload exceeds response budget.

### B.4 Pagination / Performance
- Session list default `limit=50`, max `200`.
- Payload endpoint default max response size target: 256 KB per kind.
- Large payloads must be chunked/sliced with cursor.
- UI should lazy-load payloads only when detail drawer/page is opened.
- UI must cancel in-flight payload fetch on session switch to avoid stale render.

### B.5 Redaction/Security in Display
- Display exactly stored redacted form; never reconstruct secrets client-side.
- Redacted values shown as sentinel (e.g., `"[REDACTED]"`).
- Copy/download actions include redacted values only.
- Admin warning banner: "Payloads may contain sensitive user text; handle/export with care."

---

## 3.3 Feature C — Token Generation UX Improvement

### C.1 Required UI Behavior
In token management area:
- Keep existing `Generate Token` button.
- Add adjacent read-only textbox `Generated token`.
- Add checkbox toggle: `Show token` (unchecked by default).

### C.2 One-Time Visibility Rules
1. On generation success, plaintext token is written into local UI state only.
2. Textbox displays masked format by default (e.g., `pt_****...****`).
3. If `Show token` checked, reveal full token until:
   - page refresh,
   - route change away from page,
   - explicit `Clear` action,
   - 5-minute inactivity timeout (whichever occurs first).
4. After token leaves local state, UI must not request plaintext token again (API cannot return it).

### C.3 Copy UX
- Add `Copy` button next to textbox.
- Copy copies full plaintext token only if token currently present in local state.
- On copy success: toast `Token copied. Store securely; it will not be shown again.`
- On copy attempt with no plaintext available: toast `No token available to copy. Generate a new token.`

### C.4 Security Warnings
Display inline caution text:
- "Token is shown once. Save it now."
- "Anyone with this token can use proxy APIs until revoked."

No browser localStorage/sessionStorage persistence for plaintext token.

---

## 4) API Contract Changes

## 4.1 `POST /v1/chat/completions`
### Request
- Existing OpenAI-compatible body.
- `stream` boolean supported.

### Responses
- `stream=false`: existing JSON completion behavior.
- `stream=true` + inline mode: `200` SSE stream.
- `stream=true` + queued mode: `409` JSON error (`queue_mode_streaming_unsupported`).
- Upstream non-stream fallback controlled by config `STREAM_SYNTHETIC_FALLBACK`.

## 4.2 Session Payload APIs
- Add `/api/sessions/:id/payloads` and `/api/sessions/:id/payloads/:kind` as above.
- Require same admin auth policy as existing session endpoints.
- Response metadata must include `redacted_fields`, `truncated`, `bytes`.

## 4.3 Token Generate Response (UI contract clarification)
- `POST /api/token/generate` continues returning plaintext token once in response.
- API must not offer retrieval endpoint for previously generated plaintext token.

---

## 5) UI Wireflow / State Behavior (Textual)

## 5.1 Session Inspection Wireflow
1. Operator opens Sessions list.
2. UI fetches summary page (`/api/sessions`).
3. Operator selects session row.
4. UI opens detail panel and requests `/api/sessions/:id/payloads`.
5. UI renders Inbound tab by default (pretty view).
6. Operator switches to Transformed tab; data shown from same payload response or fetched lazily.
7. If payload truncated, UI shows `Load more` button and fetches by cursor endpoint.
8. Copy/download actions operate on currently loaded redacted JSON only.

## 5.2 Token Generation Wireflow
1. Operator clicks `Generate Token`.
2. UI calls `/api/token/generate`.
3. On success:
   - store plaintext token in volatile component state,
   - textbox shows masked value,
   - `Show token` unchecked.
4. Operator may check `Show token` to reveal and click `Copy`.
5. On timeout/navigation/clear, UI wipes plaintext from state and reverts to empty textbox.

## 5.3 Streaming Client Flow (server-side behavior visible to clients)
1. Client sends chat completion with `stream=true`.
2. If mode inline, stream begins and chunks relay until `[DONE]` or terminal failure.
3. If mode queued, immediate `409` JSON error returned.

---

## 6) Security: Threat Vectors, Fixes, Solved Risk, Residual Risk

| Threat vector | Fix | What fix solves | Residual risk |
|---|---|---|---|
| Sensitive prompt content exposed in UI | Redaction before persistence; UI only reads redacted payloads; warning banner | Prevents accidental secret disclosure through admin views/export | Human-entered PII still visible if not matched by redaction rules |
| Token shoulder-surf / screenshot leakage | Masked default, explicit show toggle, volatile memory only, auto-clear timeout | Reduces casual exposure and persistent browser leakage | Visible token can still be captured while shown |
| Streaming DoS via long-lived connections | connection limits + stream timeout + cancellation on disconnect | Limits resource exhaustion and orphaned streams | Coordinated high-volume abuse still needs infra rate limiting |
| Ambiguous queue+stream behavior causing hangs | deterministic `409 queue_mode_streaming_unsupported` | Eliminates indefinite waits and client ambiguity | Some clients may not gracefully handle 409 without update |
| Over-fetch of huge payloads affecting UI/API performance | sliced payload endpoints + lazy loading + size caps | Prevents large response memory spikes and sluggish list view | Very large sessions still expensive to inspect in full |

---

## 7) Acceptance Criteria (Given/When/Then)

### AC-1 Streaming Success (Inline)
**Given** proxy mode is `inline` and upstream supports streaming  
**When** client calls `/v1/chat/completions` with `stream=true`  
**Then** client receives SSE chunks and terminal `[DONE]`, and session is recorded as forwarded.

### AC-2 Streaming Rejection (Queued)
**Given** proxy mode is `queued`  
**When** client calls `/v1/chat/completions` with `stream=true`  
**Then** proxy returns `409` with `error.type=queue_mode_streaming_unsupported` and no stream is opened.

### AC-3 Upstream Stream Unavailable (No Synthetic Fallback)
**Given** inline mode and `STREAM_SYNTHETIC_FALLBACK=false`  
**When** upstream ignores stream and returns non-stream JSON  
**Then** proxy returns `502` with `error.type=upstream_stream_unavailable`.

### AC-4 Session Payload Visibility
**Given** a completed session exists  
**When** operator opens session detail  
**Then** inbound and transformed payload tabs render with metadata (bytes, truncation, redaction count).

### AC-5 Payload Slicing
**Given** payload exceeds per-response size cap  
**When** operator clicks `Load more`  
**Then** UI fetches next cursor slice and appends without freezing list navigation.

### AC-6 Token One-Time Display
**Given** operator generates a token  
**When** request succeeds  
**Then** token appears masked in textbox, can be revealed with checkbox, and is not retrievable after clear/refresh/timeout.

### AC-7 Token Copy Guard
**Given** plaintext token is no longer in volatile state  
**When** operator clicks `Copy`  
**Then** UI shows error toast instructing regeneration.

---

## 8) Test Matrix

## 8.1 Unit Tests
- Stream mode gate logic (`inline` vs `queued`).
- SSE formatter output line framing + `[DONE]` emission.
- Upstream fallback branching with `STREAM_SYNTHETIC_FALLBACK` true/false.
- Payload slicing cursor math and boundary handling.
- Token UI state reducer: mask/reveal/timeout/clear transitions.

## 8.2 Integration Tests
- End-to-end proxy to mock upstream streaming server.
- Mid-stream upstream disconnect handling and session event capture.
- Queued mode stream request returns deterministic 409 body.
- Session payload endpoints return redacted data and metadata.
- Token generate API + UI component contract (one-time plaintext handling).

## 8.3 E2E Tests (Browser + API)
- Operator navigates session list -> detail -> inbound/transformed tabs -> copy JSON.
- Large payload truncated path with `Load more` behavior.
- Generate token -> reveal -> copy -> navigate away -> verify token cleared.
- Client receives chunked response for stream=true in inline mode.

## 8.4 Manual Tests
- Verify compatibility with OpenAI SDK client in streaming mode.
- Verify non-streaming clients unaffected.
- Validate warning copy clarity with operators.
- Run light load test (N concurrent streams) and check latency/memory thresholds.

---

## 9) Implementation Slices (Execution Order)

### Slice 1 — Contracts + Flags
- Add/confirm config flag `STREAM_SYNTHETIC_FALLBACK` (default false).
- Finalize error codes and response schemas for stream/queue behavior.

### Slice 2 — Streaming Transport in API Path
- Implement inline-mode SSE relay, cancellation, and error termination semantics.
- Add metrics and structured logging for stream lifecycle.

### Slice 3 — Session Payload API Expansion
- Add payload metadata + sliced retrieval endpoints.
- Ensure redaction pipeline is enforced before persistence/response.

### Slice 4 — UI Session Payload Viewer
- Add prompt payload tabs, controls (pretty/raw/copy/download/search), truncation load-more flow.
- Add lazy loading and cancellation on session switch.

### Slice 5 — Token UX Update
- Add generated token textbox, show/hide checkbox, copy button, warning copy.
- Implement volatile-state-only storage + timeout clear.

### Slice 6 — Tests + Rollout
- Execute test matrix.
- Rollout by environment: dev -> staging -> production with canary streaming clients.
- Monitor stream error rates and queue-mode 409 frequency.

---

## 10) Migration / Rollout Notes

- **Backward compatibility:** non-streaming path unchanged.
- **Client impact:** streaming clients in queued mode will now receive deterministic `409`; communicate in release notes.
- **Feature gating:** enable streaming in production behind config toggle if desired; keep synthetic fallback disabled initially.
- **Operational checklist:**
  1. deploy API changes,
  2. deploy UI changes,
  3. verify admin auth on new payload endpoints,
  4. run smoke tests for stream inline and queue rejection,
  5. monitor metrics for 24h.

---

## 11) Definition of Done

Done means all of the following are true:
1. All acceptance criteria (AC-1 through AC-7) pass.
2. Test matrix implemented and green in CI (unit/integration/e2e) plus manual sign-off checklist completed.
3. API docs updated for streaming behavior, queue-mode 409, and payload endpoints.
4. UI clearly shows inbound/transformed payloads and token generation one-time UX behavior.
5. Security controls validated:
   - redaction present in displayed/exported payloads,
   - plaintext token not persisted client-side,
   - stream limits/cancellation active.
6. Release notes include compatibility notes and operator guidance.

