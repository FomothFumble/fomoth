"""FIFO profit and loss per token, and the wallet's trading statistics.

Realized PnL matches lots first-in-first-out, the way a trader intuitively thinks about it: the
coins you sell are the ones you bought earliest. Unrealized PnL on whatever is still held is
marked later against a live price; here we leave it as the open cost basis so the engine can
attach a current price in one place.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from .trades import Trade


@dataclass
class TokenPnL:
    mint: str
    realized_sol: float = 0.0
    bought_sol: float = 0.0
    sold_sol: float = 0.0
    buys: int = 0
    sells: int = 0
    open_tokens: float = 0.0
    open_cost_sol: float = 0.0
    first_ts: int = 0
    last_ts: int = 0
    hold_secs: float = 0.0        # realized, weighted by lot size
    _weighted_hold: float = 0.0
    _closed_tokens: float = 0.0


@dataclass
class WalletPnL:
    tokens: dict[str, TokenPnL] = field(default_factory=dict)
    realized_sol: float = 0.0
    wins: int = 0
    losses: int = 0

    @property
    def win_rate(self) -> float:
        n = self.wins + self.losses
        return self.wins / n if n else 0.0


def compute(trades: list[Trade]) -> WalletPnL:
    lots: dict[str, deque] = defaultdict(deque)   # mint -> [(tokens, sol_cost, ts)]
    per: dict[str, TokenPnL] = {}
    wp = WalletPnL()

    for t in trades:
        tk = per.setdefault(t.mint, TokenPnL(mint=t.mint, first_ts=t.ts))
        tk.last_ts = t.ts
        if not tk.first_ts:
            tk.first_ts = t.ts

        if t.side == "buy":
            lots[t.mint].append([t.tokens, t.sol, t.ts])
            tk.bought_sol += t.sol
            tk.buys += 1
            tk.open_tokens += t.tokens
            tk.open_cost_sol += t.sol
        else:
            tk.sold_sol += t.sol
            tk.sells += 1
            remaining = t.tokens
            proceeds_per = t.sol / t.tokens if t.tokens else 0.0
            matched_cost = 0.0
            realized_here = 0.0
            while remaining > 1e-12 and lots[t.mint]:
                lot = lots[t.mint][0]
                take = min(remaining, lot[0])
                cost_per = lot[1] / lot[0] if lot[0] else 0.0
                matched_cost += take * cost_per
                realized_here += take * (proceeds_per - cost_per)
                tk._weighted_hold += take * (t.ts - lot[2])
                tk._closed_tokens += take
                lot[0] -= take
                lot[1] -= take * cost_per
                remaining -= take
                if lot[0] <= 1e-12:
                    lots[t.mint].popleft()
            tk.realized_sol += realized_here
            tk.open_tokens = max(0.0, tk.open_tokens - (t.tokens - remaining))
            tk.open_cost_sol = max(0.0, tk.open_cost_sol - matched_cost)
            wp.realized_sol += realized_here
            if realized_here > 0:
                wp.wins += 1
            elif realized_here < 0:
                wp.losses += 1

    for tk in per.values():
        if tk._closed_tokens > 0:
            tk.hold_secs = tk._weighted_hold / tk._closed_tokens
    wp.tokens = per
    return wp
