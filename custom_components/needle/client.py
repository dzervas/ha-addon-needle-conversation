"""HTTP client for a Needle playground server."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientError, ClientSession


class NeedleError(Exception):
    """Base exception for Needle client failures."""


class NeedleConnectionError(NeedleError):
    """Raised when the Needle server cannot be reached."""


class NeedleResponseError(NeedleError):
    """Raised when the Needle server returns an invalid response."""


@dataclass(slots=True)
class NeedleClient:
    """Small async client for the Needle playground API."""

    session: ClientSession
    base_url: str
    timeout: int

    async def async_model(self) -> str:
        """Return the currently loaded model name."""
        payload = await self._async_json("GET", "/model")
        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            raise NeedleResponseError("Needle /model response has no model name")
        return name.strip()

    async def async_complete(
        self, query: str, tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Ask Needle to route a natural-language command."""
        return await self._async_json(
            "POST", "/complete", json={"query": query, "tools": tools}
        )

    async def _async_json(
        self, method: str, path: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Make a request and require a JSON object response."""
        try:
            async with asyncio.timeout(self.timeout):
                async with self.session.request(
                    method, f"{self.base_url}{path}", **kwargs
                ) as response:
                    response.raise_for_status()
                    payload = await response.json(content_type=None)
        except (TimeoutError, ClientError) as err:
            raise NeedleConnectionError(str(err)) from err
        except ValueError as err:
            raise NeedleResponseError("Needle returned invalid JSON") from err

        if not isinstance(payload, dict):
            raise NeedleResponseError("Needle returned a non-object JSON response")
        return payload
