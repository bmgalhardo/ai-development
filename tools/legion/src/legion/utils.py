"""Small generic helpers."""

import json
import urllib.request


def fetch_json(url, headers, timeout=15):
    """GET a JSON document; raises urllib's HTTPError on a refusal and OSError when unreachable."""
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
        return json.loads(response.read())
