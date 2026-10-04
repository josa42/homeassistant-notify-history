const CARD_VERSION = "0.1.0";

const DOMAIN = "notify_history";
const DEFAULT_MAX_ITEMS = 20;
// After an unload (e.g. new options) the proxy comes back a moment later.
const RESUBSCRIBE_DELAYS = [500, 1000, 2000, 5000, 10000];
const TICK_MS = 60 * 1000;

const EN_FALLBACK = {
  "component.notify_history.common.card_empty": "No messages yet.",
  "component.notify_history.common.card_load_more": "Load more",
  "component.notify_history.common.card_delete": "Delete",
  "component.notify_history.common.card_more_actions": "More actions",
  "component.notify_history.common.card_failed_targets": "Failed: {targets}",
  "component.notify_history.common.card_sent_to": "Sent to: {targets}",
  "component.notify_history.common.card_not_found":
    "{entity} is not a notify history proxy.",
  "component.notify_history.common.card_editor_entity": "Notify history proxy",
  "component.notify_history.common.card_editor_title": "Title",
  "component.notify_history.common.card_editor_max_items": "Messages per page",
  "component.notify_history.common.card_editor_show_targets": "Show targets",
};

function _t(hass, key, params) {
  const full = `component.${DOMAIN}.common.${key}`;
  const raw =
    (hass && hass.localize && hass.localize(full)) || EN_FALLBACK[full] || full;
  if (!params) return raw;
  return raw.replace(/\{(\w+)\}/g, (_, k) =>
    params[k] != null ? String(params[k]) : ""
  );
}

function _lang(hass) {
  return (hass && ((hass.locale && hass.locale.language) || hass.language)) || "en";
}

const RELATIVE_STEPS = [
  ["second", 60],
  ["minute", 60],
  ["hour", 24],
  ["day", 7],
  ["week", 4.35],
  ["month", 12],
  ["year", Infinity],
];

function _relativeTime(hass, iso) {
  let value = (new Date(iso).getTime() - Date.now()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(_lang(hass), { numeric: "auto" });
  for (const [unit, size] of RELATIVE_STEPS) {
    if (Math.abs(value) < size) return rtf.format(Math.round(value), unit);
    value /= size;
  }
  return "";
}

function _absoluteTime(hass, iso) {
  return new Intl.DateTimeFormat(_lang(hass), {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
}

function _targetLabel(hass, target) {
  if (target.type === "entity") {
    const state = hass && hass.states[target.id];
    return (state && state.attributes.friendly_name) || target.id;
  }
  return target.id;
}

function _isProxy(hass, entityId) {
  const entry = hass && hass.entities && hass.entities[entityId];
  return Boolean(entry && entry.platform === DOMAIN);
}

function _el(tag, attrs, children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value == null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children || []) if (child) el.appendChild(child);
  return el;
}

const STYLE = `
  ha-card { overflow: clip; }
  .list { display: flex; flex-direction: column; padding: 0 0 8px; }
  .header + .list { padding-top: 0; }
  .header {
    padding: 12px 16px 4px;
    font-size: var(--ha-card-header-font-size, 1.25rem);
    font-weight: var(--ha-font-weight-normal, 400);
    color: var(--ha-card-header-color, var(--primary-text-color));
  }
  .empty, .error { padding: 16px; color: var(--secondary-text-color); }
  .error { color: var(--error-color); }
  .item {
    position: relative;
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 8px 8px 8px 16px;
  }
  .item + .item { border-top: 1px solid var(--divider-color); }
  .body { flex: 1; min-width: 0; }
  .title { font-weight: 500; color: var(--primary-text-color); }
  .message {
    color: var(--primary-text-color);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    cursor: pointer;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    overflow: hidden;
  }
  .message.expanded { display: block; -webkit-line-clamp: unset; }
  .meta {
    margin-top: 2px;
    font-size: var(--ha-font-size-s, 0.875rem);
    color: var(--secondary-text-color);
  }
  .failed { color: var(--warning-color); padding-top: 10px; --mdc-icon-size: 20px; }
  .menu-button {
    border: 0;
    background: none;
    color: var(--secondary-text-color);
    padding: 8px;
    border-radius: 50%;
    cursor: pointer;
    line-height: 0;
    --mdc-icon-size: 20px;
  }
  .menu-button:hover { background: var(--secondary-background-color); }
  .menu-button:focus-visible { outline: 2px solid var(--primary-color); }
  .menu {
    position: absolute;
    right: 8px;
    top: 40px;
    z-index: 1;
    min-width: 120px;
    padding: 4px 0;
    background: var(--card-background-color, var(--ha-card-background, white));
    border-radius: var(--ha-card-border-radius, 12px);
    box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0, 0, 0, 0.2));
  }
  .menu button {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    border: 0;
    background: none;
    padding: 8px 16px;
    font: inherit;
    color: var(--primary-text-color);
    cursor: pointer;
    text-align: left;
    --mdc-icon-size: 20px;
  }
  .menu button:hover, .menu button:focus-visible {
    background: var(--secondary-background-color);
    outline: none;
  }
  .more { display: flex; justify-content: center; padding: 4px 16px 0; }
`;

class NotifyHistoryCard extends HTMLElement {
  static getStubConfig(hass) {
    const entity = Object.keys((hass && hass.entities) || {}).find((id) =>
      _isProxy(hass, id)
    );
    return { entity: entity || "" };
  }

  static async getConfigElement() {
    await customElements.whenDefined("notify-history-card-editor");
    return document.createElement("notify-history-card-editor");
  }

  constructor() {
    super();
    this._messages = [];
    this._hasMore = false;
    this._expanded = new Set();
    this._openMenu = null;
    this._error = null;
    this._onDocumentClick = (e) => {
      if (this._openMenu && !e.composedPath().includes(this)) this._closeMenu();
    };
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("You need to define an entity");
    }
    const changed = !this._config || this._config.entity !== config.entity;
    this._config = { max_items: DEFAULT_MAX_ITEMS, show_targets: false, ...config };
    if (changed) this._resubscribe();
    else this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    const languageChanged = this._hass && _lang(this._hass) !== _lang(hass);
    this._hass = hass;
    if (first) this._resubscribe();
    else if (languageChanged) this._render();
  }

  getCardSize() {
    return 1 + Math.min(this._messages.length, 6);
  }

  getGridOptions() {
    return { columns: 12, min_columns: 4, min_rows: 2 };
  }

  connectedCallback() {
    this._connected = true;
    document.addEventListener("click", this._onDocumentClick);
    this._tick = setInterval(() => this._render(), TICK_MS);
    if (!this._unsub) this._resubscribe();
  }

  disconnectedCallback() {
    this._connected = false;
    document.removeEventListener("click", this._onDocumentClick);
    clearInterval(this._tick);
    this._unsubscribe();
  }

  // -- Data ----------------------------------------------------------------

  _unsubscribe() {
    clearTimeout(this._retryHandle);
    this._generation = (this._generation || 0) + 1;
    const unsub = this._unsub;
    this._unsub = null;
    if (unsub) unsub.then((fn) => fn()).catch(() => {});
  }

  // `reloading`: the proxy just unloaded, so "not found" is expected for a
  // moment and worth retrying.
  _resubscribe(attempt = 0, reloading = false) {
    this._unsubscribe();
    if (!this._connected || !this._hass || !this._config) return;
    const generation = this._generation;
    const entityId = this._config.entity;

    // Subscribe before loading, so nothing sent in between gets lost; the
    // "added" handler ignores what the first page already has.
    this._unsub = this._hass.connection.subscribeMessage(
      (event) => {
        if (generation === this._generation) this._onEvent(event);
      },
      { type: `${DOMAIN}/subscribe`, entity_id: entityId }
    );
    this._unsub
      .then(() => this._load(false, generation))
      .catch((err) => {
        if (generation !== this._generation) return;
        this._unsubscribe();
        if (reloading && attempt < RESUBSCRIBE_DELAYS.length && err && err.code === "not_found") {
          // Keep showing what we have while the proxy reloads.
          this._retryHandle = setTimeout(
            () => this._resubscribe(attempt + 1, true),
            RESUBSCRIBE_DELAYS[attempt]
          );
          return;
        }
        this._error =
          err && err.code === "not_found"
            ? _t(this._hass, "card_not_found", { entity: entityId })
            : (err && err.message) || String(err);
        this._messages = [];
        this._render();
      });
  }

  async _load(more, generation = this._generation) {
    const last = this._messages[this._messages.length - 1];
    const result = await this._hass.callWS({
      type: `${DOMAIN}/list`,
      entity_id: this._config.entity,
      limit: Math.max(1, Math.min(200, Number(this._config.max_items) || DEFAULT_MAX_ITEMS)),
      ...(more && last ? { before: last.id } : {}),
    });
    if (generation !== this._generation) return;
    const known = new Set(this._messages.map((m) => m.id));
    const page = result.messages.filter((m) => !known.has(m.id));
    this._messages = more ? [...this._messages, ...page] : result.messages;
    this._hasMore = result.has_more;
    this._error = null;
    this._render();
  }

  _onEvent(event) {
    if (event.event === "added") {
      if (this._messages.some((m) => m.id === event.message.id)) return;
      this._messages = [event.message, ...this._messages];
    } else if (event.event === "removed") {
      const ids = new Set(event.ids);
      this._messages = this._messages.filter((m) => !ids.has(m.id));
    } else if (event.event === "cleared") {
      this._messages = [];
      this._hasMore = false;
    } else if (event.event === "closed") {
      this._resubscribe(0, true);
      return;
    }
    this._render();
  }

  _delete(message) {
    this._closeMenu();
    this._hass
      .callWS({
        type: `${DOMAIN}/delete`,
        entity_id: this._config.entity,
        message_id: message.id,
      })
      .catch((err) => console.error("[notify-history-card] delete failed", err));
  }

  // -- Rendering -----------------------------------------------------------

  _closeMenu() {
    if (!this._openMenu) return;
    this._openMenu = null;
    this._render();
  }

  _render() {
    if (!this._config || !this._hass) return;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.appendChild(_el("style", { text: STYLE }));
      this._card = _el("ha-card");
      this.shadowRoot.appendChild(this._card);
    }
    const hass = this._hass;
    const state = hass.states[this._config.entity];
    const title =
      this._config.title != null
        ? this._config.title
        : (state && state.attributes.friendly_name) || "";

    const children = [];
    if (title) children.push(_el("div", { class: "header", text: title }));

    if (this._error) {
      children.push(_el("div", { class: "error", text: this._error }));
    } else if (!this._messages.length) {
      children.push(_el("div", { class: "empty", text: _t(hass, "card_empty") }));
    } else {
      children.push(
        _el("div", { class: "list" }, this._messages.map((m) => this._renderItem(m)))
      );
      if (this._hasMore) {
        const button = _el("ha-button", {
          appearance: "plain",
          text: _t(hass, "card_load_more"),
          onclick: () => this._load(true),
        });
        children.push(_el("div", { class: "more" }, [button]));
      }
    }

    // Keep focus on the menu button across re-renders triggered by the menu.
    const focused = this.shadowRoot.activeElement;
    const focusKey = focused && focused.dataset && focused.dataset.focusKey;
    this._card.replaceChildren(...children);
    if (focusKey) {
      const again = this._card.querySelector(`[data-focus-key="${focusKey}"]`);
      if (again) again.focus();
    }
  }

  _renderItem(message) {
    const hass = this._hass;
    const failed = message.targets.filter((t) => t.status === "error");
    const meta = [_relativeTime(hass, message.timestamp)];
    if (this._config.show_targets && message.targets.length) {
      meta.push(
        _t(hass, "card_sent_to", {
          targets: message.targets.map((t) => _targetLabel(hass, t)).join(", "),
        })
      );
    }

    const expanded = this._expanded.has(message.id);
    const body = _el("div", { class: "body" }, [
      message.title ? _el("div", { class: "title", text: message.title }) : null,
      _el("div", {
        class: expanded ? "message expanded" : "message",
        text: message.message,
        onclick: () => {
          if (expanded) this._expanded.delete(message.id);
          else this._expanded.add(message.id);
          this._render();
        },
      }),
      _el("div", {
        class: "meta",
        text: meta.join(" · "),
        title: _absoluteTime(hass, message.timestamp),
      }),
    ]);

    const failedIcon = failed.length
      ? _el("ha-icon", {
          class: "failed",
          icon: "mdi:alert-circle-outline",
          title: _t(hass, "card_failed_targets", {
            targets: failed.map((t) => `${_targetLabel(hass, t)} (${t.error})`).join(", "),
          }),
        })
      : null;

    const menuOpen = this._openMenu === message.id;
    const menuButton = _el(
      "button",
      {
        class: "menu-button",
        "aria-label": _t(hass, "card_more_actions"),
        "aria-haspopup": "menu",
        "aria-expanded": menuOpen ? "true" : "false",
        "data-focus-key": `menu-${message.id}`,
        onclick: (e) => {
          e.stopPropagation();
          this._openMenu = menuOpen ? null : message.id;
          this._render();
        },
      },
      [_el("ha-icon", { icon: "mdi:dots-vertical" })]
    );

    const menu = menuOpen
      ? _el(
          "div",
          {
            class: "menu",
            role: "menu",
            onkeydown: (e) => {
              if (e.key === "Escape") this._closeMenu();
            },
          },
          [
            _el(
              "button",
              { role: "menuitem", onclick: () => this._delete(message) },
              [
                _el("ha-icon", { icon: "mdi:delete-outline" }),
                _el("span", { text: _t(hass, "card_delete") }),
              ]
            ),
          ]
        )
      : null;

    return _el("div", { class: "item" }, [body, failedIcon, menuButton, menu]);
  }
}

const EDITOR_SCHEMA = [
  {
    name: "entity",
    required: true,
    selector: { entity: { filter: { integration: DOMAIN, domain: "notify" } } },
  },
  { name: "title", selector: { text: {} } },
  { name: "max_items", selector: { number: { min: 1, max: 200, mode: "box" } } },
  { name: "show_targets", selector: { boolean: {} } },
];

class NotifyHistoryCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...(config || {}) };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      const form = document.createElement("ha-form");
      form.schema = EDITOR_SCHEMA;
      form.computeLabel = (s) => _t(this._hass, `card_editor_${s.name}`);
      form.addEventListener("value-changed", (e) => {
        this._config = { ...this._config, ...e.detail.value };
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config: this._config },
            bubbles: true,
            composed: true,
          })
        );
      });
      this._form = form;
      this.appendChild(form);
    }
    this._form.hass = this._hass;
    this._form.data = {
      max_items: DEFAULT_MAX_ITEMS,
      show_targets: false,
      ...this._config,
    };
  }
}

const CARD_REGISTRATIONS = [
  ["notify-history-card", NotifyHistoryCard],
  ["notify-history-card-editor", NotifyHistoryCardEditor],
];

function registerCards() {
  const registry = window.customElements;
  if (!registry) return;
  for (const [name, cls] of CARD_REGISTRATIONS) {
    if (registry.get(name)) continue;
    try {
      registry.define(name, cls);
    } catch (e) {
      console.error("[notify-history-card] failed to define", name, e);
    }
  }
}

registerCards();

// HA swaps in a scoped custom elements polyfill while it boots, which can drop
// what was defined before. Re-assert until HA has booted; cheap.
let registerTicks = 0;
const registerTimer = setInterval(() => {
  registerCards();
  if (++registerTicks >= 60) clearInterval(registerTimer);
}, 200);
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", registerCards);
}
window.addEventListener("load", registerCards);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "notify-history-card")) {
  window.customCards.push({
    type: "notify-history-card",
    name: "Notify History",
    description: "Lists the messages a notify history proxy sent.",
    preview: true,
  });
}

console.info(
  `%c NOTIFY-HISTORY-CARD %c v${CARD_VERSION} `,
  "color:white;background:#03a9f4;padding:2px 6px;border-radius:3px 0 0 3px;font-weight:600",
  "color:#03a9f4;background:#eee;padding:2px 6px;border-radius:0 3px 3px 0;font-weight:600"
);
