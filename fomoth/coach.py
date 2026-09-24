"""The coach: concrete, worked plays from the wallet's own trades.

No generic advice. Every play names a real token, the price you sold at, where it went, and the
exact dollars a specific rule would have saved on that exact trade. The aggregate numbers come
from the same PnL the rest of the report uses.
"""
from __future__ import annotations

from statistics import median


def _median(xs):
    return median(xs) if xs else 0.0


def usd(n):
    if n is None:
        return "$0"
    neg = n < 0
    n = abs(n)
    if n >= 1e6:
        s = f"{n/1e6:.2f}M"
    elif n >= 1e3:
        s = f"{n/1e3:.1f}K"
    else:
        s = f"{n:.0f}"
    return ("-$" if neg else "$") + s


def price(p):
    if p >= 1:
        return f"${p:,.2f}"
    if p >= 0.001:
        return f"${p:.4f}"
    return f"${p:.2e}"


def toks(n):
    if n >= 1e9:
        return f"{n/1e9:.1f}B"
    if n >= 1e6:
        return f"{n/1e6:.1f}M"
    if n >= 1e3:
        return f"{n/1e3:.0f}K"
    return f"{n:.0f}"


def dur(m):
    if m < 1:
        return f"{m*60:.0f}s"
    if m < 90:
        return f"{m:.0f}m"
    if m < 1440:
        return f"{m/60:.1f}h"
    return f"{m/1440:.1f}d"


def diagnose(tokens: dict, summary: dict, total_fumble: float, examples: list, n_ran: int) -> dict:
    rows = []
    for t in tokens.values():
        size = t.get("total_invested", 0.0) or 0.0
        realized = t.get("realized", 0.0) or 0.0
        fb, ls = t.get("first_buy_time", 0) or 0, t.get("last_sell_time", 0) or 0
        rows.append({
            "realized": realized, "size": size,
            "roi": realized / size if size > 0 else 0.0,
            "hold_min": (ls - fb) / 6e4 if ls and fb and ls > fb else None,
            "n_buys": t.get("buy_transactions", 0) or 0, "win": realized > 0})

    wins = [r["realized"] for r in rows if r["realized"] > 0]
    losses = [r["realized"] for r in rows if r["realized"] < 0]
    n = len(rows) or 1
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    win_rate = summary.get("winPercentage", (len(wins) / n * 100))
    payoff = (avg_win / abs(avg_loss)) if avg_loss else 0.0
    expectancy = (win_rate / 100) * avg_win + (1 - win_rate / 100) * avg_loss

    wh = [r["hold_min"] for r in rows if r["win"] and r["hold_min"] is not None]
    lh = [r["hold_min"] for r in rows if not r["win"] and r["hold_min"] is not None]
    ah = [r["hold_min"] for r in rows if r["hold_min"] is not None]
    med_win_hold, med_loss_hold, med_hold = _median(wh), _median(lh), _median(ah)

    added = [r for r in rows if r["n_buys"] > 1]
    added_realized = sum(r["realized"] for r in added)

    recs = []

    # 1. the exit rule, anchored to the single worst fumble with real numbers
    if examples and total_fumble > 0:
        e = examples[0]
        capture = 0.25 * total_fumble
        gain = e["trail_value"] - e["sold_usd"]
        flip = (f"you flip winners in about {dur(med_win_hold)}, so you are gone long before the run. "
                if med_win_hold and med_win_hold < 60 else "")
        recs.append({
            "tag": "the exit rule",
            "title": "Bank your cost at 2x, then trail the rest",
            "detail": (
                f"Take ${e['sym']} : you sold {toks(e['sold_tokens'])} tokens at {price(e['avg_sell'])} "
                f"and walked with {usd(e['sold_usd'])}. It topped {price(e['ath_price'])} about "
                f"{dur(e['days_to_peak'] * 1440)} later, a {e['peak_mult']:.0f}x. {flip}"
                f"A 40% trailing stop off that peak would have closed near {usd(e['trail_value'])}, "
                f"{usd(gain)} more on that one trade. Make it a rule on every position: sell your "
                f"original cost the moment it doubles, then trail the remainder 35 to 40 percent off "
                f"the high and let it run. Across your {n_ran} winners that kept climbing after you "
                f"left, capturing even a quarter of it is about {usd(capture)}."),
            "impact": capture})

    # 2. the stop, anchored to the disposition gap
    if lh and wh and med_loss_hold > med_win_hold * 1.3 and med_loss_hold - med_win_hold > 0.5 and losses:
        cut = abs(sum(l for l in losses if l < 0)) * 0.4
        recs.append({
            "tag": "the stop",
            "title": "Put a hard stop on every entry before you buy",
            "detail": (
                f"You hold winners about {dur(med_win_hold)} but losers about {dur(med_loss_hold)}, so you "
                f"snatch small gains and marry the bags. Set the stop when you buy, not when you panic: "
                f"a fixed exit at minus 50 percent turns a dead position into a small, known loss and "
                f"frees the money for the next entry. On your {len(losses)} losing tokens that discipline "
                f"is worth roughly {usd(cut)}."),
            "impact": cut})

    # 3. averaging down
    if added and added_realized < 0:
        recs.append({
            "tag": "no averaging down",
            "title": "Stop adding to red. Add to green.",
            "detail": (
                f"On the {len(added)} tokens you bought more than once you are net {usd(added_realized)}. "
                f"Averaging down feels like a discount and almost always just doubles the mistake. Only "
                f"add size to a position that is already in profit, never to one that is bleeding."),
            "impact": abs(added_realized)})

    # 4. payoff, only if the edge is genuinely thin
    if payoff and payoff < 1.4 and avg_loss:
        recs.append({
            "tag": "the math",
            "title": "Your winners barely beat your losers",
            "detail": (
                f"Average win {usd(avg_win)}, average loss {usd(abs(avg_loss))}, a payoff of {payoff:.2f}. "
                f"At a {win_rate:.0f} percent hit rate that edge is paper thin, and more trades will not "
                f"fix it. The only lever is letting the winners you already pick run further, which is the "
                f"same trailing rule above."),
            "impact": abs(avg_loss) * max(0, len(wins))})

    recs.sort(key=lambda r: r["impact"], reverse=True)
    return {
        "expectancy": expectancy, "avg_win": avg_win, "avg_loss": avg_loss, "payoff": payoff,
        "win_rate": win_rate, "med_hold_min": med_hold,
        "med_win_hold_min": med_win_hold, "med_loss_hold_min": med_loss_hold,
        "recommendations": recs[:4],
    }
