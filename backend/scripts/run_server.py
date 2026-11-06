"""Chạy backend (API) trên máy: chỉ nghe 127.0.0.1.

    python scripts/run_server.py --dev      # thử nghiệm: không cần token, có trang /docs
    python scripts/run_server.py            # chế độ thật: token lấy từ biến SOHOA_TOKEN hoặc tự sinh

Bản desktop (Bước 7): Electron tự chạy file này, tự tạo token và đưa cho giao diện.
"""

import argparse
import os
import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402

from app.api import create_app  # noqa: E402
from app.winperf import power_status  # noqa: E402

DEFAULT_FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "out"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.environ.get("SOHOA_PORT", 8765)))
    parser.add_argument("--dev", action="store_true", help="Không cần token, bật /docs, cho phép giao diện ở cổng 3000")
    parser.add_argument("--frontend", type=Path, help="Thư mục giao diện đã build (mặc định: ../frontend/out nếu có)")
    parser.add_argument("--khong-mo-trinh-duyet", action="store_true", help="Không tự mở trình duyệt")
    parser.add_argument("--no-warmup", action="store_true", help="Không nạp sẵn OCR + LLM khi khởi động")
    args = parser.parse_args()

    warn = power_status()
    if warn:
        print(f"!!! CẢNH BÁO: máy {warn} -> CPU bị hạ xung, xử lý sẽ CHẬM hơn nhiều lần. Hãy cắm sạc / tắt Battery saver.")
    token = "" if args.dev else os.environ.get("SOHOA_TOKEN")
    frontend = args.frontend or DEFAULT_FRONTEND
    if not (frontend / "index.html").exists():
        frontend = None
    app = create_app(token=token, dev=args.dev, frontend_dir=frontend, warmup=not args.no_warmup)
    if not args.no_warmup:
        print("Đang nạp sẵn OCR + LLM ở nền (~30–60 giây)... có thể dùng ngay, việc xử lý sẽ tự chờ nạp xong.")
    print(f"Backend: http://127.0.0.1:{args.port}")
    if args.dev:
        print(f"Chế độ thử nghiệm (không token). Trang API: http://127.0.0.1:{args.port}/docs")
    if frontend:
        url = f"http://127.0.0.1:{args.port}/" + (f"#token={app.state.token}" if app.state.token else "")
        print(f"Giao diện: {url}")
        if not args.khong_mo_trinh_duyet:
            threading.Timer(2.0, lambda: webbrowser.open(url)).start()
    else:
        print("Chưa có giao diện đã build (frontend/out). Xem README Bước 6.")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
