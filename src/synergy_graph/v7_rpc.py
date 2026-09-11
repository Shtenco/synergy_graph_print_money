from __future__ import annotations

import time
from typing import Any

import requests

from .v7 import Rpc


class ReliableRpc(Rpc):
    """RPC transport with connection reuse, retry/backoff and counters.

    V7 originally used a fresh HTTP connection for every JSON-RPC call and
    safe_call() converted any transport/rate-limit error into an empty result.
    On public Base RPC this can misclassify healthy pools as unsupported.
    This subclass keeps the existing Rpc interface while making transient
    failures explicit and retryable.
    """

    def __init__(
        self,
        url: str,
        timeout: int = 25,
        max_retries: int = 8,
        base_delay: float = 0.20,
        max_delay: float = 8.0,
        min_interval: float = 0.025,
    ):
        super().__init__(url, timeout)
        self.session = requests.Session()
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.min_interval = min_interval
        self._last_call_at = 0.0
        self.calls = 0
        self.retries = 0
        self.transport_failures = 0
        self.rpc_failures = 0

    def _sleep_before_call(self) -> None:
        if self.min_interval <= 0:
            return
        now = time.monotonic()
        remaining = self.min_interval - (now - self._last_call_at)
        if remaining > 0:
            time.sleep(remaining)

    def _backoff(self, attempt: int, retry_after: str | None = None) -> None:
        delay = min(self.max_delay, self.base_delay * (2 ** attempt))
        if retry_after:
            try:
                delay = max(delay, min(self.max_delay, float(retry_after)))
            except ValueError:
                pass
        self.retries += 1
        time.sleep(delay)

    @staticmethod
    def _retryable_rpc_error(error: Any) -> bool:
        if not isinstance(error, dict):
            return False
        code = error.get("code")
        msg = str(error.get("message", "")).lower()
        if code in {-32005, -32016, -32000, -32603}:
            return any(x in msg for x in ("rate", "limit", "busy", "timeout", "tempor", "capacity", "too many"))
        return any(x in msg for x in ("rate limit", "too many requests", "temporarily unavailable", "request limit"))

    def call(self, method: str, params: list[Any]) -> Any:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._sleep_before_call()
            self.calls += 1
            try:
                r = self.session.post(self.url, json=payload, timeout=self.timeout)
                self._last_call_at = time.monotonic()
                if r.status_code == 429 or 500 <= r.status_code < 600:
                    if attempt < self.max_retries:
                        self._backoff(attempt, r.headers.get("Retry-After"))
                        continue
                r.raise_for_status()
                body = r.json()
                if "error" in body:
                    if attempt < self.max_retries and self._retryable_rpc_error(body["error"]):
                        self._backoff(attempt)
                        continue
                    self.rpc_failures += 1
                    raise RuntimeError(f"RPC {method}: {body['error']}")
                return body["result"]
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                self.transport_failures += 1
                if attempt < self.max_retries:
                    self._backoff(attempt)
                    continue
                raise
            except requests.HTTPError as exc:
                last_error = exc
                self.transport_failures += 1
                if attempt < self.max_retries and exc.response is not None and (
                    exc.response.status_code == 429 or 500 <= exc.response.status_code < 600
                ):
                    self._backoff(attempt, exc.response.headers.get("Retry-After"))
                    continue
                raise
        if last_error:
            raise last_error
        raise RuntimeError(f"RPC {method} exhausted retries")

    def metrics(self) -> dict[str, int]:
        return {
            "rpc_calls": self.calls,
            "rpc_retries": self.retries,
            "rpc_transport_failures": self.transport_failures,
            "rpc_nonretryable_failures": self.rpc_failures,
        }
