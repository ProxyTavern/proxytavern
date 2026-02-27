# ProxyTavern Architecture (Detailed)

Status: **ACTIVE**  
Last Updated (UTC): 2026-02-26

## 1) High-Level Architecture

```text
Prompt Client (OpenCode, etc.)
        |
        | OpenAI-compatible HTTP (chat.completions)
        v
+-------------------------+
|      ProxyTavern        |
|-------------------------|
| Auth Gateway            |
| Request Normalizer      |
| Rule Engine             |
| Mode Orchestrator       |
| Queue Manager           |
| Upstream Adapter        |
| Audit/Persistence       |
| Control API + Web UI    |
+-------------------------+
        |
        | transformed payload
        v
SillyTavern endpoint / downstream model path
```

## 2) Runtime Components

### 2.1 API Layer
- Exposes `/v1/chat/completions`
- Performs auth checks
- Parses and validates payload shape

### 2.2 Normalization Layer
- Canonicalizes request fields
- Ensures deterministic handling of message arrays/metadata

### 2.3 Rule Engine
- Applies operator-defined JSONPath-level block list
- Produces transformed payload for downstream forwarding
- Emits transformation metadata event

### 2.4 Mode Orchestrator
- Inline mode: immediate forward
- Queued mode: create pending item and await operator decision

### 2.5 Queue Manager
- Pending queue persistence
- Decision endpoints (approve/edit/reject)
- Timeout/expiry policy (configurable)

### 2.6 Upstream Adapter
- Routes transformed payload to configured endpoint
- Handles response translation/passthrough
- Captures status and errors

### 2.7 Persistence + Audit
- Event log model (append-focused)
- Session materialized views for UI
- Token hash store
- Config snapshot history

### 2.8 Web UI + Admin API
- Config controls
- Queue management
- Prompt inspection views
- Token lifecycle operations

## 3) Data Model (Target)

### 3.1 Tables / Entities
1. `tokens`
   - id
   - token_hash
   - created_at
   - revoked_at (nullable)
   - label (optional)

2. `config_state`
   - id
   - mode (`inline|queued`)
   - jsonpath_rules (json)
   - updated_at

3. `request_sessions`
   - id
   - created_at
   - status (`received|queued|approved|forwarded|rejected|error`)
   - client_meta

4. `session_events`
   - id
   - session_id
   - event_type
   - payload (json, redaction-aware)
   - created_at
   - prev_hash
   - hash

5. `queue_items`
   - id
   - session_id
   - state (`pending|approved|rejected|expired`)
   - decision_at
   - decided_by

## 4) Endpoint Surface (MVP + Near-term)

### 4.1 Public/Client Endpoints
- `POST /v1/chat/completions`

### 4.2 Control/API Endpoints
- `GET /api/config`
- `POST /api/config`
- `POST /api/token/generate`
- `POST /api/token/revoke` (near-term)
- `GET /api/sessions`
- `GET /api/sessions/:id`
- `GET /api/queue`
- `POST /api/queue/:id/approve`
- `POST /api/queue/:id/reject`
- `POST /api/queue/:id/approve-with-edit`

## 5) Security Architecture

### 5.1 Trust Boundaries
- Boundary A: Prompt client -> ProxyTavern
- Boundary B: ProxyTavern -> ST/downstream
- Boundary C: Operator browser -> Admin UI/API

### 5.2 Controls
- Token-based request auth
- Hashed token persistence
- Optional bind restrictions (loopback/LAN CIDR allowlist)
- Explicit endpoint auth policy
- Redaction pipeline before persistence (for secrets/high-risk fields)

### 5.3 Threat/Fix Mapping
1. Prompt leakage in persistent logs
   - Fix: field redaction + retention TTL + optional body logging mode
2. Unauthorized LAN access
   - Fix: token auth, allowlist, reverse proxy TLS guidance
3. Silent tampering
   - Fix: event hash-chain with integrity checks
4. Rule abuse or malformed selectors
   - Fix: selector validation + safe parser + limits

## 6) SillyTavern Extension Architecture
- File layout includes `manifest.json` and JS entrypoint
- Settings panel binds to extension config state
- Displays endpoint URL and effective port
- Supports install from GitHub URL via ST extension installer

## 7) Deployment Architecture

### 7.1 Compose Services (Target)
- `proxytavern-api`
- `proxytavern-ui` (or bundled static)
- `proxytavern-db` (if external DB chosen; SQLite may remain embedded for MVP)

### 7.2 Volumes
- persistent DB/data
- optional audit export path

### 7.3 Network
- LAN bind with optional reverse-proxy fronting
- explicit upstream endpoint config

## 8) Operational Concerns
- health endpoint for liveness
- structured logs
- backup/restore strategy for persistence
- migration path from file-based state to SQLite

## 9) Current Implementation Status
- Core API shell: **COMPLETE**
- Basic rule application: **COMPLETE**
- Basic UI shell: **COMPLETE**
- Hardened auth matrix: **IN PROGRESS**
- Queued workflow full lifecycle (current API surface): **COMPLETE**
- ST extension compliant package: **IN PROGRESS**
- SQLite persistence for implemented flows: **COMPLETE**
- Production-grade persistence schema (full audit/token lifecycle model): **IN PROGRESS**
