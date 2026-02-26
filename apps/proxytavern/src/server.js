import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import crypto from 'node:crypto';
import { applyBlockRules } from './jsonpath-lite.js';
import { createToken, getConfig, listSessions, saveSession, setConfig, verifyToken } from './store.js';

const app = express();
app.use(cors());
app.use(express.json({ limit: '5mb' }));

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const WEB_DIR = path.resolve(__dirname, '../web');

function auth(req, res, next) {
  if (req.path.startsWith('/api/')) return next();
  const token = (req.header('authorization') || '').replace(/^Bearer\s+/i, '');
  if (!verifyToken(token)) return res.status(401).json({ error: 'invalid_token' });
  return next();
}

app.get('/health', (_req, res) => res.json({ ok: true }));

app.get('/api/config', (_req, res) => {
  res.json(getConfig());
});

app.post('/api/config', (req, res) => {
  const updated = setConfig(req.body || {});
  res.json(updated);
});

app.post('/api/token/generate', (_req, res) => {
  const token = createToken();
  res.json({ token });
});

app.get('/api/sessions', (_req, res) => {
  res.json(listSessions());
});

app.post('/v1/chat/completions', auth, async (req, res) => {
  const incoming = req.body;
  const config = getConfig();
  const transformed = applyBlockRules(incoming, config.blockedJsonPaths || []);

  const upstreamUrl = process.env.UPSTREAM_URL;
  const startedAt = new Date().toISOString();
  const upstreamResp = await fetch(upstreamUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(transformed)
  });

  const upstreamBody = await upstreamResp.json().catch(async () => ({ raw: await upstreamResp.text() }));

  saveSession({
    id: crypto.randomUUID(),
    startedAt,
    incoming,
    transformed,
    upstreamBody,
    status: upstreamResp.status
  });

  res.status(upstreamResp.status).json(upstreamBody);
});

app.use('/ui', express.static(WEB_DIR));
app.get('/', (_req, res) => res.redirect('/ui'));

const port = Number(process.env.PORT || 8787);
const host = process.env.HOST || '0.0.0.0';
app.listen(port, host, () => {
  console.log(`ProxyTavern listening on http://${host}:${port}`);
});
