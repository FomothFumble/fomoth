"""Tiny stdlib backend for the site. Serves the frontend and one JSON endpoint.

    GET /                      the page
    GET /api/report?wallet=X   the fumble report, cached per wallet on disk

The Solana Tracker key lives only here, server side, read from SOLANATRACKER_KEY. The browser
never sees it. Reports are cached so a repeat lookup and the free-tier limit are both respected.

    SOLANATRACKER_KEY=... python -m fomoth.server 8080
"""
from __future__ import annotations

import json
import pathlib
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .api import SolanaTracker
from .robinhood import RobinhoodChain
from .report import build, to_dict

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
CACHE = ROOT / "_scratch" / "reports"
CACHE.mkdir(parents=True, exist_ok=True)
WALLET_RE = __import__("re").compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
EVM_RE = __import__("re").compile(r"^0x[0-9a-fA-F]{40}$")

# the robinhood skin: same page, robinhood green + neon lime instead of solana teal + purple
RH_SWAP = [
    ("#14F195", "#00C805"), ("#14f195", "#00C805"), ("#5BFFC0", "#7CFF6B"), ("#0E8F5C", "#007A03"),
    ("#8BFFCB", "#9BFF8F"), ("#0C9A5F", "#008A04"), ("#59c6b0", "#66E066"),
    ("#9945FF", "#CCFF00"), ("#9945ff", "#CCFF00"), ("#B98CFF", "#E2FF66"), ("#C6A4FF", "#E6FF80"), ("#6621C4", "#8FB300"),
    ("rgba(20,241,149,", "rgba(0,200,5,"), ("rgba(153,69,255,", "rgba(204,255,0,"),
    ("paste your Solana address…", "paste your Robinhood Chain address, 0x…"),
    ("<span>CHAIN <b>solana</b></span>", "<span>CHAIN <b>robinhood</b></span>"),
    ("your solana trading", "your robinhood chain trading"),
    ("pricing peaks · solana tracker", "pricing peaks · geckoterminal"),
    ("' SOL'", "' ETH'"), ("scanning signatures", "reading transfers"),
]


def chain_of(q: dict) -> str:
    c = (q.get("chain") or [""])[0].lower()
    if c in ("rh", "robinhood"):
        return "rh"
    if c in ("sol", "solana"):
        return "sol"
    w = (q.get("wallet") or [""])[0].strip()
    return "sol" if (w and WALLET_RE.match(w) and not EVM_RE.match(w)) else "rh"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/report":
            q = parse_qs(u.query)
            wallet = (q.get("wallet") or [""])[0].strip()
            chain = chain_of(q)
            if chain == "rh":
                if not EVM_RE.match(wallet):
                    return self._send(400, json.dumps({"error": "that is not a robinhood chain address (0x + 40 hex)"}))
                wallet = wallet.lower()
            elif not WALLET_RE.match(wallet):
                return self._send(400, json.dumps({"error": "invalid wallet"}))
            cf = CACHE / (f"rh_{wallet}.json" if chain == "rh" else f"{wallet}.json")
            if cf.exists():
                return self._send(200, cf.read_bytes())
            try:
                data = to_dict(build(wallet, RobinhoodChain(), ath_top=60) if chain == "rh" else build(wallet, SolanaTracker()))
                data["chain"] = chain
            except Exception as e:
                return self._send(502, json.dumps({"error": str(e)}))
            cf.write_text(json.dumps(data), encoding="utf-8")
            return self._send(200, json.dumps(data))

        path = "index.html" if u.path in ("/", "") else u.path.lstrip("/")
        f = WEB / path
        if f.is_file() and WEB in f.resolve().parents:
            ct = {".html": "text/html", ".png": "image/png", ".svg": "image/svg+xml",
                  ".ico": "image/x-icon", ".css": "text/css", ".js": "text/javascript",
                  ".webp": "image/webp", ".json": "application/json"}.get(f.suffix, "text/plain")
            body = f.read_bytes()
            if f.name == "index.html" and chain_of(parse_qs(u.query)) == "rh":
                html = body.decode("utf-8")
                for a, b in RH_SWAP:
                    html = html.replace(a, b)
                body = html.encode("utf-8")
            return self._send(200, body, ct)
        return self._send(404, "not found", "text/plain")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"fomoth on http://localhost:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
