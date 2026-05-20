"""東財資金流向直連測試"""
from unittest.mock import MagicMock, patch

from src.core.eastmoney_flow import (
    _parse_sector_flow_item,
    fetch_sector_fund_flow_rank,
)


class TestEastmoneyFlow:
    def test_parse_sector_flow_item(self):
        item = _parse_sector_flow_item({
            "f12": "BK0001",
            "f14": "银行",
            "f3": 1.25,
            "f62": 100000000,
            "f184": 5.5,
            "f66": 50000000,
            "f72": 30000000,
            "f78": 10000000,
            "f84": 10000000,
        })
        assert item["name"] == "银行"
        assert item["main_net"] == 100000000
        assert item["source"] == "eastmoney_http"

    def test_fetch_sector_rank_from_mock(self):
        payload = {
            "data": {
                "total": 1,
                "diff": [{
                    "f12": "BK1", "f14": "测试板块", "f3": 2.0, "f62": 1e8,
                    "f184": 1, "f66": 0, "f72": 0, "f78": 0, "f84": 0,
                }],
            }
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status = MagicMock()

        with patch("src.core.eastmoney_flow.get_session") as gs:
            session = MagicMock()
            session.get.return_value = mock_resp
            gs.return_value = session
            items = fetch_sector_fund_flow_rank(max_pages=1)
        assert len(items) == 1
        assert items[0]["name"] == "测试板块"
