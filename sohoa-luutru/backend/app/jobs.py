"""Hàng đợi xử lý: MỖI LẦN MỘT hồ sơ (OCR và LLM đều dùng hết CPU), chạy ở luồng nền.

Giao diện hỏi tiến độ qua Job.to_dict(): giai đoạn, đang ở trang/văn bản thứ mấy,
thời gian đã chạy và ước tính còn lại.
"""

from __future__ import annotations

import itertools
import queue
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable

STAGES = {
    "cho": "Đang chờ",
    "tach_trang": "Tách trang PDF",
    "nap_ocr": "Nạp model OCR",
    "ocr": "Nhận dạng chữ (OCR)",
    "tach_van_ban": "Tách văn bản",
    "nap_llm": "Nạp model AI",
    "trich_xuat": "Trích xuất trường dữ liệu",
    "luu": "Lưu kết quả",
    "xong": "Xong",
    "loi": "Lỗi",
    "huy": "Đã hủy",
}


class Cancelled(Exception):
    pass


@dataclass
class Job:
    id: int
    ho_so_id: int
    kind: str
    params: dict = field(default_factory=dict)
    stage: str = "cho"
    current: int = 0
    total: int = 0
    message: str = ""
    error: str = ""
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    stage_started: float | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def update(self, stage: str | None = None, current: int | None = None, total: int | None = None,
               message: str | None = None) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()
        if stage is not None and stage != self.stage:
            self.stage, self.stage_started = stage, time.time()
        if current is not None:
            self.current = current
        if total is not None:
            self.total = total
        if message is not None:
            self.message = message

    @property
    def done(self) -> bool:
        return self.stage in ("xong", "loi", "huy")

    def to_dict(self) -> dict:
        now = time.time()
        eta = None
        if self.stage_started and self.total and 0 < self.current < self.total:
            per_item = (now - self.stage_started) / self.current
            eta = round(per_item * (self.total - self.current))
        return {
            "id": self.id,
            "ho_so_id": self.ho_so_id,
            "kind": self.kind,
            "stage": self.stage,
            "stage_label": STAGES.get(self.stage, self.stage),
            "current": self.current,
            "total": self.total,
            "message": self.message,
            "error": self.error,
            "done": self.done,
            "elapsed": round((self.finished or now) - self.started) if self.started else 0,
            "eta_stage": eta,
        }


class JobQueue:
    def __init__(self, runner: Callable[[Job], None]):
        self._runner = runner
        self._jobs: dict[int, Job] = {}
        self._queue: queue.Queue[Job] = queue.Queue()
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, ho_so_id: int, kind: str = "xu_ly", params: dict | None = None) -> Job:
        with self._lock:
            for j in self._jobs.values():
                if j.ho_so_id == ho_so_id and not j.done:
                    return j  # hồ sơ này đang chờ / đang chạy rồi
            job = Job(next(self._ids), ho_so_id, kind, params or {})
            self._jobs[job.id] = job
        self._queue.put(job)
        return job

    def get(self, job_id: int) -> Job | None:
        return self._jobs.get(job_id)

    def latest_for(self, ho_so_id: int) -> Job | None:
        jobs = [j for j in self._jobs.values() if j.ho_so_id == ho_so_id]
        return max(jobs, key=lambda j: j.id) if jobs else None

    def active(self) -> list[Job]:
        return [j for j in self._jobs.values() if not j.done]

    def cancel(self, job_id: int) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.done:
            return False
        job.cancel_event.set()
        if job.started is None:  # chưa chạy -> hủy luôn
            job.stage, job.finished = "huy", time.time()
        return True

    def _worker(self) -> None:
        while True:
            job = self._queue.get()
            if job.cancel_event.is_set():
                continue
            job.started = time.time()
            try:
                self._runner(job)
                job.stage = "xong"
            except Cancelled:
                job.stage = "huy"
            except Exception as e:  # noqa: BLE001
                job.stage, job.error = "loi", f"{e.__class__.__name__}: {e}"
                traceback.print_exc()
            finally:
                job.finished = time.time()
