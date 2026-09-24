"""Turn a wallet into the full FOMOTH report: the stats and the fumble.

Stats come from Solana Tracker's PnL summary. The fumble is computed here: for every token the
wallet sold, if the token's all-time high arrived after the last sell, the difference between that
high and the average sell price, times the amount sold, is money left on the table.

    fumble(token) = sold_tokens * max(0, ath_price - avg_sell_price)   if ath_time > last_sell_time
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .api import SolanaTracker
from .coach import diagnose
from .verify import SUSPICIOUS_MULT, peak_after


@dataclass
class Fumble:
    mint: str
    sold_usd: float
    avg_sell: float
    ath_price: float
    ath_after_exit: bool
    left_on_table: float
    peak_mult: float          # ath vs your average sell
    sym: str = ""
    sold_tokens: float = 0.0
    days_to_peak: float = 0.0
    trail_value: float = 0.0  # what a 40%-trailing exit would have banked


@dataclass
class Report:
    wallet: str
    realized: float = 0.0
    total_invested: float = 0.0
    wins: int = 0
    losses: int = 0
    win_pct: float = 0.0
    tokens_traded: int = 0
    total_fumble: float = 0.0
    fumbles: list[Fumble] = field(default_factory=list)
    coach: dict = field(default_factory=dict)
    curve: list = field(default_factory=list)
    examples: list = field(default_factory=list)


def build(wallet: str, st: SolanaTracker, ath_top: int = 80) -> Report:
    pnl = st.pnl(wallet)
    if not pnl or not pnl.get("tokens"):
        raise RuntimeError("no trades found for this wallet, or the data source is slow. try again in a moment")
    tokens = pnl.get("tokens", {})
    s = pnl.get("summary", {})
    rep = Report(
        wallet=wallet,
        realized=s.get("realized", 0.0),
        total_invested=s.get("totalInvested", 0.0),
        wins=s.get("totalWins", 0),
        losses=s.get("totalLosses", 0),
        win_pct=s.get("winPercentage", 0.0),
        tokens_traded=len(tokens),
    )

    # only tokens the wallet actually sold, ranked by dollars sold, capped for the free tier
    sold = [(m, t) for m, t in tokens.items() if t.get("sold", 0) > 0 and t.get("sold_usd", 0) > 0]
    sold.sort(key=lambda x: x[1]["sold_usd"], reverse=True)

    verify = isinstance(st, SolanaTracker)       # robinhood peaks are read block-exact off the curve already
    for mint, t in sold[:ath_top]:
        avg_sell = t["sold_usd"] / t["sold"]
        ath = st.ath(mint) or {}
        ath_price = ath.get("highest_price", 0.0) or 0.0
        ath_time = ath.get("timestamp", 0) or 0
        last_sell = t.get("last_sell_time", 0) or 0
        after = ath_time > last_sell
        # a big claimed multiple from the solana provider gets checked against real candles first
        if verify and after and avg_sell > 0 and ath_price / avg_sell >= SUSPICIOUS_MULT:
            checked = peak_after("solana", mint, last_sell)
            if not checked or checked[0] <= avg_sell:
                after, ath_price = False, min(ath_price, checked[0] if checked else 0.0)
            elif checked[0] < ath_price:
                ath_price, ath_time = checked
        left = t["sold"] * max(0.0, ath_price - avg_sell) if after else 0.0
        rep.fumbles.append(Fumble(
            mint=mint, sold_usd=t["sold_usd"], avg_sell=avg_sell, ath_price=ath_price,
            ath_after_exit=after, left_on_table=left,
            peak_mult=(ath_price / avg_sell) if avg_sell > 0 else 0.0,
            sold_tokens=t["sold"],
            days_to_peak=max(0.0, (ath_time - last_sell) / 86_400_000.0) if after else 0.0,
            trail_value=t["sold"] * ath_price * 0.6 if after else 0.0))

    rep.fumbles.sort(key=lambda f: f.left_on_table, reverse=True)
    rep.total_fumble = sum(f.left_on_table for f in rep.fumbles)

    # symbols and worked examples for the biggest fumbles
    for f in rep.fumbles[:6]:
        if f.left_on_table > 0:
            f.sym = st.symbol(f.mint)
    rep.examples = [{
        "sym": f.sym or f.mint[:5],
        "mint": f.mint,
        "sold_tokens": f.sold_tokens,
        "avg_sell": f.avg_sell,
        "sold_usd": f.sold_usd,
        "ath_price": f.ath_price,
        "peak_mult": f.peak_mult,
        "days_to_peak": f.days_to_peak,
        "left_on_table": f.left_on_table,
        "trail_value": f.trail_value,
    } for f in rep.fumbles if f.left_on_table > 0][:4]

    n_ran = sum(1 for f in rep.fumbles if f.left_on_table > 0)
    rep.coach = diagnose(tokens, s, rep.total_fumble, rep.examples, n_ran)

    # the ghost curve: cumulative realized over time against what a hold-to-the-top would have made
    left_by_mint = {f.mint: f.left_on_table for f in rep.fumbles}
    pts = []
    for mint, t in tokens.items():
        ls = t.get("last_sell_time", 0) or 0
        if ls:
            pts.append((ls, t.get("realized", 0.0) or 0.0, left_by_mint.get(mint, 0.0)))
    pts.sort()
    a = g = 0.0
    for ts, real, left in pts:
        a += real
        g += real + left
        rep.curve.append({"t": int(ts), "actual": a, "ghost": g})
    return rep


def to_dict(rep: Report) -> dict:
    return {
        "wallet": rep.wallet,
        "realized": rep.realized,
        "total_invested": rep.total_invested,
        "wins": rep.wins,
        "losses": rep.losses,
        "win_pct": rep.win_pct,
        "tokens_traded": rep.tokens_traded,
        "total_fumble": rep.total_fumble,
        "fumbles": [{
            "mint": f.mint, "sold_usd": f.sold_usd, "avg_sell": f.avg_sell,
            "ath_price": f.ath_price, "left_on_table": f.left_on_table,
            "peak_mult": f.peak_mult} for f in rep.fumbles[:12]],
        "coach": rep.coach,
        "curve": rep.curve,
        "examples": rep.examples,
    }
