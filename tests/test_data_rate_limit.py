"""演示/輪詢場景：數據中心 GET 不應頻繁 429"""

import pytest


@pytest.mark.parametrize(
    "path",
    [
        "/api/data/sectors",
        "/api/data/north-flow?days=5",
        "/api/dashboard/market-charts?days=5",
    ],
)
def test_data_get_not_rate_limited_burst(client, path):
    for _ in range(25):
        resp = client.get(path)
        assert resp.status_code != 429, f"{path} returned 429 under demo skip rules"
