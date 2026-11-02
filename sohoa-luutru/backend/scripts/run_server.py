"""Chạy backend (API) trên máy: chỉ nghe 127.0.0.1.

    python scripts/run_server.py --dev      # thử nghiệm: không cần token, có trang /docs
    python scripts/run_server.py            # chế độ thật: token lấy từ biến SOHOA_TOKEN hoặc tự sinh

Bản desktop (Bước 7): Electron tự chạy file này, tự tạo token và đưa cho giao diện.
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402

from app.api import create_app  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.environ.get("SOHOA_PORT", 8765)))
    parser.add_argument("--dev", action="store_true", help="Không cần token, bật /docs, cho phép giao diện ở cổng 3000")
    parser.add_argument("--frontend", type=Path, help="Thư mục giao diện đã build (Bước 6)")
    args = parser.parse_args()

    token = "" if args.dev else os.environ.get("SOHOA_TOKEN")
    app = create_app(token=token, dev=args.dev, frontend_dir=args.frontend)
    print(f"Backend: http://127.0.0.1:{args.port}")
    if args.dev:
        print(f"Chế độ thử nghiệm (không token). Trang API: http://127.0.0.1:{args.port}/docs")
    elif not os.environ.get("SOHOA_TOKEN"):
        print(f"Token: {app.state.token}")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
