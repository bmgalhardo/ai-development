"""The registered providers.

A placeholder registry: the provider classes replace these names.
"""

NAMES = ("claude", "codex")


def registered():
    """Every provider's name, in the default preference order."""
    return NAMES
