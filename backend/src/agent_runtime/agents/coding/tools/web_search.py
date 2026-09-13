from __future__ import annotations

import json
import os
from dotenv import load_dotenv
import urllib.parse
import urllib.request


load_dotenv()


def web_search(query: str, num_results: int = 5) -> str:
    """Perform a web search using the SerpApi service.

    Requires SERPAPI_API_KEY environment variable.

    Args:
        query: The search query string.
        num_results: Number of top results to return (default 5).

    Returns:
        A JSON string containing an array of result objects (title, link, snippet).
    """
    # Resolve the credential lazily. A missing key must not crash the entire
    # FastAPI sidecar during module import, because users configure it from the UI.
    from agent_runtime.config.settings import settings as config_settings

    api_key = config_settings.resolved_serpapi_api_key() or os.environ.get(
        "SERPAPI_API_KEY"
    )

    if not api_key:
        return json.dumps(
            {
                "error": (
                    "SerpApi is not configured. Add a SerpApi API key in "
                    "Agent configuration > Provider secrets."
                )
            }
        )

    params = {
        "q": query,
        "api_key": api_key,
        "num": str(num_results),
        "engine": "google",
    }

    url = "https://serpapi.com/search?" + urllib.parse.urlencode(params)

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        return json.dumps({"error": str(e)})

    organic_results = data.get("organic_results", [])
    results = []
    
    for item in organic_results[:num_results]:
        results.append({
            "title": item.get("title"),
            "link": item.get("link"),
            "snippet": item.get("snippet"),
        })

    return json.dumps(results)
