# ProxyTavern Acceptance Criteria (Detailed)

Status: **ACTIVE**  
Last Updated (UTC): 2026-02-27

## 1) Test Categories
- Functional API behavior
- Rule engine correctness
- Auth and security controls
- UI workflow correctness
- Queue mode behavior
- ST extension install/config behavior
- Deployment and operations

---

## 2) Functional Acceptance Criteria

### AC-F1 OpenAI-Compatible Endpoint
**Given** a valid non-streaming `chat.completions` request  
**When** request is sent to `POST /v1/chat/completions`  
**Then** ProxyTavern accepts, processes, and forwards according to current mode and rules.

Status: **PARTIALLY COMPLETE**

### AC-F2 Response Relay
**Given** upstream returns valid completion JSON  
**When** ProxyTavern receives it  
**Then** client receives structurally compatible response and status code.

Status: **PARTIALLY COMPLETE**

### AC-F3 Error Relay
**Given** upstream returns error/non-2xx  
**When** proxied request fails  
**Then** error status and body are propagated to the client with clear operator-observable semantics.

Status: **COMPLETE (current tuple-based upstream relay contract for non-2xx)**

---

## 3) Rule Engine Acceptance Criteria

### AC-R1 JSONPath Block Rule Application
**Given** a configured block selector list  
**When** request enters processing pipeline  
**Then** targeted fields are removed before forwarding.

Status: **PARTIALLY COMPLETE**

### AC-R2 Invalid Selector Handling
**Given** malformed/unsupported selector  
**When** operator saves configuration  
**Then** system rejects with clear validation error and does not corrupt active config.

Status: **COMPLETE (validated at API save path)**

### AC-R3 Deterministic Transform
**Given** same payload + same rules  
**When** processed repeatedly  
**Then** transformed output is identical.

Status: **IN PROGRESS**

---

## 4) Authentication & Security Criteria

### AC-S1 Protected Ingress
**Given** missing/invalid token  
**When** request hits protected ingress  
**Then** response is `401` and request not forwarded.

Status: **COMPLETE (for current protected endpoint set)**

### AC-S2 Token Hash Storage
**Given** token creation event  
**When** token is persisted  
**Then** plaintext token is never stored, only hash.

Status: **COMPLETE (current implementation)**

### AC-S3 Token Lifecycle
**Given** issued token  
**When** revoked/rotated  
**Then** old token immediately fails auth and new token succeeds.

Status: **COMPLETE (core token primitives + tests)**

### AC-S4 Admin Surface Protection
**Given** UI/admin endpoint request  
**When** unauthenticated actor attempts access  
**Then** request is denied per endpoint policy.

Status: **COMPLETE (for current admin API surface)**

---

## 5) UI Criteria

### AC-U1 Inbound/Transformed Visibility
**Given** completed request session  
**When** operator opens session detail  
**Then** API exposes full inbound payload and transformed payload side-by-side (`GET /api/sessions`, `GET /api/sessions/{id}`), enabling UI rendering.

Status: **PARTIALLY COMPLETE (API complete; full UI rendering still pending)**

### AC-U2 Mode Control
**Given** operator selects mode (`inline`/`queued`)  
**When** config saved  
**Then** subsequent requests follow selected mode.

Status: **COMPLETE (API path; UI shell still partial)**

### AC-U3 Token UX
**Given** operator clicks generate token  
**When** token created  
**Then** token appears once and copy flow works.

Status: **COMPLETE (admin API returns token once per generation)**

---

## 6) Queue Mode Criteria

### AC-Q1 Pending Queue Creation
**Given** queued mode enabled  
**When** new request received  
**Then** request enters pending queue and is not auto-forwarded.

Status: **PARTIALLY COMPLETE**

### AC-Q2 Approve/Reject Actions
**Given** pending queue item  
**When** operator approves or rejects  
**Then** item state changes and session records decision.

Status: **PARTIALLY COMPLETE**

### AC-Q3 Approve with Edit
**Given** pending queue item  
**When** operator edits payload then approves  
**Then** edited payload is forwarded and audit records diff/decision.

Status: **PARTIALLY COMPLETE**

---

## 7) SillyTavern Extension Criteria

### AC-ST1 GitHub URL Install
**Given** extension GitHub URL  
**When** installed via ST extension installer  
**Then** extension loads without manifest/entrypoint errors.

Status: **COMPLETE (packaging scaffold + local validator added)**

### AC-ST2 Config Panel
**Given** extension is enabled  
**When** operator opens extension settings  
**Then** endpoint URL and user-defined port are visible/configurable.

Status: **PARTIALLY COMPLETE (settings scaffold in extension entrypoint, pending live ST verification)**

---

## 8) Deployment Criteria

### AC-D1 Docker Compose Bring-up
**Given** default compose file and env set  
**When** operator runs compose up  
**Then** services start and health endpoint is reachable.

Status: **PARTIALLY COMPLETE**

### AC-D2 LAN Access
**Given** host on LAN  
**When** authorized client calls proxy endpoint  
**Then** requests are accepted with valid token and denied without it.

Status: **IN PROGRESS**

---

## 9) Completion Dashboard
- Functional core (non-streaming path): **PARTIALLY COMPLETE**
- Rule engine baseline: **PARTIALLY COMPLETE**
- UI baseline: **PARTIALLY COMPLETE**
- Queue workflow: **PARTIALLY COMPLETE**
- ST extension compliance packaging: **PARTIALLY COMPLETE**
- Security hardening matrix: **PARTIALLY COMPLETE**
- Deployment hardening & docs: **PARTIALLY COMPLETE**
