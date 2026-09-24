"""Robinhood Chain data client with the same surface as SolanaTracker: pnl(), ath(), symbol().

There is no wallet-PnL provider for Robinhood Chain (chain id 4663), so this reads the chain itself.
Every ERC-20 transfer into or out of the wallet, grouped by transaction, becomes a buy or a sell of
the memecoin against whatever moved the other way in the same transaction: USDG, a tokenized stock,
WETH, or native ETH. A token counts as money when its unit price is at least $0.50 (USDG, stocks,
ETH); anything cheaper is the asset being traded. The peak after the wallet's exit is read off the
launchpad curve fills themselves, block by block; GeckoTerminal candles are only a small fallback.

Dollar values use today's price of the quote token. USDG is a dollar and stock tokens move slowly,
so the error is small; it is larger only for old trades paid in ETH.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

RPCS = ["https://rpc.mainnet.chain.robinhood.com", "https://robinhood-rpc.publicnode.com"]
GT = "https://api.geckoterminal.com/api/v2"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
CURVE_BUY = "0xec36bf571f136799e8dc0b0b8bea4b04d8bd3d43de838aab0d5fc21d4cbfc455"
CURVE_SELL = "0x8113d738abdcb6b38357e9d53a54a7157861a09031b453651f0fe7fe151f59df"
SWAP_V4 = "0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f"
ETH_USDG_POOL = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"
MONEY_MIN = 0.5            # $ per unit: at or above this a token is money, below it is a memecoin
MAX_TXS = 1500


def _pad(a: str) -> str:
    return "0x" + "0" * 24 + a.lower()[2:]


def _signed(x: int) -> int:
    return x - (1 << 256) if x >= (1 << 255) else x


class RobinhoodChain:
    def __init__(self, gt_pace: float = 2.2, pace: float = 0.12):
        self.gt_pace = gt_pace
        self.pace = pace
        self._dec: dict[str, int] = {}
        self._px: dict[str, float] = {}
        self._eth: float | None = None
        self._gt_last = 0.0

    # ------------------------------------------------------------------ transport
    def _call(self, payload, tries: int = 10):
        body = json.dumps(payload).encode()
        last = None
        for i in range(tries):
            req = urllib.request.Request(RPCS[i % len(RPCS)], body,
                                         {"Content-Type": "application/json", "User-Agent": "fomoth/0.2"})
            try:
                out = json.load(urllib.request.urlopen(req, timeout=60))
                time.sleep(self.pace)                      # stay under the public rpc's rate limit
                if isinstance(out, dict) and "error" in out:
                    raise RuntimeError(out["error"].get("message", "rpc error"))
                return out
            except Exception as e:
                last = e
                busy = "429" in str(e) or "Too Many" in str(e)
                time.sleep(min(20, 2 ** i) if busy else 0.7 * (i + 1))   # the public rpc rate limits hard
        raise RuntimeError(f"robinhood rpc unavailable: {last}")

    def _rpc(self, method, params):
        return self._call({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})["result"]

    def _batch(self, reqs, size: int = 25):
        out = [None] * len(reqs)
        for i in range(0, len(reqs), size):
            chunk = reqs[i:i + size]
            try:
                res = self._call([{"jsonrpc": "2.0", "id": k, "method": m, "params": p}
                                  for k, (m, p) in enumerate(chunk)])
                for r in res:
                    out[i + r["id"]] = r.get("result")
            except Exception:
                for k, (m, p) in enumerate(chunk):
                    try:
                        out[i + k] = self._rpc(m, p)
                    except Exception:
                        pass
        return out

    def _logs(self, topics, lo: int, hi: int, depth: int = 0, address=None):
        """All logs for a filter in [lo, hi]; halves the range when the node times out."""
        flt = {"fromBlock": hex(lo), "toBlock": hex(hi), "topics": topics}
        if address:
            flt["address"] = address
        try:
            return self._call({"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs", "params": [flt]}, tries=3)["result"] or []
        except Exception:
            if depth > 7 or hi - lo < 50_000:
                raise
            mid = (lo + hi) // 2
            return (self._logs(topics, lo, mid, depth + 1, address)
                    + self._logs(topics, mid + 1, hi, depth + 1, address))

    def _gt(self, path):
        wait = self._gt_last + self.gt_pace - time.time()
        if wait > 0:
            time.sleep(wait)
        for i in range(4):
            self._gt_last = time.time()
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

    # ------------------------------------------------------------------ token facts
    def decimals(self, token: str) -> int:
        if token not in self._dec:
            try:
                r = self._rpc("eth_call", [{"to": token, "data": "0x313ce567"}, "latest"])
                self._dec[token] = int(r, 16) if r and r != "0x" else 18
            except Exception:
                self._dec[token] = 18
        return self._dec[token]

    def eth_usd(self) -> float:
        if self._eth is None:
            r = self._rpc("eth_call", [{"to": ETH_USDG_POOL, "data": "0x3850c7bd"}, "latest"])
            sq = int(r[2:66], 16) / 2 ** 96
            self._eth = sq * sq * 1e12
        return self._eth

    def prices(self, tokens) -> dict[str, float]:
        need = [t for t in tokens if t not in self._px]
        for i in range(0, len(need), 30):
            chunk = need[i:i + 30]
            d = self._gt(f"/simple/networks/robinhood/token_price/{','.join(chunk)}")
            got = ((d or {}).get("data", {}).get("attributes", {}).get("token_prices") or {})
            for t in chunk:
                p = got.get(t) or got.get(t.lower())
                self._px[t] = float(p) if p else 0.0
        return {t: self._px.get(t, 0.0) for t in tokens}

    def symbol(self, mint: str) -> str:
        try:
            h = self._rpc("eth_call", [{"to": mint, "data": "0x95d89b41"}, "latest"])
            n = int(h[2 + 64:2 + 128], 16)
            s = bytes.fromhex(h[2 + 128:2 + 128 + n * 2]).decode("utf-8", "ignore").strip()
            return s[:16] if s and all(31 < ord(c) < 127 for c in s) else ""
        except Exception:
            return ""

    def _peaks_after_exit(self, last_sell: dict, head: int, eth: float, avg_sell: dict) -> dict:
        """Highest price each token traded at on its launchpad curve AFTER the wallet's last sell.

        Block-exact and unit-free: the best curve fill after the exit is compared with the curve fill the
        wallet itself sold into, in the curve's own quote units, so no quote-token price can distort it.
        """
        if not last_sell:
            return {}
        mints = list(last_sell)
        curve_of: dict[str, str] = {}
        for i in range(0, len(mints), 40):
            chunk = mints[i:i + 40]
            try:
                for lg in self._logs([TRANSFER, "0x" + "0" * 64], 0, head, address=chunk):
                    if len(lg["topics"]) == 3 and lg["data"] not in ("0x", "") and int(lg["data"], 16) == 10 ** 27:
                        curve_of[lg["address"].lower()] = "0x" + lg["topics"][2][-40:]
            except Exception:
                pass
        by_curve = {c: m for m, c in curve_of.items()}
        fills: dict[str, list] = {}
        curves = list(by_curve)
        for i in range(0, len(curves), 20):
            chunk = curves[i:i + 20]
            lo = min(last_sell[by_curve[c]] for c in chunk)
            try:
                got = self._logs([[CURVE_BUY, CURVE_SELL]], lo, head, address=chunk)
            except Exception:
                got = []
            for lg in got:
                c = lg["address"].lower()
                m = by_curve.get(c)
                if m and int(lg["blockNumber"], 16) >= last_sell[m]:
                    fills.setdefault(c, []).append(lg)
        # the multiple is measured in the curve's own units, the price ratio of the best fill after the
        # exit over the fill the wallet sold into. no quote token, no dollar price, nothing to mis-price:
        # the dollar peak is then the wallet's own average sell times that multiple
        peaks = {}
        for c, fs in fills.items():
            m = by_curve[c]
            exit_r, best, best_blk = 0.0, 0.0, 0
            for lg in fs:
                d = lg["data"][2:]
                w0, w1 = int(d[0:64] or "0", 16), int(d[64:128] or "0", 16)
                is_buy = lg["topics"][0] == CURVE_BUY
                quote, tok = (w0, w1) if is_buy else (w1, w0)
                if tok < 10 ** 21 or quote <= 0:
                    continue                                   # under 1,000 tokens: dust, no price signal
                r = quote / tok
                blk = int(lg["blockNumber"], 16)
                if blk == last_sell[m] and not is_buy:
                    exit_r = max(exit_r, r)                    # the wallet's own exit fill
                elif blk > last_sell[m] and r > best:
                    best, best_blk = r, blk
            if exit_r > 0 and best > exit_r and avg_sell.get(m):
                peaks[m] = {"highest_price": avg_sell[m] * best / exit_r, "timestamp": self._ts_of(best_blk)}
        return peaks

    def ath(self, mint: str) -> dict | None:
        """Peak price after the wallet's exit: on-chain curve fills first, gecko candles as a small fallback."""
        if getattr(self, "_peaks", None) is not None and mint in self._peaks:
            return self._peaks[mint]
        if getattr(self, "_gecko_left", 6) <= 0:
            return None
        self._gecko_left = getattr(self, "_gecko_left", 6) - 1
        pools = self._gt(f"/networks/robinhood/tokens/{mint}/pools?page=1")
        best, best_ts = 0.0, 0
        for p in ((pools or {}).get("data") or [])[:2]:
            addr = p["attributes"]["address"]
            created = p["attributes"].get("pool_created_at") or ""
            frames = ["hour"]
            try:
                age_days = (time.time() - time.mktime(time.strptime(created[:19], "%Y-%m-%dT%H:%M:%S"))) / 86400
                if age_days > 40:
                    frames.append("day")
            except Exception:
                pass
            for tf in frames:
                c = self._gt(f"/networks/robinhood/pools/{addr}/ohlcv/{tf}?limit=1000&token={mint}&currency=usd")
                for row in ((c or {}).get("data", {}).get("attributes", {}).get("ohlcv_list") or []):
                    ts, hi = int(row[0]), float(row[2])
                    if hi > best:
                        best, best_ts = hi, ts * 1000   # candle start: conservative for "peak after exit"
        return {"highest_price": best, "timestamp": best_ts} if best > 0 else None

    # ------------------------------------------------------------------ the wallet
    def pnl(self, wallet: str) -> dict | None:
        w = wallet.lower()
        head = int(self._rpc("eth_blockNumber", []), 16)
        logs = self._logs([TRANSFER, None, _pad(w)], 0, head) + self._logs([TRANSFER, _pad(w)], 0, head)
        by_tx: dict[str, list] = {}
        for lg in logs:
            if len(lg["topics"]) == 3 and lg["data"] not in ("0x", ""):
                by_tx.setdefault(lg["transactionHash"], []).append(lg)
        if not by_tx:
            return None
        txs = sorted(by_tx, key=lambda h: int(by_tx[h][0]["blockNumber"], 16))[-MAX_TXS:]

        # block -> unix time, interpolated between two real anchors (blocks are about 100 ms apart)
        b_lo = int(by_tx[txs[0]][0]["blockNumber"], 16)
        a_lo = self._rpc("eth_getBlockByNumber", [hex(b_lo), False])
        a_hi = self._rpc("eth_getBlockByNumber", [hex(head), False])
        t_lo, t_hi = int(a_lo["timestamp"], 16), int(a_hi["timestamp"], 16)
        rate = (t_hi - t_lo) / max(1, head - b_lo)
        ts_of = lambda b: int((t_lo + (b - b_lo) * rate) * 1000)

        tx_meta = self._batch([("eth_getTransactionByHash", [h]) for h in txs])
        tokens = sorted({lg["address"].lower() for h in txs for lg in by_tx[h]})
        todo = [t for t in tokens if t not in self._dec]
        for t, r in zip(todo, self._batch([("eth_call", [{"to": t, "data": "0x313ce567"}, "latest"]) for t in todo])):
            try:
                self._dec[t] = int(r, 16) if r and r != "0x" else 18
            except Exception:
                self._dec[t] = 18
        px = self.prices(tokens)
        eth = self.eth_usd()
        money = {t for t in tokens if px.get(t, 0.0) >= MONEY_MIN}

        trades = []                     # (mint, side, tokens, usd, ts_ms)
        need_receipt = []
        for h, meta in zip(txs, tx_meta):
            delta: dict[str, int] = {}
            gin: dict[str, int] = {}                     # gross money into the wallet, per token
            gout: dict[str, int] = {}                    # gross money out of the wallet, per token
            for lg in by_tx[h]:
                t = lg["address"].lower()
                v = int(lg["data"], 16)
                if lg["topics"][2].endswith(w[2:]):
                    delta[t] = delta.get(t, 0) + v
                    gin[t] = gin.get(t, 0) + v
                if lg["topics"][1].endswith(w[2:]):
                    delta[t] = delta.get(t, 0) - v
                    gout[t] = gout.get(t, 0) + v
            assets = [(t, d) for t, d in delta.items() if t not in money and d != 0]
            if len(assets) != 1:
                continue                # transfers, multi-token routes or pure money moves: not a trade
            mint, d = assets[0]
            side = "buy" if d > 0 else "sell"
            # routes hop through WETH and other money tokens that net to zero on the wallet, so the
            # trade is priced by its largest single money leg in dollars, not by the net flow
            legs = gout if side == "buy" else gin
            usd = max([legs[t] / 10 ** self._dec[t] * px[t] for t in legs if t in money] or [0.0])
            if side == "buy" and meta:
                paid_native = int(meta.get("value", "0x0"), 16) / 1e18 * eth
                if w in (meta.get("from", "").lower(), (meta.get("to") or "").lower()):
                    usd = max(usd, paid_native)
            amount = abs(d) / 10 ** self._dec[mint]
            blk = int(by_tx[h][0]["blockNumber"], 16)
            if side == "sell" and usd <= 0:
                need_receipt.append((h, mint, amount, ts_of(blk), blk))
                continue
            if abs(usd) > 0:
                trades.append((mint, side, amount, abs(usd), ts_of(blk), blk))

        # sells paid out in native ETH leave no transfer; read the amount off the curve or v4 event
        recs = self._batch([("eth_getTransactionReceipt", [h]) for h, *_ in need_receipt])
        for (h, mint, amount, ts, blk), rc in zip(need_receipt, recs):
            got = 0.0
            rlogs = (rc or {}).get("logs", [])
            for L in rlogs:
                d2 = L.get("data", "0x")[2:]
                if L["topics"][0] == CURVE_SELL and len(d2) >= 128:
                    curve = _pad(L["address"])
                    qt = next((x["address"].lower() for x in rlogs if x["topics"][0] == TRANSFER and len(x["topics"]) == 3
                               and x["topics"][1] == curve and x["address"].lower() != mint), None)
                    if qt:                          # the curve paid out an erc-20 quote token
                        self.decimals(qt)
                        got = max(got, int(d2[64:128], 16) / 10 ** self._dec[qt] * self.prices([qt])[qt])
                    else:                           # no token left the curve: it paid native eth
                        got = max(got, int(d2[64:128], 16) / 1e18 * eth)
                elif L["topics"][0] == SWAP_V4 and len(d2) >= 128:
                    a0 = _signed(int(d2[0:64], 16))
                    if a0 > 0:
                        got = max(got, a0 / 1e18 * eth)
            if got > 0:
                trades.append((mint, "sell", amount, got, ts, blk))

        per: dict[str, dict] = {}
        last_sell_blk: dict[str, int] = {}
        for mint, side, amount, usd, ts, blk in sorted(trades, key=lambda x: x[4]):
            p = per.setdefault(mint, {"bought": 0.0, "bought_usd": 0.0, "sold": 0.0, "sold_usd": 0.0,
                                      "buy_transactions": 0, "sell_transactions": 0,
                                      "first_buy_time": 0, "last_sell_time": 0})
            if side == "buy":
                p["bought"] += amount
                p["bought_usd"] += usd
                p["buy_transactions"] += 1
                p["first_buy_time"] = p["first_buy_time"] or ts
            else:
                p["sold"] += amount
                p["sold_usd"] += usd
                p["sell_transactions"] += 1
                p["last_sell_time"] = ts
                last_sell_blk[mint] = blk
        wins = losses = 0
        realized_total = invested = 0.0
        for p in per.values():
            avg_cost = p["bought_usd"] / p["bought"] if p["bought"] > 0 else 0.0
            p["realized"] = p["sold_usd"] - min(p["sold"], p["bought"] or p["sold"]) * avg_cost
            p["total_invested"] = p["bought_usd"]
            realized_total += p["realized"]
            invested += p["bought_usd"]
            if p["sold"] > 0:
                wins += p["realized"] > 0
                losses += p["realized"] < 0
        self._ts_of = ts_of
        top = sorted(last_sell_blk, key=lambda m: -per[m]["sold_usd"])[:60]
        avg = {m: per[m]["sold_usd"] / per[m]["sold"] for m in top if per[m]["sold"] > 0}
        self._peaks = self._peaks_after_exit({m: last_sell_blk[m] for m in top}, head, eth, avg)
        return {"tokens": per, "summary": {
            "realized": realized_total, "totalInvested": invested, "totalWins": wins, "totalLosses": losses,
            "winPercentage": wins / (wins + losses) * 100 if wins + losses else 0.0}}
