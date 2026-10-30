"""Legion's settings: the only reader of the environment and `.env`.

Every setting is a `WORK_` variable. The environment wins over `.env`, unknown
`WORK_` keys in `.env` are ignored, and invalid values fail when loading.
"""

import os
from pathlib import Path
from typing import Annotated

from pydantic import (BaseModel, Field, PositiveFloat, PositiveInt, ValidationError, create_model, field_validator,
                      model_validator)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from pydantic_settings import SettingsError as SourceError

from .providers import registry

DEFAULT_EFFORT = "medium"


class SettingsError(Exception):
    """Settings that can't be used, naming each variable and why."""


class Role(BaseModel):
    """A provider's model and effort for one role; an unset model keeps the CLI's default."""

    model: str | None = None
    effort: str | None = None


class ProviderRoles(BaseModel):
    """A provider's settings per role, from `WORK_<PROVIDER>__<ROLE>__MODEL` and `__EFFORT`."""

    implement: Role = Field(default_factory=Role)
    review: Role = Field(default_factory=Role)
    fix: Role = Field(default_factory=Role)

    def role(self, name):
        """The settings for a role, effort defaulting to medium; fix falls back to implement per field."""
        role = getattr(self, name)
        fallback = self.implement if name == "fix" else Role()
        return Role(model=role.model or fallback.model,
                    effort=role.effort or fallback.effort or DEFAULT_EFFORT)


class BaseLegionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WORK_", env_file=".env", env_nested_delimiter="__",
                                      extra="ignore")

    root: Path = Field(default_factory=Path.cwd, description="the workflow repo, holding .scratch and .logins")
    preference: Annotated[list[str], NoDecode] = Field(default_factory=registry.installed)
    wait: PositiveInt = 1800
    timeout: PositiveInt = 14400
    budget_usd: PositiveFloat = 15
    container: bool = False
    dashboard: bool = True
    dashboard_port: int = Field(8765, ge=1, le=65535)
    dashboard_host: str = "127.0.0.1"
    logins: Path | None = None
    image: str | None = None
    container_memory: str = "1536m"
    container_pids: PositiveInt = 512
    after_build: str = ""

    @field_validator("preference", mode="before")
    @classmethod
    def split(cls, value):
        if isinstance(value, str):
            return [name.strip() for name in value.split(",") if name.strip()]
        return value

    @field_validator("preference")
    @classmethod
    def known(cls, names):
        for name in names:
            if name not in registry.names():
                raise ValueError(f"unknown provider {name}; known: {', '.join(registry.names())}")
            if names.count(name) > 1:
                raise ValueError(f"{name} more than once")
        return names

    @model_validator(mode="after")
    def known_efforts(self):
        for name in registry.names():
            for role, settings in self.roles(name):
                if settings.effort and settings.effort not in registry.efforts(name):
                    variable = f"WORK_{name}__{role}__EFFORT".upper()
                    raise ValueError(f"{variable}: {settings.effort} is not one of "
                                     f"{', '.join(registry.efforts(name))}")
        return self

    @property
    def logins_folder(self):
        return self.logins or self.root / ".logins"

    def roles(self, provider):
        """A provider's settings per role."""
        return getattr(self, provider)

    def role(self, provider, role):
        """A provider's model and effort for a role, with the defaults applied."""
        return self.roles(provider).role(role)

    @classmethod
    def load(cls):
        """The settings, or a SettingsError naming each invalid variable.

        `.env` is the workflow root's: `WORK_ROOT` from the environment, else the current folder.
        """
        root = Path(os.environ.get("WORK_ROOT") or Path.cwd())
        try:
            return cls(_env_file=root / ".env")
        except ValidationError as error:
            lines = [f"{cls.variable(problem['loc'])}: {problem['msg']}" if problem["loc"] else problem["msg"]
                     for problem in error.errors()]
            raise SettingsError("Invalid settings:\n" + "\n".join(lines)) from None
        except SourceError as error:
            raise SettingsError(f"Invalid settings: {error}") from None

    @staticmethod
    def variable(location):
        """The environment variable for a validation error's location."""
        return "WORK_" + "__".join(str(part) for part in location if not isinstance(part, int)).upper()


# One nested field per registered provider, so no setting names a provider here.
Settings = create_model("Settings", __base__=BaseLegionSettings,
                        **{name: (ProviderRoles, Field(default_factory=ProviderRoles)) for name in registry.names()})
