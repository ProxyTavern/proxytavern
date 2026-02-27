import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const htmlPath = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../web/index.html");

test("UI exposes config controls and actions", () => {
  const html = fs.readFileSync(htmlPath, "utf8");
  for (const needle of [
    "id=\"upstreamUrl\"",
    "id=\"mode\"",
    "id=\"paths\"",
    "id=\"authEnabled\"",
    "id=\"authHeaderName\"",
    "id=\"maxSessions\"",
    "id=\"storePayloads\"",
    "id=\"save\"",
    "id=\"reset\"",
    "id=\"test\""
  ]) {
    assert.ok(html.includes(needle), "missing UI element: " + needle);
  }
});
