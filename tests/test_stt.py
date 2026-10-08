"""Provider behavior tests with lightweight Home Assistant interface doubles.

The HTTP tests exercise real transport. These doubles allow provider lifecycle
and buffering tests without installing/running Home Assistant Core.
"""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock
from dataclasses import dataclass
from enum import IntEnum, StrEnum

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def provider_modules(monkeypatch):
    def module(name, **attributes):
        result = ModuleType(name)
        result.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, result)
        return result

    class Format(StrEnum):
        WAV = "wav"
    class Codec(StrEnum):
        PCM = "pcm"
    class Bits(IntEnum):
        BITRATE_16 = 16
    class Rate(IntEnum):
        SAMPLERATE_16000 = 16000
    class Channels(IntEnum):
        CHANNEL_MONO = 1
    class State(StrEnum):
        SUCCESS = "success"
        ERROR = "error"
    @dataclass
    class Result:
        text: str | None
        result: State
    @dataclass
    class Processing:
        requires_external_vad: bool
        prefers_auto_gain_enabled: bool
        prefers_noise_reduction_enabled: bool
    class Entity:
        def check_metadata(self, metadata):
            return (metadata.language in self.supported_languages
                    and metadata.format in self.supported_formats
                    and metadata.codec in self.supported_codecs
                    and metadata.bit_rate in self.supported_bit_rates
                    and metadata.sample_rate in self.supported_sample_rates
                    and metadata.channel in self.supported_channels)
    stt = module("homeassistant.components.stt", SpeechToTextEntity=Entity,
                 AudioFormats=Format, AudioCodecs=Codec, AudioBitRates=Bits,
                 AudioSampleRates=Rate, AudioChannels=Channels,
                 SpeechResultState=State, SpeechResult=Result,
                 SpeechAudioProcessing=Processing)
    module("homeassistant")
    module("homeassistant.components", stt=stt)
    module("homeassistant.core", HomeAssistant=object)
    module("homeassistant.helpers")
    module("homeassistant.helpers.entity_platform", AddConfigEntryEntitiesCallback=object)
    package = module("test_needle", NeedleConfigEntry=object)
    package.__path__ = [str(ROOT / "custom_components/needle")]
    for name in ("const", "client", "stt"):
        fullname = "test_needle." + name
        spec = importlib.util.spec_from_file_location(fullname, ROOT / "custom_components/needle" / (name + ".py"))
        target = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, fullname, target)
        spec.loader.exec_module(target)
    return sys.modules["test_needle.stt"], sys.modules["test_needle.client"], sys.modules["test_needle.const"]


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "de", "pl"])
async def test_selected_language_and_split_sample_upload(provider_modules, language):
    provider, _, _ = provider_modules
    client = SimpleNamespace(async_transcribe=AsyncMock(return_value="hello"))
    entry = SimpleNamespace(entry_id="test", runtime_data=SimpleNamespace(client=client, stt_language=language))
    entity = provider.WhistleSpeechToTextEntity(entry)
    metadata = SimpleNamespace(language=language, format="wav", codec="pcm", bit_rate=16, sample_rate=16000, channel=1)
    closed = []
    async def audio():
        try:
            yield b"\0"  # Individual chunks need not be sample-aligned.
            yield b"\0\xff\x7f"
        finally:
            closed.append(True)
    assert entity.supported_languages == [language]
    assert entity.audio_processing.requires_external_vad
    result = await entity.async_process_audio_stream(metadata, audio())
    assert result.text == "hello" and result.result == "success"
    client.async_transcribe.assert_awaited_once_with(b"\0\0\xff\x7f", language)
    assert closed


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["oversized", "unaligned", "empty", "wrong_language", "wrong_rate", "server_error", "silence"])
async def test_audio_errors_and_silence(provider_modules, case):
    provider, client_module, const = provider_modules
    client = SimpleNamespace(async_transcribe=AsyncMock(return_value=""))
    if case == "server_error":
        client.async_transcribe.side_effect = client_module.NeedleResponseError("failed")
    entity = provider.WhistleSpeechToTextEntity(SimpleNamespace(entry_id="test", runtime_data=SimpleNamespace(client=client, stt_language="en")))
    metadata = SimpleNamespace(language="el" if case == "wrong_language" else "en", format="wav", codec="pcm", bit_rate=16, sample_rate=48000 if case == "wrong_rate" else 16000, channel=1)
    closed = []
    async def audio():
        try:
            if case == "oversized":
                yield b"\0" * const.MAX_AUDIO_BYTES
                yield b"\0\0"
                pytest.fail("Oversized input must stop consuming audio")
            elif case == "unaligned":
                yield b"\0"
            elif case != "empty":
                yield b"\0\0"
        finally:
            closed.append(True)
    result = await entity.async_process_audio_stream(metadata, audio())
    assert result.result == ("success" if case == "silence" else "error")
    if case not in ("silence", "server_error"):
        client.async_transcribe.assert_not_awaited()
    if case not in ("wrong_language", "wrong_rate"):
        assert closed


@pytest.mark.asyncio
@pytest.mark.parametrize("languages,configured,expected", [
    (["en", "de"], None, ("conversation", "stt")),
    (["en", "de"], "de", ("conversation", "stt")),
    (None, None, ("conversation",)),
])
async def test_setup_defaults_and_old_addon_fallback(provider_modules, monkeypatch, languages, configured, expected):
    _, client_module, _ = provider_modules
    class ConfigEntry:
        def __class_getitem__(cls, item):
            return cls
    class Platform(StrEnum):
        CONVERSATION = "conversation"
        STT = "stt"
    for name, attributes in {
        "homeassistant.config_entries": {"ConfigEntry": ConfigEntry},
        "homeassistant.const": {"CONF_URL": "url", "Platform": Platform},
        "homeassistant.exceptions": {"ConfigEntryNotReady": RuntimeError},
        "homeassistant.helpers.aiohttp_client": {"async_get_clientsession": lambda hass: None},
    }.items():
        module = ModuleType(name)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)
    fullname = "test_needle"
    spec = importlib.util.spec_from_file_location(fullname, ROOT / "custom_components/needle/__init__.py")
    lifecycle = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, fullname, lifecycle)
    spec.loader.exec_module(lifecycle)
    fake_client = SimpleNamespace(async_model=AsyncMock(return_value="needle-3"),
                                  async_stt_languages=AsyncMock(return_value=languages))
    if languages is None:
        fake_client.async_stt_languages.side_effect = client_module.NeedleConnectionError("404")
    monkeypatch.setattr(lifecycle, "NeedleClient", lambda **kwargs: fake_client)
    entry = SimpleNamespace(data={"url": "http://needle:7860"})
    if configured:
        entry.data["stt_language"] = configured
    hass = SimpleNamespace(config_entries=SimpleNamespace(
        async_forward_entry_setups=AsyncMock(), async_unload_platforms=AsyncMock(return_value=True)))
    assert await lifecycle.async_setup_entry(hass, entry)
    assert entry.runtime_data.stt_language == (configured or "en")
    hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(entry, expected)
    assert await lifecycle.async_unload_entry(hass, entry)
    hass.config_entries.async_unload_platforms.assert_awaited_once_with(entry, expected)
