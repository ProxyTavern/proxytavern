import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const __dirname = path.dirname(new URL(import.meta.url).pathname);
const DATA_DIR = path.resolve(__dirname, "../data");
const STORE_PATH = path.join(DATA_DIR, "state.json");

const DEFAULT_CONFIG = {
  mode: "inline",
  upstreamUrl: "http://127.0.0.1:5000/v1/chat/completions",
  blockedJsonPaths: [],
  retention: {
    maxSessions: 200,
    storePayloads: true
  },
  upstreamAuth: {
    enabled: false,
    headerName: "Authorization",
    tokenConfigured: false
  }
};

function envBootstrapConfig() {
  return {
    mode: process.env.MODE || DEFAULT_CONFIG.mode,
    upstreamUrl: process.env.UPSTREAM_URL || DEFAULT_CONFIG.upstreamUrl,
    retention: {
      maxSessions: Number(process.env.MAX_SESSIONS || DEFAULT_CONFIG.retention.maxSessions),
      storePayloads: process.env.STORE_PAYLOADS ? process.env.STORE_PAYLOADS === "true" : DEFAULT_CONFIG.retention.storePayloads
    },
    upstreamAuth: {
      enabled: Boolean(process.env.UPSTREAM_AUTH_TOKEN),
      headerName: process.env.UPSTREAM_AUTH_HEADER || "Authorization",
      tokenConfigured: Boolean(process.env.UPSTREAM_AUTH_TOKEN)
    }
  };
}

function ensureStore() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  if (!fs.existsSync(STORE_PATH)) {
    fs.writeFileSync(
      STORE_PATH,
      JSON.stringify(
        {
          config: { runtimeOverrides: {} },
          tokens: [],
          sessions: []
        },
        null,
        2
      )
    );
  }
}

function readStore() {
  ensureStore();
  return JSON.parse(fs.readFileSync(STORE_PATH, "utf8"));
}

function writeStore(state) {
  fs.writeFileSync(STORE_PATH, JSON.stringify(state, null, 2));
}

function mergeConfig(bootstrap, overrides) {
  return {
    ...DEFAULT_CONFIG,
    ...bootstrap,
    ...overrides,
    retention: {
      ...DEFAULT_CONFIG.retention,
      ...(bootstrap.retention || {}),
      ...(overrides.retention || {})
    },
    upstreamAuth: {
      ...DEFAULT_CONFIG.upstreamAuth,
      ...(bootstrap.upstreamAuth || {}),
      ...(overrides.upstreamAuth || {})
    }
  };
}

function assertUrl(value, field) {
  try {
    const u = new URL(value);
    if (!["http:", "https:"].includes(u.protocol)) {
      throw new Error("unsupported protocol");
    }
  } catch (_err) {
    throw new Error(`${field} must be a valid http(s) URL`);
  }
}

function validatePath(pathValue) {
  if (typeof pathValue !== "string") return false;
  // Safe subset for jsonpath-lite parser.
  return /^\$\.[A-Za-z0-9_\[\]\.\-]+$/.test(pathValue);
}

function sanitizePatch(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new Error("Request body must be an object");
  }

  const allowed = new Set(["mode", "upstreamUrl", "blockedJsonPaths", "retention", "upstreamAuth"]);
  const unknown = Object.keys(input).filter((k) => !allowed.has(k));
  if (unknown.length) {
    throw new Error(`Unknown config field(s): ${unknown.join(", ")}`);
  }

  const patch = {};

  if ("mode" in input) {
    if (input.mode !== "inline" && input.mode !== "queued") {
      throw new Error("mode must be one of: inline, queued");
    }
    patch.mode = input.mode;
  }

  if ("upstreamUrl" in input) {
    if (typeof input.upstreamUrl !== "string") {
      throw new Error("upstreamUrl must be a string");
    }
    const trimmed = input.upstreamUrl.trim();
    assertUrl(trimmed, "upstreamUrl");
    patch.upstreamUrl = trimmed;
  }

  if ("blockedJsonPaths" in input) {
    if (!Array.isArray(input.blockedJsonPaths)) {
      throw new Error("blockedJsonPaths must be an array of JSONPath strings");
    }
    const normalized = [...new Set(input.blockedJsonPaths.map((p) => (typeof p === "string" ? p.trim() : p)).filter(Boolean))];
    if (normalized.some((p) => !validatePath(p))) {
      throw new Error("blockedJsonPaths contains invalid entries. Use format like $.messages[0].content");
    }
    patch.blockedJsonPaths = normalized;
  }

  if ("retention" in input) {
    const r = input.retention;
    if (!r || typeof r !== "object" || Array.isArray(r)) {
      throw new Error("retention must be an object");
    }
    patch.retention = {};
    if ("maxSessions" in r) {
      if (!Number.isInteger(r.maxSessions) || r.maxSessions < 10 || r.maxSessions > 5000) {
        throw new Error("retention.maxSessions must be an integer between 10 and 5000");
      }
      patch.retention.maxSessions = r.maxSessions;
    }
    if ("storePayloads" in r) {
      if (typeof r.storePayloads !== "boolean") {
        throw new Error("retention.storePayloads must be a boolean");
      }
      patch.retention.storePayloads = r.storePayloads;
    }
  }

  if ("upstreamAuth" in input) {
    const a = input.upstreamAuth;
    if (!a || typeof a !== "object" || Array.isArray(a)) {
      throw new Error("upstreamAuth must be an object");
    }
    patch.upstreamAuth = {};
    if ("enabled" in a) {
      if (typeof a.enabled !== "boolean") {
        throw new Error("upstreamAuth.enabled must be a boolean");
      }
      patch.upstreamAuth.enabled = a.enabled;
    }
    if ("headerName" in a) {
      if (typeof a.headerName !== "string" || !/^[A-Za-z0-9\-]{2,64}$/.test(a.headerName.trim())) {
        throw new Error("upstreamAuth.headerName must be a valid header name");
      }
      patch.upstreamAuth.headerName = a.headerName.trim();
    }
    if ("token" in a || "tokenConfigured" in a) {
      throw new Error("upstreamAuth token values are write-protected; set UPSTREAM_AUTH_TOKEN in environment");
    }
  }

  return patch;
}

export function getConfig() {
  const state = readStore();
  const runtimeOverrides = state.config?.runtimeOverrides || {};
  const effective = mergeConfig(envBootstrapConfig(), runtimeOverrides);
  effective.upstreamAuth = {
    ...effective.upstreamAuth,
    tokenConfigured: Boolean(process.env.UPSTREAM_AUTH_TOKEN)
  };
  return {
    ...effective,
    sources: {
      mode: runtimeOverrides.mode ? "runtime" : "env/default",
      upstreamUrl: runtimeOverrides.upstreamUrl ? "runtime" : "env/default"
    }
  };
}

export function setConfig(nextConfig) {
  const patch = sanitizePatch(nextConfig);
  const state = readStore();
  const currentOverrides = state.config?.runtimeOverrides || {};
  state.config = {
    runtimeOverrides: {
      ...currentOverrides,
      ...patch,
      retention: {
        ...(currentOverrides.retention || {}),
        ...(patch.retention || {})
      },
      upstreamAuth: {
        ...(currentOverrides.upstreamAuth || {}),
        ...(patch.upstreamAuth || {})
      }
    }
  };
  writeStore(state);
  return getConfig();
}

export function resetConfig() {
  const state = readStore();
  state.config = { runtimeOverrides: {} };
  writeStore(state);
  return getConfig();
}

export function createToken() {
  const raw = crypto.randomBytes(24).toString("base64url");
  const hash = crypto.createHash("sha256").update(raw).digest("hex");
  const state = readStore();
  state.tokens.push({ hash, createdAt: new Date().toISOString(), active: true });
  writeStore(state);
  return raw;
}

export function verifyToken(rawToken) {
  if (!rawToken) return false;
  const hash = crypto.createHash("sha256").update(rawToken).digest("hex");
  return readStore().tokens.some((t) => t.hash === hash && t.active);
}

export function saveSession(entry) {
  const cfg = getConfig();
  const state = readStore();

  const sanitizedEntry = cfg.retention.storePayloads
    ? entry
    : {
        ...entry,
        incoming: { redacted: true },
        transformed: { redacted: true },
        upstreamBody: { redacted: true }
      };

  state.sessions.unshift(sanitizedEntry);
  state.sessions = state.sessions.slice(0, cfg.retention.maxSessions);
  writeStore(state);
}

export function listSessions() {
  return readStore().sessions;
}
