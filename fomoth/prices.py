"""Token price history from GeckoTerminal, free and keyless.

Used only by the regret engine, to answer one question per token: after you sold, how high did it
go. Daily candles are enough for a fumble estimate and keep the number of calls low. Results are
cached to _scratch so a second run does not touch the network.

GeckoTerminal allows about 30 calls a minute, so the caller paces itself.
"""
from __future__ import annotations

import json
import pathlib
import time
import urllib.request

BASE = "https://api.geckoterminal.com/api/v2"
UA = {"User-Agent": "fomoth/0.1", "Accept": "application/json"}
CACHE = pathlib.Path(__file__).resolve().parent.parent / "_scratch" / "prices"
CACHE.mkdir(parents=True, exist_ok=True)


def _get(url: str) -> dict | None:
    for i in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(3 * (i + 1))
            else:
                return None
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def _top_pool(mint: str) -> str | None:
    d = _get(f"{BASE}/networks/solana/tokens/{mint}/pools?page=1")
    if not d or not d.get("data"):
        return None
    # pools come sorted by liquidity; the first is the canonical one
    pid = d["data"][0]["id"]                 # e.g. "solana_<pool>"
    return pid.split("_", 1)[1] if "_" in pid else pid


def daily(mint: str, pace: float = 2.2) -> list[tuple[int, float, float]]:
    """[(ts, high_usd, close_usd)] daily, oldest first. Empty if the token has no live pool."""
    cf = CACHE / f"{mint}.json"
    if cf.exists():
        return [tuple(r) for r in json.loads(cf.read_text())]

    pool = _top_pool(mint)
    time.sleep(pace)
    rows: list[tuple[int, float, float]] = []
    if pool:
        d = _get(f"{BASE}/networks/solana/pools/{pool}/ohlcv/day?aggregate=1&limit=1000&currency=usd")
        time.sleep(pace)
        ohlcv = (((d or {}).get("data") or {}).get("attributes") or {}).get("ohlcv_list") or []
        for c in ohlcv:
            # [ts, open, high, low, close, volume]
            rows.append((int(c[0]), float(c[2]), float(c[4])))
        rows.sort()
    cf.write_text(json.dumps(rows), encoding="utf-8")
    return rows
