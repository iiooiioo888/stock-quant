"""任務執行期間捕獲 stdout/stderr，供 WebSocket 與任務日誌 API 使用。"""
from __future__ import annotations

import io
import sys
import threading
from contextlib import contextmanager
from typing import TextIO


class _TaskLogWriter(io.TextIOBase):
    def __init__(self, task_id: str, underlying: TextIO):
        self._task_id = task_id
        self._underlying = underlying
        self._buf = ""

    def write(self, s: str) -> int:
        if not s:
            return 0
        n = self._underlying.write(s)
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                _append_line(self._task_id, line)
        return n

    def flush(self) -> None:
        self._underlying.flush()
        if self._buf.strip():
            _append_line(self._task_id, self._buf.rstrip())
            self._buf = ""


@contextmanager
def task_log_context(task_id: str):
    """在 worker 線程內重定向 print / traceback 輸出。"""
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = _TaskLogWriter(task_id, old_out)  # type: ignore[assignment]
    sys.stderr = _TaskLogWriter(task_id, old_err)  # type: ignore[assignment]
    try:
        yield
    finally:
        try:
            sys.stdout.flush()  # type: ignore[union-attr]
            sys.stderr.flush()  # type: ignore[union-attr]
        except Exception:
            pass
        sys.stdout, sys.stderr = old_out, old_err


def _append_line(task_id: str, line: str) -> None:
    from src.core.task_manager import append_task_log

    append_task_log(task_id, line)


def capture_exception(task_id: str, exc: BaseException) -> None:
    import traceback

    _append_line(task_id, traceback.format_exc().rstrip())
