# AGENTS.md

Notes for AI coding agents working on this repo.

## Repo shape

- Custom Home Assistant integration in `custom_components/notify_history/`.
  One config entry per proxy (a helper). Targets and the max age live in
  `entry.options`; the options flow reloads the entry.
- `proxy.py` forwards a message to every target at once and records it.
  `history.py` owns the stored messages and notifies listeners (`added`,
  `removed`, `cleared`, `closed`). `notify.py` is the entity and the target of
  the `delete` and `clear` services. `websocket_api.py` serves the card.
- Each proxy also registers the legacy service `notify.<slugified title>` from
  `__init__.py`, and removes it on unload. The config flow leaves out the
  proxies' own entities and services as targets so proxies cannot loop.
- The card ships at `custom_components/notify_history/www/notify-history-card.js`,
  registered via `add_extra_js_url`. `CARD_VERSION` in `__init__.py` and in the
  JS is the cache buster; the release workflow bumps both.
- Tests use `pytest-homeassistant-custom-component` and live in `tests/`.
  `make install` creates `./venv`, then `make test` and `make lint`.
  pytest-socket stays enabled: the websocket tests need `socket_enabled`.

## Card

- Plain `HTMLElement`, no build step. Build DOM with `_el()` and put user
  content in `textContent`, never `innerHTML`: messages come from automations.
- The card subscribes before it loads the first page, so nothing sent in
  between is lost; `added` events for messages it already has are ignored.
- On `closed` (the proxy unloaded, e.g. new options) the card subscribes again,
  retrying while the proxy is still reloading.
- HA swaps in a custom elements polyfill while it boots. `registerCards()` is
  re-run for a while so the card stays defined; without it the dashboard shows
  "Custom element doesn't exist" now and then.
- Everything user-facing goes through `_t(hass, key, params)` against
  `component.notify_history.common.card_*`. Keep `EN_FALLBACK`, `strings.json`,
  `translations/en.json` (a copy of `strings.json`) and `translations/de.json`
  in sync.
- Check layout changes on a real dashboard, not a bare HTML page: `make dev-up`,
  or run `venv/bin/hass -c <config dir>` with `custom_components/notify_history`
  linked into it, and drive it with Puppeteer.

## Always

- Run `make test` after a Python change and `make lint` before committing.
- Commit unrelated changes separately.
- Add user-facing changes to `CHANGELOG.md` under `## Unreleased`.

## Release

`make release` (or `make release VERSION=<version|major|minor|patch>`) runs the
release workflow: CI, then it bumps `manifest.json` and `CARD_VERSION` in
`__init__.py` and `notify-history-card.js`, dates the changelog, commits, tags,
pushes and publishes. It releases `origin/main`, so `make release` stops on
unpushed or uncommitted changes. The first release needs an explicit version:
`make release VERSION=0.1.0`.
