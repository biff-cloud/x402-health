"""x402 pay-per-call (Solana USDC) for /v1/*. Pattern reused from solana-agent-toolbox.

Env: X402_ENABLED, PAY_TO_ADDRESS, X402_NETWORK (CAIP-2), PAY_ASSET, FACILITATOR_URL or FACILITATOR_KEYPAIR,
PAYMENT_RPC_URL, PUBLIC_BASE_URL, EXAMPLE_TARGET_URL, PRICE_CHECK / PRICE_HISTORY / PRICE_RELIABLE (atomic USDC units).
"""
import json, os
from urllib.parse import quote
from solders.keypair import Keypair
from x402 import x402ResourceServer, x402Facilitator
from x402.http import HTTPFacilitatorClient
from x402.http.types import RouteConfig, PaymentOption
from x402.http.middleware.fastapi import payment_middleware
from x402.mechanisms.svm.exact import ExactSvmServerScheme, ExactSvmFacilitatorScheme
from x402.mechanisms.svm.signers import FacilitatorKeypairSigner
from x402.mechanisms.svm import SOLANA_DEVNET_CAIP2, SOLANA_MAINNET_CAIP2, USDC_DEVNET_ADDRESS, USDC_MAINNET_ADDRESS
from x402.extensions.bazaar import declare_discovery_extension
from x402.extensions.bazaar.resource_service import OutputConfig

DEFAULT_DEVNET_PAY_TO = "9ZPaDj2Qcg4gXXEhArSNmtdHHSrXPWKmsDecnt94D44V"  # throwaway devnet address
EX = "https://api.example.com/paid"
# Live x402 endpoint used in discovery examples; override when the toolbox moves off Render.
_TARGET = quote(os.getenv("EXAMPLE_TARGET_URL",
    "https://solana-agent-toolbox.onrender.com/v1/wallet/J41TaA2hn4YpASarwJK3oByxrKkpQDRVWaNyNCFV6o3d"), safe="")

# route -> (env price var, default atomic, description, tags, query example, output example, example path)
ROUTES = {
    "GET /v1/check": ("PRICE_CHECK", "5000", "Live health check of any x402 endpoint: reachable, valid 402 metadata, network/price/payTo, latency, 7-day uptime",
                      ["x402", "health-check", "monitoring", "uptime"], {"url": EX},
                      {"reachable": True, "status": 402, "validX402": True, "latencyMs": 180, "accepts": [{"network": "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp", "amountAtomic": "5000", "payTo": "..."}], "problems": []},
                      "/v1/check?url=" + _TARGET),
    "GET /v1/history": ("PRICE_HISTORY", "2000", "Uptime, x402-validity and latency history (up to 30 days) for an x402 endpoint",
                        ["x402", "uptime", "history", "monitoring"], {"url": EX, "days": "7"},
                        {"checks": 48, "uptimePct": 97.9, "validX402Pct": 95.8, "medianLatencyMs": 210},
                        "/v1/history?url=" + _TARGET),
    "GET /v1/reliable": ("PRICE_RELIABLE", "10000", "Ranked reliable x402 services by category/network, from public x402 catalogs scored by our probes",
                         ["x402", "directory", "discovery", "reliability"], {"category": "ai", "network": "solana", "limit": "20"},
                         {"results": [{"url": "...", "category": "ai", "uptimePct": 100.0, "validX402Pct": 100.0, "score": 98.2}]},
                         "/v1/reliable?category=ai"),
}

def config():
    net = os.getenv("X402_NETWORK", SOLANA_DEVNET_CAIP2)
    return {"enabled": os.getenv("X402_ENABLED", "1") == "1", "network": net,
            "pay_to": os.getenv("PAY_TO_ADDRESS", DEFAULT_DEVNET_PAY_TO),
            "asset": os.getenv("PAY_ASSET", USDC_MAINNET_ADDRESS if net == SOLANA_MAINNET_CAIP2 else USDC_DEVNET_ADDRESS),
            "facilitator_url": os.getenv("FACILITATOR_URL"), "facilitator_keypair": os.getenv("FACILITATOR_KEYPAIR"),
            "rpc": os.getenv("PAYMENT_RPC_URL")}

def price(key):
    env, default = ROUTES[key][0], ROUTES[key][1]
    return os.getenv(env, default)

def build_routes(cfg):
    out = {}
    for key, (_, _, desc, tags, q, ex, _) in ROUTES.items():
        ext = declare_discovery_extension(input=q, output=OutputConfig(example=ex))
        out[key] = RouteConfig(
            accepts=PaymentOption(scheme="exact", pay_to=cfg["pay_to"], network=cfg["network"],
                                  price={"amount": price(key), "asset": cfg["asset"], "extra": {}}, max_timeout_seconds=120),
            description=desc, mime_type="application/json", service_name="x402 Health", tags=tags, extensions=ext)
    return out

def build_server(cfg):
    if cfg["facilitator_url"]:
        fac = HTTPFacilitatorClient({"url": cfg["facilitator_url"]})
    else:
        path = cfg["facilitator_keypair"]
        if not path: raise RuntimeError("set FACILITATOR_URL or FACILITATOR_KEYPAIR")
        kp = Keypair.from_bytes(bytes(json.load(open(path))))
        fac = x402Facilitator()
        fac.register([cfg["network"]], ExactSvmFacilitatorScheme(FacilitatorKeypairSigner(kp, rpc_url=cfg["rpc"])))
    server = x402ResourceServer(fac)
    server.register(cfg["network"], ExactSvmServerScheme(rpc_url=cfg["rpc"]))
    return server

def install(app):
    cfg = config()
    if not cfg["enabled"]: return
    if cfg["network"] == SOLANA_MAINNET_CAIP2 and not os.getenv("PAY_TO_ADDRESS"):
        raise RuntimeError("mainnet requires an explicit PAY_TO_ADDRESS")
    mw = payment_middleware(build_routes(cfg), build_server(cfg))

    @app.middleware("http")
    async def x402_mw(request, call_next):
        return await mw(request, call_next)

    base = os.getenv("PUBLIC_BASE_URL", "https://x402-health.onrender.com").rstrip("/")

    @app.get("/.well-known/x402")
    async def discovery():
        return {"version": 1, "x402Version": 2, "service": "x402 Health",
                "resources": [base + v[6] for v in ROUTES.values()],
                "network": cfg["network"], "payTo": cfg["pay_to"], "asset": cfg["asset"],
                "routes": [{"route": k, "priceAtomic": price(k), "example": base + v[6], "description": v[2], "tags": v[3]} for k, v in ROUTES.items()],
                "instructions": "USDC on Solana mainnet via x402 v2 (exact). Unpaid requests return 402 with a PAYMENT-REQUIRED header."}

    orig = app.openapi
    def openapi_with_payment():
        if app.openapi_schema: return app.openapi_schema
        s = orig()
        s["info"]["title"] = "x402 Health (x402)"
        s["info"]["description"] = ("Health checks, uptime history and a reliability-ranked directory of x402 services, paid per call "
                                    "in USDC on Solana via x402. Informational only; no guarantee of any listed service.")
        s["servers"] = [{"url": base}]
        s["info"]["contact"] = {"name": "GitHub issues", "url": "https://github.com/biff-cloud/x402-health/issues"}
        s["info"]["license"] = {"name": "MIT"}
        for path, ops in s["paths"].items():
            key = f"GET {path}"
            if key not in ROUTES: continue
            for op in ops.values():
                op["x-payment-info"] = {"protocols": ["x402"], "price": {"mode": "fixed", "currency": "USD", "amount": f"{int(price(key)) / 1e6:g}"},
                                        "network": cfg["network"], "asset": cfg["asset"], "payTo": cfg["pay_to"]}
                op.setdefault("responses", {})["402"] = {"description": "Payment Required (x402 v2; see PAYMENT-REQUIRED header)"}
        app.openapi_schema = s
        return s
    app.openapi = openapi_with_payment
