"""Random SFW anime GIFs from the Fluxpoint API.

Endpoints documented at https://docs.fluxpoint.dev/api/endpoints/sfw-anime-gifs:
``GET https://api.fluxpoint.dev/sfw/gif/<imageType>`` with the API token in the
``Authorization`` header returns JSON shaped like::

    {"success": true, "code": 200, "message": "", "id": "...", "file": "https://..."}

Every failure mode - missing key, HTTP errors, timeouts, malformed payloads -
resolves to ``None`` so a command can still reply without a GIF.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

log = logging.getLogger("matrimony.gifs")

BASE_URL = "https://api.fluxpoint.dev/sfw/gif"
DEFAULT_TIMEOUT = 10.0

# Fluxpoint endpoints used by Matrimony's action commands.
GIF_TYPES = (
    "baka",
    "bite",
    "blush",
    "cry",
    "dance",
    "feed",
    "fluff",
    "grab",
    "handhold",
    "highfive",
    "hug",
    "kiss",
    "laugh",
    "lick",
    "neko",
    "pat",
    "poke",
    "punch",
    "shrug",
    "slap",
    "smug",
)


class FluxpointClient:
    """Tiny async client for Fluxpoint's ``/sfw/gif/<imageType>`` endpoints.

    An ``aiohttp.ClientSession`` is created lazily on first use and reused;
    one may be injected for tests. ``close()`` is safe to call repeatedly.
    """

    def __init__(
        self,
        api_key: str = "",
        *,
        session: Any = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = api_key
        self._session = session
        self._owns_session = session is None
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def _get_session(self) -> Any:
        if self._session is None or getattr(self._session, "closed", False):
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def fetch_url(self, image_type: str) -> str | None:
        """Return a random GIF URL for ``image_type``, or ``None`` on failure.

        Never raises: network errors, non-200 responses, timeouts, and
        unexpected payloads are logged and turned into a GIF-less reply.
        """
        if not self.api_key:
            return None
        session = await self._get_session()
        try:
            async with session.get(
                f"{BASE_URL}/{image_type}",
                headers={"Authorization": self.api_key},
                timeout=self._timeout,
            ) as resp:
                if resp.status != 200:
                    log.warning(
                        "Fluxpoint gif %r: HTTP %s", image_type, resp.status
                    )
                    return None
                data = await resp.json(content_type=None)
        except Exception as exc:  # aiohttp errors, timeouts, bad JSON
            log.warning("Fluxpoint gif %r failed: %s", image_type, exc)
            return None
        if not isinstance(data, dict) or not data.get("success"):
            log.warning("Fluxpoint gif %r: unexpected payload %r", image_type, data)
            return None
        url = data.get("file")
        if not isinstance(url, str) or not url:
            log.warning("Fluxpoint gif %r: no file URL in %r", image_type, data)
            return None
        return url

    async def close(self) -> None:
        session, self._session = self._session, None
        if session is not None and self._owns_session:
            await session.close()
