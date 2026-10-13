import threading
import time
from collections import deque

# Failed-login throttle. Process-local and in-memory by design: it needs no
# schema or new dependency, and still stops online password guessing against
# a single-process deployment. With several workers/instances each keeps its
# own counts, so the effective limit is multiplied by the process count --
# enough to blunt brute force, not a substitute for edge rate limiting.
#
# Two windows: per (client ip, account) so one attacker can't lock a victim
# out from everywhere, and per client ip so credential stuffing across many
# accounts from one address is bounded too.


class LoginThrottle:
    def __init__(self, max_per_account: int = 5, max_per_ip: int = 30, window_seconds: int = 15 * 60):
        self.max_per_account = max_per_account
        self.max_per_ip = max_per_ip
        self.window = window_seconds
        self._lock = threading.Lock()
        self._failures: dict[str, deque[float]] = {}

    @staticmethod
    def _keys(ip: str, email: str) -> tuple[str, str]:
        return f"acct:{ip}|{email}", f"ip:{ip}"

    def _live(self, key: str, now: float) -> deque[float] | None:
        hits = self._failures.get(key)
        if hits is None:
            return None
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if not hits:
            del self._failures[key]
            return None
        return hits

    def retry_after(self, ip: str, email: str) -> int:
        """Seconds the caller must wait; 0 means the attempt is allowed."""
        now = time.monotonic()
        acct_key, ip_key = self._keys(ip, email)
        wait = 0
        with self._lock:
            for key, limit in ((acct_key, self.max_per_account), (ip_key, self.max_per_ip)):
                hits = self._live(key, now)
                if hits is not None and len(hits) >= limit:
                    wait = max(wait, int(hits[0] + self.window - now) + 1)
        return wait

    def record_failure(self, ip: str, email: str) -> str | None:
        """Records a failed attempt. Returns which lockout this very failure
        starts -- "account" (this ip + account) or "ip" (the address as a
        whole) -- or None, so the caller can report the lockout once instead
        of on every refused retry, and against the right thing: an address
        lockout is not about whichever account happened to tip it."""
        now = time.monotonic()
        locked_now = None
        with self._lock:
            if len(self._failures) > 10_000:  # opportunistic sweep so keys can't pile up forever
                for key in list(self._failures):
                    self._live(key, now)
            acct_key, ip_key = self._keys(ip, email)
            for key, limit, which in ((ip_key, self.max_per_ip, "ip"), (acct_key, self.max_per_account, "account")):
                hits = self._failures.setdefault(key, deque())
                hits.append(now)
                if len(hits) == limit:
                    locked_now = which  # "account" wins if both tip at once
        return locked_now

    def record_success(self, ip: str, email: str) -> None:
        with self._lock:
            self._failures.pop(self._keys(ip, email)[0], None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


login_throttle = LoginThrottle()


class SeenRecently:
    """Remembers keys for a window, so an event can be reported once per key
    per window rather than once per request. Process-local, like the throttle
    above (several workers may each report a key once)."""

    def __init__(self, window_seconds: int = 10 * 60, max_keys: int = 10_000):
        self.window = window_seconds
        self.max_keys = max_keys
        self._lock = threading.Lock()
        self._seen: dict[str, float] = {}

    def first(self, key: str) -> bool:
        """True the first time a key is seen in the window (and records it)."""
        now = time.monotonic()
        with self._lock:
            if len(self._seen) > self.max_keys:
                self._seen = {k: t for k, t in self._seen.items() if t > now - self.window}
            seen_at = self._seen.get(key)
            if seen_at is not None and seen_at > now - self.window:
                return False
            self._seen[key] = now
            return True

    def reset(self) -> None:
        with self._lock:
            self._seen.clear()


# One session.refresh_replayed audit row per retired refresh token per window.
refresh_replays = SeenRecently()
