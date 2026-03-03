"""Lightweight web search via DuckDuckGo (no API key required)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def search_web(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Return a list of {title, href, body} dicts from DuckDuckGo.

    Returns an empty list on any failure so callers can degrade gracefully.
    """
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [
            {
                "title": r.get("title", ""),
                "href": r.get("href", ""),
                "body": r.get("body", ""),
            }
            for r in results
        ]
    except Exception:
        logger.warning("web search failed for query=%s", query, exc_info=True)
        return []
