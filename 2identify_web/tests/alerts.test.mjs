import assert from "node:assert/strict";
import test from "node:test";

import {
  ApiRequestError,
  SessionTokenStore,
  alertCardModel,
  createAlertsApi,
  createPolling,
  filterAlerts,
} from "../alerts.js";
import { MobileAlertsController } from "../controller.js";

const alerts = [
  {
    id: 1,
    level: "critical",
    status: "nao_lido",
    summary: "Pessoa na área",
    created_at: "2026-09-10T10:00:00Z",
    occurrence: {
      employee: { name: "Ana", sector: { name: "Montagem" } },
      image_reference: "C:\\evidencias\\alerta.jpg",
      video_reference: null,
    },
    operational_context: { operation_id: 4, operation_name: "Soldagem" },
  },
  {
    id: 2,
    level: "warning",
    status: "lido",
    summary: "Postura inadequada",
    created_at: "2026-09-10T10:01:00Z",
    occurrence: { employee: null, image_reference: null, video_reference: null },
    operational_context: null,
  },
  {
    id: 3,
    level: "critical",
    status: "encerrado",
    summary: "Ocorrência encerrada",
    created_at: "2026-09-10T10:02:00Z",
    occurrence: { employee: null, image_reference: null, video_reference: null },
    operational_context: null,
  },
];

test("filters separate active critical, attention, resolved and all alerts", () => {
  assert.deepEqual(filterAlerts(alerts, "all").map((item) => item.id), [1, 2, 3]);
  assert.deepEqual(filterAlerts(alerts, "critical").map((item) => item.id), [1]);
  assert.deepEqual(filterAlerts(alerts, "attention").map((item) => item.id), [2]);
  assert.deepEqual(filterAlerts(alerts, "resolved").map((item) => item.id), [3]);
});

test("card model indicates local evidence without exposing a broken link", () => {
  const card = alertCardModel(alerts[0]);

  assert.equal(card.operation, "Soldagem");
  assert.equal(card.employee, "Ana");
  assert.equal(card.sector, "Montagem");
  assert.equal(card.hasEvidence, true);
  assert.equal("evidenceUrl" in card, false);
  assert.equal(JSON.stringify(card).includes("C:\\evidencias"), false);
});

test("session token store uses only its injected session storage", () => {
  const values = new Map();
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  const session = new SessionTokenStore(storage);

  session.save("jwt-value");
  assert.equal(session.read(), "jwt-value");
  session.clear();
  assert.equal(session.read(), null);
});

test("API client uses existing admin endpoints and never sends token in URL", async () => {
  const requests = [];
  const fetchFn = async (url, options) => {
    requests.push({ url, options });
    return {
      ok: true,
      status: 200,
      json: async () =>
        url.endsWith("/login")
          ? { access_token: "admin-jwt", token_type: "bearer" }
          : { items: alerts, total: 3, limit: 100, offset: 0 },
    };
  };
  const api = createAlertsApi("http://192.168.1.20:8000", fetchFn);

  const login = await api.login("admin", "senha");
  const listed = await api.list(login.accessToken);

  assert.equal(requests[0].url, "http://192.168.1.20:8000/auth/admin/login");
  assert.equal(requests[1].url, "http://192.168.1.20:8000/admin/alerts?limit=100&offset=0");
  assert.equal(requests[1].options.headers.Authorization, "Bearer admin-jwt");
  assert.equal(requests[1].url.includes("admin-jwt"), false);
  assert.equal(listed.length, 3);
});

test("401 is classified so the controller can expire the session", async () => {
  const api = createAlertsApi("http://localhost:8000", async () => ({
    ok: false,
    status: 401,
    json: async () => ({ detail: "credencial inválida" }),
  }));

  await assert.rejects(() => api.list("expired"), (error) => {
    assert.equal(error instanceof ApiRequestError, true);
    assert.equal(error.status, 401);
    return true;
  });
});

test("controller supports login, manual refresh, filters and logout", async () => {
  let listCalls = 0;
  const api = {
    login: async () => ({ accessToken: "jwt" }),
    list: async () => {
      listCalls += 1;
      return alerts;
    },
  };
  let token = null;
  const session = {
    read: () => token,
    save: (value) => { token = value; },
    clear: () => { token = null; },
  };
  const rendered = [];
  const view = {
    showLogin: () => rendered.push("login"),
    showAlerts: () => rendered.push("alerts"),
    setLoading: () => {},
    renderAlerts: (items) => rendered.push(items.map((item) => item.id)),
    showError: (message) => rendered.push(message),
  };
  let stopped = false;
  const polling = { start: () => {}, stop: () => { stopped = true; } };
  const controller = new MobileAlertsController({ api, session, view, polling });

  await controller.login("admin", "senha");
  controller.setFilter("critical");
  await controller.refresh();
  controller.logout();

  assert.equal(listCalls, 2);
  assert.equal(token, null);
  assert.equal(stopped, true);
  assert.deepEqual(rendered.at(-2), [1]);
  assert.equal(rendered.at(-1), "login");
});

test("controller clears an expired session and reports unavailable API", async () => {
  const events = [];
  let token = "expired";
  const session = {
    read: () => token,
    save: () => {},
    clear: () => { token = null; },
  };
  const view = {
    showLogin: () => events.push("login"),
    showAlerts: () => {},
    setLoading: () => {},
    renderAlerts: () => {},
    showError: (message) => events.push(message),
  };
  const polling = { start: () => {}, stop: () => {} };
  const expired = new MobileAlertsController({
    api: { login: async () => ({}), list: async () => { throw new ApiRequestError(401); } },
    session,
    view,
    polling,
  });
  await expired.restore();

  assert.equal(token, null);
  assert.equal(events.at(-1), "login");

  const unavailable = new MobileAlertsController({
    api: { login: async () => ({}), list: async () => { throw new TypeError("offline"); } },
    session: { ...session, read: () => "jwt" },
    view,
    polling,
  });
  await unavailable.restore();
  assert.equal(events.at(-1), "Não foi possível acessar a API.");
});

test("polling runs lightly and stop cancels the scheduled callback", async () => {
  let callback;
  let cleared = null;
  const scheduler = {
    setInterval: (fn, milliseconds) => {
      assert.equal(milliseconds, 30_000);
      callback = fn;
      return 17;
    },
    clearInterval: (id) => { cleared = id; },
  };
  let loads = 0;
  const polling = createPolling(async () => { loads += 1; }, scheduler, 30_000);

  polling.start();
  await callback();
  polling.stop();

  assert.equal(loads, 1);
  assert.equal(cleared, 17);
});
