"""Fetch a wallet's whole history once, derive trades, cache both to _scratch/.

Run in the background; it flushes progress so it can be watched. The cache lets the regret engine
and the habit detector iterate without hammering the RPC again.

    python tools/fetch.py <wallet>
"""
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from fomoth.chain import Chain
from fomoth.pnl import compute
from fomoth.trades import derive_all

SCRATCH = pathlib.Path(__file__).resolve().parent.parent / "_scratch"
SCRATCH.mkdir(exist_ok=True)


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    wallet = sys.argv[1]
    ch = Chain(pace=0.05)
    log(f"listing signatures for {wallet}")
    sigs_full = ch.signatures(wallet)
    sigs = [s["signature"] for s in sigs_full if not s.get("err")]
    log(f"{len(sigs_full)} signatures, {len(sigs)} successful")

    t0 = time.time()
    txmap = ch.transactions_batched(sigs, size=25, gap=0.8, rounds=6, log=log)
    cov = len(txmap) / len(sigs) * 100 if sigs else 0
    log(f"fetched {len(txmap)}/{len(sigs)} ({cov:.0f}% coverage) in {time.time()-t0:.0f}s")

    txs = list(txmap.values())
    trades = derive_all(txs, wallet)
    log(f"{len(trades)} swaps derived")

    (SCRATCH / f"trades_{wallet}.json").write_text(json.dumps([{
        "ts": t.ts, "sig": t.sig, "mint": t.mint, "side": t.side,
        "sol": t.sol, "tokens": t.tokens, "price": t.price} for t in trades]), encoding="utf-8")

    wp = compute(trades)
    price = ch.sol_price_usd() or 0.0
    tokens = sorted(wp.tokens.values(), key=lambda x: x.realized_sol)
    log(f"realized PnL {wp.realized_sol:+.2f} SOL (${wp.realized_sol*price:,.0f}), "
        f"win rate {wp.win_rate*100:.0f}%, {len(wp.tokens)} tokens")
    log("worst 5: " + ", ".join(f"{t.mint[:5]} {t.realized_sol:+.1f}" for t in tokens[:5]))
    log("best 5: " + ", ".join(f"{t.mint[:5]} {t.realized_sol:+.1f}" for t in tokens[-5:]))
    log(f"cache written to _scratch/trades_{wallet}.json")


if __name__ == "__main__":
    main()
