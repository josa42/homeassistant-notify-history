# Changelog

## Unreleased

### Added

- **Notify proxies that keep a history.** A proxy forwards each message to
  its notify entities and legacy notify services at once and stores it with
  the outcome per target. It is both a notify entity and a `notify.<name>`
  service, so automations written for a legacy notify service can switch over
  by changing the action name. A failing target does not fail the action
  unless every target failed.

- **Retention per proxy.** Messages older than the configured number of days
  (14 by default) are deleted, and a proxy keeps at most 1000.

- **`notify_history.delete` and `notify_history.clear`** remove one message or
  the whole history.

- **The notify history card.** It lists a proxy's messages, newest first,
  updates live, loads more on demand, marks messages that failed for a target
  and deletes a message from its menu. It comes with a visual editor.
