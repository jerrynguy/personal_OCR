"""Tải llama.cpp (llama-server) bản Windows từ GitHub — CHỈ CẦN CHẠY MỘT LẦN KHI CÓ MẠNG.

    python scripts/download_llama_cpp.py --auto            # TỰ CHỌN theo phần cứng máy này (khuyên dùng)
    python scripts/download_llama_cpp.py                   # bản CPU
    python scripts/download_llama_cpp.py --variant cuda    # card NVIDIA
    python scripts/download_llama_cpp.py --variant vulkan  # card AMD / Intel Arc
    python scripts/download_llama_cpp.py --tag b6500       # một phiên bản cụ thể

Bản CPU luôn được tải kèm (dự phòng). Bản CPU tự chọn tập lệnh nhanh nhất của máy (AVX2 / AVX-512).
Giải nén vào sohoa-luutru/models/llama.cpp/<variant>/
"""

import argparse
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import LLAMA_CPP_DIR  # noqa: E402
from app.llm import SERVER_EXE  # noqa: E402

REPO = "ggml-org/llama.cpp"
VARIANTS = ("cpu", "cuda", "vulkan")
ASSET_PATTERNS = {
    "cpu": r"bin-win-cpu-x64\.zip$",
    "vulkan": r"bin-win-vulkan-x64\.zip$",
    "cuda": r"bin-win-cuda-([\d.]+)-x64\.zip$",
}
# Bản CPU: không được chứa tên các backend GPU / kiến trúc khác.
NOT_CPU = ("cuda", "cudart", "vulkan", "hip", "radeon", "sycl", "opencl", "kompute", "openvino", "arm64")


def _cuda_version(name: str) -> tuple[int, ...]:
    m = re.search(ASSET_PATTERNS["cuda"], name)
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def pick_asset(assets: list[dict], variant: str) -> list[dict]:
    """Các file cần tải cho một bản (bản CUDA = file chính + gói thư viện cudart). Rỗng nếu không có."""
    if variant == "cuda":
        mains = [a for a in assets if _cuda_version(a["name"]) and not a["name"].lower().startswith("cudart")]
        if not mains:
            return []
        # Ưu tiên CUDA 12.x: chạy được với driver NVIDIA phổ biến; CUDA 13 cần driver rất mới.
        mains.sort(key=lambda a: (_cuda_version(a["name"])[0] != 12, [-x for x in _cuda_version(a["name"])]))
        main = mains[0]
        ver = ".".join(map(str, _cuda_version(main["name"])))
        rt = [a for a in assets if a["name"].lower().startswith("cudart") and f"cuda-{ver}-x64" in a["name"]]
        return [main, *rt[:1]]
    for a in assets:
        if re.search(ASSET_PATTERNS[variant], a["name"]):
            return [a]
    for a in assets:
        n = a["name"].lower()
        if not (n.endswith(".zip") and "win" in n and ("x64" in n or "amd64" in n)):
            continue
        if variant == "cpu" and not any(k in n for k in NOT_CPU):
            return [a]
        if variant == "vulkan" and "vulkan" in n:
            return [a]
    return []


def fetch_releases(tag: str | None) -> list[dict]:
    base = f"https://api.github.com/repos/{REPO}/releases"
    url = f"{base}/tags/{tag}" if tag else f"{base}?per_page=30"
    print(f"Đang hỏi GitHub: {url}")
    data = requests.get(url, timeout=30).json()
    if isinstance(data, dict) and "assets" not in data:
        raise RuntimeError(f"Không đọc được thông tin phiên bản: {data.get('message', data)}")
    return [data] if isinstance(data, dict) else [r for r in data if not r.get("draft")]


def download(asset: dict, dest_zip: Path) -> None:
    with requests.get(asset["browser_download_url"], stream=True, timeout=60) as r:
        r.raise_for_status()
        done = 0
        with open(dest_zip, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                done += len(chunk)
                print(f"\r  {done / max(asset['size'], 1):6.1%}", end="")
    print()


def install(variant: str, releases: list[dict]) -> int:
    # "Bản mới nhất" theo GitHub có thể không kèm file Windows -> lấy bản gần nhất có file đúng loại.
    tag, assets = None, []
    for rel in releases:
        assets = pick_asset(rel.get("assets", []), variant)
        if assets:
            tag = rel["tag_name"]
            break
    if not assets:
        print(f"Không thấy file Windows '{variant}' trong {len(releases)} bản gần nhất. Danh sách:")
        for rel in releases[:5]:
            names = ", ".join(a["name"] for a in rel.get("assets", [])) or "(không có file)"
            print(f"  {rel['tag_name']}: {names[:400]}")
        return 1

    dest = LLAMA_CPP_DIR / variant
    LLAMA_CPP_DIR.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    for asset in assets:
        zip_path = LLAMA_CPP_DIR / asset["name"]
        print(f"[{variant}] phiên bản {tag}: tải {asset['name']} ({asset['size'] / 1048576:.0f} MB)")
        download(asset, zip_path)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(dest)  # bản CUDA: file chính + cudart giải nén chung một thư mục
        zip_path.unlink()
    (dest / "VERSION.txt").write_text(tag, encoding="utf-8")

    exes = list(dest.rglob(SERVER_EXE))
    if not exes:
        print(f"Giải nén xong nhưng không thấy {SERVER_EXE} trong {dest}")
        return 1
    print(f"[OK] {exes[0]}")
    out = subprocess.run([str(exes[0]), "--version"], capture_output=True, text=True, cwd=exes[0].parent)
    print((out.stdout + out.stderr).strip()[-600:])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--variant", choices=VARIANTS, default="cpu")
    g.add_argument("--auto", action="store_true", help="Tự chọn bản theo phần cứng máy này (+ bản CPU dự phòng)")
    parser.add_argument("--tag", help="Ví dụ b6500. Mặc định: bản mới nhất có file Windows")
    args = parser.parse_args()

    variants = [args.variant]
    if args.auto:
        from app.llm import hardware_profile

        _hw, rec = hardware_profile()
        for line in rec["ly_do"]:
            print(f"  - {line}")
        variants = list(dict.fromkeys([rec["llama_variant"], "cpu"]))
        print(f"Sẽ tải: {', '.join(variants)}")

    try:
        releases = fetch_releases(args.tag)
    except Exception as e:  # noqa: BLE001
        print(e)
        return 1
    return max(install(v, releases) for v in variants)


if __name__ == "__main__":
    raise SystemExit(main())
