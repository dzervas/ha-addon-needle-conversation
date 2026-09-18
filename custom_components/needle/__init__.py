"""Needle Conversation integration."""

from __future__ import annotations

from dataclasses import dataclass

from aiohttp import ClientSession

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import NeedleClient, NeedleError
from .const import (
    CONF_CONFIDENCE_THRESHOLD,
    CONF_MAX_CALLS,
    CONF_TIMEOUT,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_MAX_CALLS,
    DEFAULT_TIMEOUT,
)

PLATFORMS = (Platform.CONVERSATION,)


@dataclass(slots=True)
class NeedleRuntimeData:
    """Runtime data shared by Needle entities."""

    client: NeedleClient
    model_name: str
    confidence_threshold: float
    max_calls: int


type NeedleConfigEntry = ConfigEntry[NeedleRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: NeedleConfigEntry) -> bool:
    """Set up Needle from a config entry."""
    session: ClientSession = async_get_clientsession(hass)
    client = NeedleClient(
        session=session,
        base_url=str(entry.data[CONF_URL]).rstrip("/"),
        timeout=int(entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)),
    )

    try:
        model_name = await client.async_model()
    except NeedleError as err:
        raise ConfigEntryNotReady(f"Unable to connect to Needle: {err}") from err

    entry.runtime_data = NeedleRuntimeData(
        client=client,
        model_name=model_name,
        confidence_threshold=float(
            entry.data.get(
                CONF_CONFIDENCE_THRESHOLD, DEFAULT_CONFIDENCE_THRESHOLD
            )
        ),
        max_calls=int(entry.data.get(CONF_MAX_CALLS, DEFAULT_MAX_CALLS)),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NeedleConfigEntry) -> bool:
    """Unload a Needle config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

