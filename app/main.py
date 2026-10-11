"""x402 Health: pay-per-call health checks and a reliability-ranked directory of x402 services."""
import asyncio, json, os
from fastapi import FastAPI, HTTPException, Query
from app import store
from app.probe import probe, BadTarget

app = FastAPI(title="x402 Health", version="1.0.0",
              description="Check whether an x402 endpoint is up and serves valid 402 payment metadata; uptime history; reliable services by category.")

@app.on_event("startup")
async def _start():
    if os.getenv("CRAWLER_ENABLED", "1") == "1":
        asyncio.create_task(__import__("app.crawler", fromlist=["loop"]).loop())

@app.get("/health")
async def health():
    return {"ok": True, **store.stats()}

@app.get("/v1/check")
async def check(url: str = Query(..., description="x402 resource URL to probe"),
                method: str = Query("GET", pattern="^(GET|POST)$")):
    """Probe a URL now: reachability, HTTP 402 validity, accepted network/price/payTo, latency, plus 7-day history."""
    try:
        res = await probe(url, method)
    except BadTarget as e:
        raise HTTPException(400, str(e))
    store.record(res)
    h = store.history(url, 7)
    res["history7d"] = {k: h[k] for k in ("checks", "uptimePct", "validX402Pct", "medianLatencyMs", "firstSeen")}
    return res

@app.get("/v1/history")
async def history(url: str = Query(...), days: int = Query(7, ge=1, le=30)):
    """Uptime / validity / latency history from our periodic probes (no live probe)."""
    return store.history(url, days)

def ranked(category=None, network=None, limit=20, min_checks=2):
    out = []
    for url, method, name, desc, tags, cat, nets, price, src in store.services():
        if category and cat != category: continue
        nets = json.loads(nets)
        if network and not any(network.lower() in n.lower() for n in nets): continue
        h = store.history(url, 7)
        if h["checks"] < min_checks: continue
        score = (h["validX402Pct"] or 0) * 0.7 + (h["uptimePct"] or 0) * 0.2 + max(0, 10 - (h["medianLatencyMs"] or 5000) / 300)
        out.append({"url": url, "method": method, "name": name, "description": desc[:200], "category": cat, "networks": nets,
                    "priceUsd": price, "sources": json.loads(src), "checks7d": h["checks"], "uptimePct": h["uptimePct"],
                    "validX402Pct": h["validX402Pct"], "medianLatencyMs": h["medianLatencyMs"], "score": round(score, 1)})
    out.sort(key=lambda x: -x["score"])
    return out[:limit]

@app.get("/v1/reliable")
async def reliable(category: str | None = Query(None, description="ai, crypto-data, search-scrape, finance, data, media, other"),
                   network: str | None = Query(None, description="substring of CAIP-2 network, e.g. solana or eip155:8453"),
                   limit: int = Query(20, ge=1, le=100)):
    """Ranked reliable x402 services (crawled from public discovery catalogs, scored by our probes)."""
    return {"category": category, "network": network, "results": ranked(category, network, limit)}

@app.get("/categories")
async def categories():
    """Free: category counts in the crawled catalog."""
    c = {}
    for row in store.services(): c[row[5]] = c.get(row[5], 0) + 1
    return c

# ---------------- x402 payments (must be installed last) ----------------
from app import payments  # noqa: E402
payments.install(app)
