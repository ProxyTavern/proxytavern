import test from "node:test";
import assert from "node:assert/strict";
import request from "supertest";
import fs from "node:fs";
import path from "node:path";
import { createApp } from "../src/server.js";

const statePath = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../data/state.json");

function resetState() {
  fs.mkdirSync(path.dirname(statePath), { recursive: true });
  fs.writeFileSync(statePath, JSON.stringify({ config: { runtimeOverrides: {} }, tokens: [], sessions: [] }, null, 2));
}

test.beforeEach(() => {
  resetState();
  delete process.env.UPSTREAM_URL;
  delete process.env.UPSTREAM_AUTH_TOKEN;
  delete process.env.UPSTREAM_AUTH_HEADER;
});

test("GET /api/config returns safe auth metadata only", async () => {
  process.env.UPSTREAM_AUTH_TOKEN = "super-secret";
  const app = createApp();
  const res = await request(app).get("/api/config");
  assert.equal(res.status, 200);
  assert.equal(res.body.upstreamAuth.tokenConfigured, true);
  assert.equal("token" in res.body.upstreamAuth, false);
});

test("POST /api/config validates invalid mode and JSONPath", async () => {
  const app = createApp();
  const r1 = await request(app).post("/api/config").send({ mode: "bad" });
  assert.equal(r1.status, 422);
  assert.match(r1.body.message, /mode must be one of/);

  const r2 = await request(app).post("/api/config").send({ blockedJsonPaths: ["messages[0]"] });
  assert.equal(r2.status, 422);
  assert.match(r2.body.message, /invalid entries/);
});

test("POST /api/config applies runtime override precedence over env", async () => {
  process.env.UPSTREAM_URL = "http://env.example/v1/chat/completions";
  const app = createApp();
  const before = await request(app).get("/api/config");
  assert.equal(before.body.upstreamUrl, "http://env.example/v1/chat/completions");

  const updated = await request(app)
    .post("/api/config")
    .send({ upstreamUrl: "http://runtime.example/v1/chat/completions", mode: "queued" });

  assert.equal(updated.status, 200);
  assert.equal(updated.body.upstreamUrl, "http://runtime.example/v1/chat/completions");
  assert.equal(updated.body.mode, "queued");
  assert.equal(updated.body.sources.upstreamUrl, "runtime");
});

test("POST /api/config/reset clears overrides", async () => {
  const app = createApp();
  await request(app).post("/api/config").send({ mode: "queued" });
  const reset = await request(app).post("/api/config/reset");
  assert.equal(reset.status, 200);
  assert.equal(reset.body.mode, "inline");
});
