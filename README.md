# Tap Electric RFID Auth

<img src="custom_components/tap_electric_rfid_auth/brand/logo.png" alt="Tap Electric RFID Auth logo" width="96" height="96">

> **Disclaimer:** this is an independent, community-made integration. It is
> **not affiliated with, endorsed by, or supported by Tap Electric** in any
> way. It simply talks to the public Tap Electric REST API
> (`api.tapelectric.app`) using an API key you provide yourself. "Tap
> Electric" and any related names/logos belong to their respective owner;
> use of this integration is entirely at your own risk.

## Goal

Tap Electric normally requires anyone who wants to charge to scan a
physical RFID card, which authorizes (and bills) that session. Tap
Electric itself lets you configure one RFID tag to charge **for free**.

**The whole point of this integration is that you never have to physically
scan that card for your own car.** Walking up to the charger with a card
every time is annoying - especially when Home Assistant already knows your
car just arrived. Instead: give Home Assistant that free RFID tag for a
charger, then build an automation that presses the **Authorize session**
button whenever HA recognizes your own car has arrived (presence
detection, a Bluetooth/BLE tracker, an OBD sensor, a smart plug - whatever
you already use). Your car then starts charging automatically and for
free, with zero physical interaction - while everyone else still scans
their own RFID and pays as normal. The "free" part lives entirely in Tap
Electric's own configuration; this integration is just the trigger.

Everything else in this integration (the session sensors, the online/active
binary sensors, the stop button) exists to support that goal - so you can
see what's happening and stop a session remotely from an automation too.

### Example automation

```yaml
automation:
  - alias: "Auto-authorize my car at the driveway charger"
    trigger:
      - trigger: state
        entity_id: device_tracker.my_car # however you detect your own car
        to: "home"
    condition:
      # don't re-trigger if a session is already running
      - condition: state
        entity_id: binary_sensor.driveway_charger_active_session
        state: "off"
    action:
      - action: button.press
        target:
          entity_id: button.driveway_charger_authorize_session
```

## What it does

Home Assistant (HACS) custom integration for **Tap Electric** EV chargers.
Connects to your Tap Electric account and turns every charger into a Home
Assistant device, with sensors to see what's going on and buttons to
authorize or stop a charging session - fully working and tested end-to-end
against a real charger.

## Features

- Simple setup: just enter your Tap Electric API key
- Every charger on your account becomes a device automatically
- Per charger:
  - **Online** - whether the charger is currently reachable
  - **Active session** - clearly on/off, so you can see at a glance whether
    it's charging
  - **Current session** - energy delivered so far by the session that's
    charging right now, as **Wh** and as **kWh** (same value, the kWh one
    is handy for the Energy dashboard); reads 0 whenever nothing is charging
  - **Last session** - energy of the last *finished* session, again as
    **Wh** and **kWh**. This one never jumps to the live session - it keeps
    showing the most recently completed one
  - **Current session duration** - how long the session charging right now
    has been running; reads 0 whenever nothing is charging
  - **Last session duration** - how long the last *finished* session lasted
  - **Authorize session** button - starts a session using the RFID tag you
    configured for that charger; usable from automations
  - **Stop session** button - stops the current session; greyed out
    whenever nothing is running
  - a configurable **RFID tag** per charger
- Update your API key at any time without removing/re-adding the integration
- Checks for updates in the background every **hour** normally, every **10
  minutes** while a session is active so things stay reasonably fresh while
  charging; pressing Authorize or Stop refreshes immediately (twice, a few
  seconds apart, to make sure the change has landed)
- Diagnostics download with your API key redacted

## Installation (HACS)

1. HACS → Integrations → ⋮ → Custom repositories → add this repo URL, category "Integration".
2. Install "Tap Electric RFID Auth", restart Home Assistant.
3. Settings → Devices & Services → Add integration → search "Tap Electric" → enter your API key.

## Configuration

### Set a charger's RFID tag

Every charger needs an RFID tag configured before "Authorize session" works
on it:

1. Settings → Devices & Services → click the **Tap Electric** tile
2. Find the charger in the list and click its gear icon (⚙️)
3. Enter the RFID tag (hex) and save

> **Tip:** to actually charge for free (see [Goal](#goal) above), create a
> dedicated RFID tag in Tap Electric itself and set it to charge for free,
> then enter that same tag here. Don't reuse a tag that's tied to your own
> paid account/card unless you want those sessions billed as normal.

### Change your API key later

Settings → Devices & Services → find **Tap Electric** → ⋮ → **Reconfigure**

### A charger added to your account later

Settings → Devices & Services → click the **Tap Electric** tile → look for
the option to add a device → pick the new charger and optionally set its
RFID tag right away.

## Development setup

This repo develops and tests against a real Home Assistant instance running
in Docker ([`.devcontainer/docker-compose.yml`](.devcontainer/docker-compose.yml)).
`custom_components/` and `config/` are bind-mounted straight from the repo,
so code changes just need a restart to take effect - no copying/symlinking.

### Requirements

- Docker (Docker Desktop or equivalent) - that's it.
  VS Code + the "Dev Containers" extension is optional, for an integrated
  editor experience.

### Quick start (any terminal, no VS Code required)

```bash
./scripts/setup     # pulls + starts Home Assistant, waits until it's up
```

Then open <http://localhost:8123>, complete onboarding (throwaway local
account), and add the integration: Settings → Devices & Services → Add
integration → "Tap Electric RFID Auth" → enter a Tap Electric API key.

Everyday commands:

| Script             | What it does                                              |
| ------------------- | ---------------------------------------------------------- |
| `./scripts/restart` | restart Home Assistant to pick up integration code changes |
| `./scripts/logs`    | tail Home Assistant logs                                   |
| `./scripts/lint`    | run ruff                                                    |
| `./scripts/test`    | run pytest                                                  |
| `./scripts/stop`    | stop the containers (keeps `config/` + onboarding state)   |

`lint` and `test` run directly if `ruff`/`pytest` are already on `PATH`
(e.g. inside the VS Code dev container below), otherwise they transparently
fall back to a throwaway container - so plain `./scripts/test` works right
after cloning, with only Docker installed.

### Alternative: VS Code Dev Container

Open this folder in VS Code → "Reopen in Container" (or run the
*Dev Containers: Reopen in Container* command) to get an editor pre-wired
with Python tooling, attached to a `dev` container that shares its network
with `homeassistant` (so `localhost:8123` also works from its integrated
terminal). The tasks above are also available as VS Code tasks
(`Terminal → Run Task…`) — they just call the same `scripts/*`.

## Project structure

```
.devcontainer/                        devcontainer + docker-compose (dev + homeassistant services)
scripts/                               setup/restart/logs/lint/test/stop wrapper scripts
config/                                Home Assistant config dir used by the dev container
  configuration.yaml
custom_components/tap_electric_rfid_auth/
  __init__.py                         entry setup/unload
  api.py                              REST client (chargers, sessions, authorize, stop)
  config_flow.py                      API-key config flow + per-charger subentry flow
  const.py
  coordinator.py                      polls chargers + sessions (interval speeds up while a
                                       session is active); resolves + caches OCPP transaction ids
  data.py                             runtime data / typed ConfigEntry
  entity.py                           shared base entity (one per charger/subentry)
  util.py                             shared helpers (ISO timestamp parsing)
  sensor.py                           current/last session energy (Wh + kWh) + duration sensors
  binary_sensor.py                    online / active-session sensors
  button.py                           authorize / stop-session buttons
  diagnostics.py
  manifest.json
  strings.json / translations/en.json, nl.json
  brand/                               logo source + generated icon/logo PNGs (see brand/README.md)
tests/                                 pytest-homeassistant-custom-component tests
.github/workflows/                     hassfest + HACS validation, lint/tests
hacs.json
```

