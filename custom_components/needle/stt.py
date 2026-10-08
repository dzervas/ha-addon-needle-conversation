"""Whistle speech recognition for Home Assistant Assist pipelines."""
from __future__ import annotations

from collections.abc import AsyncIterable
import logging

from homeassistant.components import stt
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NeedleConfigEntry
from .client import NeedleError
from .const import MAX_AUDIO_BYTES

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeedleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Expose a selectable speech-to-text entity."""
    async_add_entities([WhistleSpeechToTextEntity(entry)])


class WhistleSpeechToTextEntity(stt.SpeechToTextEntity):
    """Transcribe Assist audio with the add-on's isolated Whistle worker."""

    _attr_name = "Whistle"
    _attr_has_entity_name = True

    def __init__(self, entry: NeedleConfigEntry) -> None:
        self._attr_unique_id = f"{entry.entry_id}-whistle"
        self._client = entry.runtime_data.client
        self._language = entry.runtime_data.stt_language

    @property
    def supported_languages(self) -> list[str]:
        # Advertise the configured language so pipeline metadata cannot disagree.
        return [self._language]

    @property
    def supported_formats(self) -> list[stt.AudioFormats]:
        return [stt.AudioFormats.WAV]

    @property
    def supported_codecs(self) -> list[stt.AudioCodecs]:
        return [stt.AudioCodecs.PCM]

    @property
    def supported_bit_rates(self) -> list[stt.AudioBitRates]:
        return [stt.AudioBitRates.BITRATE_16]

    @property
    def supported_sample_rates(self) -> list[stt.AudioSampleRates]:
        return [stt.AudioSampleRates.SAMPLERATE_16000]

    @property
    def supported_channels(self) -> list[stt.AudioChannels]:
        return [stt.AudioChannels.CHANNEL_MONO]

    @property
    def audio_processing(self) -> stt.SpeechAudioProcessing:
        return stt.SpeechAudioProcessing(
            requires_external_vad=True,
            prefers_auto_gain_enabled=True,
            prefers_noise_reduction_enabled=True,
        )

    async def async_process_audio_stream(
        self, metadata: stt.SpeechMetadata, stream: AsyncIterable[bytes]
    ) -> stt.SpeechResult:
        """Bound buffering to 30 seconds; reject oversized input without truncation."""
        if not self.check_metadata(metadata):
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
        audio = bytearray()
        iterator = aiter(stream)
        try:
            async for chunk in iterator:
                if len(audio) + len(chunk) > MAX_AUDIO_BYTES:
                    _LOGGER.error("Whistle supports at most 30 seconds per utterance")
                    return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
                audio.extend(chunk)
            if not audio or len(audio) % 2:
                return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
            text = await self._client.async_transcribe(bytes(audio), self._language)
        except (NeedleError, OSError):
            _LOGGER.exception("Whistle speech recognition failed")
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
        finally:
            if (close := getattr(iterator, "aclose", None)) is not None:
                await close()
        return stt.SpeechResult(text, stt.SpeechResultState.SUCCESS)
