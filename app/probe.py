"""Probe a URL and parse its x402 payment requirements (v1 body or v2 PAYMENT-REQUIRED header)."""
import asyncio, base64, ipaddress, json, os, socket, time
from urllib.parse import urlparse
import httpx

UA = "x402-health-probe/1.0 (+https://github.com/biff-cloud/x402-health)"

class BadTarget(ValueError): pass

def _public(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise BadTarget("host does not resolve")
    for i in infos:
        ip = ipaddress.ip_address(i[4][0])
        if os.getenv("PROBE_ALLOW_FAKEIP") == "1" and ip in ipaddress.ip_network("198.18.0.0/15"): continue  # local sandbox DNS only
        if not ip.is_global: raise BadTarget("target resolves to a non-public address")

async def check_target(url):
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname: raise BadTarget("url must be http(s)://host/...")
    if len(url) > 2048: raise BadTarget("url too long")
    await asyncio.to_thread(_public, p.hostname)

def _b64json(s):
    try:
        return json.loads(base64.b64decode(s + "=" * (-len(s) % 4)))
    except Exception:
        return None

def parse_402(resp):
    """Return (payload, version, problems)."""
    problems, payload = [], None
    h = resp.headers.get("payment-required")
    if h:
        payload = _b64json(h)
        if payload is None: problems.append("PAYMENT-REQUIRED header is not base64 JSON")
    if payload is None:
        try: payload = resp.json()
        except Exception: payload = None
    if not isinstance(payload, dict):
        return None, None, problems + ["no x402 payment requirements found (header or JSON body)"]
    ver = payload.get("x402Version")
    accepts = payload.get("accepts")
    if not isinstance(accepts, list) or not accepts: problems.append("accepts[] missing or empty")
    else:
        for i, a in enumerate(accepts):
            if not isinstance(a, dict): problems.append(f"accepts[{i}] not an object"); continue
            for k in ("scheme", "network", "payTo", "asset"):
                if not a.get(k): problems.append(f"accepts[{i}].{k} missing")
            if not (a.get("amount") or a.get("maxAmountRequired")): problems.append(f"accepts[{i}] has no amount")
    if ver not in (1, 2): problems.append("x402Version missing or unknown")
    return payload, ver, problems

def summarize(accepts):
    out = []
    for a in accepts or []:
        if not isinstance(a, dict): continue
        amt = a.get("amount") or a.get("maxAmountRequired")
        out.append({"scheme": a.get("scheme"), "network": a.get("network"), "payTo": a.get("payTo"),
                    "asset": a.get("asset"), "amountAtomic": str(amt) if amt is not None else None,
                    "approxUsd": (int(amt) / 1e6 if str(amt).isdigit() else None)})
    return out

async def probe(url, method="GET", timeout=10.0, client=None, check=True):
    if check: await check_target(url)
    own = client is None
    client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers={"user-agent": UA})
    t0 = time.perf_counter()
    res = {"url": url, "method": method, "checkedAt": int(time.time())}
    try:
        r = await client.request(method, url, json={} if method == "POST" else None)
        res["latencyMs"] = round((time.perf_counter() - t0) * 1000)
        res["status"] = r.status_code
        res["reachable"] = True
        if r.status_code == 402:
            payload, ver, problems = parse_402(r)
            res["x402Version"] = ver
            res["accepts"] = summarize(payload.get("accepts") if payload else None)
            res["problems"] = problems
            res["validX402"] = not problems
        else:
            res["validX402"] = False
            res["problems"] = [f"expected HTTP 402 for an unpaid request, got {r.status_code}"]
    except httpx.HTTPError as e:
        res.update(reachable=False, validX402=False, status=None, latencyMs=round((time.perf_counter() - t0) * 1000),
                   problems=[f"request failed: {type(e).__name__}"])
    finally:
        if own: await client.aclose()
    return res
