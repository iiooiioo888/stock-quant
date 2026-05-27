"""
定時任務調度器測試
"""
import pytest


class TestSchedulerRegistry:
    def test_catalog_has_jobs(self):
        from src.core.scheduler import get_catalog, JOB_CATALOG
        catalog = get_catalog()
        assert len(catalog) == len(JOB_CATALOG)
        assert any(c["id"] == "incremental_update" for c in catalog)

    def test_enable_disable_job(self):
        from src.core.scheduler import (
            enable_job,
            disable_job,
            list_jobs,
            start_scheduler,
        )

        start_scheduler(auto_register=False)
        enable_job("daily_report")
        ids = {j["id"] for j in list_jobs()}
        assert "daily_report" in ids
        disable_job("daily_report")
        ids = {j["id"] for j in list_jobs()}
        assert "daily_report" not in ids

    def test_setup_from_settings_respects_flags(self, monkeypatch):
        from src.config import settings
        from src.core.scheduler import setup_from_settings, list_jobs

        monkeypatch.setattr(settings, "scheduler_enabled", True)
        monkeypatch.setattr(settings, "scheduler_job_incremental", True)
        monkeypatch.setattr(settings, "scheduler_job_daily_report", False)
        monkeypatch.setattr(settings, "scheduler_job_data_quality", False)
        monkeypatch.setattr(settings, "scheduler_job_degradation", False)
        monkeypatch.setattr(settings, "scheduler_job_correlation", False)
        monkeypatch.setattr(settings, "scheduler_job_leaderboard", False)

        setup_from_settings()
        ids = {j["id"] for j in list_jobs()}
        assert "incremental_update" in ids
        assert "daily_report" not in ids

    def test_run_job_unknown_raises(self):
        from src.core.scheduler import run_job_now
        with pytest.raises(ValueError, match="未知任務"):
            run_job_now("not_a_real_job")

    def test_scheduled_run_registers_task(self):
        import time
        from src.core.scheduler import _run_scheduled_as_task
        from src.core.task_manager import get_task

        task_id = _run_scheduled_as_task(
            "test_scheduled",
            "測試定時",
            lambda: {"ok": True},
        )
        assert task_id
        task = get_task(task_id)
        assert task is not None
        assert task["task_type"] == "scheduled_job"
        assert "定時·測試定時" in (task.get("title") or "")

        for _ in range(100):
            t = get_task(task_id)
            if t["status"] in ("completed", "failed", "cancelled"):
                break
            time.sleep(0.05)
        assert get_task(task_id)["status"] == "completed"
