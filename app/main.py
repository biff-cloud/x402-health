"""x402 Health: pay-per-call health checks and a reliability-ranked directory of x402 services."""
import asyncio, json, os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Request
from app import store
from app.probe import probe, BadTarget

@asynccontextmanager
async def _lifespan(_app):
    # Hold a strong ref: asyncio keeps only weak refs to tasks, so a bare create_task can be GC'd.
    task = None
    if os.getenv("CRAWLER_ENABLED", "1") == "1":
        from app.crawler import loop
        task = asyncio.create_task(loop())
    yield
    if task:
        task.cancel()

app = FastAPI(title="x402 Health", version="1.0.0", lifespan=_lifespan,
              description="Check whether an x402 endpoint is up and serves valid 402 payment metadata; uptime history; reliable services by category.")

@app.middleware("http")
async def api_catalog_link(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("Link", '</.well-known/api-catalog>; rel="api-catalog"')  # RFC 9727 discovery
    return resp

@app.get("/health")
async def health():
    return {"ok": True, "commit": os.getenv("RENDER_GIT_COMMIT", "")[:7] or None, **store.stats()}

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

BASE = os.getenv("PUBLIC_BASE_URL", "https://x402-health.onrender.com").rstrip("/")
LLMS = f"""# x402 Health

> Pay-per-call health checks and a reliability-ranked directory of x402 services, for AI agents that want to know
> whether an x402 endpoint works before paying it. Paid in USDC on Solana mainnet via x402 v2 (exact). No accounts, no API keys.

## Paid endpoints (unpaid requests get HTTP 402 with a PAYMENT-REQUIRED header)
- [GET /v1/check?url=URL&method=GET]({BASE}/v1/check): $0.005. Live probe: reachable, valid 402 metadata, network/price/payTo, latency, 7-day uptime
- [GET /v1/history?url=URL&days=7]({BASE}/v1/history): $0.002. Uptime, validity and latency history (up to 30 days)
- [GET /v1/reliable?category=ai&network=solana]({BASE}/v1/reliable): $0.01. Ranked reliable services. Categories: ai, crypto-data, search-scrape, finance, data, media, other

## Free
- [OpenAPI with x-payment-info]({BASE}/openapi.json)
- [x402 discovery]({BASE}/.well-known/x402)
- [Category counts]({BASE}/categories)
- [Source, MCP server, examples](https://github.com/biff-cloud/x402-health)

Informational only. A good score does not guarantee a service is honest or safe to pay.
"""

from fastapi.responses import PlainTextResponse, JSONResponse

@app.get("/llms.txt", response_class=PlainTextResponse, include_in_schema=False)
async def llms():
    return LLMS

@app.get("/.well-known/api-catalog", include_in_schema=False)
async def api_catalog():
    return JSONResponse({"linkset": [{"anchor": BASE, "service-desc": [{"href": f"{BASE}/openapi.json", "type": "application/vnd.oai.openapi+json"}],
                         "service-doc": [{"href": "https://github.com/biff-cloud/x402-health#readme"}],
                         "status": [{"href": f"{BASE}/health"}]}]}, media_type="application/linkset+json")

@app.get("/categories")
async def categories():
    """Free: category counts in the crawled catalog."""
    c = {}
    for row in store.services(): c[row[5]] = c.get(row[5], 0) + 1
    return c

# ---------------- x402 payments (must be installed last) ----------------
from app import payments  # noqa: E402
payments.install(app)
