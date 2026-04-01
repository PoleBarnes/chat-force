"""Web search tool wrapper.

This is a placeholder that will be backed by a real search provider
(e.g., Brave Search, Tavily, or SerpAPI) once the integration is configured.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def web_search(query: str, num_results: int = 5) -> list[dict[str, Any]]:
    """Search the web and return results.

    Parameters
    ----------
    query:
        The search query string.
    num_results:
        Maximum number of results to return.

    Returns
    -------
    list[dict]
        Each dict has ``title``, ``url``, and ``snippet`` keys.
        Currently returns an empty list (placeholder).
    """
    logger.info("Web search requested (not yet connected): %r", query)
    # TODO: Integrate with a search provider (Brave, Tavily, SerpAPI).
    # The provider API key would come from os.environ via Doppler.
    return []
