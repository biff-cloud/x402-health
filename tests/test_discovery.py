import os
os.environ.update(X402_ENABLED="0", CRAWLER_ENABLED="0", DB_PATH=":memory:")
from fastapi.testclient import TestClient
from app.main import app

def test_llms_and_catalog():
    c = TestClient(app)
    assert "/v1/check" in c.get("/llms.txt").text
    assert c.get("/.well-known/api-catalog").json()["linkset"][0]["service-desc"]

def test_api_catalog_link_header():
    r = TestClient(app).get("/health")
    assert r.headers["link"] == '</.well-known/api-catalog>; rel="api-catalog"'
