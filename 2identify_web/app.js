import {
  CATEGORY_LABEL,
  SEVERITY_LABEL,
  STATE_COPY,
  arrivedCritical,
  countAlerts,
  filterAlerts,
  formatAgo,
  formatClock,
  fromSnapshot,
  mergeAlerts,
  overallState,
  placeLine,
  reconnectDelay,
  statusLabel,
} from "./panel.js";

const STREAM_URL = "/api/public/stream";
const SNAPSHOT_URL = "/api/public/alerts";
// The server pings every 15 s; two missed pings mean the link is dead.
const STALE_AFTER_MS = 35_000;
const ARRIVAL_MS = 12_000;

const MARK = { critical: "#i-critical", warning: "#i-warning", inconclusive: "#i-inconclusive" };
const ICON = {
  safe: "#i-safe",
  critical: "#i-critical",
  warning: "#i-warning",
  inconclusive: "#i-inconclusive",
  connecting: "#i-connecting",
  offline: "#i-offline",
};
const EMPTY = {
  all: ["Nenhum alerta até agora", "Quando a IA detectar um risco, ele aparece aqui na hora."],
  open: ["Nenhum alerta em aberto", "Tudo o que a IA sinalizou já foi tratado."],
  critical: ["Nenhum alerta crítico", "Quedas e riscos graves aparecem aqui em destaque."],
  closed: ["Nenhum alerta encerrado", "Alertas tratados pela equipe aparecem aqui."],
};

const $ = (id) => document.getElementById(id);
const view = {
  link: $("link"),
  linkText: $("link-text"),
  now: $("now"),
  nowIcon: $("now-icon"),
  nowWord: $("now-word"),
  nowHint: $("now-hint"),
  nowLead: $("now-lead"),
  nowLeadTitle: $("now-lead-title"),
  nowLeadPlace: $("now-lead-place"),
  nowMeta: $("now-meta"),
  notice: $("notice"),
  list: $("list"),
  loading: $("loading"),
  empty: $("empty"),
  emptyTitle: $("empty-title"),
  emptyCopy: $("empty-copy"),
  arrival: $("arrival"),
  arrivalTitle: $("arrival-title"),
  arrivalPlace: $("arrival-place"),
  row: $("row"),
  filters: [...document.querySelectorAll("[data-filter]")],
  counts: [...document.querySelectorAll("[data-count]")],
};

const state = {
  alerts: new Map(),
  loaded: false,
  link: "connecting", // connecting | live | reconnecting | offline | source-down
  sourceOnline: true,
  filter: "all",
  lastData: 0,
  fresh: new Set(),
  shownState: null,
};

let source = null;
let attempts = 0;
let retryTimer = 0;
let watchdog = 0;
let arrivalTimer = 0;

// ---------------------------------------------------------------- stream

function connect() {
  clearTimeout(retryTimer);
  source?.close();
  if (!("EventSource" in window)) {
    poll();
    return;
  }
  source = new EventSource(STREAM_URL);
  source.addEventListener("open", () => {
    attempts = 0;
  });
  source.addEventListener("snapshot", (event) => {
    const data = parse(event);
    if (!data) return;
    // A fresh snapshot replaces local state: nothing duplicated, nothing stale.
    state.alerts = fromSnapshot(data.alerts);
    state.loaded = true;
    state.sourceOnline = data.source_online !== false;
    alive();
  });
  source.addEventListener("alerts", (event) => {
    const data = parse(event);
    if (!data) return;
    const incoming = data.alerts ?? [];
    const critical = arrivedCritical(state.alerts, incoming);
    for (const alert of incoming) if (!state.alerts.has(alert.id)) state.fresh.add(alert.id);
    state.alerts = mergeAlerts(state.alerts, incoming, data.removed ?? []);
    alive();
    if (critical.length) announce(critical[critical.length - 1]);
  });
  source.addEventListener("status", (event) => {
    const data = parse(event);
    if (!data) return;
    state.sourceOnline = data.source_online !== false;
    alive();
  });
  source.addEventListener("ping", () => alive());
  source.addEventListener("error", () => {
    if (source.readyState === EventSource.CLOSED) {
      // The browser gave up (server restart, panel full): retry with backoff.
      scheduleReconnect();
    } else {
      setLink(navigator.onLine === false ? "offline" : "reconnecting");
    }
  });
}

function scheduleReconnect() {
  source?.close();
  source = null;
  setLink(navigator.onLine === false ? "offline" : "reconnecting");
  clearTimeout(retryTimer);
  retryTimer = setTimeout(connect, reconnectDelay(attempts));
  attempts += 1;
}

async function poll() {
  try {
    const response = await fetch(SNAPSHOT_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(String(response.status));
    const data = await response.json();
    state.alerts = fromSnapshot(data.alerts);
    state.loaded = true;
    state.sourceOnline = data.source_online !== false;
    alive();
    retryTimer = setTimeout(poll, 4_000);
  } catch {
    setLink("reconnecting");
    retryTimer = setTimeout(poll, reconnectDelay(attempts++));
  }
}

function parse(event) {
  try {
    return JSON.parse(event.data);
  } catch {
    return null;
  }
}

function alive() {
  state.lastData = Date.now();
  setLink(state.sourceOnline ? "live" : "source-down", false);
  clearTimeout(watchdog);
  watchdog = setTimeout(() => {
    if (Date.now() - state.lastData >= STALE_AFTER_MS) scheduleReconnect();
  }, STALE_AFTER_MS);
  render();
}

function setLink(link, rerender = true) {
  if (state.link === link) return;
  state.link = link;
  if (rerender) render();
}

// ---------------------------------------------------------------- render

const LINK_TEXT = {
  connecting: "Conectando",
  live: "Ao vivo",
  reconnecting: "Reconectando",
  offline: "Sem internet",
  "source-down": "Sistema sem resposta",
};

function render() {
  const now = Date.now();
  const alerts = [...state.alerts.values()];
  const live = state.link === "live";

  view.link.dataset.link = state.link;
  view.linkText.textContent = LINK_TEXT[state.link];

  renderNow(overallState(alerts, { live, loaded: state.loaded, now }));
  renderNotice();

  const counts = countAlerts(alerts, now);
  for (const node of view.counts) node.textContent = String(counts[node.dataset.count] ?? 0);
  for (const button of view.filters) {
    button.setAttribute("aria-pressed", String(button.dataset.filter === state.filter));
  }

  view.loading.hidden = state.loaded;
  const visible = filterAlerts(alerts, state.filter, now);
  view.list.replaceChildren(...visible.map((alert) => renderRow(alert, now)));
  state.fresh.clear();
  const [title, copy] = EMPTY[state.filter];
  view.emptyTitle.textContent = title;
  view.emptyCopy.textContent = copy;
  view.empty.hidden = !state.loaded || visible.length > 0;
}

function renderNow({ state: current, lead, open }) {
  const copy = STATE_COPY[current];
  document.body.dataset.state = current;
  view.now.dataset.state = current;
  view.nowIcon.setAttribute("href", ICON[current]);
  view.nowWord.textContent = copy.word;
  view.nowHint.textContent = current === "safe" || !lead ? copy.hint : openText(open);
  if (state.shownState && state.shownState !== current) {
    view.now.classList.remove("is-changed");
    void view.now.offsetWidth; // restart the one-shot animation
    view.now.classList.add("is-changed");
  }
  state.shownState = current;

  view.nowLead.hidden = !lead;
  if (lead) {
    view.nowLeadTitle.textContent = lead.title;
    const place = placeLine(lead).join(", ");
    view.nowLeadPlace.textContent = [place, `às ${formatClock(lead.created_at)}`]
      .filter(Boolean).join(" ");
  }
  view.nowMeta.textContent = state.lastData
    ? `Atualizado às ${formatClock(new Date(state.lastData).toISOString())}`
    : "";
}

function openText(open) {
  return open === 1 ? "1 alerta em aberto" : `${open} alertas em aberto`;
}

function renderNotice() {
  const messages = {
    reconnecting: "A conexão caiu. Reconectando e mostrando os últimos dados recebidos.",
    offline: "Seu celular está sem internet. O painel volta sozinho quando a conexão voltar.",
    "source-down": "O sistema de alertas não está respondendo. Os dados abaixo podem estar desatualizados.",
  };
  const text = state.loaded ? messages[state.link] : null;
  view.notice.hidden = !text;
  view.notice.textContent = text ?? "";
}

function renderRow(alert, now) {
  const node = view.row.content.firstElementChild.cloneNode(true);
  node.dataset.id = String(alert.id);
  node.dataset.severity = alert.severity;
  node.dataset.closed = String(alert.status === "encerrado" || alert.condition === "resolvida");
  if (state.fresh.has(alert.id)) node.classList.add("is-new");
  const clock = node.querySelector(".alert-clock");
  clock.dateTime = alert.created_at;
  clock.textContent = formatClock(alert.created_at);
  node.querySelector(".alert-ago").textContent = formatAgo(alert.created_at, now);
  node.querySelector(".alert-mark use").setAttribute("href", MARK[alert.severity] ?? MARK.warning);
  node.querySelector(".alert-severity").textContent = SEVERITY_LABEL[alert.severity] ?? "Atenção";
  node.querySelector(".alert-category").textContent = CATEGORY_LABEL[alert.category] ?? "Segurança";
  node.querySelector(".alert-title").textContent = alert.title;
  const place = placeLine(alert);
  if (place.length) {
    node.querySelector(".alert-place").hidden = false;
    node.querySelector(".alert-place-text").textContent = place.join(", ");
  }
  const status = node.querySelector(".alert-status");
  status.textContent = statusLabel(alert);
  status.dataset.status = alert.status === "novo" && alert.condition !== "resolvida"
    ? "new"
    : "done";
  return node;
}

function announce(alert) {
  view.arrivalTitle.textContent = `Alerta crítico: ${alert.title}`;
  view.arrivalPlace.textContent = placeLine(alert).join(", ");
  view.arrival.hidden = false;
  clearTimeout(arrivalTimer);
  arrivalTimer = setTimeout(() => {
    view.arrival.hidden = true;
  }, ARRIVAL_MS);
}

// ---------------------------------------------------------------- QR

async function setupShare() {
  const share = $("share");
  if (!share) return;
  let url = location.origin;
  try {
    const response = await fetch("/api/public/config", { cache: "no-store" });
    if (response.ok) url = (await response.json()).public_url || url;
  } catch {
    // The page's own address is the best fallback.
  }
  // Only offer the QR when it leads somewhere the audience's phones can reach.
  if (/^(localhost|127\.|\[::1\]$|0\.0\.0\.0$)/.test(new URL(url).hostname)) return;
  $("share-qr").src = `/api/public/qr.svg?url=${encodeURIComponent(url)}`;
  $("share-url").textContent = url.replace(/^https?:\/\//, "");
  share.hidden = false;
}

// ---------------------------------------------------------------- wiring

for (const button of view.filters) {
  button.addEventListener("click", () => {
    state.filter = button.dataset.filter;
    render();
  });
}
$("arrival-close").addEventListener("click", () => {
  view.arrival.hidden = true;
});
window.addEventListener("offline", () => setLink("offline"));
window.addEventListener("online", () => scheduleReconnectNow());
document.addEventListener("visibilitychange", () => {
  // Phones freeze background tabs; come back with a fresh snapshot.
  if (document.visibilityState === "visible" && Date.now() - state.lastData > STALE_AFTER_MS) {
    scheduleReconnectNow();
  }
});
// Keeps relative times and the open-alert window current between events.
setInterval(render, 30_000);

function scheduleReconnectNow() {
  attempts = 0;
  connect();
}

render();
connect();
setupShare();
