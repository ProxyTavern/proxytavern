# ProxyTavern PRD (Product Requirements Document)

Status: **ACTIVE**  
Last Updated (UTC): 2026-02-26

## 1. Product Overview
ProxyTavern is a local/self-hosted prompt middleware and policy control plane. It provides an OpenAI-compatible ingress for prompt clients and routes requests through configurable transformation policy before upstream forwarding (via SillyTavern path). It includes a web UI for full payload visibility and intervention.

## 2. Goals
1. Give users deterministic control over prompt payloads, especially system/developer context fields.
2. Allow integration with existing OpenAI-compatible clients without requiring client-specific hacks.
3. Provide clear, inspectable transformation history and request lifecycle visibility.
4. Support both automated and human-in-the-loop prompt handling modes.

## 3. Success Criteria (MVP)
- SC-1: Client app can use ProxyTavern as OpenAI-compatible endpoint for non-streaming chat completions.
- SC-2: Operator can define JSONPath-level block rules that affect outgoing payloads.
- SC-3: UI displays inbound and transformed payload for recent sessions.
- SC-4: Token generation works from UI and token validates for protected calls.
- SC-5: Queued mode can hold requests until operator approval.
- SC-6: ST extension installs from GitHub URL and exposes endpoint/port config.

## 4. Personas
- **Operator (single user)**: controls policy and routing behavior.
- **Prompt Client Integrator**: points AI apps at ProxyTavern API endpoint.
- **SillyTavern User**: installs/configures extension and links endpoint path.

## 5. User Stories
1. As an operator, I want to inspect all inbound structured prompts so I can verify what the client is sending.
2. As an operator, I want to block specific JSON fields so hidden/system instructions can be removed or altered.
3. As an operator, I want queued approval mode so I can manually review high-risk requests.
4. As an operator, I want to generate API tokens in UI so client onboarding is quick.
5. As a SillyTavern user, I want install-via-URL and a simple settings panel to minimize setup friction.

## 6. Feature Requirements

### 6.1 API Compatibility (MVP)
- Endpoint: `POST /v1/chat/completions`
- Mode: non-streaming only
- Input: OpenAI-like JSON body
- Output: passthrough-compatible JSON response

### 6.2 Rule Engine
- Supports JSONPath-like selectors
- Rule action for MVP: field drop/block
- Runtime update via control panel

### 6.3 UI Control Panel
- Session list and detail views
- Side-by-side inbound vs transformed payload
- Config panel for mode and block rules
- Token generation + copy UX

### 6.4 Modes
- **Inline**: transform + forward immediately
- **Queued**: hold request in pending queue until operator action

### 6.5 Persistence
- MVP recommendation: SQLite-backed append-only event model (or equivalent persistent store)
- Retention policy configurable (default 7 days)
- Runtime state separation from code repository

### 6.6 Security
- Token auth required for ingress/admin sensitive operations
- Hashed token storage (no plaintext persistence)
- LAN-safe defaults + clear hardening guidance

### 6.7 SillyTavern Extension
- Must include valid `manifest.json`
- JS entrypoint + settings UI
- Expose endpoint URL + configurable port visualization
- Installable via ST third-party extension Git URL flow

## 7. UX Requirements
- Minimal friction setup (<10 minutes for local LAN setup)
- Clear visibility of what changed in payload
- No hidden transformations
- Safe default mode and clear mode indicator

## 8. Metrics (MVP)
- Request success rate
- Transformation application rate
- Queue approval latency
- Auth failure count
- Upstream error rate

## 9. Release Plan

### Phase A (Current)
- Core proxy pass-through
- basic UI shell
- token generation
- block rules baseline

Status: **PARTIALLY COMPLETE**

### Phase B
- auth hardening matrix
- full queued workflow + operator actions
- ST extension packaging compliance

Status: **IN PROGRESS**

### Phase C
- docs, test matrix, LAN deployment hardening
- operator playbook

Status: **NOT STARTED**

## 10. Open Questions
1. How strict should admin/UI endpoint auth be in local-only mode?
2. What exact queue timeout/auto-expire policy should apply?
3. Which JSONPath dialect/engine should be standardized for edge cases?
4. Should transformed payload diff be exportable in MVP or post-MVP?

## 11. Completion Markers
- Product intent and target users: **COMPLETE**
- MVP feature set: **COMPLETE**
- Detailed acceptance-by-feature mapping: **IN PROGRESS**
- Final release readiness checklist: **IN PROGRESS**
