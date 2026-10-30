"""The registered providers: every `Provider` subclass in this package, one file each.

Deleting a provider's file removes it.
"""

from importlib import import_module
import pkgutil
import shutil

from .base import Provider


class Registry:
    """Provider classes by name, in the default preference order."""

    def __init__(self, classes):
        self.classes = {cls.name: cls for cls in sorted(classes, key=lambda cls: cls.rank)}

    @classmethod
    def discover(cls):
        """The subclasses of every module in this package."""
        for module in pkgutil.iter_modules(__path__):
            import_module(f"{__name__}.{module.name}")
        return cls(Provider.__subclasses__())

    def names(self):
        return tuple(self.classes)

    def installed(self):
        """Every registered provider whose CLI is on PATH, in the default preference order."""
        return [name for name, cls in self.classes.items() if shutil.which(cls.name)]

    def efforts(self, name):
        return self.classes[name].efforts

    def provider(self, name, settings):
        return self.classes[name](settings)


registry = Registry.discover()
