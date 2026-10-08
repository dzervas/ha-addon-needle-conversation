## 3.1.0-1

- Bundle cactus-needle 3.1.0, its speech-capable native engine, and Whistle weights.
- Add `/stt` capability discovery and bounded `/transcribe` PCM16 input on the
  existing internal HTTP port. Keep Whistle in its own process to isolate the
  native runtime's global state from conversation and playground operations.
- Expose Whistle through custom integration 0.3.0 as an Assist STT entity.
- Add a speech language selector defaulting to English, including reconfiguration.
- Keep older add-on connections working as conversation-only integrations.

# Changelog

## 3.0.2-2

- Stop publishing the playground port on the Home Assistant host and LAN.
- Keep browser access behind authenticated Home Assistant ingress.
- Document the Supervisor-internal endpoint at
  `http://local-addon-needle-3:7860` for Home Assistant Core clients.

## 3.0.2-1

- Upgrade `cactus-needle` from 2.0.6 to 3.0.2.
- Download the generation-3 native engine and base `needle3.cact` weights at
  image-build time.
- Use `NEEDLE3_LIB_PATH` for the generation-3 engine.
- Disable upstream anonymous telemetry inside the add-on.
- Patch the upstream 3.0.2 playground to reset the active generation-3 agent
  and report the correct base-model name.
- Preserve Home Assistant ingress URL rewriting.
- Reject generation-2 custom weights with a clear startup error.
