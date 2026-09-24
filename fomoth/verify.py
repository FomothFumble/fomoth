"""Second opinion on suspicious all-time highs.

The Solana data provider sometimes returns an all-time high that never traded: a GOAT peak of $15.40
when the real one was about $1.40, a 20,000x "peak" on a dead token. One bad high like that turns a
wallet's fumble into nine figures. So any peak that claims a big multiple is checked against real
GeckoTerminal candles, counting only candles that opened after the wallet's last sell. If the candles
can't confirm it, the lower confirmed peak is used, and with no candles at all the fumble is dropped.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

GT = "https://api.geckoterminal.com/api/v2"
SUSPICIOUS_MULT = 15.0
_last = [0.0]


def _gt(path: str):
    wait = _last[0] + 2.2 - time.time()
    if wait > 0:
        time.sleep(wait)
    for i in range(4):
        _last[0] = time.time()
        try:
            req = urllib.request.Request(GT + path, headers={"Accept": "application/json", "User-Agent": "fomoth/0.2"})
            return json.load(urllib.request.urlopen(req, timeout=40))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(3 * (i + 1))
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def peak_after(network: str, mint: str, since_ms: int) -> tuple[float, int] | None:
    """Highest candle high (USD) that opened at or after since_ms, with its time in ms. None = no data."""
    pools = _gt(f"/networks/{network}/tokens/{mint}/pools?page=1")
    rows = []
    for p in ((pools or {}).get("data") or [])[:2]:
        addr = p["attributes"]["address"]
        for tf in ("hour", "day"):
            c = _gt(f"/networks/{network}/pools/{addr}/ohlcv/{tf}?limit=1000&token={mint}&currency=usd")
            rows += ((c or {}).get("data", {}).get("attributes", {}).get("ohlcv_list") or [])
    after = [(float(r[2]), int(r[0]) * 1000) for r in rows if int(r[0]) * 1000 >= since_ms]
    if not rows:
        return None
    if not after:
        return (0.0, 0)
    return max(after)
