"""Turn raw transactions into clean trade rows, without decoding a single DEX.

The trick, the same one used to read creator fees: for each transaction, look at how the
wallet's balances moved. If a memecoin balance went up while SOL went down, it was a buy. If
the memecoin went down while SOL came in, a sell. This is agnostic to pump.fun, Raydium and
Jupiter alike, because they all end in the same balance change.

A "SOL leg" is the sum of the native lamport change and any wrapped-SOL (WSOL) change, since
routers wrap and unwrap constantly. Stablecoin legs are handled the same way later; for v0 we
price everything in SOL.
"""
from __future__ import annotations

from dataclasses import dataclass

WSOL = "So11111111111111111111111111111111111111112"
STABLES = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
}
IGNORE_MINTS = {WSOL} | STABLES


@dataclass
class Trade:
    ts: int
    sig: str
    mint: str
    side: str          # "buy" or "sell"
    sol: float         # SOL leg, always positive
    tokens: float      # token amount, always positive
    price: float       # SOL per token

    def __str__(self) -> str:
        return (f"{self.side:4s} {self.mint[:6]}… {self.tokens:>16,.2f} tok  "
                f"{self.sol:>10.4f} SOL  @ {self.price:.3e}")


def _wallet_token_deltas(tx: dict, wallet: str) -> dict[str, float]:
    """Per-mint change in the wallet's token balances across the transaction."""
    meta = tx["meta"]
    pre = {}
    for b in meta.get("preTokenBalances", []):
        if b.get("owner") == wallet:
            pre[b["mint"]] = pre.get(b["mint"], 0.0) + float(b["uiTokenAmount"]["uiAmount"] or 0)
    post = {}
    for b in meta.get("postTokenBalances", []):
        if b.get("owner") == wallet:
            post[b["mint"]] = post.get(b["mint"], 0.0) + float(b["uiTokenAmount"]["uiAmount"] or 0)
    mints = set(pre) | set(post)
    return {m: post.get(m, 0.0) - pre.get(m, 0.0) for m in mints}


def _wallet_index(tx: dict, wallet: str) -> int | None:
    keys = [k["pubkey"] if isinstance(k, dict) else k
            for k in tx["transaction"]["message"]["accountKeys"]]
    return keys.index(wallet) if wallet in keys else None


def derive(tx: dict, wallet: str) -> Trade | None:
    """One trade from one transaction, or None if it is not a swap for this wallet."""
    if tx.get("meta", {}).get("err"):
        return None
    deltas = _wallet_token_deltas(tx, wallet)

    # the SOL leg: native lamports plus any WSOL movement
    sol_leg = 0.0
    idx = _wallet_index(tx, wallet)
    if idx is not None:
        m = tx["meta"]
        sol_leg += (m["postBalances"][idx] - m["preBalances"][idx]) / 1e9
    sol_leg += deltas.get(WSOL, 0.0)

    # the memecoin leg: exactly one non-SOL, non-stable mint that actually moved
    movers = {m: d for m, d in deltas.items() if m not in IGNORE_MINTS and abs(d) > 1e-9}
    if len(movers) != 1:
        return None
    mint, tok = next(iter(movers.items()))

    # a buy: token in, SOL out. a sell: token out, SOL in. signs must oppose.
    if tok > 0 and sol_leg < 0:
        side = "buy"
    elif tok < 0 and sol_leg > 0:
        side = "sell"
    else:
        return None

    sol = abs(sol_leg)
    tokens = abs(tok)
    if sol < 1e-6 or tokens < 1e-9:
        return None
    return Trade(ts=tx["blockTime"], sig=tx["transaction"]["signatures"][0], mint=mint,
                 side=side, sol=sol, tokens=tokens, price=sol / tokens)


def derive_all(txs, wallet: str) -> list[Trade]:
    out = [t for t in (derive(tx, wallet) for tx in txs) if t]
    out.sort(key=lambda t: t.ts)
    return out
