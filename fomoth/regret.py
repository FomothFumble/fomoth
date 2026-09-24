"""The regret engine: how much you left on the table.

For every token the wallet sold, it asks how high the price went after each sell and values the
difference against what you actually got. The sum is the fumble: money that was on the table and
that a later exit would have captured.

Everything is in USD, taken from the same daily candles, so the comparison is internally
consistent. It runs on the biggest positions first, because that is where the real fumble lives
and because a keyless price source is rate limited.

    fumble_usd(sell) = tokens_sold * max(0, peak_high_after_sell - price_at_sell)
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass

from .prices import daily
from .trades import Trade

DAY = 86400


@dataclass
class TokenRegret:
    mint: str
    sold_tokens: float = 0.0
    fumble_usd: float = 0.0        # left on the table across all sells
    peak_mult: float = 0.0        # peak after your last sell vs your last sell price
    sells: int = 0
    priced: bool = False          # did we have price history for it


def _series(mint: str):
    rows = daily(mint)                 # [(ts, high, close)]
    ts = [r[0] for r in rows]
    high = [r[1] for r in rows]
    close = [r[2] for r in rows]
    return ts, high, close


def token_regret(mint: str, sells: list[Trade]) -> TokenRegret:
    tr = TokenRegret(mint=mint, sells=len(sells))
    ts, high, close = _series(mint)
    if not ts:
        return tr
    tr.priced = True

    # suffix max of daily highs, so "peak after day i" is O(1)
    suffix = list(high)
    for i in range(len(suffix) - 2, -1, -1):
        suffix[i] = max(suffix[i], suffix[i + 1])

    last_sell_price = None
    last_sell_day = None
    for s in sells:
        day = s.ts - (s.ts % DAY)
        j = bisect.bisect_left(ts, day)
        if j >= len(ts):
            j = len(ts) - 1
        price_at = close[j] if close[j] > 0 else high[j]
        peak_after = suffix[j]
        tr.sold_tokens += s.tokens
        tr.fumble_usd += s.tokens * max(0.0, peak_after - price_at)
        if last_sell_day is None or s.ts > last_sell_day:
            last_sell_day, last_sell_price = s.ts, price_at
    if last_sell_price and last_sell_price > 0:
        k = bisect.bisect_left(ts, last_sell_day - (last_sell_day % DAY))
        k = min(k, len(suffix) - 1)
        tr.peak_mult = suffix[k] / last_sell_price
    return tr


def compute(trades: list[Trade], top_n: int = 25):
    """Regret for the top_n tokens by SOL sold. Returns (rows, total_fumble_usd, coverage)."""
    sells: dict[str, list[Trade]] = {}
    volume: dict[str, float] = {}
    for t in trades:
        if t.side == "sell":
            sells.setdefault(t.mint, []).append(t)
            volume[t.mint] = volume.get(t.mint, 0.0) + t.sol
    ranked = sorted(volume, key=volume.get, reverse=True)[:top_n]
    rows = [token_regret(m, sells[m]) for m in ranked]
    total = sum(r.fumble_usd for r in rows)
    priced = sum(1 for r in rows if r.priced)
    return rows, total, (priced, len(ranked))
