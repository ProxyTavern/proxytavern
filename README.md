# ProxyTavern

Monorepo:
- `apps/proxytavern`: OpenAI-compatible MITM proxy + control panel
- `apps/st-extension`: SillyTavern extension scaffold

## Quick start

```bash
npm install
cp apps/proxytavern/.env.example apps/proxytavern/.env
npm --workspace apps/proxytavern run start
```

Open UI: `http://<host>:8787/ui`

## Current MVP features

- `POST /v1/chat/completions` pass-through (non-streaming)
- API token generation (`/api/token/generate`)
- JSONPath-lite blocking rules (field drop)
- Inbound vs transformed prompt inspection in UI
