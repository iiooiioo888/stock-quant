"""unit 測試：預設阻擋真實外網（可用 @pytest.mark.network 跳過）。"""
import pytest

from tests.helpers.network_guard import block_requests_session


@pytest.fixture(autouse=True)
def _unit_block_external_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("network"):
        return
    block_requests_session(monkeypatch)
