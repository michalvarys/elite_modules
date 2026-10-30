"""Minimal ggLeap Public API client (no Odoo dependency, so it can be faked in tests).

* AuthToken (Settings → API → Public API in ggLeap admin) is exchanged for a JWT that is
  valid 10 minutes; it is renewed every 5 minutes.
* Basic tier allows 20 requests/minute and 10 000/day; the client keeps a minimal gap
  between calls (``rpm``), counts calls and refuses to go over ``max_calls``.
* 401 → new JWT (and the other Authorization scheme), 429/5xx → short pause and retry
  (write calls carry an idempotency key, so a retry is safe).
"""
import json
import logging
import time

import requests

_logger = logging.getLogger(__name__)

BASES = {
    "production": "https://api.ggleap.com/production",
    "beta": "https://api.ggleap.com/beta",
}
MAX_PAGES = 2000


class GgleapError(Exception):
    """API answered with an error that retrying will not fix."""


class GgleapAuthError(GgleapError):
    """The AuthToken was refused."""


class GgleapBudgetError(GgleapError):
    """The call limit for this run (or for today) is used up."""


class GgleapClient:
    def __init__(self, base, auth_token, rpm=18, max_calls=None, timeout=60, sleep=time.sleep):
        if not auth_token:
            raise GgleapAuthError("Chybí AuthToken ggLeapu (Konfigurace → Nastavení).")
        self.base = base.rstrip("/")
        self.auth_token = auth_token
        self.min_interval = 60.0 / max(float(rpm or 18), 0.1)
        self.max_calls = max_calls
        self.timeout = timeout
        self.sleep = sleep
        self.session = requests.Session()
        self.jwt = None
        self.jwt_at = 0.0
        self.scheme = ""  # "" or "Bearer "; switched automatically on 401
        self.last_call = 0.0
        self.calls = 0

    # ------------------------------------------------------------------ helpers
    def _throttle(self):
        if self.max_calls is not None and self.calls >= self.max_calls:
            raise GgleapBudgetError("Vyčerpán limit volání API pro tento běh.")
        wait = self.last_call + self.min_interval - time.time()
        if wait > 0:
            self.sleep(wait)
        self.last_call = time.time()
        self.calls += 1

    def _ensure_jwt(self):
        if self.jwt and time.time() - self.jwt_at < 300:
            return
        self._throttle()
        resp = self.session.post(self.base + "/authorization/public-api/auth",
                                 json={"AuthToken": self.auth_token},
                                 headers={"Accept": "application/json"}, timeout=self.timeout)
        if resp.status_code in (400, 401, 403):
            raise GgleapAuthError("ggLeap odmítl AuthToken (HTTP %s)." % resp.status_code)
        if resp.status_code >= 400:
            raise GgleapError("Přihlášení k ggLeap selhalo: HTTP %s %s" % (resp.status_code, resp.text[:200]))
        self.jwt = resp.json()["Jwt"]
        self.jwt_at = time.time()

    @staticmethod
    def encode(params):
        """ggLeap wants arrays as ``Name[]=a&Name[]=b`` and booleans as true/false."""
        pairs = []
        for key, value in (params or {}).items():
            if value is None:
                continue
            if isinstance(value, (list, tuple, set)):
                name = key if key.endswith("[]") else key + "[]"
                pairs.extend((name, str(v)) for v in value)
            elif isinstance(value, bool):
                pairs.append((key, "true" if value else "false"))
            else:
                pairs.append((key, str(value)))
        return pairs

    # ------------------------------------------------------------------ public
    def get(self, path, params=None):
        return self._request("GET", path, params=params)

    def post(self, path, body, correlation_id=None):
        """Write call. ggLeap treats ``X-Correlation-Id`` as an idempotency key, so a retry
        with the same id does not do the change twice."""
        headers = {"X-Correlation-Id": correlation_id} if correlation_id else {}
        return self._request("POST", path, body=body, headers=headers)

    def _request(self, method, path, params=None, body=None, headers=None):
        last = None
        for attempt in range(4):
            self._ensure_jwt()
            self._throttle()
            try:
                resp = self.session.request(method, self.base + path, params=self.encode(params), json=body,
                                            timeout=self.timeout,
                                            headers=dict(headers or {}, Authorization=self.scheme + self.jwt,
                                                         Accept="application/json"))
            except requests.RequestException as err:
                last = err
                self.sleep(5 * (attempt + 1))
                continue
            if resp.status_code == 401:
                self.jwt = None
                self.scheme = "Bearer " if self.scheme == "" else ""
                last = "HTTP 401"
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                last = "HTTP %s" % resp.status_code
                _logger.info("ggLeap %s na %s, čekám", resp.status_code, path)
                self.sleep(20 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                raise GgleapError("%s %s: %s" % (resp.status_code, path, resp.text[:300]))
            return resp.json() if resp.content else {}
        raise GgleapError("API opakovaně selhalo: %s (%s)" % (path, last))

    def paged(self, path, params, key):
        """Yields items of all pages (PaginationToken). An empty page with a token goes on."""
        token, seen = None, set()
        for _ in range(MAX_PAGES):
            query = dict(params or {})
            if token:
                query["PaginationToken"] = token
            data = self.get(path, query)
            for item in data.get(key) or []:
                yield item
            token = data.get("PaginationToken")
            if not token or token in seen:
                return
            seen.add(token)

    def describe(self):
        return json.dumps({"base": self.base, "calls": self.calls})
