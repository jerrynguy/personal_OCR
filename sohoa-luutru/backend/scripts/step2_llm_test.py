"""BƯỚC 2 — Kiểm tra LLM offline: nạp model, đo tốc độ, thử trích xuất trường dữ liệu.

    python scripts/step2_llm_test.py
    python scripts/step2_llm_test.py --text-file ..\\data\\step1\\<tên>\\page_001.txt
    python scripts/step2_llm_test.py --variant vulkan --ngl 99     # thử GPU Iris Xe

Mặc định dùng văn bản OCR của PDF mẫu (Quyết định 125/QĐ-UBND) và tự chấm đúng/sai.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm import LlamaServer  # noqa: E402

# Văn bản giống hệt đầu ra OCR thật (kể cả lỗi viết thường "sở nội vụ" của OCR).
SAMPLE_OCR = """ỦY BAN NHÂN DÂN   |   CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
TỈNH AN BÌNH   |   Độc lập - Tự do - Hạnh phúc
Số: 125/QĐ-UBND   |   An Bình, ngày 15 tháng 3 năm 2025
QUYẾT ĐỊNH
Về việc thành lập Tổ công tác số hóa tài liệu lưu trữ
CHỦ TỊCH ỦY BAN NHÂN DÂN TỈNH AN BÌNH
Căn cứ Luật Lưu trữ ngày 21 tháng 6 năm 2024;
Căn cứ Thông tư số 05/2025/TT-BNV ngày 14 tháng 5 năm 2025;
Theo đề nghị của Giám đốc sở nội vụ.
QUYẾT ĐỊNH:
Điều 1. Thành lập Tổ công tác số hóa tài liệu lưu trữ của tỉnh.
Điều 2. Tổ công tác có nhiệm vụ số hóa toàn bộ hồ sơ giai đoạn
2015 - 2024 đang bảo quản tại Kho lưu trữ chuyên dụng.
1
--- hết trang 1 ---
Điều 3. Quyết định này có hiệu lực kể từ ngày ký.
Nơi nhận:   |   CHỦ TỊCH
- Như Điều 3;
- Lưu: VT, NV.
Nguyễn Văn An
2"""

EXPECTED = {
    "so_ky_hieu": "125/QĐ-UBND",
    "ngay_ban_hanh": "15/03/2025",
    "ten_loai": "Quyết định",
    "trich_yeu": "Về việc thành lập Tổ công tác số hóa tài liệu lưu trữ",
    "co_quan_ban_hanh": "Ủy ban nhân dân tỉnh An Bình",
    "nguoi_ky": "Nguyễn Văn An",
    "chuc_vu_nguoi_ky": "Chủ tịch",
    "do_mat": "Thường",
}

# Schema thử nghiệm (một phần trường "Tài liệu" của TT05). Schema đầy đủ làm ở Bước 3.
SCHEMA = {
    "type": "object",
    "properties": {
        "so_ky_hieu": {"type": "string"},
        "ngay_ban_hanh": {"type": "string", "pattern": "^([0-9]{2}/[0-9]{2}/[0-9]{4})?$"},
        "ten_loai": {"type": "string"},
        "trich_yeu": {"type": "string"},
        "co_quan_ban_hanh": {"type": "string"},
        "nguoi_ky": {"type": "string"},
        "chuc_vu_nguoi_ky": {"type": "string"},
        "do_mat": {"type": "string", "enum": ["Thường", "Mật", "Tối mật", "Tuyệt mật"]},
    },
    "required": list(EXPECTED),
    "additionalProperties": False,
}

SYSTEM = (
    "Bạn là chuyên viên lưu trữ, trích xuất thông tin văn bản hành chính Việt Nam theo thể thức "
    "Nghị định 30/2020/NĐ-CP. Đầu vào là văn bản OCR (có thể sai chính tả nhẹ; ký tự '|' ngăn cách "
    "2 cột trên cùng một dòng). Quy tắc:\n"
    "- so_ky_hieu: giữ NGUYÊN số và ký hiệu sau chữ 'Số:', không thêm bớt.\n"
    "- ngay_ban_hanh: ngày ở dòng địa danh, ngày tháng năm, định dạng dd/mm/yyyy.\n"
    "- ten_loai: tên loại văn bản viết thường chữ cái đầu (Quyết định, Công văn, Tờ trình...). "
    "Nếu không có tên loại mà có dòng 'V/v' dưới số ký hiệu thì là 'Công văn'.\n"
    "- trich_yeu: trích yếu nội dung ngay dưới tên loại (hoặc sau 'V/v'), viết đúng chính tả.\n"
    "- co_quan_ban_hanh: cơ quan ban hành ở góc trên bên trái, viết hoa chữ cái đầu đúng quy tắc.\n"
    "- nguoi_ky, chuc_vu_nguoi_ky: ở phần chữ ký cuối văn bản.\n"
    "- do_mat: 'Thường' nếu không có dấu độ mật.\n"
    "Không đoán: trường nào không có trong văn bản thì để chuỗi rỗng."
)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[.;:,]", "", str(s))).strip().lower()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text-file", type=Path, help="Văn bản OCR thật (file .txt của Bước 1)")
    parser.add_argument("--variant", choices=["cpu", "vulkan"], default="cpu")
    parser.add_argument("--ngl", type=int, default=0, help="Số lớp đưa lên GPU (chỉ bản vulkan)")
    parser.add_argument("--threads", type=int)
    args = parser.parse_args()

    text = args.text_file.read_text(encoding="utf-8") if args.text_file else SAMPLE_OCR
    expected = None if args.text_file else EXPECTED

    server = LlamaServer(variant=args.variant, threads=args.threads, gpu_layers=args.ngl)
    print(f"Model : {server.model_path.name} ({server.model_path.stat().st_size / 1e9:.1f} GB)")
    print(f"Server: {server.exe}")
    print("Đang nạp model (lần đầu có thể mất 1–3 phút)...")
    try:
        load = server.start()
    except Exception as e:  # noqa: BLE001
        print(f"LỖI khi bật llama-server: {e}")
        return 1
    print(f"Nạp xong: {load:.1f}s\n")

    try:
        llm = server.client()

        print("== Test 1: trả lời ngắn (đo tốc độ sinh chữ)")
        t0 = time.perf_counter()
        answer, t1 = llm.chat(
            [{"role": "user", "content": "Trả lời đúng 1 câu ngắn: Thủ đô của Việt Nam là gì?"}],
            max_tokens=48,
        )
        print(f"   {answer.strip()}")
        print(
            f"   {time.perf_counter() - t0:.1f}s | sinh chữ {t1.get('predicted_per_second', 0):.1f} token/s\n"
        )

        print("== Test 2: trích xuất trường dữ liệu từ văn bản OCR (ép JSON schema)")
        t0 = time.perf_counter()
        result, t2 = llm.extract_json(SYSTEM, f"Văn bản OCR:\n\n{text}", SCHEMA, max_tokens=400)
        total = time.perf_counter() - t0
        print(json.dumps(result, ensure_ascii=False, indent=2))

        if expected:
            ok = 0
            print("\n   Chấm điểm:")
            for k, v in expected.items():
                good = norm(result.get(k, "")) == norm(v)
                ok += good
                mark = "ĐÚNG" if good else f"SAI  (đáp án: {v})"
                print(f"   {k:18s} {mark}")
            print(f"   => {ok}/{len(expected)} trường đúng")

        print(
            f"\n   Thời gian: {total:.1f}s | đọc prompt {t2.get('prompt_n', '?')} token @ "
            f"{t2.get('prompt_per_second', 0):.1f} token/s | sinh {t2.get('predicted_n', '?')} token @ "
            f"{t2.get('predicted_per_second', 0):.1f} token/s"
        )
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
