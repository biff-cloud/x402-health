# x402 Health

Live: https://x402-health.onrender.com · Also see [Solana Agent Toolbox](https://github.com/biff-cloud/solana-agent-toolbox) · [All services](https://biff-cloud.github.io)

Pay-per-call health checks and a reliability-ranked directory for **x402** services. Built for AI agents that need to know whether an x402 endpoint is up and correctly configured before paying it.

Payments: USDC on Solana mainnet via x402 v2 (`exact` scheme, PayAI facilitator). Unpaid requests to `/v1/*` return HTTP 402 with a `PAYMENT-REQUIRED` header.

| Endpoint | Price | What it returns |
|---|---|---|
| `GET /v1/check?url=<x402 url>&method=GET\|POST` | $0.005 | Live probe: reachable, HTTP status, valid 402 metadata (v1 body or v2 header), accepted network / price / payTo / asset, latency, problems, 7-day uptime |
| `GET /v1/history?url=<url>&days=7` | $0.002 | Uptime %, valid-x402 %, median latency, recent checks (up to 30 days) |
| `GET /v1/reliable?category=ai&network=solana&limit=20` | $0.01 | Ranked services by category (ai, crypto-data, search-scrape, finance, data, media, other), scored by our probes |
| `GET /health`, `/categories`, `/.well-known/x402`, `/openapi.json` | free | Status, catalog counts, discovery metadata |

## Quick start for agents

**1. See the price (free):**
```bash
curl -i "https://x402-health.onrender.com/v1/check?url=https%3A%2F%2Fsolana-agent-toolbox.onrender.com%2Fv1%2Fwallet%2FJ41TaA2hn4YpASarwJK3oByxrKkpQDRVWaNyNCFV6o3d"   # HTTP 402 + PAYMENT-REQUIRED header (base64 JSON: network, amount, payTo)
```

**2. Pay and call, TypeScript** (`npm i @x402/fetch @x402/svm @solana/kit @scure/base`):
```ts
import { x402Client, wrapFetchWithPayment } from "@x402/fetch";
import { ExactSvmScheme } from "@x402/svm/exact/client";
import { createKeyPairSignerFromBytes } from "@solana/kit";
import { base58 } from "@scure/base";

const signer = await createKeyPairSignerFromBytes(base58.decode(process.env.SVM_PRIVATE_KEY!)); // small dedicated wallet with a little USDC
const client = new x402Client();
client.register("solana:*", new ExactSvmScheme(signer));
const pay = wrapFetchWithPayment(fetch, client);
console.log(await (await pay("https://x402-health.onrender.com/v1/check?url=https%3A%2F%2Fsolana-agent-toolbox.onrender.com%2Fv1%2Fwallet%2FJ41TaA2hn4YpASarwJK3oByxrKkpQDRVWaNyNCFV6o3d")).json());
```

**3. Pay and call, Python** (`pip install "x402[svm,httpx]"`):
```python
import asyncio, os
from x402 import x402Client
from x402.http.clients import x402HttpxClient
from x402.mechanisms.svm.exact import register_exact_svm_client
from x402.mechanisms.svm.signers import KeypairSigner

c = x402Client()
register_exact_svm_client(c, KeypairSigner.from_base58(os.environ["SOLANA_PRIVATE_KEY"]))
async def main():
    async with x402HttpxClient(c, timeout=90) as h:
        print((await h.get("https://x402-health.onrender.com/v1/check?url=https%3A%2F%2Fsolana-agent-toolbox.onrender.com%2Fv1%2Fwallet%2FJ41TaA2hn4YpASarwJK3oByxrKkpQDRVWaNyNCFV6o3d")).json())
asyncio.run(main())
```

**4. MCP (Claude Desktop `claude_desktop_config.json`, Cursor `~/.cursor/mcp.json`):**
```json
{"mcpServers": {"x402-health": {"command": "uvx",
  "args": ["--from", "git+https://github.com/biff-cloud/x402-health", "x402-health-mcp"],
  "env": {"SOLANA_PRIVATE_KEY": "<base58 key of a SMALL dedicated wallet>", "MAX_PRICE_ATOMIC": "10000"}}}}
```
Payments are USDC on Solana mainnet. The facilitator (PayAI) pays the SOL fees, so the wallet needs only a few cents of USDC. Use a dedicated low-balance wallet, never your main one.

MCP tools: `check_x402_endpoint`, `x402_endpoint_history`, `reliable_x402_services`.

Discovery files: `/llms.txt`, `/.well-known/x402`, `/.well-known/api-catalog`, `/openapi.json` (with `x-payment-info`).

## How the directory is built
A background crawler reads the public x402 discovery ("Bazaar") catalogs of the PayAI facilitator and Coinbase CDP every 30 minutes, then probes a sample of listed resources with one unpaid request each (it never pays). x402scan is not crawled. Categories come from keyword matching and are approximate.

## Run
```
pip install -r requirements.txt
X402_ENABLED=0 uvicorn app.main:app            # no payments, local dev
X402_ENABLED=0 python -m pytest -q
```
Deploy: Render Blueprint from this repo (`render.yaml`). On the free plan history is in SQLite under /tmp and resets on restart. Render free gives 750 instance-hours/month per workspace, shared with another service, so the keepalive workflow pings only 14:00-23:59 UTC (~318 h/month per service); outside that window the first call may take about a minute while the instance wakes.

## Safety
Targets must be public http(s) hosts; private, loopback and link-local addresses are refused. Redirects are not followed.

## Disclaimer
Informational only, provided as is with no warranty. A good score does not guarantee that a listed service is honest, delivers what it promises, or is safe to pay. Results reflect our own probes at specific times. Listing data belongs to its sources. Not financial advice. MIT licensed.
