import assert from "node:assert/strict";
import test from "node:test";

import {
  arrivedCritical,
  countAlerts,
  filterAlerts,
  formatAgo,
  fromSnapshot,
  mergeAlerts,
  overallState,
  reconnectDelay,
  sortAlerts,
  statusLabel,
} from "../panel.js";

const NOW = Date.parse("2026-10-24T15:00:00.000Z");

function alert(id, overrides = {}) {
  const created = new Date(NOW - (100 - id) * 60_000).toISOString();
  return {
    id,
    category: "ppe",
    severity: "warning",
    title: "EPI obrigatório ausente",
    status: "novo",
    condition: "ativa",
    camera: "Câmera 1",
    sector: null,
    operation: null,
    created_at: created,
    updated_at: created,
    ...overrides,
  };
}

test("merging the same alert twice keeps a single entry", () => {
  const first = mergeAlerts(new Map(), [alert(1)]);
  const again = mergeAlerts(first, [alert(1), alert(1)]);
  assert.equal(again.size, 1);
});

test("an older copy never overwrites a newer status", () => {
  const closed = alert(1, { status: "encerrado", updated_at: "2026-10-24T14:59:00.000Z" });
  const stale = alert(1, { status: "novo", updated_at: "2026-10-24T14:00:00.000Z" });
  const merged = mergeAlerts(fromSnapshot([closed]), [stale]);
  assert.equal(merged.get(1).status, "encerrado");
});

test("status changes from the stream replace the card in place", () => {
  const base = fromSnapshot([alert(1)]);
  const merged = mergeAlerts(base, [
    alert(1, { status: "confirmado", updated_at: "2026-10-24T14:58:00.000Z" }),
  ]);
  assert.equal(merged.size, 1);
  assert.equal(statusLabel(merged.get(1)), "Equipe ciente");
});

test("removed ids leave the panel", () => {
  const merged = mergeAlerts(fromSnapshot([alert(1), alert(2)]), [], [1]);
  assert.deepEqual([...merged.keys()], [2]);
});

test("a snapshot after reconnecting replaces everything", () => {
  const before = fromSnapshot([alert(1), alert(2)]);
  const after = fromSnapshot([alert(2), alert(3)]);
  assert.notEqual(before, after);
  assert.deepEqual([...after.keys()].sort(), [2, 3]);
});

test("alerts are listed newest first, ties broken by id", () => {
  const same = "2026-10-24T14:00:00.000Z";
  const sorted = sortAlerts([
    alert(1),
    alert(5),
    alert(3, { created_at: same }),
    alert(4, { created_at: same }),
  ]);
  assert.deepEqual(sorted.map((item) => item.id), [4, 3, 5, 1]);
});

test("state is safe only when connected and nothing is open", () => {
  const closed = alert(1, { status: "encerrado" });
  assert.equal(overallState([closed], { now: NOW }).state, "safe");
  assert.equal(overallState([], { live: false, now: NOW }).state, "offline");
  assert.equal(overallState([], { loaded: false, now: NOW }).state, "connecting");
});

test("the most severe open alert leads the state", () => {
  const result = overallState(
    [
      alert(1, { severity: "inconclusive", category: "inconclusive" }),
      alert(2, { severity: "critical", category: "fall", title: "Queda detectada" }),
      alert(3),
    ],
    { now: NOW },
  );
  assert.equal(result.state, "critical");
  assert.equal(result.lead.id, 2);
  assert.equal(result.open, 3);
});

test("resolved conditions and old alerts do not keep the panel red", () => {
  const resolved = alert(1, { severity: "critical", condition: "resolvida" });
  const old = alert(2, {
    severity: "critical",
    created_at: "2026-10-23T01:00:00.000Z",
    updated_at: "2026-10-23T01:00:00.000Z",
  });
  assert.equal(overallState([resolved, old], { now: NOW }).state, "safe");
});

test("filters and counts agree", () => {
  const alerts = [
    alert(1, { status: "encerrado" }),
    alert(2, { severity: "critical" }),
    alert(3, { condition: "resolvida" }),
    alert(4),
  ];
  const counts = countAlerts(alerts, NOW);
  assert.deepEqual(
    { all: counts.all, open: counts.open, critical: counts.critical, closed: counts.closed },
    { all: 4, open: 2, critical: 1, closed: 2 },
  );
  assert.deepEqual(filterAlerts(alerts, "open", NOW).map((item) => item.id), [4, 2]);
  assert.deepEqual(filterAlerts(alerts, "critical", NOW).map((item) => item.id), [2]);
  assert.deepEqual(filterAlerts(alerts, "closed", NOW).map((item) => item.id), [3, 1]);
});

test("only critical alerts that just arrived trigger the banner", () => {
  const known = fromSnapshot([alert(1, { severity: "critical" })]);
  const arrived = arrivedCritical(
    known,
    [alert(1, { severity: "critical" }), alert(2, { severity: "critical" }), alert(3)],
    NOW,
  );
  assert.deepEqual(arrived.map((item) => item.id), [2]);
});

test("relative time reads naturally", () => {
  assert.equal(formatAgo(new Date(NOW - 20_000).toISOString(), NOW), "agora");
  assert.equal(formatAgo(new Date(NOW - 5 * 60_000).toISOString(), NOW), "há 5 min");
  assert.equal(formatAgo(new Date(NOW - 3 * 3_600_000).toISOString(), NOW), "há 3 h");
});

test("reconnect backoff grows and is capped", () => {
  assert.deepEqual([0, 1, 2, 3, 10].map(reconnectDelay), [2000, 4000, 8000, 16000, 30000]);
});
