"""Simulated backtest task for demo / development.

Replace the body of run_backtest with real backtesting logic later.
"""

import time
import random
from datetime import datetime, timedelta
from ..app.celery_app import celery_app
from ..app.database import async_session
from ..app.models.task import Task
from sqlalchemy import select, update


def _update_task(task_id: str, **kwargs):
    """Synchronous DB update helper for Celery worker."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    db_url = "sqlite:///./data/tasks.db"
    engine = create_engine(db_url)
    with Session(engine) as session:
        stmt = update(Task).where(Task.id == task_id).values(**kwargs)
        session.execute(stmt)
        session.commit()


def _generate_equity_curve(days: int = 252, annual_return: float = 0.15, volatility: float = 0.20):
    """Generate a simulated equity curve with realistic random walk."""
    dt = timedelta(days=1)
    start = datetime(2024, 1, 1)
    daily_return_mean = annual_return / 252
    daily_return_std = volatility / (252 ** 0.5)

    curve = []
    value = 1_000_000.0
    for i in range(days):
        date = (start + dt * i).strftime("%Y-%m-%d")
        curve.append({"date": date, "value": round(value, 2)})
        daily_ret = random.gauss(daily_return_mean, daily_return_std)
        value *= (1 + daily_ret)

    return curve


def _generate_monthly_returns(equity_curve: list[dict]):
    """Derive monthly returns from equity curve."""
    if not equity_curve:
        return []

    monthly = {}
    for point in equity_curve:
        month = point["date"][:7]  # YYYY-MM
        monthly[month] = point["value"]

    result = []
    prev = None
    for month, val in monthly.items():
        if prev is not None:
            ret = round((val - prev) / prev * 100, 2)
            result.append({"month": month, "return": ret})
        prev = val

    return result


def _generate_trade_log(num_trades: int = 100):
    """Generate simulated trade log."""
    trades = []
    date = datetime(2024, 1, 1)
    symbols = ["000001.SZ", "600036.SH", "000858.SZ", "601318.SH", "300750.SZ"]
    for i in range(num_trades):
        entry_date = date + timedelta(days=random.randint(1, 3))
        exit_date = entry_date + timedelta(days=random.randint(1, 30))
        pnl = round(random.uniform(-5, 10), 2)
        trades.append({
            "id": i + 1,
            "symbol": random.choice(symbols),
            "direction": random.choice(["buy", "sell"]),
            "entry_date": entry_date.strftime("%Y-%m-%d"),
            "exit_date": exit_date.strftime("%Y-%m-%d"),
            "pnl_pct": pnl,
            "shares": random.randint(100, 10000),
        })
        date = exit_date

    return trades


@celery_app.task(bind=True, name="tasks.backtest.run_backtest")
def run_backtest(self, task_id: str, config: dict | None = None):
    """
    Simulated backtest execution.

    In production, replace the loop body with real strategy backtesting
    (e.g., using backtrader, zipline, or custom engine).
    """
    _update_task(task_id, status="running", started_at=datetime.utcnow(), celery_task_id=self.request.id)

    total_steps = 100
    try:
        for step in range(1, total_steps + 1):
            time.sleep(random.uniform(0.05, 0.15))

            progress = round(step / total_steps * 100, 1)
            _update_task(task_id, progress=progress)
            self.update_state(state="PROGRESS", meta={"progress": progress})

        # Generate rich simulated result
        equity_curve = _generate_equity_curve()
        final_value = equity_curve[-1]["value"]
        initial_value = equity_curve[0]["value"]
        total_return = round((final_value - initial_value) / initial_value * 100, 2)

        result = {
            "total_return": total_return,
            "sharpe_ratio": round(random.uniform(-0.5, 3.0), 2),
            "max_drawdown": round(random.uniform(5, 30), 2),
            "win_rate": round(random.uniform(30, 70), 1),
            "total_trades": random.randint(50, 500),
            "initial_capital": initial_value,
            "final_value": round(final_value, 2),
            "annual_return": round(total_return * (252 / len(equity_curve)), 2),
            "volatility": round(random.uniform(10, 30), 2),
            "calmar_ratio": round(random.uniform(0.3, 2.5), 2),
            "equity_curve": equity_curve,
            "monthly_returns": _generate_monthly_returns(equity_curve),
            "trade_log": _generate_trade_log(random.randint(50, 150)),
        }

        _update_task(
            task_id,
            status="success",
            progress=100.0,
            result=result,
            finished_at=datetime.utcnow(),
        )
        return result

    except Exception as exc:
        _update_task(
            task_id,
            status="failed",
            error_message=str(exc),
            finished_at=datetime.utcnow(),
        )
        raise
