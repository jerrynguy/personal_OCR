"""Kiểm tra máy: phần cứng nhận diện được, cấu hình app sẽ dùng, còn thiếu gì.

    python scripts/kiem_tra_may.py

Dùng trên MỌI máy định cài app (laptop văn phòng, workstation...) để biết app sẽ chạy thế nào.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DET_MODELS, DOC_ORI_MODEL, VIETOCR_MODELS, paddle_model_dir, vietocr_weights_path  # noqa: E402
from app.llm import _llm_config, hardware_profile, installed_variants, resolve_runtime  # noqa: E402
from app.winperf import power_status  # noqa: E402


def main() -> int:
    hw, rec = hardware_profile()
    print("== Phần cứng")
    print(f"  Hệ điều hành : {hw['he_dieu_hanh']}")
    print(f"  CPU          : {hw['cpu']} — {hw['nhan']} nhân / {hw['luong']} luồng"
          f" — AVX2 {'có' if hw['avx2'] else 'KHÔNG'}, AVX-512 {'có' if hw['avx512'] else 'không'}")
    print(f"  RAM          : {hw['ram_gb']} GB")
    if hw["gpu"]:
        for g in hw["gpu"]:
            vram = f"{g['vram_gb']} GB VRAM" if g["vram_gb"] else "VRAM không rõ"
            print(f"  Card đồ họa  : {g['ten']} ({g['hang']}, {'tích hợp' if g['tich_hop'] else 'rời'}, {vram})")
    else:
        print("  Card đồ họa  : không nhận diện được")
    warn = power_status()
    if warn:
        print(f"  !!! Nguồn điện: {warn} -> sẽ chạy chậm")

    print("\n== Cấu hình đề nghị cho máy này")
    for line in rec["ly_do"]:
        print(f"  - {line}")
    print(f"  - LLM: llama.cpp bản '{rec['llama_variant']}', {rec['gpu_layers']} lớp lên GPU"
          f" {' '.join(rec['extra_args'])}; {rec['llm_tier_ten']}")

    print("\n== Đã cài")
    print(f"  llama.cpp    : {', '.join(installed_variants()) or 'CHƯA CÓ'}")
    rt = resolve_runtime()
    print(f"  Sẽ chạy      : bản {rt['variant']}, {rt['gpu_layers']} lớp lên GPU {' '.join(rt['extra_args'])}")
    model = _llm_config().get("path", "")
    print(f"  Model LLM    : {Path(model).name if model else 'CHƯA CHỌN'}"
          + ("" if not model or Path(model).exists() else " (FILE KHÔNG CÒN)"))
    ocr_ok = all(paddle_model_dir(n).exists() for n in [DOC_ORI_MODEL, *DET_MODELS]) and all(
        vietocr_weights_path(n).exists() for n in VIETOCR_MODELS
    )
    print(f"  Model OCR    : {'đủ' if ocr_ok else 'THIẾU — chạy python scripts/download_models.py'}")

    todo = []
    if rt["ghi_chu"] or rec["llama_variant"] not in installed_variants():
        todo.append("python scripts/download_llama_cpp.py --auto")
    if not model:
        todo.append("python scripts/download_llm.py ... (chọn model hạng phù hợp ở trên)")
    if todo:
        print("\n== Nên làm")
        for t in todo:
            print(f"  {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
