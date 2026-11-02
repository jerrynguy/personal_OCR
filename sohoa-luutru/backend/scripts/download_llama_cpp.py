"""Tải llama.cpp (llama-server) bản Windows từ GitHub — CHỈ CẦN CHẠY MỘT LẦN KHI CÓ MẠNG.

    python scripts/download_llama_cpp.py                 # bản CPU (mặc định, khuyên dùng)
    python scripts/download_llama_cpp.py --variant vulkan  # bản dùng GPU Intel Iris Xe (thử nghiệm)
    python scripts/download_llama_cpp.py --tag b6500     # một phiên bản cụ thể

Bản CPU tự chọn tập lệnh nhanh nhất của máy (i7-1185G7 có AVX-512).
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
ASSET_PATTERNS = {
    "cpu": r"bin-win-cpu-x64\.zip$",
    "vulkan": r"bin-win-vulkan-x64\.zip$",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=list(ASSET_PATTERNS), default="cpu")
    parser.add_argument("--tag", help="Ví dụ b6500. Mặc định: bản mới nhất")
    args = parser.parse_args()

    api = f"https://api.github.com/repos/{REPO}/releases/" + (
        f"tags/{args.tag}" if args.tag else "latest"
    )
    print(f"Đang hỏi GitHub: {api}")
    release = requests.get(api, timeout=30).json()
    if "assets" not in release:
        print(f"Không đọc được thông tin phiên bản: {release.get('message', release)}")
        return 1

    tag = release["tag_name"]
    assets = [a for a in release["assets"] if re.search(ASSET_PATTERNS[args.variant], a["name"])]
    if not assets:
        names = [a["name"] for a in release["assets"] if "win" in a["name"]]
        print(f"Không thấy file '{args.variant}' trong {tag}. Các file Windows có:\n  " + "\n  ".join(names))
        return 1
    asset = assets[0]

    dest = LLAMA_CPP_DIR / args.variant
    zip_path = LLAMA_CPP_DIR / asset["name"]
    LLAMA_CPP_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Phiên bản {tag}: tải {asset['name']} ({asset['size'] / 1048576:.0f} MB)")
    with requests.get(asset["browser_download_url"], stream=True, timeout=60) as r:
        r.raise_for_status()
        done = 0
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                done += len(chunk)
                print(f"\r  {done / asset['size']:6.1%}", end="")
    print()

    if dest.exists():
        shutil.rmtree(dest)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dest)
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


if __name__ == "__main__":
    raise SystemExit(main())
