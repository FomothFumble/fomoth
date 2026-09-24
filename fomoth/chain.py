"""Solana RPC reader: pull a wallet's full transaction history, parsed.

Deliberately thin. It talks to any JSON-RPC endpoint, paginates signatures, fetches parsed
transactions and backs off on rate limits. The public endpoint works for small and medium
wallets; a Helius key drops in by changing one URL when the history is large.

Nothing here decodes a DEX. That happens in trades.py, from balance deltas, so this stays a
plain transport layer.
"""
from __future__ import annotations

import json
import time
import urllib.request
from typing import Iterator

PUBLIC_RPC = "https://api.mainnet-beta.solana.com"
UA = {"User-Agent": "fomoth/0.1", "Content-Type": "application/json"}


class Chain:
    def __init__(self, rpc: str = PUBLIC_RPC, pace: float = 0.12):
        self.rpc = rpc
        self.pace = pace

    def _call(self, method: str, params: list, tries: int = 7) -> dict:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        for i in range(tries):
            try:
                req = urllib.request.Request(self.rpc, body, UA)
                out = json.load(urllib.request.urlopen(req, timeout=45))
                if "error" in out and "429" in str(out["error"]):
                    raise RuntimeError("429")
                return out
            except Exception:
                time.sleep(1.5 * (i + 1))
        return {}

    def signatures(self, wallet: str) -> list[dict]:
        """Every signature for the wallet, newest first, across all pages."""
        out, before = [], None
        while True:
            p = {"limit": 1000}
            if before:
                p["before"] = before
            page = self._call("getSignaturesForAddress", [wallet, p]).get("result", [])
            out += page
            if len(page) < 1000:
                break
            before = page[-1]["signature"]
            time.sleep(self.pace)
        return out

    def transactions(self, sigs: list[str]) -> Iterator[dict]:
        """Parsed transactions, one at a time so a huge wallet streams instead of buffering."""
        for sig in sigs:
            tx = self._call("getTransaction", [sig, {"maxSupportedTransactionVersion": 0,
                                                     "encoding": "jsonParsed"}]).get("result")
            time.sleep(self.pace)
            if tx:
                yield tx

    def _batch(self, chunk: list[str]) -> dict[str, dict]:
        """One JSON-RPC batch: returns {signature: tx or None}."""
        body = json.dumps([
            {"jsonrpc": "2.0", "id": i, "method": "getTransaction",
             "params": [s, {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"}]}
            for i, s in enumerate(chunk)]).encode()
        try:
            req = urllib.request.Request(self.rpc, body, UA)
            res = json.load(urllib.request.urlopen(req, timeout=90))
        except Exception:
            return {s: None for s in chunk}
        out = {}
        if isinstance(res, list):
            for item in res:
                i = item.get("id")
                if isinstance(i, int) and 0 <= i < len(chunk):
                    out[chunk[i]] = item.get("result")
        return {s: out.get(s) for s in chunk}

    def transactions_batched(self, sigs: list[str], size: int = 25, gap: float = 1.0,
                             rounds: int = 5, log=None) -> dict[str, dict]:
        """Fetch many transactions with batches and retries, tolerant of a throttling endpoint.

        Returns {signature: tx}. Signatures the endpoint never returned are simply absent, so a
        caller can report coverage honestly instead of pretending the history is complete.
        """
        got: dict[str, dict] = {}
        pending = list(sigs)
        for r in range(rounds):
            if not pending:
                break
            still = []
            for i in range(0, len(pending), size):
                chunk = pending[i:i + size]
                res = self._batch(chunk)
                for s, tx in res.items():
                    if tx:
                        got[s] = tx
                    else:
                        still.append(s)
                if log:
                    log(f"round {r+1}: {len(got)}/{len(sigs)} fetched, {len(still)} to retry")
                time.sleep(gap)
            pending = still
            time.sleep(gap * 2)
        return got

    def sol_price_usd(self) -> float | None:
        try:
            req = urllib.request.Request(
                "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
                headers={"User-Agent": "fomoth/0.1"})
            return json.load(urllib.request.urlopen(req, timeout=20))["solana"]["usd"]
        except Exception:
            return None
