import asyncio, base64, json, os
os.environ.setdefault("DB_PATH", ":memory:")
import httpx, pytest
from app.probe import probe, parse_402, check_target, BadTarget
from app import store

V2 = {"x402Version": 2, "accepts": [{"scheme": "exact", "network": "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp", "payTo": "J41T", "asset": "EPj", "amount": "5000"}]}

def client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))

def run(c): return asyncio.run(c)

def test_valid_v2_header():
    h = lambda r: httpx.Response(402, headers={"payment-required": base64.b64encode(json.dumps(V2).encode()).decode()})
    res = run(probe("https://x.test/a", client=client(h), check=False))
    assert res["validX402"] and res["x402Version"] == 2 and res["accepts"][0]["approxUsd"] == 0.005

def test_v1_body_and_problems():
    bad = {"x402Version": 1, "accepts": [{"scheme": "exact", "network": "base", "maxAmountRequired": "10000"}]}
    res = run(probe("https://x.test/a", client=client(lambda r: httpx.Response(402, json=bad)), check=False))
    assert not res["validX402"] and any("payTo" in p for p in res["problems"])

def test_not_402():
    res = run(probe("https://x.test/a", client=client(lambda r: httpx.Response(200, json={})), check=False))
    assert res["reachable"] and not res["validX402"]

def test_unreachable():
    def h(r): raise httpx.ConnectError("boom")
    res = run(probe("https://x.test/a", client=client(h), check=False))
    assert res["reachable"] is False

@pytest.mark.parametrize("u", ["http://127.0.0.1/", "http://169.254.169.254/latest", "ftp://x.com/", "http://localhost:8080/"])
def test_ssrf_blocked(u):
    with pytest.raises(BadTarget): run(check_target(u))

def test_history():
    for ok in (1, 1, 0):
        store.record({"url": "https://h.test", "checkedAt": int(__import__("time").time()), "reachable": bool(ok), "validX402": bool(ok), "status": 402, "latencyMs": 100})
    import time; h = store.history("https://h.test", 30)
    assert h["checks"] == 3 and h["uptimePct"] == 66.7
