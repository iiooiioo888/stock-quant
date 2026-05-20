"""北向資金按日聚合"""
from src.core.capital_flow import aggregate_north_flow_daily


def test_aggregate_north_flow_daily():
    raw = [
        {"date": "2026-01-02", "code": "沪股通", "main_net": 1e8},
        {"date": "2026-01-02", "code": "深股通", "main_net": 2e8},
        {"date": "2026-01-03", "code": "沪股通", "main_net": -5e7},
    ]
    daily = aggregate_north_flow_daily(raw)
    assert len(daily) == 2
    assert daily[0]["date"] == "2026-01-02"
    assert daily[0]["sh_net"] == 1e8
    assert daily[0]["sz_net"] == 2e8
    assert daily[0]["total_net"] == 3e8
