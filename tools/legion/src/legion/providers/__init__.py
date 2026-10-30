"""The registered providers.

A placeholder registry: the provider classes replace these names.
"""

import shutil

NAMES = ("claude", "codex")


def registered():
    """Every provider's name, in the default preference order."""
    return NAMES


def installed():
    """Every registered provider whose CLI is on PATH, in the default preference order."""
    return [name for name in registered() if shutil.which(name)]
