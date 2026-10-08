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

The integration also registers **Whistle** as a selectable speech-to-text engine
when connected to the updated add-on. Speech stays local; no microphone or GPU
access is required by the add-on.

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
3. Use `http://18153281-addon-needle-3:7860` as the server URL when installed
   from this repository. If installed locally under `/addons`, use
   `http://local-addon-needle-3:7860` instead. For forks or alternate repository
   URLs, use the installed app identifier with underscores replaced by hyphens.
4. Under **Settings → Voice assistants**, select **Needle Conversation** as the
   conversation agent for the desired Assist pipeline.
5. Select **Whistle** under **Speech-to-text**. Keep your existing text-to-speech
   provider (for example, Piper); Whistle handles speech recognition only.
6. The integration's **Whistle language** setting defaults to **English**. Change
   it during setup or via the integration's **Reconfigure** menu, and select the
   same language in the Assist pipeline.

Whistle supports English, German, French, Spanish, Italian, Dutch, and Polish.
**Greek is not supported.** Audio must be 16 kHz mono PCM16, with a maximum of
30 seconds per utterance. Longer utterances fail rather than being truncated.
Update both the add-on and custom integration, then restart/reload the integration
for Whistle to appear. Older add-ons continue to provide conversation only.

Only entities exposed to Assist can be controlled. Start with harmless devices
and keep the default confidence gate until you have tested your own entity names
and commands.

If setup reports **Cannot connect to a compatible Needle server**, first check
that the app is started and the URL uses its actual Supervisor identifier.
For example, `18153281_addon_needle_3` becomes `18153281-addon-needle-3`. The
`local-` prefix applies only to locally installed apps. The app log should show
`Needle 3 and Whistle ready on port 7860`. Home Assistant Core logs now include
the underlying connection or response error for failed setup/reconfiguration.

## Requirements

- Home Assistant OS or Supervised
- Home Assistant 2026.8 or newer
- `amd64` or `aarch64`

Detailed add-on and troubleshooting documentation is in
[`addon-needle-3/DOCS.md`](addon-needle-3/DOCS.md).

## License

MIT. Needle itself is maintained by Cactus Compute and distributed separately
under its own terms.

## Development checks

Use Python 3.12 or newer. Install `requirements-test.txt`, then run `pytest -q`.
Provider tests use lightweight Home Assistant interface doubles; HTTP tests use
real sockets. To also exercise the native runtime, prefetch the generation-3
engine and both models, set `NEEDLE3_LIB_PATH` and `NEEDLE_TEST_NATIVE=1`, and run
pytest again. Optionally set `NEEDLE_TEST_SPEECH_PCM` to Whisper's JFK fixture
converted to raw 16 kHz mono PCM16. This checks recognition and subsequent Needle
tool calls in the same running server. A live Home Assistant/Supervisor install
is still required to verify the voice-assistant UI and container lifecycle.
