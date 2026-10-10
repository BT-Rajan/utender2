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

    def record_failure(self, ip: str, email: str) -> bool:
        """Records a failed attempt. Returns True when this very failure is
        the one that tips the account or the address into lockout, so the
        caller can audit the lockout once instead of on every refused retry."""
        now = time.monotonic()
        locked_now = False
        with self._lock:
            if len(self._failures) > 10_000:  # opportunistic sweep so keys can't pile up forever
                for key in list(self._failures):
                    self._live(key, now)
            acct_key, ip_key = self._keys(ip, email)
            for key, limit in ((acct_key, self.max_per_account), (ip_key, self.max_per_ip)):
                hits = self._failures.setdefault(key, deque())
                hits.append(now)
                if len(hits) == limit:
                    locked_now = True
        return locked_now

    def record_success(self, ip: str, email: str) -> None:
        with self._lock:
            self._failures.pop(self._keys(ip, email)[0], None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


login_throttle = LoginThrottle()
