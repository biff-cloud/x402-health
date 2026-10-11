"""MCP (stdio) wrapper for x402 Health. Each tool call pays $0.002-0.01 USDC via x402 from YOUR wallet.

Env:
  SOLANA_PRIVATE_KEY   base58 secret key of a small, dedicated spending wallet (a little USDC; no SOL needed).
  X402_HEALTH_URL      default https://x402-health.onrender.com
  MAX_PRICE_ATOMIC     per-call cap in USDC base units (default 10000 = $0.01).
"""
import os
from urllib.parse import urlencode
from mcp.server.mcpserver import MCPServer
from x402 import x402Client
from x402.http.clients import x402HttpxClient
from x402.mechanisms.svm.exact import register_exact_svm_client
from x402.mechanisms.svm.signers import KeypairSigner

URL = os.getenv("X402_HEALTH_URL", "https://x402-health.onrender.com").rstrip("/")
MAINNET = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

server = MCPServer(name="x402-health", version="1.0.0",
                   instructions="Check x402 endpoints before paying them, and find reliable x402 services by category. Paid per call in USDC on Solana.")

def _client():
    key = os.getenv("SOLANA_PRIVATE_KEY")
    if not key: raise RuntimeError("Set SOLANA_PRIVATE_KEY (base58) for a small dedicated USDC spending wallet")
    c = x402Client()
    c.set_spend_controls({"max_amount_per_payment": False,
                          "allowed_assets": [{"network": MAINNET, "asset": USDC, "max_amount_per_payment": os.getenv("MAX_PRICE_ATOMIC", "10000")}]})
    register_exact_svm_client(c, KeypairSigner.from_base58(key), networks=[MAINNET])
    return c

async def _get(path, params):
    async with x402HttpxClient(_client(), base_url=URL, timeout=90) as h:
        r = await h.get(path + "?" + urlencode({k: v for k, v in params.items() if v is not None}))
        try: data = r.json()
        except Exception: data = {"text": r.text[:2000]}
        return {"error": r.status_code, "detail": data} if r.status_code >= 400 else data

@server.tool()
async def check_x402_endpoint(url: str, method: str = "GET") -> dict:
    """Probe an x402 endpoint now ($0.005): reachable, valid 402 metadata, accepted network/price/payTo, latency, 7-day uptime."""
    return await _get("/v1/check", {"url": url, "method": method})

@server.tool()
async def x402_endpoint_history(url: str, days: int = 7) -> dict:
    """Uptime, x402-validity and latency history for an endpoint, up to 30 days ($0.002)."""
    return await _get("/v1/history", {"url": url, "days": days})

@server.tool()
async def reliable_x402_services(category: str | None = None, network: str | None = None, limit: int = 20) -> dict:
    """Ranked reliable x402 services ($0.01). category: ai, crypto-data, search-scrape, finance, data, media, other. network: e.g. solana or eip155:8453."""
    return await _get("/v1/reliable", {"category": category, "network": network, "limit": limit})

def main():
    server.run()

if __name__ == "__main__":
    main()
