# x402 Health

Pay-per-call health checks and a reliability-ranked directory for **x402** services. Built for AI agents that need to know whether an x402 endpoint is up and correctly configured before paying it.

Payments: USDC on Solana mainnet via x402 v2 (`exact` scheme, PayAI facilitator). Unpaid requests to `/v1/*` return HTTP 402 with a `PAYMENT-REQUIRED` header.

| Endpoint | Price | What it returns |
|---|---|---|
| `GET /v1/check?url=<x402 url>&method=GET\|POST` | $0.005 | Live probe: reachable, HTTP status, valid 402 metadata (v1 body or v2 header), accepted network / price / payTo / asset, latency, problems, 7-day uptime |
| `GET /v1/history?url=<url>&days=7` | $0.002 | Uptime %, valid-x402 %, median latency, recent checks (up to 30 days) |
| `GET /v1/reliable?category=ai&network=solana&limit=20` | $0.01 | Ranked services by category (ai, crypto-data, search-scrape, finance, data, media, other), scored by our probes |
| `GET /health`, `/categories`, `/.well-known/x402`, `/openapi.json` | free | Status, catalog counts, discovery metadata |

## How the directory is built
A background crawler reads the public x402 discovery ("Bazaar") catalogs of the PayAI facilitator and Coinbase CDP every 30 minutes, then probes a sample of listed resources with one unpaid request each (it never pays). x402scan is not crawled. Categories come from keyword matching and are approximate.

## Run
```
pip install -r requirements.txt
X402_ENABLED=0 uvicorn app.main:app            # no payments, local dev
X402_ENABLED=0 python -m pytest -q
```
Deploy: Render Blueprint from this repo (`render.yaml`). On the free plan history is in SQLite under /tmp and resets on restart.

## Safety
Targets must be public http(s) hosts; private, loopback and link-local addresses are refused. Redirects are not followed.

## Disclaimer
Informational only, provided as is with no warranty. A good score does not guarantee that a listed service is honest, delivers what it promises, or is safe to pay. Results reflect our own probes at specific times. Listing data belongs to its sources. Not financial advice. MIT licensed.
