(() => {
  const KEY_BASE_URL = "proxytavern.baseUrl";
  const KEY_PORT = "proxytavern.port";
  const KEY_ST_ENDPOINT = "proxytavern.stEndpoint";
  const PANEL_ID = "proxytavern-status-panel";

  const defaults = {
    baseUrl: "http://127.0.0.1",
    port: "8080",
    stEndpoint: "http://127.0.0.1:8000",
  };

  const state = {
    baseUrl: localStorage.getItem(KEY_BASE_URL) || defaults.baseUrl,
    port: String(localStorage.getItem(KEY_PORT) || defaults.port),
    stEndpoint: localStorage.getItem(KEY_ST_ENDPOINT) || defaults.stEndpoint,
    status: "unknown",
    lastCheck: "never",
  };

  function save(key, value) {
    localStorage.setItem(key, String(value));
  }

  function getProxyEndpoint() {
    return `${state.baseUrl.replace(/\/$/, "")}:${state.port}`;
  }

  function updatePanel() {
    const root = document.getElementById(PANEL_ID);
    if (!root) return;

    const statusEl = root.querySelector("[data-pt-status]");
    const ptEl = root.querySelector("[data-pt-endpoint]");
    const stEl = root.querySelector("[data-st-endpoint]");
    const lastEl = root.querySelector("[data-last-check]");

    if (statusEl) statusEl.textContent = state.status;
    if (ptEl) ptEl.textContent = getProxyEndpoint();
    if (stEl) stEl.textContent = state.stEndpoint;
    if (lastEl) lastEl.textContent = state.lastCheck;
  }

  async function refreshStatus() {
    const now = new Date();

    try {
      const res = await fetch(`${getProxyEndpoint()}/health`, { method: "GET" });
      state.status = res.ok ? "online" : `error (${res.status})`;
    } catch (_err) {
      state.status = "offline";
    }

    state.lastCheck = now.toLocaleString();
    updatePanel();
  }

  function createStatusPanel() {
    if (document.getElementById(PANEL_ID)) return null;

    const panel = document.createElement("div");
    panel.id = PANEL_ID;
    panel.style.cssText = "border:1px solid var(--SmartThemeBorderColor,#555);padding:10px;margin-top:10px;border-radius:6px;";

    const title = document.createElement("h4");
    title.textContent = "ProxyTavern status";
    title.style.margin = "0 0 8px 0";

    const makeRow = (label, attr) => {
      const row = document.createElement("div");
      row.style.margin = "4px 0";
      const strong = document.createElement("strong");
      strong.textContent = `${label}: `;
      const value = document.createElement("span");
      value.setAttribute(attr, "true");
      row.appendChild(strong);
      row.appendChild(value);
      return row;
    };

    const refreshBtn = document.createElement("button");
    refreshBtn.type = "button";
    refreshBtn.textContent = "Refresh";
    refreshBtn.style.marginTop = "8px";
    refreshBtn.addEventListener("click", refreshStatus);

    panel.appendChild(title);
    panel.appendChild(makeRow("PT status", "data-pt-status"));
    panel.appendChild(makeRow("PT endpoint", "data-pt-endpoint"));
    panel.appendChild(makeRow("ST endpoint", "data-st-endpoint"));
    panel.appendChild(makeRow("Last check", "data-last-check"));
    panel.appendChild(refreshBtn);

    return panel;
  }

  function registerViaNewApi() {
    const api = window?.SillyTavern?.settings;
    if (!api) return false;

    api.registerExtensionSettings?.("proxytavern", {
      label: "ProxyTavern",
      items: [
        {
          type: "text",
          key: "baseUrl",
          label: "Proxy endpoint base URL",
          default: state.baseUrl,
          onChange: (value) => {
            state.baseUrl = value || defaults.baseUrl;
            save(KEY_BASE_URL, state.baseUrl);
            updatePanel();
          },
        },
        {
          type: "number",
          key: "port",
          label: "Proxy port",
          default: state.port,
          onChange: (value) => {
            state.port = String(value || defaults.port);
            save(KEY_PORT, state.port);
            updatePanel();
          },
        },
        {
          type: "text",
          key: "stEndpoint",
          label: "SillyTavern endpoint",
          default: state.stEndpoint,
          onChange: (value) => {
            state.stEndpoint = value || defaults.stEndpoint;
            save(KEY_ST_ENDPOINT, state.stEndpoint);
            updatePanel();
          },
        },
      ],
    });

    const panel = createStatusPanel();
    if (!panel) return true;

    if (typeof api.registerExtensionPanel === "function") {
      api.registerExtensionPanel("proxytavern-status", {
        label: "ProxyTavern status",
        element: panel,
      });
      updatePanel();
      return true;
    }

    return false;
  }

  function registerViaLegacyDom() {
    const panel = createStatusPanel();
    if (!panel) {
      updatePanel();
      return true;
    }

    const selectors = [
      "#extensions_settings",
      "#extensions_container",
      "#extensionsMenu",
      "#extensions",
      "body",
    ];

    let host = null;
    for (const selector of selectors) {
      host = document.querySelector(selector);
      if (host) break;
    }

    if (!host) return false;

    host.appendChild(panel);
    updatePanel();
    return true;
  }

  function boot() {
    const registeredWithNewApi = registerViaNewApi();
    if (!registeredWithNewApi) registerViaLegacyDom();
    refreshStatus();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
