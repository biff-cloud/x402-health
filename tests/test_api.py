import base64, json, os, subprocess, sys

def test_paid_routes_return_402(tmp_path):
    code = r'''
import base64, json
from fastapi.testclient import TestClient
from app.main import app
from app import store, crawler
c = TestClient(app)
assert c.get("/health").status_code == 200
for p in ["/v1/check?url=https://example.com", "/v1/history?url=https://example.com", "/v1/reliable"]:
    r = c.get(p); assert r.status_code == 402, (p, r.status_code)
    a = json.loads(base64.b64decode(r.headers["payment-required"]))["accepts"][0]
    print(json.dumps([p, a["amount"], a["payTo"], a["network"]]))
o = c.get("/openapi.json").json()
assert o["paths"]["/v1/check"]["get"]["x-payment-info"]["protocols"] == ["x402"]
assert len(c.get("/.well-known/x402").json()["resources"]) == 3
s = crawler.normalize({"resource": "https://a.test/x", "description": "LLM inference", "accepts": [{"network": "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp", "amount": "3000"}]}, "payai")
assert s["category"] == "ai" and s["price_usd"] == 0.003
'''
    env = {**os.environ, "X402_ENABLED": "1", "X402_NETWORK": "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp",
           "PAY_TO_ADDRESS": "J41TaA2hn4YpASarwJK3oByxrKkpQDRVWaNyNCFV6o3d", "FACILITATOR_URL": "https://facilitator.payai.network",
           "CRAWLER_ENABLED": "0", "DB_PATH": str(tmp_path / "t.db"), "PYTHONPATH": "."}
    out = subprocess.run([sys.executable, "-W", "ignore", "-c", code], env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[-2000:]
    rows = [json.loads(l) for l in out.stdout.strip().splitlines()]
    assert [r[1] for r in rows] == ["5000", "2000", "10000"]
    assert all(r[2] == "J41TaA2hn4YpASarwJK3oByxrKkpQDRVWaNyNCFV6o3d" for r in rows)

def test_health_reports_deployed_commit(monkeypatch):
    monkeypatch.setenv("X402_ENABLED", "0")  # app import must not need a facilitator
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setenv("RENDER_GIT_COMMIT", "5cc5a1cdeadbeef")
    assert TestClient(app).get("/health").json()["commit"] == "5cc5a1c"
