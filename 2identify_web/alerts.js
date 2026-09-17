export class ApiRequestError extends Error {
  constructor(status, message = "A API não concluiu a solicitação.") {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

function normalizedBaseUrl(value) {
  const parsed = new URL(value);
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new TypeError("A origem da API precisa usar HTTP ou HTTPS.");
  }
  return parsed.origin;
}

export function createAlertsApi(baseUrl, fetchFn = globalThis.fetch) {
  const origin = normalizedBaseUrl(baseUrl);

  async function request(path, options) {
    const response = await fetchFn(`${origin}${path}`, options);
    if (!response.ok) {
      throw new ApiRequestError(response.status);
    }
    return response.json();
  }

  return Object.freeze({
    async login(username, password) {
      const payload = await request("/auth/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (typeof payload.access_token !== "string" || !payload.access_token) {
        throw new ApiRequestError(502, "A API retornou uma sessão inválida.");
      }
      return { accessToken: payload.access_token };
    },

    async list(accessToken) {
      const items = [];
      const limit = 100;
      for (let offset = 0; ; offset += limit) {
        const payload = await request(`/admin/alerts?limit=${limit}&offset=${offset}`, {
          method: "GET",
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (!Array.isArray(payload.items) || !Number.isInteger(payload.total) || payload.total < 0) {
          throw new ApiRequestError(502, "A API retornou uma lista de alertas inválida.");
        }
        items.push(...payload.items);
        if (items.length >= payload.total) {
          return items;
        }
        if (payload.items.length !== limit) {
          throw new ApiRequestError(502, "A API interrompeu a paginação dos alertas.");
        }
      }
    },
  });
}

export class SessionTokenStore {
  static key = "2identify.admin.jwt";

  constructor(storage) {
    this.storage = storage;
  }

  read() {
    return this.storage.getItem(SessionTokenStore.key);
  }

  save(token) {
    this.storage.setItem(SessionTokenStore.key, token);
  }

  clear() {
    this.storage.removeItem(SessionTokenStore.key);
  }
}

export function filterAlerts(items, filter) {
  if (filter === "critical") {
    return items.filter((item) => item.status !== "encerrado" && item.level === "critical");
  }
  if (filter === "attention") {
    return items.filter((item) => item.status !== "encerrado" && item.level !== "critical");
  }
  if (filter === "resolved") {
    return items.filter((item) => item.status === "encerrado");
  }
  return [...items];
}

function formattedDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Horário indisponível";
  }
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

export function alertCardModel(alert) {
  const occurrence = alert.occurrence ?? {};
  const employee = occurrence.employee ?? null;
  const operation = alert.operational_context ?? null;
  const sector = employee?.sector?.name ?? occurrence.camera?.sector?.name ?? "Não informado";
  const isResolved = alert.status === "encerrado";
  const isCritical = alert.level === "critical";
  return Object.freeze({
    id: alert.id,
    severity: isResolved ? "resolved" : isCritical ? "critical" : "attention",
    severityLabel: isResolved ? "Resolvido" : isCritical ? "Crítico" : "Atenção",
    statusLabel: isResolved ? "Ocorrência encerrada" : alert.status === "lido" ? "Confirmado" : "Novo",
    summary: alert.summary || "Alerta de segurança",
    employee: employee?.name ?? "Não identificado",
    operation: operation?.operation_name ?? "Não informada",
    sector,
    camera: occurrence.camera?.name ?? "Não informada",
    occurredAt: formattedDate(alert.created_at),
    hasEvidence: Boolean(occurrence.image_reference || occurrence.video_reference),
  });
}

export function createPolling(load, scheduler = globalThis, intervalMs = 30_000) {
  let handle = null;
  return Object.freeze({
    start() {
      if (handle === null) {
        handle = scheduler.setInterval(() => load(), intervalMs);
      }
    },
    stop() {
      if (handle !== null) {
        scheduler.clearInterval(handle);
        handle = null;
      }
    },
  });
}
