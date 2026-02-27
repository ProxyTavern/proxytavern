# ProxyTavern Scope (Detailed)

Status: **ACTIVE**  
Last Updated (UTC): 2026-02-26

## 1) Vision
Build a self-hosted, dockerized middleware platform (**ProxyTavern**) that sits between prompt clients (e.g., OpenCode) and downstream model paths (via SillyTavern), enabling deep prompt visibility, dynamic prompt shaping/blocking, and controlled forwarding.

## 2) Core Problem
Many AI apps do not expose sufficient controls for system/developer prompt behavior. Users need a man-in-the-middle control layer to inspect and modify prompt payloads before they are sent downstream.

## 3) Product Components (Two Deliverables)

### A. ProxyTavern Service (Dockerized)
- OpenAI-compatible ingress (`chat.completions`, non-streaming Day 1)
- Request normalization + rule-based transformation/blocking
- Token-based auth for client access
- Admin/control API for configuration and token lifecycle
- Web UI control panel for visibility and intervention
- Persistence/audit for request lifecycle and transformation history

### B. SillyTavern Extension (GitHub-installable)
- Installable from GitHub URL through ST extension installer
- Minimal settings/config UI in ST
- Shows endpoint URL and user-defined port
- Integrates with ProxyTavern connectivity model

## 4) In-Scope (MVP / Day 1)
1. Non-streaming `chat.completions` path only
2. Single-user auth model
3. LAN deployment target
4. Dynamic JSONPath-level field blocking
5. Two selectable edit modes:
   - Inline (synchronous transform)
   - Queued approval flow
6. Control panel to view:
   - Full structured inbound prompt (from prompt client)
   - Full structured transformed/downstream payload
7. API token generation from UI with copy UX
8. Dockerized service deployment
9. SillyTavern extension initial viable package + settings panel

## 5) Explicitly Out of Scope (MVP)
- SSE/token streaming passthrough
- Multi-user roles / RBAC
- Embeddings/responses/audio endpoints
- Advanced cluster deployment (K8s)
- Federated multi-node policy management

## 6) Users & Primary Jobs
- **Power user/operator:** enforce prompt policy on apps with poor prompt controls
- **Developer/integrator:** point OpenAI-compatible client apps at ProxyTavern endpoint
- **SillyTavern user:** install extension quickly and configure endpoint/port linkage

## 7) Functional Requirements (FR)

### FR-1 Ingress Compatibility
ProxyTavern SHALL expose OpenAI-compatible `POST /v1/chat/completions` for non-streaming requests.

### FR-2 Authentication
ProxyTavern SHALL require a valid API token for protected prompt ingress and admin operations (exact endpoint protection matrix defined in architecture doc).

### FR-3 Prompt Inspection
System SHALL capture and render inbound request body and transformed body in UI.

### FR-4 JSONPath Blocking
System SHALL support user-defined JSONPath-like selectors to remove/block target fields prior to forwarding.

### FR-5 Mode Switching
System SHALL support runtime mode toggle:
- inline mode (auto-transform + forward)
- queued mode (hold request pending operator action)

### FR-6 Queue Actions
In queued mode, operator SHALL be able to:
- approve as-is
- approve after edit
- reject/drop request

### FR-7 Upstream Forwarding
System SHALL forward transformed payload to configured upstream endpoint and relay response to client.

### FR-8 Session/Audit Storage
System SHALL persist request/transform/decision artifacts with timestamps and status.

### FR-9 Token Management UI
System SHALL allow token creation (and eventually revoke/rotate) from UI.

### FR-10 ST Extension Installability
ST extension SHALL be installable via GitHub URL and show endpoint/port config in its settings UI.

## 8) Non-Functional Requirements (NFR)
- NFR-1 Security-first defaults (LAN-conscious hardening)
- NFR-2 Deterministic transformation behavior
- NFR-3 Low-latency inline mode for non-streaming calls
- NFR-4 Crash-safe persistence for audit events
- NFR-5 Clear observability in UI (status/error visibility)

## 9) Deployment/Environment Constraints
- Primary development environment: Proxmox CT104
- Target runtime: Docker / Docker Compose
- Network posture: LAN exposure with token auth controls

## 10) External Dependencies
- SillyTavern extension APIs/packaging rules
- OpenAI-compatible client behavior (OpenCode and similar)
- Upstream provider route via ST/adapter endpoint

## 11) Risks Summary
1. Prompt leakage in logs/audit storage
2. Unauthorized LAN access if token handling is weak
3. Request tampering without strong audit integrity
4. JSONPath edge-case mismatches causing over/under-blocking

## 12) Current Completion Snapshot
- Scope discovery and constraints capture: **COMPLETE**
- MVP boundary definition: **COMPLETE**
- Detailed architecture doc: **IN PROGRESS (pending finalization)**
- Final acceptance matrix: **IN PROGRESS**
