"""Minimal JSON-RPC 2.0 client for the Odoo routes of the contract (standard library only)."""

from __future__ import annotations

import itertools
import json
import logging
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Optional

log = logging.getLogger(__name__)

STATUS_ROUTE = "/winvet/api/v1/status"
PUSH_ROUTE = "/winvet/api/v1/push"
RETRY_HTTP_CODES = (408, 429, 500, 502, 503, 504)


class OdooError(Exception):
    """Odoo answered, but refused the request (``ok: false``, JSON-RPC error, HTTP 4xx)."""


class OdooTransportError(OdooError):
    """Odoo could not be reached (after all retries)."""


class OdooClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 60.0,
        retries: int = 3,
        backoff: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.timeout = timeout
        self.retries = max(0, int(retries))
        self.backoff = backoff
        self._sleep = sleep
        self._ids = itertools.count(1)
        parsed = urllib.parse.urlparse(self.base_url)
        if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            log.warning("Odoo URL is not HTTPS - the API key and personal data travel unencrypted")

    def __repr__(self) -> str:  # never expose the key
        return f"OdooClient({self.base_url!r})"

    def call(self, route: str, params: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(
            {"jsonrpc": "2.0", "method": "call", "params": params, "id": next(self._ids)},
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + route,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )
        attempt = 0
        while True:
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = response.read()
                break
            except urllib.error.HTTPError as exc:
                if exc.code in RETRY_HTTP_CODES and attempt < self.retries:
                    reason = f"HTTP {exc.code}"
                else:
                    raise OdooError(f"{route}: HTTP {exc.code}") from None
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
                if attempt >= self.retries:
                    raise OdooTransportError(f"{route}: {exc}") from None
                reason = str(exc)
            delay = self.backoff * (2 ** attempt)
            attempt += 1
            log.warning("Odoo %s failed (%s), retry %d/%d in %.1fs", route, reason, attempt, self.retries, delay)
            self._sleep(delay)

        try:
            answer = json.loads(payload.decode("utf-8"))
        except ValueError:
            raise OdooError(f"{route}: answer is not JSON") from None
        if not isinstance(answer, dict):
            raise OdooError(f"{route}: unexpected answer")
        if answer.get("error"):
            error = answer["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            data = error.get("data") if isinstance(error, dict) else None
            if isinstance(data, dict) and data.get("message"):
                message = f"{message}: {data['message']}"
            raise OdooError(f"{route}: JSON-RPC error: {message}")
        result = answer.get("result")
        if not isinstance(result, dict) or not result.get("ok"):
            error = result.get("error") if isinstance(result, dict) else None
            raise OdooError(f"{route}: refused: {error or 'ok is not true'}")
        return result

    def status(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.call(STATUS_ROUTE, payload)

    def push(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.call(PUSH_ROUTE, payload)


def make_client(odoo_config, sleep: Optional[Callable[[float], None]] = None) -> OdooClient:
    kwargs = {"sleep": sleep} if sleep else {}
    return OdooClient(
        odoo_config.url, odoo_config.api_key, timeout=odoo_config.timeout, retries=odoo_config.retries, **kwargs
    )
