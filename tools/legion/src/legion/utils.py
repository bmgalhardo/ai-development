"""Small generic helpers."""

from datetime import datetime
import json
import urllib.request


def fetch_json(url, headers, timeout=15):
    """GET a JSON document; raises urllib's HTTPError on a refusal and OSError when unreachable."""
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
        return json.loads(response.read())


def save_json(path, value):
    """Write JSON atomically: readers see the old file or the new one, never half of it."""
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def say(message):
    """Print a line of the run's log, with the time."""
    print(f"{datetime.now():%H:%M} {message}", flush=True)
