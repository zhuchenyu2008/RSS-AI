from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional


class FetchScheduler:
    def __init__(self, interval_minutes: int, task: Callable[[], None]):
        self._interval_minutes = interval_minutes
        self._task = task
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, name="FetchScheduler", daemon=True)
            self._thread.start()

    def stop(self):
        with self._lock:
            self._stop_event.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2)
            self._thread = None

    def update_interval(self, interval_minutes: int):
        with self._lock:
            logging.info(f"更新抓取间隔为 {interval_minutes} 分钟")
            self._interval_minutes = interval_minutes
            # Trigger immediate cycle by setting stop and restart
            self.stop()
            self.start()

    def _run(self):
        logging.info("调度器已启动")
        while not self._stop_event.is_set():
            try:
                self._task()
            except Exception as e:
                logging.exception(f"执行抓取任务时发生异常: {e}")
            # Sleep with small steps to react to stop event quickly
            total = max(self._interval_minutes, 1) * 60
            for _ in range(total):
                if self._stop_event.is_set():
                    break
                time.sleep(1)
        logging.info("调度器已停止")


class AlignedScheduler:
    def __init__(
        self,
        name: str,
        compute_next_run: Callable[[datetime], datetime],
        task: Callable[[], None],
    ):
        self._name = name
        self._compute_next_run = compute_next_run
        self._task = task
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
            self._thread.start()

    def stop(self):
        with self._lock:
            self._stop_event.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2)
            self._thread = None

    def _run(self):
        logging.info(f"{self._name} 调度器已启动")
        try:
            next_run = self._compute_next_run(datetime.now(timezone.utc))
        except Exception:
            logging.exception(f"{self._name} 获取下一次运行时间失败，调度器退出")
            return

        while not self._stop_event.is_set():
            now = datetime.now(timezone.utc)
            wait_seconds = max((next_run - now).total_seconds(), 0)
            if self._stop_event.wait(timeout=wait_seconds):
                break
            try:
                self._task()
            except Exception as exc:
                logging.exception(f"{self._name} 执行任务时异常: {exc}")
            try:
                next_run = self._compute_next_run(datetime.now(timezone.utc))
            except Exception:
                logging.exception(f"{self._name} 计算下一次运行时间失败，调度器退出")
                break
        logging.info(f"{self._name} 调度器已停止")
