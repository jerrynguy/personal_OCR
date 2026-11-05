"""Chạy LLM offline bằng llama.cpp (llama-server) và gọi nó qua HTTP nội bộ (127.0.0.1).

- LlamaServer: bật/tắt tiến trình llama-server, chỉ nghe trên 127.0.0.1, có khóa API
  ngẫu nhiên mỗi lần chạy -> chương trình khác trên máy không gọi ké được.
- LlmClient: gửi prompt, ÉP output đúng JSON schema (llama.cpp chuyển schema thành
  grammar nên model không thể trả sai cấu trúc).
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path

import requests

from app.config import (
    ACTIVE_LLM_FILE,
    DEFAULT_LLM_NAME,
    LLAMA_CPP_DIR,
    LLM_CTX,
    LLM_DIR,
    LOGS_DIR,
    default_threads,
)
from app.winperf import disable_power_throttling

SERVER_EXE = "llama-server.exe" if sys.platform == "win32" else "llama-server"


def find_llama_server(variant: str = "cpu") -> Path:
    """Tìm llama-server trong models/llama.cpp/<variant>/ (cpu, cuda hoặc vulkan)."""
    base = LLAMA_CPP_DIR / variant
    found = sorted(base.rglob(SERVER_EXE)) if base.exists() else []
    if not found:
        raise FileNotFoundError(
            f"Chưa có {SERVER_EXE} trong {base}. Chạy 'python scripts/download_llama_cpp.py'."
        )
    return found[0]


def is_gguf(path: Path) -> bool:
    """File model llama.cpp bắt đầu bằng 4 byte 'GGUF'."""
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"GGUF"
    except OSError:
        return False


def default_model_path() -> Path | None:
    """Model mặc định (gpt-oss-20b-MXFP4.gguf): trong models/llm/ hoặc trong lịch sử đã dùng."""
    for p in [*sorted(LLM_DIR.rglob(DEFAULT_LLM_NAME)), *map(Path, _llm_config().get("lich_su", []))]:
        if p.name == DEFAULT_LLM_NAME and p.exists():
            return p
    return None


def active_model_path() -> Path:
    path_str = _llm_config().get("path")
    if path_str and Path(path_str).exists():
        return Path(path_str)
    default = default_model_path()
    if default:
        return default
    if path_str:
        raise FileNotFoundError(f"File model không còn tồn tại: {path_str}")
    raise FileNotFoundError(
        f"Chưa có model AI. Chép {DEFAULT_LLM_NAME} vào {LLM_DIR} hoặc chọn model trong mục 'Model AI'."
    )


def set_active_model(path: Path) -> None:
    cfg = _llm_config()
    resolved = str(path.resolve())
    cfg["path"] = resolved
    cfg["lich_su"] = list(dict.fromkeys([resolved, *cfg.get("lich_su", [])]))[:20]
    ACTIVE_LLM_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_LLM_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def list_models() -> list[dict]:
    """Các file .gguf có thể chọn: trong models/llm/ + các file đã từng dùng (vd. thư mục LM Studio)."""
    try:
        active = str(active_model_path().resolve())
    except FileNotFoundError:
        active = ""
    paths = [p for p in LLM_DIR.rglob("*.gguf") if "mmproj" not in p.name.lower()]
    paths += [Path(p) for p in _llm_config().get("lich_su", [])]
    out, seen = [], set()
    for p in paths:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen or not p.exists():
            continue
        seen.add(key)
        out.append({
            "duong_dan": key,
            "ten": p.name,
            "dung_luong_gb": round(p.stat().st_size / 1e9, 1),
            "dang_dung": key == active,
            "mac_dinh": p.name == DEFAULT_LLM_NAME,
            "trong_thu_muc_app": LLM_DIR.resolve() in p.resolve().parents,
        })
    return sorted(out, key=lambda m: (not m["dang_dung"], not m["mac_dinh"], m["ten"].lower()))


def _llm_config() -> dict:
    """models/llm/active.json: {"path": ..., và tùy chọn ghi đè: "variant", "gpu_layers", "extra_args"}."""
    try:
        return json.loads(ACTIVE_LLM_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


@lru_cache(maxsize=1)
def hardware_profile() -> tuple[dict, dict]:
    """(phần cứng, cấu hình đề nghị) — dò một lần mỗi lần mở app."""
    from app.hardware import detect, recommend

    hw = detect()
    return hw.to_dict(), recommend(hw)


def installed_variants() -> list[str]:
    return [v for v in ("cuda", "vulkan", "cpu") if (LLAMA_CPP_DIR / v).exists() and any((LLAMA_CPP_DIR / v).rglob(SERVER_EXE))]


def resolve_runtime(variant: str | None = None, gpu_layers: int | None = None,
                    extra_args: list[str] | None = None) -> dict:
    """Chọn bản llama.cpp + số lớp lên GPU. Thứ tự ưu tiên: tham số > active.json > tự dò phần cứng.
    Bản đề nghị chưa được cài -> lùi về bản CPU (vẫn chạy được, chỉ chậm hơn)."""
    cfg = _llm_config()
    _hw, rec = hardware_profile()
    chosen = variant or cfg.get("variant") or rec["llama_variant"]
    note = ""
    if chosen not in installed_variants():
        note = f"Máy hợp với bản '{chosen}' nhưng chưa cài -> tạm dùng bản CPU"
        chosen = "cpu"
    auto = chosen == rec["llama_variant"]
    if gpu_layers is None:
        gpu_layers = cfg.get("gpu_layers", rec["gpu_layers"] if auto else (99 if chosen != "cpu" else 0))
    if extra_args is None:
        extra_args = cfg.get("extra_args", rec["extra_args"] if auto else [])
    if chosen == "cpu":
        gpu_layers, extra_args = 0, [a for a in extra_args if a != "--cpu-moe"]
    return {"variant": chosen, "gpu_layers": gpu_layers, "extra_args": list(extra_args), "ghi_chu": note}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LlamaServer:
    def __init__(
        self,
        model_path: Path | None = None,
        variant: str | None = None,
        ctx: int = LLM_CTX,
        threads: int | None = None,
        gpu_layers: int | None = None,
        extra_args: list[str] | None = None,
    ):
        """variant / gpu_layers / extra_args = None -> tự chọn theo phần cứng (xem resolve_runtime)."""
        self.runtime = resolve_runtime(variant, gpu_layers, extra_args)
        variant, gpu_layers, extra_args = (
            self.runtime["variant"], self.runtime["gpu_layers"], self.runtime["extra_args"]
        )
        self.exe = find_llama_server(variant)
        self.model_path = model_path or active_model_path()
        self.port = _free_port()
        self.api_key = secrets.token_urlsafe(24)
        self.base_url = f"http://127.0.0.1:{self.port}"
        threads = threads or default_threads()
        self.args = [
            str(self.exe),
            "-m", str(self.model_path),
            "--host", "127.0.0.1",
            "--port", str(self.port),
            "--api-key", self.api_key,
            "-c", str(ctx),
            "-np", "1",  # 1 người dùng -> dồn toàn bộ ngữ cảnh cho 1 luồng xử lý
            "-t", str(threads),  # sinh chữ: số nhân thật
            "-tb", str(os.cpu_count() or threads),  # đọc prompt: dùng mọi luồng (nhanh hơn rõ)
            "-ngl", str(gpu_layers),
            "--jinja",  # dùng đúng chat template đi kèm model
            "--no-webui",
            *(extra_args or []),
        ]
        self.proc: subprocess.Popen | None = None
        self.log_path = LOGS_DIR / "llama-server.log"

    def start(self, timeout: float = 900) -> float:
        """Bật server, chờ nạp xong model. Trả về số giây nạp."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(self.log_path, "w", encoding="utf-8", errors="replace")
        t0 = time.perf_counter()
        self.proc = subprocess.Popen(
            self.args,
            stdout=log,
            stderr=subprocess.STDOUT,
            cwd=str(self.exe.parent),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        # llama-server không có cửa sổ -> Windows coi là tiến trình nền và hạ tốc độ. Tắt việc đó.
        disable_power_throttling(getattr(self.proc, "_handle", None))
        while time.perf_counter() - t0 < timeout:
            if self.proc.poll() is not None:
                raise RuntimeError(
                    f"llama-server tắt đột ngột (mã {self.proc.returncode}). "
                    f"Xem log: {self.log_path}\n{self.tail_log()}"
                )
            try:
                r = requests.get(f"{self.base_url}/health", timeout=2)
                if r.status_code == 200:
                    return time.perf_counter() - t0
            except requests.RequestException:
                pass
            time.sleep(0.5)
        self.stop()
        raise TimeoutError(f"llama-server không sẵn sàng sau {timeout}s. Xem log: {self.log_path}")

    def tail_log(self, n: int = 15) -> str:
        try:
            return "\n".join(self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
        except OSError:
            return ""

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def client(self) -> "LlmClient":
        return LlmClient(self.base_url, self.api_key)

    def __enter__(self) -> "LlamaServer":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()


class LlmClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 1800):
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.trust_env = False  # không bao giờ đi qua proxy: chỉ gọi 127.0.0.1
        self.session.headers["Authorization"] = f"Bearer {api_key}"

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 512,
        temperature: float = 0.0,
        json_schema: dict | None = None,
        reasoning_effort: str = "low",
    ) -> tuple[str, dict]:
        """Trả về (nội dung, timings). timings có prompt_per_second / predicted_per_second.

        Model "suy nghĩ trước khi trả lời" (gpt-oss...) dùng một phần max_tokens cho phần
        suy nghĩ ẩn; reasoning_effort="low" để nó suy nghĩ ngắn. Model khác bỏ qua tham số này.
        """
        body = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "cache_prompt": True,
            "chat_template_kwargs": {"reasoning_effort": reasoning_effort},
        }
        if json_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "ket_qua", "schema": json_schema, "strict": True},
            }
        r = self.session.post(f"{self.base_url}/v1/chat/completions", json=body, timeout=self.timeout)
        if r.status_code != 200:
            raise RuntimeError(f"LLM lỗi {r.status_code}: {r.text[:500]}")
        data = r.json()
        message = data["choices"][0]["message"]
        content = message.get("content") or ""
        timings = data.get("timings", {})
        timings["finish_reason"] = data["choices"][0].get("finish_reason")
        reasoning = message.get("reasoning_content") or ""
        if reasoning:
            timings["reasoning_chars"] = len(reasoning)
            timings["reasoning_preview"] = reasoning[:300]
        return content, timings

    def extract_json(
        self, system: str, user: str, schema: dict, max_tokens: int = 1024
    ) -> tuple[dict, dict]:
        content, timings = self.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=max_tokens,
            json_schema=schema,
        )
        try:
            return json.loads(content), timings
        except json.JSONDecodeError as e:
            hint = " (hết max_tokens giữa chừng)" if timings.get("finish_reason") == "length" else ""
            if not content and timings.get("reasoning_preview"):
                hint += (
                    f". Model dùng hết giới hạn cho phần suy nghĩ ({timings['reasoning_chars']} ký tự), "
                    f"chưa kịp trả lời. Đoạn đầu: {timings['reasoning_preview'][:200]!r}"
                )
            raise ValueError(f"LLM trả về JSON không hợp lệ{hint}: {content[:300]}") from e
