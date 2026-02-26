import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const __dirname = path.dirname(new URL(import.meta.url).pathname);
const DATA_DIR = path.resolve(__dirname, '../data');
const STORE_PATH = path.join(DATA_DIR, 'state.json');

function ensureStore() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  if (!fs.existsSync(STORE_PATH)) {
    fs.writeFileSync(
      STORE_PATH,
      JSON.stringify({
        config: { mode: 'inline', blockedJsonPaths: [] },
        tokens: [],
        sessions: []
      }, null, 2)
    );
  }
}

function readStore() {
  ensureStore();
  return JSON.parse(fs.readFileSync(STORE_PATH, 'utf8'));
}

function writeStore(state) {
  fs.writeFileSync(STORE_PATH, JSON.stringify(state, null, 2));
}

export function getConfig() {
  return readStore().config;
}

export function setConfig(nextConfig) {
  const state = readStore();
  state.config = { ...state.config, ...nextConfig };
  writeStore(state);
  return state.config;
}

export function createToken() {
  const raw = crypto.randomBytes(24).toString('base64url');
  const hash = crypto.createHash('sha256').update(raw).digest('hex');
  const state = readStore();
  state.tokens.push({ hash, createdAt: new Date().toISOString(), active: true });
  writeStore(state);
  return raw;
}

export function verifyToken(rawToken) {
  if (!rawToken) return false;
  const hash = crypto.createHash('sha256').update(rawToken).digest('hex');
  return readStore().tokens.some((t) => t.hash === hash && t.active);
}

export function saveSession(entry) {
  const state = readStore();
  state.sessions.unshift(entry);
  state.sessions = state.sessions.slice(0, 200);
  writeStore(state);
}

export function listSessions() {
  return readStore().sessions;
}
