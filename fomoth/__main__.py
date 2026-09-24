"""fomoth <wallet> — read a wallet, derive its trades, print the PnL summary.

v0 pipeline: chain -> trades -> pnl. The regret engine, habit detector and coach land next; the
CLI shell here proves the reader and the FIFO PnL against a real wallet.
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from .chain import Chain
from .pnl import compute
from .trades import derive_all

# Solana palette in truecolor ANSI
P = "\x1b[38;2;153;69;255m"   # purple
G = "\x1b[38;2;20;241;149m"   # green
R = "\x1b[38;2;255;77;77m"    # loss red
D = "\x1b[38;2;120;120;130m"  # dim
B = "\x1b[1m"
X = "\x1b[0m"

MOTH = rf"""{P}   ▲   {X}
{P}  ╱ ╲  {X}  {B}{G}FOMOTH{X}  {D}the trade you fumbled{X}
{P} ╲╱ ╲╱ {X}"""


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python -m fomoth <wallet-address>")
        return 1
    wallet = sys.argv[1]
    ch = Chain()

    print(MOTH)
    print(f"{D}reading {wallet}…{X}")
    sigs = [s["signature"] for s in ch.signatures(wallet)]
    print(f"{D}{len(sigs)} transactions, deriving trades…{X}")
    trades = derive_all(ch.transactions(sigs), wallet)
    print(f"{D}{len(trades)} swaps found{X}\n")

    wp = compute(trades)
    price = ch.sol_price_usd() or 0.0

    rows = sorted(wp.tokens.values(), key=lambda t: t.realized_sol)
    def usd(sol): return f"${sol*price:,.0f}" if price else f"{sol:.2f} SOL"

    print(f"{B}worst and best realized{X}")
    for t in rows[:5] + rows[-5:]:
        c = R if t.realized_sol < 0 else G
        hold = f"{t.hold_secs/60:.0f}m" if t.hold_secs else "-"
        print(f"  {c}{t.realized_sol:+9.3f} SOL{X}  {t.mint[:8]}…  "
              f"{D}{t.buys}b/{t.sells}s hold {hold}{X}")

    tot = wp.realized_sol
    c = G if tot >= 0 else R
    print(f"\n{B}realized PnL{X}   {c}{tot:+.3f} SOL  {usd(tot)}{X}")
    print(f"{B}win rate{X}      {wp.win_rate*100:.0f}%  ({wp.wins}W / {wp.losses}L)")
    print(f"{B}tokens traded{X} {len(wp.tokens)}")
    print(f"\n{D}next: regret engine (peak after every sell), habits, coach{X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
