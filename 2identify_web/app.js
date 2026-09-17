import {
  SessionTokenStore,
  alertCardModel,
  createAlertsApi,
  createPolling,
} from "./alerts.js";
import { MobileAlertsController } from "./controller.js";

const element = (id) => document.getElementById(id);
const loginView = element("login-view");
const alertsView = element("alerts-view");
const loginForm = element("login-form");
const loginError = element("login-error");
const alertsError = element("alerts-error");
const loadingState = element("loading-state");
const alertsList = element("alerts-list");
const summaryCount = element("summary-count");
const lastUpdated = element("last-updated");
const loginButton = element("login-button");
const refreshButton = element("refresh-button");
const filterButtons = [...document.querySelectorAll("[data-filter]")];

function textElement(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = value;
  return node;
}

function detail(label, value) {
  const wrapper = document.createElement("div");
  wrapper.append(textElement("dt", "", label), textElement("dd", "", value));
  return wrapper;
}

function alertCard(alert) {
  const item = alertCardModel(alert);
  const card = document.createElement("article");
  card.className = `alert-card ${item.severity}`;

  const header = document.createElement("div");
  header.className = "card-header";
  header.append(
    textElement("span", "severity", item.severityLabel),
    textElement("time", "card-time", item.occurredAt),
  );
  const title = textElement("h2", "", item.summary);
  const details = document.createElement("dl");
  details.className = "details-grid";
  details.append(
    detail("Funcionário", item.employee),
    detail("Operação", item.operation),
    detail("Setor", item.sector),
    detail("Câmera", item.camera),
    detail("Status", item.statusLabel),
  );
  card.append(header, title, details);
  if (item.hasEvidence) {
    card.append(textElement("span", "evidence-badge", "Evidência registrada"));
  }
  return card;
}

const view = {
  showLogin() {
    loginView.hidden = false;
    alertsView.hidden = true;
    element("password").value = "";
  },
  showAlerts() {
    loginError.hidden = true;
    loginView.hidden = true;
    alertsView.hidden = false;
  },
  setLoading(active) {
    loadingState.hidden = !active;
    loginButton.disabled = active;
    refreshButton.disabled = active;
  },
  showError(message) {
    const target = loginView.hidden ? alertsError : loginError;
    target.textContent = message;
    target.hidden = !message;
  },
  renderAlerts(items, activeFilter) {
    alertsError.hidden = true;
    alertsList.replaceChildren();
    filterButtons.forEach((button) => {
      button.classList.toggle("active", button.dataset.filter === activeFilter);
    });
    summaryCount.textContent = `${items.length} ${items.length === 1 ? "ocorrência" : "ocorrências"}`;
    if (items.length === 0) {
      alertsList.append(textElement("p", "empty-state", "Nenhum alerta neste filtro."));
    } else {
      alertsList.append(...items.map(alertCard));
    }
    lastUpdated.textContent = `Atualizado às ${new Intl.DateTimeFormat("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date())}`;
  },
};

const apiHost = window.location.hostname.includes(":")
  ? `[${window.location.hostname}]`
  : window.location.hostname;
const api = createAlertsApi(`${window.location.protocol}//${apiHost}:8000`);
const session = new SessionTokenStore(window.sessionStorage);
let controller;
const polling = createPolling(() => controller.refresh(), window, 30_000);
controller = new MobileAlertsController({ api, session, view, polling });

loginForm.addEventListener("submit", (event) => {
  event.preventDefault();
  loginError.hidden = true;
  void controller.login(element("username").value.trim(), element("password").value);
});
refreshButton.addEventListener("click", () => void controller.refresh());
element("logout-button").addEventListener("click", () => controller.logout());
filterButtons.forEach((button) => {
  button.addEventListener("click", () => controller.setFilter(button.dataset.filter));
});

void controller.restore();
