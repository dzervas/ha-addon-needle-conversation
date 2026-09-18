"""Config flow for Needle Conversation."""

from __future__ import annotations

import logging
from typing import Any, override

import probatio

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .client import NeedleClient, NeedleError
from .const import (
    CONF_CONFIDENCE_THRESHOLD,
    CONF_MAX_CALLS,
    CONF_TIMEOUT,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_MAX_CALLS,
    DEFAULT_TIMEOUT,
    DOMAIN,
    MAX_CONFIDENCE_THRESHOLD,
    MAX_MAX_CALLS,
    MAX_TIMEOUT,
    MIN_CONFIDENCE_THRESHOLD,
    MIN_MAX_CALLS,
    MIN_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


def _schema(defaults: dict[str, Any]) -> probatio.Schema:
    """Build the configuration schema."""
    return probatio.Schema(
        {
            probatio.Required(
                CONF_URL,
                description={"suggested_value": defaults.get(CONF_URL, "")},
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
            probatio.Required(
                CONF_CONFIDENCE_THRESHOLD,
                description={
                    "suggested_value": defaults.get(
                        CONF_CONFIDENCE_THRESHOLD,
                        DEFAULT_CONFIDENCE_THRESHOLD,
                    )
                },
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_CONFIDENCE_THRESHOLD,
                    max=MAX_CONFIDENCE_THRESHOLD,
                    step=0.01,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            probatio.Required(
                CONF_TIMEOUT,
                description={
                    "suggested_value": defaults.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
                },
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_TIMEOUT,
                    max=MAX_TIMEOUT,
                    step=1,
                    unit_of_measurement="s",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            probatio.Required(
                CONF_MAX_CALLS,
                description={
                    "suggested_value": defaults.get(CONF_MAX_CALLS, DEFAULT_MAX_CALLS)
                },
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_MAX_CALLS,
                    max=MAX_MAX_CALLS,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                )
            ),
        }
    )


class NeedleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a Needle Conversation config flow."""

    VERSION = 1

    async def _async_validate(self, data: dict[str, Any]) -> tuple[str, str]:
        """Validate settings and return normalized URL and model name."""
        url = str(data[CONF_URL]).strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            raise ValueError("URL must begin with http:// or https://")

        client = NeedleClient(
            session=async_get_clientsession(self.hass),
            base_url=url,
            timeout=int(data[CONF_TIMEOUT]),
        )
        model_name = await client.async_model()
        return url, model_name

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial setup."""
        errors: dict[str, str] = {}
        defaults = user_input or {
            CONF_URL: "http://local-addon-needle-3:7860",
            CONF_CONFIDENCE_THRESHOLD: DEFAULT_CONFIDENCE_THRESHOLD,
            CONF_TIMEOUT: DEFAULT_TIMEOUT,
            CONF_MAX_CALLS: DEFAULT_MAX_CALLS,
        }

        if user_input is not None:
            try:
                url, model_name = await self._async_validate(user_input)
            except ValueError:
                errors["base"] = "invalid_url"
            except NeedleError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error while connecting to Needle")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(url.lower())
                self._abort_if_unique_id_configured()
                data = {**user_input, CONF_URL: url}
                return self.async_create_entry(title=model_name, data=data)

        return self.async_show_form(
            step_id="user", data_schema=_schema(defaults), errors=errors
        )

    @override
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        defaults = user_input or dict(entry.data)

        if user_input is not None:
            try:
                url, model_name = await self._async_validate(user_input)
            except ValueError:
                errors["base"] = "invalid_url"
            except NeedleError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error while connecting to Needle")
                errors["base"] = "unknown"
            else:
                data = {**user_input, CONF_URL: url}
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=url.lower(),
                    title=model_name,
                    data=data,
                )

        return self.async_show_form(
            step_id="reconfigure", data_schema=_schema(defaults), errors=errors
        )
