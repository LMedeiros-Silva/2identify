// Pure panel logic: no DOM, no network, so it runs under `node --test`.

export const OPEN_WINDOW_HOURS = 12;

const SEVERITY_RANK = { critical: 3, warning: 2, inconclusive: 1 };

export const STATE_COPY = {
  critical: { word: "CRÍTICO", hint: "Alerta crítico em aberto" },
  warning: { word: "ATENÇÃO", hint: "Alerta de segurança em aberto" },
  inconclusive: { word: "INCONCLUSIVO", hint: "A IA não conseguiu confirmar a segurança" },
  safe: { word: "SEGURO", hint: "Nenhum alerta em aberto" },
  connecting: { word: "CONECTANDO", hint: "Buscando os alertas da IA" },
  offline: { word: "SEM CONEXÃO", hint: "O estado atual não pode ser confirmado" },
};

export const CATEGORY_LABEL = {
  fall: "Queda",
  ppe: "EPI",
  risk_area: "Área de risco",
  ergonomics: "Ergonomia",
  monitoring: "Monitoramento",
  inconclusive: "Verificação de EPI",
  safety: "Segurança",
};

export const SEVERITY_LABEL = {
  critical: "Crítico",
  warning: "Atenção",
  inconclusive: "Inconclusivo",
};

export const FILTERS = ["all", "open", "critical", "closed"];

function time(value) {
  const parsed = Date.parse(value ?? "");
  return Number.isNaN(parsed) ? 0 : parsed;
}

// Applies a batch of alerts by id; an older copy never overwrites a newer one.
export function mergeAlerts(current, incoming, removed = []) {
  const next = new Map(current);
  for (const id of removed) next.delete(id);
  for (const alert of incoming) {
    if (!alert || !Number.isInteger(alert.id)) continue;
    const known = next.get(alert.id);
    if (known && time(known.updated_at) > time(alert.updated_at)) continue;
    next.set(alert.id, alert);
  }
  return next;
}

export function fromSnapshot(alerts) {
  return mergeAlerts(new Map(), alerts ?? []);
}

export function sortAlerts(alerts) {
  return [...alerts].sort(
    (a, b) => time(b.created_at) - time(a.created_at) || b.id - a.id,
  );
}

export function isClosed(alert) {
  return alert.status === "encerrado" || alert.condition === "resolvida";
}

export function isOpen(alert, now = Date.now()) {
  return !isClosed(alert) && now - time(alert.created_at) <= OPEN_WINDOW_HOURS * 3_600_000;
}

// The most severe open alert decides the state; ties go to the newest.
export function overallState(alerts, { live = true, loaded = true, now = Date.now() } = {}) {
  if (!loaded) return { state: "connecting", lead: null, open: 0 };
  if (!live) return { state: "offline", lead: null, open: 0 };
  const open = sortAlerts(alerts).filter((alert) => isOpen(alert, now));
  let lead = null;
  for (const alert of open) {
    if (!lead || (SEVERITY_RANK[alert.severity] ?? 0) > (SEVERITY_RANK[lead.severity] ?? 0)) {
      lead = alert;
    }
  }
  return { state: lead ? lead.severity : "safe", lead, open: open.length };
}

export function sameDay(value, now = Date.now()) {
  const a = new Date(time(value));
  const b = new Date(now);
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate();
}

export function countAlerts(alerts, now = Date.now()) {
  const counts = { all: 0, open: 0, critical: 0, closed: 0, today: 0 };
  for (const alert of alerts) {
    counts.all += 1;
    if (isOpen(alert, now)) counts.open += 1;
    if (alert.severity === "critical") counts.critical += 1;
    if (isClosed(alert)) counts.closed += 1;
    if (sameDay(alert.created_at, now)) counts.today += 1;
  }
  return counts;
}

export function filterAlerts(alerts, filter, now = Date.now()) {
  const sorted = sortAlerts(alerts);
  if (filter === "open") return sorted.filter((alert) => isOpen(alert, now));
  if (filter === "critical") return sorted.filter((alert) => alert.severity === "critical");
  if (filter === "closed") return sorted.filter(isClosed);
  return sorted;
}

// Critical alerts that just appeared, for the arrival banner.
export function arrivedCritical(previous, incoming, now = Date.now()) {
  return incoming.filter(
    (alert) => alert.severity === "critical" && !previous.has(alert.id) && isOpen(alert, now),
  );
}

export function statusLabel(alert) {
  if (alert.status === "encerrado") return "Encerrado";
  if (alert.condition === "resolvida") return "Condição resolvida";
  if (alert.status === "confirmado") return "Equipe ciente";
  return "Novo";
}

export function formatClock(value) {
  const parsed = time(value);
  if (!parsed) return "--:--";
  return new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" })
    .format(new Date(parsed));
}

export function formatAgo(value, now = Date.now()) {
  const parsed = time(value);
  if (!parsed) return "";
  const minutes = Math.max(0, Math.floor((now - parsed) / 60_000));
  if (minutes < 1) return "agora";
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `há ${hours} h`;
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit" })
    .format(new Date(parsed));
}

export function placeLine(alert) {
  return [alert.camera, alert.sector, alert.operation].filter(Boolean);
}

// Backoff for manual reconnects: 2 s, 4 s, 8 s … capped at 30 s.
export function reconnectDelay(attempt) {
  return Math.min(30_000, 2_000 * 2 ** Math.max(0, attempt));
}
