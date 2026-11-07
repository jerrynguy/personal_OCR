"""Tìm / tải / chọn model LLM dạng GGUF (chạy được bằng llama.cpp).

1) Tìm các bản GGUF trên Hugging Face (cần mạng):
    python scripts/download_llm.py --search "gemma-4-26B-A4B"

2) Tải một file cụ thể từ kết quả tìm được (cần mạng, ~15–18 GB):
    python scripts/download_llm.py --repo <tên repo> --file <tên file .gguf>

3) HOẶC dùng file .gguf đã có sẵn trên máy (ví dụ app khác đã tải về):
    python scripts/download_llm.py --use "D:\\duong\\dan\\model.gguf"

Model được chọn ghi vào models/llm/active.json.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import LLM_DIR  # noqa: E402
from app.llm import set_active_model  # noqa: E402


def search(query: str, limit: int) -> None:
    from huggingface_hub import HfApi

    api = HfApi()
    models = list(api.list_models(search=query, filter="gguf", sort="downloads", limit=limit))
    if not models:
        print("Không tìm thấy. Thử từ khóa ngắn hơn, ví dụ: --search gemma-4")
        return
    for m in models:
        try:
            info = api.model_info(m.id, files_metadata=True)
        except Exception as e:  # noqa: BLE001
            print(f"\n== {m.id}  (không đọc được danh sách file: {e.__class__.__name__})")
            continue
        ggufs = [s for s in info.siblings if s.rfilename.lower().endswith(".gguf")]
        # bỏ file "mmproj" (phần xử lý ảnh, bước này chưa cần)
        ggufs = [s for s in ggufs if "mmproj" not in s.rfilename.lower()]
        gated = " [CẦN ĐĂNG NHẬP/ĐỒNG Ý ĐIỀU KHOẢN]" if getattr(info, "gated", False) else ""
        print(f"\n== {m.id}  (lượt tải: {getattr(m, 'downloads', '?')}){gated}")
        for s in sorted(ggufs, key=lambda s: s.rfilename):
            size = f"{(s.size or 0) / 1e9:5.1f} GB" if s.size else "   ? GB"
            print(f"   {size}  {s.rfilename}")
    print(
        "\nGợi ý: chọn file Q4 (ưu tiên có chữ QAT, sau đó Q4_K_M), dung lượng ~15–18 GB."
        "\nRồi chạy: python scripts/download_llm.py --repo <repo> --file <file>"
    )


def download(repo: str, filename: str) -> Path:
    """Tải file model. Mạng ngắt -> tự thử lại; chạy lại script -> tải TIẾP từ chỗ dở (xem app/download.py)."""
    from app.download import download as fetch, hf_url

    dest = LLM_DIR / repo.replace("/", "__") / filename
    if dest.exists():
        print(f"Đã có {dest}")
        return dest
    # Cách tải cũ (huggingface_hub) để lại file tạm vài GB nếu cửa sổ bị đóng giữa chừng -> dọn cho đỡ tốn ổ đĩa
    for junk in (dest.parent / ".cache" / "huggingface" / "download").glob("*.incomplete"):
        junk.unlink(missing_ok=True)
    print(f"Đang tải {repo} / {filename} vào {dest.parent}")
    print("(mạng ngắt thì app tự thử lại; lỡ tắt cửa sổ thì bấm đúp lại cai-dat.bat — tải tiếp từ chỗ dở)")
    return fetch(hf_url(repo, filename), dest)


def main() -> int:
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--search", help="Từ khóa tìm model GGUF trên Hugging Face")
    g.add_argument("--repo", help="Tên repo trên Hugging Face (dùng kèm --file)")
    g.add_argument("--use", type=Path, help="Dùng file .gguf có sẵn trên máy")
    parser.add_argument("--file", help="Tên file .gguf trong repo")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()

    if args.search:
        search(args.search, args.limit)
        return 0

    if args.repo:
        if not args.file:
            print("Thiếu --file")
            return 1
        from app.download import DownloadError

        try:
            path = download(args.repo, args.file)
        except DownloadError as e:
            print(f"\n!!! {e}")
            return 1
        except KeyboardInterrupt:
            print("\nĐã dừng. Chạy lại sẽ tải tiếp từ chỗ dở.")
            return 1
    else:
        path = args.use
        if not path.exists() or path.suffix.lower() != ".gguf":
            print(f"Không thấy file .gguf: {path}")
            return 1

    set_active_model(path)
    print(f"[OK] Model đang dùng: {path}  ({path.stat().st_size / 1e9:.1f} GB)")
    print("Tiếp theo: python scripts/step2_llm_test.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
