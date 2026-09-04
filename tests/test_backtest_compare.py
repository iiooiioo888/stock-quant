"""
回測結果對比 + 實驗版本管理測試
"""

import uuid

import pytest

from src.core.backtest_compare import (
    compare_backtests,
    create_experiment,
    delete_experiment,
    get_experiment,
    list_experiments,
)
from src.core.db import get_backtest_history, save_backtest_result


def _insert_backtest(code: str, strategy: str, params: dict, sharpe: float, ret: float) -> int:
    """插入一條回測記錄並返回 id"""
    save_backtest_result(
        {
            "code": code,
            "strategy": strategy,
            "params": params,
            "total_return_pct": ret,
            "sharpe_ratio": sharpe,
            "max_drawdown_pct": 10.0,
            "annual_return_pct": ret / 2,
            "sortino_ratio": sharpe * 1.1,
            "calmar_ratio": ret / 10.0,
            "total_trades": 20,
            "win_rate_pct": 55.0,
            "initial_cash": 100000,
            "final_value": 100000 * (1 + ret / 100),
        }
    )
    rows = get_backtest_history(code=code, strategy=strategy, limit=1)
    assert rows, "回測記錄應已寫入"
    return int(rows[0]["id"])


@pytest.fixture
def three_backtests():
    tag = uuid.uuid4().hex[:8]
    code = f"T{tag[:7]}"
    ids = [
        _insert_backtest(code, "dual_ma", {"fast": 5, "slow": 20}, 1.0, 10.0),
        _insert_backtest(code, "dual_ma", {"fast": 8, "slow": 30}, 2.0, 25.0),
        _insert_backtest(code, "macd", {"fast": 12, "slow": 26}, 0.5, 5.0),
    ]
    return code, ids


def test_compare_ranking_and_params_diff(three_backtests):
    code, ids = three_backtests
    out = compare_backtests(ids, metric="sharpe_ratio")

    assert out["missing_ids"] == []
    assert len(out["items"]) == 3

    # 排名：sharpe 2.0 (id[1]) > 1.0 (id[0]) > 0.5 (id[2])
    ranking = out["ranking"]
    assert [r["id"] for r in ranking] == [ids[1], ids[0], ids[2]]
    assert ranking[0]["rank"] == 1

    # 參數差異：fast/slow 取值不同應被標出
    assert "fast" in out["params_diff"]
    assert str(ids[0]) in out["params_diff"]["fast"]

    # 每項指標最佳
    assert out["best"]["sharpe_ratio"]["id"] == ids[1]
    assert out["best"]["total_return_pct"]["value"] == 25.0


def test_compare_missing_ids(three_backtests):
    _, ids = three_backtests
    out = compare_backtests([ids[0], 99999999])
    assert out["missing_ids"] == [99999999]
    assert len(out["items"]) == 1


def test_compare_validation():
    with pytest.raises(ValueError, match="至少一個"):
        compare_backtests([])
    with pytest.raises(ValueError, match="找不到"):
        compare_backtests([99999998])


def test_experiment_crud(three_backtests):
    _, ids = three_backtests
    name = f"實驗_{uuid.uuid4().hex[:6]}"

    exp = create_experiment(name, ids, note="對比三組參數")
    assert exp["id"] > 0
    assert exp["backtest_ids"] == ids

    # 詳情含對比
    detail = get_experiment(exp["id"])
    assert detail["name"] == name
    assert detail["compare"]["ranking"][0]["id"] == ids[1]

    # 列表可見
    exps = list_experiments(limit=200)
    match = next((e for e in exps if e["id"] == exp["id"]), None)
    assert match is not None and match["item_count"] == 3

    # 刪除
    assert delete_experiment(exp["id"]) is True
    assert get_experiment(exp["id"]) is None


def test_experiment_validation(three_backtests):
    _, ids = three_backtests
    with pytest.raises(ValueError, match="名稱不可為空"):
        create_experiment("", ids)
    with pytest.raises(ValueError, match="至少需要一條"):
        create_experiment("x", [])
    with pytest.raises(ValueError, match="不存在"):
        create_experiment("x", [99999997])


# ====== API 層 ======


@pytest.fixture
def auth_headers(client):
    pw = "test_bt_compare_pw_2026"
    username = f"cmp_{uuid.uuid4().hex[:8]}"
    client.post("/api/auth/register", json={"username": username, "password": pw})
    resp = client.post("/api/auth/login", json={"username": username, "password": pw})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def test_compare_api(client, auth_headers, three_backtests):
    _, ids = three_backtests
    resp = client.post(
        "/api/backtest/compare",
        headers=auth_headers,
        json={"ids": ids, "metric": "sharpe_ratio"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["ranking"][0]["id"] == ids[1]

    # 空 ids → 400
    resp2 = client.post("/api/backtest/compare", headers=auth_headers, json={"ids": []})
    assert resp2.status_code == 400


def test_experiments_api(client, auth_headers, three_backtests):
    _, ids = three_backtests
    name = f"API實驗_{uuid.uuid4().hex[:6]}"

    # 建立
    resp = client.post(
        "/api/backtest/experiments",
        headers=auth_headers,
        json={"name": name, "ids": ids, "note": "api 測試"},
    )
    assert resp.status_code == 200, resp.text
    exp_id = resp.json()["experiment"]["id"]

    # 列表
    resp = client.get("/api/backtest/experiments", headers=auth_headers)
    assert resp.status_code == 200
    assert any(e["id"] == exp_id for e in resp.json()["experiments"])

    # 詳情
    resp = client.get(f"/api/backtest/experiments/{exp_id}")
    assert resp.status_code == 200
    assert resp.json()["experiment"]["compare"]["ranking"]

    # 刪除
    resp = client.delete(f"/api/backtest/experiments/{exp_id}", headers=auth_headers)
    assert resp.status_code == 200
    resp = client.get(f"/api/backtest/experiments/{exp_id}")
    assert resp.status_code == 404
