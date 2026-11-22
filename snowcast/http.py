"""Tiny stdlib HTTP helper with retries. No third-party deps."""

import gzip
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config


class HTTPError(Exception):
    def __init__(self, url, status, body=""):
        super().__init__(f"HTTP {status} for {url}: {body[:300]}")
        self.status = status
        self.body = body


def get_json(url, params=None, timeout=30, retries=2):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params, safe=',')}"
    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={
            "User-Agent": config.USER_AGENT, "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            # 4xx = our request is wrong (bad token/variable) or missing: don't retry
            if 400 <= e.code < 500:
                raise HTTPError(url, e.code, body) from None
            last = HTTPError(url, e.code, body)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
        time.sleep(2 * (attempt + 1))
    raise last
