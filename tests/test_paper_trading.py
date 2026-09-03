"""模擬交易引擎單元測試。"""

from src.core.paper_trading import PaperTradingEngine


def test_paper_engine_initial_status():
    eng = PaperTradingEngine(capital=50000, name="單元測試盤", session_id="paper_test_1")
    st = eng.get_status()
    assert st["session_id"] == "paper_test_1"
    assert st["status"] == "stopped"
    assert st["initial_capital"] == 50000
    assert st["total_trades"] == 0


def test_paper_engine_start_stop(monkeypatch):
    from src.core.database import init_database

    init_database()
    eng = PaperTradingEngine(capital=10000, session_id="paper_test_2")
    monkeypatch.setattr(
        "src.core.paper_trading.SignalEngine.update_weights_from_backtest",
        lambda self: None,
    )
    eng.start()
    assert eng.get_status()["status"] == "active"
    eng.stop()
    assert eng.get_status()["status"] == "stopped"


def test_paper_tick_when_stopped_is_noop():
    eng = PaperTradingEngine(session_id="paper_test_3")
    assert eng.tick() == []
