"""Crawl public x402 discovery catalogs (x402 'Bazaar' discovery API) and probe listed services.

Sources (public, unauthenticated discovery endpoints):
  - PayAI facilitator:   https://facilitator.payai.network/discovery/resources
  - Coinbase CDP:        https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources
x402scan is not crawled (its search API is itself paid; no bulk-use terms found).
"""
import asyncio, os, random, re
import httpx
from app import store
from app.probe import probe, UA

CATALOGS = {
    "payai": "https://facilitator.payai.network/discovery/resources",
    "cdp": "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources",
}
MAX_PER_CATALOG = int(os.getenv("CRAWL_MAX_PER_CATALOG", "1500"))
PROBES_PER_CYCLE = int(os.getenv("PROBES_PER_CYCLE", "300"))
CYCLE_SECONDS = int(os.getenv("CRAWL_INTERVAL_SECONDS", "1800"))

CATEGORIES = [
    ("ai", r"\b(ai|llm|gpt|inference|model|image gen|chat|agent|embedding|prompt|claude|openai)\b"),
    ("crypto-data", r"\b(token|wallet|defi|swap|onchain|on-chain|solana|base|ethereum|nft|dex|price|crypto|blockchain)\b"),
    ("search-scrape", r"\b(search|scrape|crawl|web|browser|extract|serp|news)\b"),
    ("finance", r"\b(stock|market|finance|forex|trading|payment|invoice|gift card)\b"),
    ("data", r"\b(data|api|lookup|weather|geo|dns|domain|whois|enrich|ip)\b"),
    ("media", r"\b(image|video|audio|tts|speech|music|meme)\b"),
]

def categorize(text):
    t = text.lower()
    for name, rx in CATEGORIES:
        if re.search(rx, t): return name
    return "other"

def normalize(item, source):
    url = item.get("resource")
    if not isinstance(url, str) or not url.startswith("http"): return None
    md = item.get("metadata") or {}
    desc = item.get("description") or md.get("description") or ""
    tags = item.get("tags") or md.get("tags") or []
    name = item.get("serviceName") or md.get("serviceName") or ""
    accepts = [a for a in item.get("accepts") or [] if isinstance(a, dict)]
    prices = [int(a.get("amount") or a.get("maxAmountRequired")) / 1e6 for a in accepts
              if str(a.get("amount") or a.get("maxAmountRequired") or "").isdigit()]
    method = ((item.get("extensions") or {}).get("bazaar", {}).get("info", {}).get("input", {}) or {}).get("method", "GET")
    return {"url": url, "method": "POST" if str(method).upper() == "POST" else "GET", "name": str(name)[:120],
            "description": str(desc), "tags": [str(x) for x in tags][:10] if isinstance(tags, list) else [],
            "category": categorize(" ".join([str(name), str(desc), " ".join(map(str, tags if isinstance(tags, list) else []))])),
            "networks": sorted({a.get("network") for a in accepts if a.get("network")}),
            "price_usd": min(prices) if prices else None, "source": source}

async def crawl_catalog(client, source, base):
    n, offset, limit = 0, 0, 100
    while n < MAX_PER_CATALOG:
        try:
            r = await client.get(base, params={"limit": limit, "offset": offset})
            r.raise_for_status(); items = r.json().get("items") or []
        except Exception:
            break
        for it in items:
            s = normalize(it, source)
            if s: store.upsert_service(s); n += 1
        if len(items) < limit: break
        offset += limit
        await asyncio.sleep(1)
    return n

async def cycle():
    async with httpx.AsyncClient(timeout=20, headers={"user-agent": UA}) as c:
        for src, base in CATALOGS.items():
            await crawl_catalog(c, src, base)
    rows = store.services()
    random.shuffle(rows)
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient(timeout=10, follow_redirects=False, headers={"user-agent": UA}) as c:
        async def one(row):
            async with sem:
                try:
                    store.record(await probe(row[0], row[1], client=c))
                except Exception:
                    pass
        await asyncio.gather(*(one(r) for r in rows[:PROBES_PER_CYCLE]))

async def loop():
    while True:
        try: await cycle()
        except Exception: pass
        await asyncio.sleep(CYCLE_SECONDS)
