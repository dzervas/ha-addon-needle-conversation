"""Conversation platform for Needle."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal, override

import probatio

from homeassistant.components import conversation
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent, llm
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NeedleConfigEntry
from .client import NeedleError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeedleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Needle conversation entity."""
    async_add_entities([NeedleConversationEntity(entry)])


def _snake_case(value: str) -> str:
    """Convert a Home Assistant tool name to a Needle-friendly name."""
    value = value.replace("__", "_")
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    value = re.sub(r"[^A-Za-z0-9_]+", "_", value)
    return value.strip("_").lower()


def _format_tools(
    api: llm.APIInstance,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Convert HA tools to Needle schemas and return alias mapping."""
    tools: list[dict[str, Any]] = []
    aliases: dict[str, str] = {}

    for index, tool in enumerate(api.tools):
        # Needle is a one-shot action router. Context/query tools need another
        # language-model turn to turn their result into speech, which Needle
        # deliberately does not provide.
        if tool.name.endswith("__GetLiveContext"):
            continue

        alias = _snake_case(tool.name)
        if not alias or alias in aliases:
            alias = f"ha_tool_{index}"

        parameters = probatio.to_openapi(
            tool.parameters,
            custom_serializer=api.custom_serializer or llm.selector_serializer,
            openapi_version="3.1.0",
        )
        tools.append(
            {
                "name": alias,
                "description": tool.description or f"Execute {tool.name}",
                "parameters": parameters,
            }
        )
        aliases[alias] = tool.name

    return tools, aliases


def _parse_arguments(value: Any) -> dict[str, Any] | None:
    """Parse and validate a Needle function-call argument object."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


def _result_speech(result: conversation.ToolResultContent) -> str | None:
    """Extract HA's localized intent speech from a tool result."""
    data = result.result.data
    original = getattr(data, "original", None)
    if original is None:
        return None

    response = original.as_dict()
    speech = response.get("speech", {}).get("plain", {}).get("speech")
    return speech.strip() if isinstance(speech, str) and speech.strip() else None


class NeedleConversationEntity(
    conversation.ConversationEntity,
    conversation.AbstractConversationAgent,
):
    """Needle-backed Assist conversation agent."""

    _attr_has_entity_name = False
    _attr_name = "Needle Conversation"
    _attr_icon = "mdi:needle"
    _attr_supported_features = conversation.ConversationEntityFeature.CONTROL

    def __init__(self, entry: NeedleConfigEntry) -> None:
        """Initialize the entity."""
        self.entry = entry
        self._attr_unique_id = entry.entry_id

    @property
    @override
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Needle accepts text in any language supported by its model."""
        return MATCH_ALL

    @override
    async def async_added_to_hass(self) -> None:
        """Register the entity as a conversation agent."""
        await super().async_added_to_hass()
        conversation.async_set_agent(self.hass, self.entry, self)

    @override
    async def async_will_remove_from_hass(self) -> None:
        """Unregister the conversation agent."""
        conversation.async_unset_agent(self.hass, self.entry)
        await super().async_will_remove_from_hass()

    @override
    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> conversation.ConversationResult:
        """Route a user command through Needle and execute safe HA tools."""
        native_result = await self._async_handle_native(user_input, chat_log)
        if native_result is not None:
            return native_result

        try:
            await chat_log.async_provide_llm_data(
                user_input.as_llm_context(DOMAIN),
                llm.LLM_API_ASSIST,
            )
        except conversation.ConverseError as err:
            return err.as_conversation_result()

        if chat_log.llm_api is None:
            return self._async_refuse(
                user_input, chat_log, "Home Assistant did not provide any tools."
            )

        tools, aliases = _format_tools(chat_log.llm_api)
        if not tools:
            return self._async_refuse(
                user_input,
                chat_log,
                "No controllable entities are exposed to Assist.",
            )

        try:
            response = await self.entry.runtime_data.client.async_complete(
                user_input.text, tools
            )
        except NeedleError as err:
            _LOGGER.error("Needle request failed: %s", err)
            return self._async_refuse(
                user_input, chat_log, "I couldn't reach Needle."
            )

        _LOGGER.debug("Needle response: %s", response)

        if error := response.get("error"):
            _LOGGER.error("Needle returned an error: %s", error)
            return self._async_refuse(
                user_input, chat_log, "Needle could not process that request."
            )

        if response.get("success") is False or response.get("type") == "refuse":
            return self._async_refuse(
                user_input,
                chat_log,
                "I couldn't match that to a Home Assistant action.",
            )

        confidence = response.get("confidence")
        if not isinstance(confidence, int | float):
            _LOGGER.warning(
                "Rejected Needle output without calibrated confidence; calls=%s",
                _call_names(response.get("function_calls")),
            )
            return self._async_refuse(
                user_input,
                chat_log,
                "Needle did not provide a calibrated confidence score.",
            )
        if float(confidence) < self.entry.runtime_data.confidence_threshold:
            _LOGGER.info(
                "Rejected Needle output with confidence %.3f (minimum %.3f); calls=%s",
                float(confidence),
                self.entry.runtime_data.confidence_threshold,
                _call_names(response.get("function_calls")),
            )
            return self._async_refuse(
                user_input,
                chat_log,
                "I'm not confident enough to safely do that.",
            )

        raw_calls = response.get("function_calls")
        if not isinstance(raw_calls, list) or not raw_calls:
            return self._async_refuse(
                user_input,
                chat_log,
                "I couldn't match that to a Home Assistant action.",
            )
        if len(raw_calls) > self.entry.runtime_data.max_calls:
            return self._async_refuse(
                user_input,
                chat_log,
                "That request contains too many actions.",
            )

        tool_inputs: list[llm.ToolInput] = []
        for raw_call in raw_calls:
            if not isinstance(raw_call, dict):
                return self._async_refuse(
                    user_input, chat_log, "Needle returned an invalid action."
                )

            alias = raw_call.get("name")
            arguments = _parse_arguments(raw_call.get("arguments", {}))
            if not isinstance(alias, str) or alias not in aliases or arguments is None:
                _LOGGER.warning("Rejected invalid Needle function call: %s", raw_call)
                return self._async_refuse(
                    user_input, chat_log, "Needle returned an invalid action."
                )

            tool_inputs.append(
                llm.ToolInput(tool_name=aliases[alias], tool_args=arguments)
            )

        tool_results: list[conversation.ToolResultContent] = []
        assistant_call = conversation.AssistantContent(
            agent_id=user_input.agent_id,
            content=None,
            tool_calls=tool_inputs,
        )
        async for tool_result in chat_log.async_add_assistant_content(assistant_call):
            tool_results.append(tool_result)

        if any(result.result.error for result in tool_results):
            speech = "I couldn't complete that request."
        else:
            responses = [
                text
                for result in tool_results
                if (text := _result_speech(result)) is not None
            ]
            speech = " ".join(dict.fromkeys(responses)) or "Done."

        chat_log.async_add_assistant_content_without_tools(
            conversation.AssistantContent(
                agent_id=user_input.agent_id,
                content=speech,
            )
        )
        return conversation.async_get_result_from_chat_log(user_input, chat_log)

    async def _async_handle_native(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> conversation.ConversationResult | None:
        """Let Home Assistant handle exact local intents before Needle."""
        try:
            trigger_speech = await conversation.async_handle_sentence_triggers(
                self.hass, user_input, chat_log
            )
            if trigger_speech is not None:
                response = intent.IntentResponse(
                    language=user_input.language or self.hass.config.language
                )
                response.async_set_speech(trigger_speech)
                return self._async_native_result(
                    user_input, chat_log, response, trigger_speech
                )

            response = await conversation.async_handle_intents(
                self.hass, user_input, chat_log
            )
        except Exception:  # noqa: BLE001 - isolate failures in HA's recognizer.
            _LOGGER.exception(
                "Native Home Assistant intent handling failed for %r", user_input.text
            )
            return self._async_refuse(
                user_input,
                chat_log,
                "Home Assistant couldn't process that request.",
            )

        if response is None:
            return None

        speech = response.speech.get("plain", {}).get("speech", "")
        if not isinstance(speech, str) or not speech.strip():
            speech = "Done."
        return self._async_native_result(user_input, chat_log, response, speech)

    @staticmethod
    def _async_native_result(
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
        response: intent.IntentResponse,
        speech: str,
    ) -> conversation.ConversationResult:
        """Complete a result already handled by Home Assistant."""
        chat_log.async_add_assistant_content_without_tools(
            conversation.AssistantContent(
                agent_id=user_input.agent_id,
                content=speech,
            )
        )
        return conversation.ConversationResult(
            response=response,
            conversation_id=chat_log.conversation_id,
        )

    @staticmethod
    def _async_refuse(
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
        speech: str,
    ) -> conversation.ConversationResult:
        """Add a refusal to the chat log and return it."""
        chat_log.async_add_assistant_content_without_tools(
            conversation.AssistantContent(
                agent_id=user_input.agent_id,
                content=speech,
            )
        )
        return conversation.async_get_result_from_chat_log(user_input, chat_log)


def _call_names(value: Any) -> list[str]:
    """Return safe call names for diagnostics."""
    if not isinstance(value, list):
        return []
    return [
        name
        for call in value
        if isinstance(call, dict) and isinstance((name := call.get("name")), str)
    ]
