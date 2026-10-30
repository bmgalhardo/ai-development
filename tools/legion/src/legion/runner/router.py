"""Which provider takes a step: a pure choice from the preference and the run's state."""

from pydantic import BaseModel


class Situation(BaseModel):
    """The run's state for one issue: cooldowns (Unix seconds), who is signed out, who failed it, who implemented it."""

    cooldowns: dict[str, float] = {}
    signed_out: set[str] = set()
    failed: set[str] = set()
    implementer: str | None = None


class Use(BaseModel):
    provider: str


class Wait(BaseModel):
    until: float


class Stop(BaseModel):
    """Every provider in the preference is signed out."""

    signed_out: list[str]


class Router:
    """Chooses the provider for a step, in the preference's order.

    Implement and fix: the first ready provider, preferring one that hasn't
    failed the issue. Review: the first ready provider other than the issue's
    implementer, else the implementer; a review never waits for a cooling
    reviewer. Nobody ready: wait for the earliest reset. Everyone signed out: stop.
    """

    def __init__(self, preference):
        self.preference = list(preference)

    def choose(self, role, situation, now):
        available = [name for name in self.preference if name not in situation.signed_out]
        if not available:
            return Stop(signed_out=sorted(situation.signed_out & set(self.preference)))
        ready = [name for name in available if situation.cooldowns.get(name, 0) <= now]
        if not ready:
            return Wait(until=min(situation.cooldowns[name] for name in available))
        # min keeps the preference's order among equally ranked providers.
        return Use(provider=min(ready, key=lambda name: self.rank(name, role, situation)))

    @staticmethod
    def rank(name, role, situation):
        """Lower is better: a reviewer other than the implementer first, then one that hasn't failed."""
        return (role == "review" and name == situation.implementer, name in situation.failed)
