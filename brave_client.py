import os
import requests
from typing import Optional

_BRAVE_API_KEY_CHECKED = False

def get_brave_headshot(talent_name: str) -> Optional[str]:
    """
    Fetch the first 'isolated' headshot result from Brave Image Search.
    Query: "<talent name> head shot"
    """
    global _BRAVE_API_KEY_CHECKED
    api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        if not _BRAVE_API_KEY_CHECKED:
            print("[Brave] WARNING: BRAVE_API_KEY not set. Brave image search disabled.")
            _BRAVE_API_KEY_CHECKED = True
        return None

    url = "https://api.search.brave.com/res/v1/images/search"
    params = {
        "q": f"{talent_name} head shot",
        "count": 1,
        "safesearch": "strict"
    }
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])

        if results:
            # Brave returns the image URL in results[0]['properties']['url']
            return results[0].get("properties", {}).get("url")
        else:
            print(f"[Brave] No results for: {talent_name}")

    except Exception as e:
        print(f"[Brave] Error searching for {talent_name}: {e}")

    return None
