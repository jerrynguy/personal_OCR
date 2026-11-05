"""Nhận diện phần cứng của máy đang chạy và chọn cách chạy LLM phù hợp.

App được cài trên nhiều loại máy (laptop văn phòng, workstation có card NVIDIA...) nên
KHÔNG được ghép cứng cấu hình theo một máy. Quy tắc:

- Card NVIDIA  -> llama.cpp bản CUDA, đưa model lên GPU (nhanh gấp nhiều lần CPU).
  Thiếu VRAM: chuyên gia (expert) của model MoE để ở RAM, phần còn lại lên GPU (--cpu-moe).
- Card AMD / Intel Arc rời -> bản Vulkan, đưa model lên GPU.
- Chỉ có GPU tích hợp (Intel Iris Xe, UHD...) -> bản CPU (tận dụng AVX2 / AVX-512).
- Cỡ model theo RAM (và VRAM): máy yếu dùng model nhỏ, máy mạnh dùng model lớn.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field

# Các "hạng" model LLM theo bộ nhớ cần (GB, file Q4 ~ RAM chiếm khi chạy).
LLM_TIERS = {
    "lon": {"ten": "Model lớn (vd. Gemma 4 26B-A4B, gpt-oss-20b)", "can_gb": 13, "ram_toi_thieu": 24},
    "nho": {"ten": "Model nhỏ (vd. Gemma 4 E4B, Qwen3 4B)", "can_gb": 4, "ram_toi_thieu": 12},
}


@dataclass
class Gpu:
    ten: str
    hang: str  # nvidia | amd | intel | khac
    vram_gb: float | None  # None = không đọc được
    tich_hop: bool  # GPU tích hợp trong CPU (dùng chung RAM)


@dataclass
class Hardware:
    he_dieu_hanh: str
    cpu: str
    nhan: int
    luong: int
    ram_gb: float
    avx2: bool
    avx512: bool
    gpu: list[Gpu] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _run(cmd: list[str], timeout: int = 10) -> str:
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _nvidia_gpus() -> list[Gpu]:
    if not shutil.which("nvidia-smi"):
        return []
    out = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
    gpus = []
    for line in out.strip().splitlines():
        name, _, mem = line.rpartition(",")
        try:
            gpus.append(Gpu(name.strip(), "nvidia", round(float(mem) / 1024, 1), False))
        except ValueError:
            continue
    return gpus


def _windows_gpus() -> list[Gpu]:
    """Card đồ họa theo Windows (dùng để biết hãng; VRAM của Windows không tin được > 4GB)."""
    out = _run([
        "powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_VideoController | Select-Object Name | ConvertTo-Json",
    ], timeout=20)
    try:
        data = json.loads(out) if out.strip() else []
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    gpus = []
    for d in data:
        name = (d.get("Name") or "").strip()
        low = name.lower()
        if not name or "microsoft basic" in low or "remote" in low:
            continue
        if "nvidia" in low:
            hang = "nvidia"
        elif "amd" in low or "radeon" in low:
            hang = "amd"
        elif "intel" in low:
            hang = "intel"
        else:
            hang = "khac"
        tich_hop = (hang == "intel" and "arc" not in low) or ("radeon" in low and "graphics" in low and "rx" not in low)
        gpus.append(Gpu(name, hang, None, tich_hop))
    return gpus


def detect() -> Hardware:
    import platform

    import psutil

    try:
        import cpuinfo

        info = cpuinfo.get_cpu_info()
        cpu_name, flags = info.get("brand_raw", ""), set(info.get("flags", []))
    except Exception:  # noqa: BLE001
        cpu_name, flags = platform.processor(), set()

    gpus = _nvidia_gpus()
    if sys.platform == "win32":
        known = {g.ten for g in gpus}
        gpus += [g for g in _windows_gpus() if g.ten not in known and not (g.hang == "nvidia" and gpus)]
    return Hardware(
        he_dieu_hanh=f"{platform.system()} {platform.release()}",
        cpu=cpu_name,
        nhan=psutil.cpu_count(logical=False) or 1,
        luong=psutil.cpu_count() or 1,
        ram_gb=round(psutil.virtual_memory().total / 2**30, 1),
        avx2="avx2" in flags,
        avx512="avx512f" in flags,
        gpu=gpus,
    )


def recommend(hw: Hardware) -> dict:
    """Cấu hình đề nghị cho llama.cpp + hạng model, kèm lý do (để hiện cho người dùng)."""
    ly_do: list[str] = []
    nvidia = [g for g in hw.gpu if g.hang == "nvidia" and g.vram_gb]
    roi_khac = [g for g in hw.gpu if g.hang in ("amd", "intel") and not g.tich_hop]

    variant, gpu_layers, extra = "cpu", 0, []
    vram = 0.0
    if nvidia:
        best = max(nvidia, key=lambda g: g.vram_gb)
        vram = best.vram_gb
        variant, gpu_layers = "cuda", 99
        ly_do.append(f"Có card NVIDIA {best.ten} ({vram:g} GB VRAM) -> chạy LLM trên GPU (CUDA)")
    elif roi_khac:
        variant, gpu_layers = "vulkan", 99
        ly_do.append(f"Có card rời {roi_khac[0].ten} -> chạy LLM trên GPU (Vulkan)")
    else:
        simd = "AVX-512" if hw.avx512 else "AVX2" if hw.avx2 else "không có AVX2 (sẽ chậm)"
        ly_do.append(f"Không có card đồ họa rời -> chạy LLM trên CPU ({hw.nhan} nhân, {simd})")

    # Hạng model: theo RAM; có VRAM lớn thì model lớn chạy hoàn toàn trên GPU.
    if hw.ram_gb >= LLM_TIERS["lon"]["ram_toi_thieu"] or vram >= LLM_TIERS["lon"]["can_gb"] + 1:
        tier = "lon"
    elif hw.ram_gb >= LLM_TIERS["nho"]["ram_toi_thieu"]:
        tier = "nho"
        ly_do.append(f"RAM {hw.ram_gb:g} GB -> dùng model nhỏ (model lớn cần >= {LLM_TIERS['lon']['ram_toi_thieu']} GB)")
    else:
        tier = "nho"
        ly_do.append(f"RAM {hw.ram_gb:g} GB là RẤT THẤP — có thể không chạy được LLM; nên dùng máy >= 16 GB")

    if variant == "cuda" and vram < LLM_TIERS[tier]["can_gb"] + 1:
        extra = ["--cpu-moe"]  # MoE: chuyên gia ở RAM, attention trên GPU -> vẫn nhanh khi thiếu VRAM
        ly_do.append(f"VRAM {vram:g} GB chưa đủ chứa cả model -> để phần 'chuyên gia' ở RAM (--cpu-moe)")

    return {
        "llama_variant": variant,
        "gpu_layers": gpu_layers,
        "extra_args": extra,
        "llm_tier": tier,
        "llm_tier_ten": LLM_TIERS[tier]["ten"],
        "ly_do": ly_do,
    }
