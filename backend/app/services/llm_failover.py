"""Process-local admission/cooldowns. Contains no patient data or completions.

A threading lock protects short synchronous state transitions across event
loops/threads. Network I/O never holds the lock. One admitted request per
model prevents a concurrent wave from repeating the same failing probe.
Workers/processes have independent registries; no distributed quota claim.
"""
import threading
import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class _State:
    until: float = 0.0
    failures: int = 0
    in_flight: bool = False


class CooldownRegistry:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._states: dict[tuple[str, str], _State] = {}

    def admit(self, provider: str, model: str) -> str | None:
        with self._lock:
            now = self._clock()
            group = self._states.get((provider, "*"))
            state = self._states.setdefault((provider, model), _State())
            if group is not None and group.until > now:
                return "provider_cooldown"
            if state.until > now:
                return "model_cooldown"
            if state.in_flight:
                return "in_flight"
            state.in_flight = True
            return None

    def finish(
        self, provider: str, model: str, *, outcome: str,
        cooldown: float, threshold: int, retry_after: float = 0,
        provider_wide: bool = False,
    ) -> None:
        with self._lock:
            state = self._states[(provider, model)]
            state.in_flight = False
            if outcome in ("cancelled", "internal_error"):
                return
            if outcome == "success":
                state.failures = 0
                state.until = 0.0
                return
            state.failures += 1
            if outcome in ("rate_limit", "authentication", "configuration") or (
                state.failures >= threshold or retry_after > 0
            ):
                state.until = max(state.until, self._clock() + max(cooldown, retry_after))
            if provider_wide:
                group = self._states.setdefault((provider, "*"), _State())
                group.until = max(group.until, self._clock() + max(cooldown, retry_after))
