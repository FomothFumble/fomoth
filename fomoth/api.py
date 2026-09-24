"""Solana Tracker data client.

One provider covers the whole backend: per-wallet PnL with a summary, and an all-time-high per
token with its timestamp. The wallet stats come straight from /pnl; the fumble is ours, computed
by asking whether the token's peak arrived after the wallet had already sold.

The key is read from SOLANATRACKER_KEY so it never lands in the repo.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

BASE = "https://data.solanatracker.io"


class SolanaTracker:
    def __init__(self, key: str | None = None, pace: float = 0.34):
        self.key = key or os.environ.get("SOLANATRACKER_KEY", "")
        self.pace = pace                      # 3 req/s on the free tier
        if not self.key:
            raise RuntimeError("set SOLANATRACKER_KEY")

    def _get(self, path: str, tries: int = 5):
        h = {"x-api-key": self.key, "User-Agent": "fomoth/0.1"}
        for i in range(tries):
            try:
                req = urllib.request.Request(BASE + path, headers=h)
                return json.load(urllib.request.urlopen(req, timeout=60))
            except urllib.error.HTTPError as e:
                if e.code == 429 or 500 <= e.code < 600:   # rate limit or gateway timeout, retry
                    time.sleep(1.5 * (i + 1))
                else:
                    return None
            except Exception:
                time.sleep(1.2 * (i + 1))
        return None

    def pnl(self, wallet: str) -> dict | None:
        """{'tokens': {mint: {...}}, 'summary': {...}}"""
        return self._get(f"/pnl/{wallet}")

    def ath(self, mint: str) -> dict | None:
        """{'highest_price', 'timestamp', ...}. Paced for the free tier."""
        d = self._get(f"/tokens/{mint}/ath")
        time.sleep(self.pace)
        return d

    def symbol(self, mint: str) -> str:
        """Token ticker, for worked examples. Empty string if unknown."""
        d = self._get(f"/tokens/{mint}")
        time.sleep(self.pace)
        try:
            return (d.get("token", {}).get("symbol") or "").strip()
        except Exception:
            return ""
