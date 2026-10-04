# Notify History for Home Assistant

Custom integration that proxies notifications and keeps a history of every message it sends, plus a card that shows that history.

Each **proxy** forwards a message to one or more targets: notify entities (`notify.send_message`) and legacy notify services such as the Companion App's `notify.mobile_app_<device>`. A proxy shows up as both a notify entity and a legacy notify service, so you can point existing automations at it by changing the action name.

## Installation

**HACS (recommended):** add this repository as a custom integration in HACS, then install *Notify History*.

**Manual:** copy `custom_components/notify_history` into your Home Assistant `config/custom_components/` directory.

Restart Home Assistant. The card is registered automatically, there is no dashboard resource to add.

## Usage

1. **Settings → Devices & Services → Helpers → Create helper → Notify History**.
2. Give the proxy a name, pick its targets and how long to keep messages (14 days by default).
3. Send through it:

```yaml
# Like any legacy notify service: message, title, data and target.
action: notify.family
data:
  title: Front door
  message: The front door has been open for 10 minutes.
  data:
    tag: front-door

# Or through the notify entity: message and title only.
action: notify.send_message
target:
  entity_id: notify.family
data:
  message: The washing machine is done.
```

Targets and retention can be changed later from the proxy's **Configure** dialog.

### What goes where

| Sent through | Notify entity targets get | Notify service targets get |
|---|---|---|
| `notify.<name>` | `message`, `title` | `message`, `title`, `data`, `target` |
| `notify.send_message` | `message`, `title` | `message`, `title` |

All targets are called at once. When one fails, the others still get the message and the failure is recorded with it. The action only fails when every target failed.

If a notify service with the proxy's name already exists, the proxy skips registering `notify.<name>` and logs a warning. The notify entity works either way.

## History

Each message is stored with its title, text, `data`, the way it was sent and the outcome per target. Messages older than the configured number of days are deleted, and a proxy keeps at most 1000 messages. The history lives in `.storage/notify_history.<entry_id>` and is deleted with the proxy.

Two actions manage it:

```yaml
action: notify_history.delete
target:
  entity_id: notify.family
data:
  message_id: 01J...

action: notify_history.clear
target:
  entity_id: notify.family
```

## Card

```yaml
type: custom:notify-history-card
entity: notify.family
```

| Option | Default | |
|---|---|---|
| `entity` | | The proxy's notify entity |
| `title` | the entity's name | Header text, `""` for none |
| `max_items` | `20` | Messages per page; more load on demand |
| `show_targets` | `false` | List the targets under each message |

The card updates live. Click a message to expand it, use the menu on a message to delete it. A warning icon marks messages that failed for at least one target; hover it to see which and why.

## Development

```sh
make install   # venv with the test dependencies
make test
make lint
make dev-up    # Home Assistant in Docker at http://localhost:8123
```

`make release` starts the release workflow. See [AGENTS.md](AGENTS.md) for notes on working on this repo.
