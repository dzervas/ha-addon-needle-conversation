# Needle Conversation for Home Assistant

Local, low-latency Home Assistant voice control powered by
[Cactus Compute Needle 3](https://cactuscompute.com/needle).

This repository contains two pieces:

- **Needle 3 add-on** — runs the native Needle model and its HTTP API in an
  isolated Supervisor container. Its playground is available only through
  authenticated Home Assistant ingress; port `7860` is not published to the
  LAN.
- **Needle Conversation integration** — registers a conversation agent inside
  Home Assistant Core, exposes only Home Assistant's permitted Assist tools,
  validates Needle's structured calls, and executes them with the requesting
  user's Home Assistant context.

Both are required because an add-on cannot register an Assist conversation
entity or safely execute actions inside Home Assistant, while a custom
integration should not bundle and supervise the native inference runtime.

Home Assistant's native intents run first for exact commands, state queries,
time/date questions, and sentence triggers. Needle handles actionable requests
that the native recognizer does not match. It is a tool router, not a general
chatbot.

## Install

### 1. Add-on

1. In **Settings → Add-ons → Add-on Store → Repositories**, add:
   `https://github.com/dzervas/ha-addon-needle-conversation`
2. Install and start **Needle 3**.
3. Optionally enable **Start on boot**, **Watchdog**, and the sidebar entry.

### 2. Custom integration

Install this repository as a custom **Integration** in HACS, or copy
`custom_components/needle` to `/config/custom_components/needle`. Restart Home
Assistant afterwards.

Then:

1. Open **Settings → Devices & services → Add integration**.
2. Add **Needle Conversation**.
3. Use `http://local-addon-needle-3:7860` as the server URL.
4. Under **Settings → Voice assistants**, select **Needle Conversation** as the
   conversation agent for the desired Assist pipeline.

Only entities exposed to Assist can be controlled. Start with harmless devices
and keep the default confidence gate until you have tested your own entity names
and commands.

## Requirements

- Home Assistant OS or Supervised
- Home Assistant 2026.8 or newer
- `amd64` or `aarch64`

Detailed add-on and troubleshooting documentation is in
[`addon-needle-3/DOCS.md`](addon-needle-3/DOCS.md).

## License

MIT. Needle itself is maintained by Cactus Compute and distributed separately
under its own terms.
