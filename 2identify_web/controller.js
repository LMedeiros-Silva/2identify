import { ApiRequestError, filterAlerts } from "./alerts.js";

const VALID_FILTERS = new Set(["all", "critical", "attention", "resolved"]);

export class MobileAlertsController {
  constructor({ api, session, view, polling }) {
    this.api = api;
    this.session = session;
    this.view = view;
    this.polling = polling;
    this.alerts = [];
    this.filter = "all";
  }

  async restore() {
    if (!this.session.read()) {
      this.view.showLogin();
      return;
    }
    this.view.showAlerts();
    await this.refresh();
    if (this.session.read()) {
      this.polling.start();
    }
  }

  async login(username, password) {
    this.view.setLoading(true);
    try {
      const result = await this.api.login(username, password);
      this.session.save(result.accessToken);
      this.view.showAlerts();
      await this.refresh();
      if (this.session.read()) {
        this.polling.start();
      }
    } catch (error) {
      this.session.clear();
      this.view.showLogin();
      this.view.showError(
        error instanceof ApiRequestError && error.status === 401
          ? "Usuário ou senha inválidos."
          : "Não foi possível acessar a API.",
      );
    } finally {
      this.view.setLoading(false);
    }
  }

  async refresh() {
    const token = this.session.read();
    if (!token) {
      this.logout();
      return;
    }
    this.view.setLoading(true);
    try {
      this.alerts = await this.api.list(token);
      this.render();
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 401) {
        this.logout();
      } else {
        this.view.showError("Não foi possível acessar a API.");
      }
    } finally {
      this.view.setLoading(false);
    }
  }

  setFilter(filter) {
    this.filter = VALID_FILTERS.has(filter) ? filter : "all";
    this.render();
  }

  render() {
    this.view.renderAlerts(filterAlerts(this.alerts, this.filter), this.filter);
  }

  logout() {
    this.polling.stop();
    this.session.clear();
    this.alerts = [];
    this.view.showLogin();
  }
}
