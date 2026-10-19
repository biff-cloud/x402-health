import importlib, os
import app.payments as payments

def _paths():
    return [v[6] for v in payments.ROUTES.values()]

def test_default_example_targets_toolbox():
    os.environ.pop("EXAMPLE_TARGET_URL", None)
    importlib.reload(payments)
    assert "/v1/check?url=https%3A%2F%2Fsolana-agent-toolbox.onrender.com%2Fv1%2Fwallet%2FJ41TaA2hn4YpASarwJK3oByxrKkpQDRVWaNyNCFV6o3d" in _paths()

def test_example_target_override():
    os.environ["EXAMPLE_TARGET_URL"] = "https://toolbox.example.org/v1/wallet/abc"
    try:
        importlib.reload(payments)
        assert "/v1/history?url=https%3A%2F%2Ftoolbox.example.org%2Fv1%2Fwallet%2Fabc" in _paths()
        assert not any("onrender" in p for p in _paths())
    finally:
        os.environ.pop("EXAMPLE_TARGET_URL")
        importlib.reload(payments)
