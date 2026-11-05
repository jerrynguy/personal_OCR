"""BƯỚC 3 — PDF hồ sơ -> OCR -> tách từng văn bản -> trích xuất trường TT05 (luật + LLM).

    python scripts/step3_extract_pdf.py <file.pdf> [--ho-so thong_tin.json] [--no-llm]

- Kết quả OCR được lưu lại; chạy lại lần sau tự dùng lại (thêm --ocr-lai để OCR lại).
- Thông tin nhập tay của phông/hồ sơ (mã hồ sơ, thời hạn lưu trữ...) lấy từ file JSON
  --ho-so, hoặc tự tìm file <tên PDF>.ho_so.json nằm cạnh PDF.
- Kết quả: data/step3/<tên file>/ket_qua.json
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATA_DIR  # noqa: E402
from app.extract import build_ho_so, extract_document  # noqa: E402
from app.ocr import OcrPage  # noqa: E402
from app.pdf_render import low_dpi_warning, render_pdf  # noqa: E402
from app.segment import split_documents  # noqa: E402
from app.tt05 import defaults, labels  # noqa: E402

SHOW = [
    "ten_loai_tai_lieu", "so_cua_tai_lieu", "ky_hieu_cua_tai_lieu", "ngay_ban_hanh",
    "co_quan_ban_hanh", "trich_yeu_noi_dung", "tu_khoa", "ngon_ngu", "nguoi_ky",
    "chuc_vu_nguoi_ky", "do_mat", "so_luong_trang", "ma_luu_tru_tai_lieu",
]


def norm(s) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[.;:,]", "", str(s))).strip().lower()


def ocr_pages(pdf: Path, out_dir: Path, pages: str | None, redo: bool) -> tuple[list[OcrPage], list[int]]:
    images = render_pdf(pdf, out_dir, pages=pages)
    page_nos = [int(p.stem.split("_")[1]) for p in images]
    cached = [p.with_suffix(".ocr.json") for p in images]
    if not redo and all(c.exists() for c in cached):
        print(f"Dùng lại kết quả OCR đã lưu ({len(images)} trang). Thêm --ocr-lai để OCR lại.")
        return [OcrPage.from_dict(json.loads(c.read_text(encoding="utf-8"))) for c in cached], page_nos

    from app.ocr import OcrEngine

    t0 = time.perf_counter()
    engine = OcrEngine()
    print(f"Nạp OCR ({engine.description}): {time.perf_counter() - t0:.1f}s")
    result = []
    for img, cache in zip(images, cached):
        t0 = time.perf_counter()
        page = engine.run(img)
        cache.write_text(json.dumps(page.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  OCR {img.name}: {len(page.lines)} dòng, {time.perf_counter() - t0:.1f}s")
        result.append(page)
    return result, page_nos


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--ho-so", type=Path, help="File JSON thông tin phông/hồ sơ nhập tay")
    parser.add_argument("--pages", help="Ví dụ 1-10 (mặc định: tất cả)")
    parser.add_argument("--no-llm", action="store_true", help="Chỉ chạy luật, không dùng LLM")
    parser.add_argument("--ocr-lai", action="store_true", help="OCR lại, không dùng kết quả cũ")
    args = parser.parse_args()

    warning = low_dpi_warning(args.pdf)
    if warning:
        print(f"!!! {warning}")

    ho_so_file = args.ho_so or args.pdf.with_suffix(".ho_so.json")
    info = json.loads(ho_so_file.read_text(encoding="utf-8")) if ho_so_file.exists() else {}
    phong_in, ho_so_in = info.get("phong", {}), info.get("ho_so", {})
    print(f"Thông tin hồ sơ: {ho_so_file if ho_so_file.exists() else '(không có — để trống)'}")

    out_dir = DATA_DIR / "step3" / args.pdf.stem
    pages, page_nos = ocr_pages(args.pdf, out_dir, args.pages, args.ocr_lai)
    docs = split_documents(pages, page_nos)
    print(f"\nTách được {len(docs)} văn bản: " + ", ".join(f"[trang {d.page_range}]" for d in docs))

    server = llm = None
    if not args.no_llm:
        from app.llm import LlamaServer

        server = LlamaServer()
        print(f"Đang nạp LLM ({server.model_path.name})...")
        print(f"Nạp xong: {server.start():.1f}s")
        llm = server.client()

    ho_so_base = {**defaults("ho_so"), **ho_so_in}
    records = []
    try:
        for i, doc in enumerate(docs, 1):
            t0 = time.perf_counter()
            rec = extract_document(doc, llm, ho_so_base, stt=i)
            dt = time.perf_counter() - t0
            records.append(rec)
            lab = labels("tai_lieu") | labels("bo_sung")
            print(f"\n=== Văn bản {i} (trang {rec['trang_pdf']}) — {dt:.1f}s")
            for k in SHOW:
                src = rec["_nguon"].get(k, "")
                print(f"  {lab.get(k, k):48s} {str(rec.get(k, ''))[:70]:70s} {('[' + src + ']') if src else ''}")
            if rec["can_kiem_tra"]:
                print(f"  >> Cần kiểm tra: {rec['can_kiem_tra']}")
            t = rec.get("_llm_timings") or {}
            if t.get("prompt_n") is not None:
                print(f"  LLM: đọc {t['prompt_n']} token ({(t.get('prompt_ms') or 0) / 1000:.1f}s), "
                      f"viết {t['predicted_n']} token ({(t.get('predicted_ms') or 0) / 1000:.1f}s)")
    finally:
        if server:
            server.stop()

    ho_so = build_ho_so(ho_so_in, records, args.pdf.name)
    phong = {**defaults("phong"), **phong_in}
    print("\n=== Hồ sơ (tự tính)")
    for k in ("ma_ho_so", "thoi_gian_bat_dau", "thoi_gian_ket_thuc", "tong_so_tai_lieu", "so_luong_trang", "tu_khoa"):
        print(f"  {labels('ho_so')[k]:30s} {ho_so[k]}")

    truth_file = args.pdf.with_suffix(".truth.json")
    truth_docs = json.loads(truth_file.read_text(encoding="utf-8")).get("documents") if truth_file.exists() else None
    if truth_docs:
        print("\n=== Chấm điểm so với đáp án")
        if len(truth_docs) != len(records):
            print(f"  Tách SAI: {len(records)} văn bản, đáp án {len(truth_docs)}")
        total = ok = 0
        for i, (rec, truth) in enumerate(zip(records, truth_docs), 1):
            for k, v in truth.items():
                total += 1
                good = norm(rec.get(k, "")) == norm(v)
                ok += good
                if not good:
                    print(f"  Văn bản {i} – {k}: '{rec.get(k, '')}'  (đáp án: '{v}')")
        print(f"  => {ok}/{total} trường đúng")

    out_file = out_dir / "ket_qua.json"
    out_file.write_text(
        json.dumps({"phong": phong, "ho_so": ho_so, "tai_lieu": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nĐã lưu: {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
