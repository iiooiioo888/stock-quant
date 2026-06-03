"""responses Mock 範例（P1）。"""
import pytest

responses = pytest.importorskip("responses")


@responses.activate
def test_yahoo_chart_mocked():
    import requests

    responses.add(
        responses.GET,
        "https://example.com/mock-chart",
        json={"chart": {"result": [{"meta": {"symbol": "TEST"}}]}},
        status=200,
    )
    r = requests.get("https://example.com/mock-chart", timeout=5)
    assert r.status_code == 200
    assert r.json()["chart"]["result"][0]["meta"]["symbol"] == "TEST"
