"""Hàng đợi xử lý: MỖI LẦN MỘT hồ sơ (OCR và LLM đều dùng hết CPU), chạy ở luồng nền.

Hàng đợi BỀN: danh sách hồ sơ chờ nằm trong CSDL (ho_so.trang_thai = 'cho'), nên
- tắt app giữa chừng (kể cả mất điện) -> mở lại thì tự làm tiếp từ hồ sơ đang dở;
- xếp hàng nghìn hồ sơ để chạy qua đêm không tốn bộ nhớ;
- tạm dừng / tiếp tục được (trạng thái tạm dừng cũng được nhớ khi tắt app).

Thứ tự: việc người dùng vừa bấm trên một hồ sơ (uu_tien = 1) làm trước các hồ sơ nhập hàng loạt (0).
Giao diện hỏi tiến độ qua Job.to_dict(): giai đoạn, đang ở trang/văn bản thứ mấy, thời gian còn lại.
"""

from __future__ import annotations

import itertools
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable

from app import db
from app.winperf import keep_awake

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
    "tam_dung": "Tạm dừng — sẽ làm tiếp",
}

# Ước tính thời gian ban đầu (trước khi đo được trên máy này): giây / trang OCR, giây / văn bản AI.
DEFAULT_RATES = {"ocr": 5.0, "ai": 45.0}
SETTING_PAUSED = "hang_doi_tam_dung"


class Cancelled(Exception):
    pass


@dataclass
class Job:
    id: int
    ho_so_id: int
    kind: str  # 'xu_ly' (đầy đủ) | 'ocr' (chỉ đọc chữ, để gợi ý trang đầu tài liệu)
    params: dict = field(default_factory=dict)
    uu_tien: int = 0
    stage: str = "cho"
    current: int = 0
    total: int = 0
    message: str = ""
    error: str = ""
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    stage_started: float | None = None
    stage_seconds: dict = field(default_factory=dict)  # thời gian thực tế của từng giai đoạn
    stats: dict = field(default_factory=dict)  # số trang đã OCR, số văn bản đã chạy AI (để ước tính)
    requeue: bool = False  # bị dừng vì TẠM DỪNG hàng đợi -> xếp lại, làm tiếp sau
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def update(self, stage: str | None = None, current: int | None = None, total: int | None = None,
               message: str | None = None) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()
        if stage is not None:
            self.set_stage(stage)
        if current is not None:
            self.current = current
        if total is not None:
            self.total = total
        if message is not None:
            self.message = message

    def set_stage(self, stage: str) -> None:
        """Đổi giai đoạn (không kiểm tra hủy) và cộng dồn thời gian của giai đoạn vừa xong."""
        if stage == self.stage:
            return
        now = time.time()
        if self.stage_started is not None:
            self.stage_seconds[self.stage] = round(self.stage_seconds.get(self.stage, 0) + now - self.stage_started, 1)
        self.stage, self.stage_started = stage, now

    @property
    def done(self) -> bool:
        return self.stage in ("xong", "loi", "huy", "tam_dung")

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
            "thoi_gian_giai_doan": {STAGES.get(k, k): v for k, v in self.stage_seconds.items()},
        }


class JobQueue:
    def __init__(self, runner: Callable[[Job], None], start: bool = True):
        self._runner = runner
        self._jobs: dict[int, Job] = {}  # các lần xử lý đã / đang chạy trong phiên này (để xem tiến độ)
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self.current: Job | None = None
        self.paused = db.get_setting(SETTING_PAUSED) == "1"
        self.recovered = db.recover_interrupted()  # tắt app giữa chừng -> làm tiếp
        self.rates = {k: float(db.get_setting(f"toc_do_{k}", str(v))) for k, v in DEFAULT_RATES.items()}
        if start:
            threading.Thread(target=self._worker, daemon=True, name="hang-doi").start()

    # ------------------------------------------------------------ xếp hàng
    def submit(self, ho_so_id: int, kind: str = "xu_ly", params: dict | None = None, uu_tien: int = 1) -> dict:
        """Xếp 1 hồ sơ (người dùng bấm trên màn hồ sơ: ưu tiên làm trước hàng loạt)."""
        cur = self.current
        if cur is not None and cur.ho_so_id == ho_so_id and not cur.done:
            return cur.to_dict()  # hồ sơ này đang chạy rồi
        db.enqueue([ho_so_id], {"kind": kind, **(params or {})}, uu_tien)
        self._wake.set()
        return self.progress(ho_so_id)

    def submit_many(self, ids: list[int], kind: str = "xu_ly", params: dict | None = None, uu_tien: int = 0) -> int:
        running = self.current.ho_so_id if self.current and not self.current.done else None
        n = db.enqueue([i for i in ids if i != running], {"kind": kind, **(params or {})}, uu_tien)
        self._wake.set()
        return n

    def cancel(self, ho_so_id: int) -> bool:
        """Hủy hồ sơ đang chạy, hoặc bỏ hồ sơ đang chờ khỏi hàng."""
        cur = self.current
        if cur is not None and cur.ho_so_id == ho_so_id and not cur.done:
            cur.cancel_event.set()
            return True
        return db.dequeue([ho_so_id]) > 0

    def cancel_job(self, job_id: int) -> bool:
        job = self._jobs.get(job_id)
        return job is not None and not job.done and self.cancel(job.ho_so_id)

    def cancel_waiting(self, ids: list[int]) -> int:
        return db.dequeue(ids)

    # ------------------------------------------------------------ tạm dừng
    def pause(self) -> None:
        """Tạm dừng NGAY: hồ sơ đang chạy được xếp lại đầu hàng (giữ phần đã OCR / đã chạy AI)."""
        self.paused = True
        db.set_setting(SETTING_PAUSED, "1")
        cur = self.current
        if cur is not None and not cur.done:
            cur.requeue = True
            cur.cancel_event.set()

    def resume(self) -> None:
        self.paused = False
        db.set_setting(SETTING_PAUSED, "0")
        self._wake.set()

    # ------------------------------------------------------------ xem
    def get(self, job_id: int) -> Job | None:
        return self._jobs.get(job_id)

    def running_for(self, ho_so_id: int) -> bool:
        cur = self.current
        return cur is not None and cur.ho_so_id == ho_so_id and not cur.done

    def progress(self, ho_so_id: int) -> dict | None:
        """Tiến độ của hồ sơ: đang chạy / đang chờ (kèm thứ tự) / lần chạy gần nhất trong phiên."""
        cur = self.current
        if cur is not None and cur.ho_so_id == ho_so_id and not cur.done:
            return cur.to_dict()
        pos = db.queue_position(ho_so_id)
        if pos:
            return {"id": None, "ho_so_id": ho_so_id, "kind": "xu_ly", "stage": "cho",
                    "stage_label": STAGES["cho"], "current": 0, "total": 0, "done": False,
                    "message": ("Hàng đợi đang tạm dừng — " if self.paused else "") + f"thứ {pos} trong hàng đợi",
                    "error": "", "elapsed": 0, "eta_stage": None, "thoi_gian_giai_doan": {}, "thu_tu": pos}
        jobs = [j for j in self._jobs.values() if j.ho_so_id == ho_so_id]
        return max(jobs, key=lambda j: j.id).to_dict() if jobs else None

    def estimate(self, waiting: list[dict]) -> int:
        """Ước tính số giây để làm hết các hồ sơ đang chờ (theo tốc độ đo được trên máy này)."""
        sec = 0.0
        for w in waiting:
            sec += w["so_trang"] * self.rates["ocr"]
            if w["co_ai"]:
                sec += w["so_tai_lieu"] * self.rates["ai"]
        cur = self.current
        if cur is not None and not cur.done and cur.total and cur.stage in ("ocr", "trich_xuat"):
            rate = self.rates["ocr" if cur.stage == "ocr" else "ai"]
            sec += (cur.total - cur.current) * rate
        return round(sec)

    def summary(self, limit: int = 20) -> dict:
        waiting = db.queue_waiting()
        cur = self.current if self.current is not None and not self.current.done else None
        return {
            "tam_dung": self.paused,
            "dang_chay": {**cur.to_dict(), "ma_ho_so": _ma(cur.ho_so_id)} if cur else None,
            "so_cho": len(waiting),
            "so_trang_cho": sum(w["so_trang"] for w in waiting),
            "so_tai_lieu_cho": sum(w["so_tai_lieu"] for w in waiting),
            "uoc_tinh_giay": self.estimate(waiting),
            "toc_do": {"giay_moi_trang_ocr": round(self.rates["ocr"], 1), "giay_moi_van_ban_ai": round(self.rates["ai"], 1)},
            "dang_cho": waiting[:limit],
        }

    def active(self) -> list[Job]:
        cur = self.current
        return [cur] if cur is not None and not cur.done else []

    # ------------------------------------------------------------ chạy
    def _learn(self, job: Job) -> None:
        """Cập nhật tốc độ trung bình (để ước tính thời gian còn lại của hàng đợi)."""
        for key, n_key, s_key in (("ocr", "ocr_pages", "ocr_s"), ("ai", "ai_docs", "ai_s")):
            n, s = job.stats.get(n_key, 0), job.stats.get(s_key, 0.0)
            if n > 0 and s > 0:
                w = min(0.5, n / 20)  # nhiều mẫu -> tin hơn
                self.rates[key] = (1 - w) * self.rates[key] + w * (s / n)
                db.set_setting(f"toc_do_{key}", f"{self.rates[key]:.2f}")

    def _worker(self) -> None:
        awake = False
        while True:
            nxt = None
            if not self.paused:
                try:
                    nxt = db.next_pending()
                except Exception:  # noqa: BLE001 — CSDL bận / lỗi tạm thời: thử lại sau
                    traceback.print_exc()
            if (nxt is not None) != awake:  # còn việc -> không cho máy ngủ; hết việc / tạm dừng -> cho ngủ
                awake = nxt is not None
                keep_awake(awake)
            if nxt is None:
                self._wake.wait(2)
                self._wake.clear()
                continue
            ho_so_id, params, uu_tien = nxt
            kind = params.pop("kind", "xu_ly")
            job = Job(next(self._ids), ho_so_id, kind, params, uu_tien)
            with self._lock:
                self._jobs[job.id] = job
                self.current = job
            job.started = time.time()
            try:
                self._runner(job)
                job.set_stage("xong")
                self._learn(job)
            except Cancelled:
                job.set_stage("tam_dung" if job.requeue else "huy")
                self._learn(job)
                _safe_db(lambda: db.enqueue([ho_so_id], {"kind": kind, **params, "tiep_tuc": True}, uu_tien,
                                            keep_order=True)
                         if job.requeue else db.end_stopped(ho_so_id, "Đã hủy lần xử lý gần nhất"))
            except Exception as e:  # noqa: BLE001
                job.error = f"{e.__class__.__name__}: {e}"
                job.set_stage("loi")
                traceback.print_exc()
                # luôn đưa hồ sơ ra khỏi hàng đợi, kể cả lỗi xảy ra trước khi kịp đổi trạng thái
                _safe_db(lambda: db.end_stopped(ho_so_id, job.error, error=True))
            finally:
                job.finished = time.time()
            # giữ lịch sử trong phiên ở mức vừa phải
            if len(self._jobs) > 500:
                for jid in sorted(self._jobs)[:-200]:
                    self._jobs.pop(jid, None)


def _ma(ho_so_id: int) -> str:
    return db.code_of(ho_so_id)


def _safe_db(fn) -> None:
    try:
        fn()
    except Exception:  # noqa: BLE001 — hồ sơ đã bị xóa...
        traceback.print_exc()
