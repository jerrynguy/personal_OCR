"""Tải file rất lớn (model AI ~12 GB) chịu được mạng chập chờn.

Vì sao không dùng thẳng huggingface_hub: bản mới của thư viện này dừng khi mạng im 10 giây và XÓA phần đã tải
khi lỗi -> mỗi lần chạy lại phải tải lại từ đầu (gặp khi cài trên máy thật: tải được vài GB thì lỗi, chạy lại thì
bắt đầu từ 0). Ở đây:
- tải vào file '<tên>.dang_tai' NẰM YÊN trên đĩa: lỗi / tắt cửa sổ / chạy lại -> tải TIẾP từ chỗ dở (HTTP Range);
- tự thử lại khi mạng ngắt (đến khi không còn tiến triển sau nhiều lần liền);
- kiểm tra ổ đĩa đủ chỗ trước khi tải;
- giữ Windows không ngủ trong lúc tải;
- tải xong: kiểm tra dung lượng + mã SHA-256 (nếu máy chủ cho biết) rồi mới đổi tên thành file thật.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import time
from pathlib import Path

import requests

from app.winperf import keep_awake

CHUNK = 1 << 20
MAX_FAILS = 30  # số lần lỗi LIÊN TIẾP không tải thêm được byte nào thì mới bỏ cuộc
TIMEOUT = (30, 120)  # (kết nối, chờ dữ liệu) giây


class DownloadError(Exception):
    """Lỗi đã có lời giải thích tiếng Việt cho người dùng."""


def hf_url(repo: str, filename: str, revision: str = "main") -> str:
    return f"https://huggingface.co/{repo}/resolve/{revision}/{filename}"


def remote_info(session: requests.Session, url: str) -> tuple[int | None, str | None]:
    """(dung lượng, sha256) của file trên Hugging Face, đọc từ header — không tải nội dung."""
    r = session.head(url, allow_redirects=False, timeout=TIMEOUT)
    if r.status_code in (401, 403, 404):
        raise DownloadError(f"Không tìm thấy file trên máy chủ (mã {r.status_code}): {url}")
    size = r.headers.get("x-linked-size") or (r.headers.get("content-length") if r.status_code == 200 else None)
    etag = (r.headers.get("x-linked-etag") or "").strip('"').lower()
    return (int(size) if size else None), (etag if re.fullmatch(r"[0-9a-f]{64}", etag) else None)


def _print(*args, **kw) -> None:
    print(*args, **kw, flush=True)


def _gb(n: float) -> str:
    return f"{n / 1e9:.2f} GB"


def _is_disk_full(e: OSError) -> bool:
    return getattr(e, "errno", None) == 28 or getattr(e, "winerror", None) in (39, 112)


def check_space(folder: Path, need: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(folder).free
    margin = 500 * 1024 * 1024
    if free < need + margin:
        drive = folder.resolve().anchor or str(folder)
        raise DownloadError(
            f"Ổ {drive} không đủ chỗ: còn trống {_gb(free)}, cần thêm khoảng {_gb(need + margin)}. "
            "Hãy xóa bớt file trên ổ này (vd. thư mục Downloads, Thùng rác), hoặc chuyển cả thư mục app sang ổ "
            "khác còn nhiều chỗ (vd. ổ D:) rồi bấm đúp lại cai-dat.bat."
        )


def sha256_of(path: Path, log=_print) -> str:
    h = hashlib.sha256()
    total, done, last = path.stat().st_size, 0, 0.0
    with open(path, "rb") as f:
        while chunk := f.read(8 * CHUNK):
            h.update(chunk)
            done += len(chunk)
            if time.time() - last > 1:
                log(f"\r  Kiểm tra file: {done * 100 // max(total, 1)}%   ", end="")
                last = time.time()
    log("\r  Kiểm tra file: 100%   ")
    return h.hexdigest()


def download(url: str, dest: Path, log=_print, session: requests.Session | None = None,
             max_fails: int = MAX_FAILS, wait=time.sleep) -> Path:
    """Tải url -> dest (tải tiếp nếu đã có phần dở). Trả về dest. Lỗi -> DownloadError có lời giải thích."""
    session = session or requests.Session()
    part = dest.with_name(dest.name + ".dang_tai")
    dest.parent.mkdir(parents=True, exist_ok=True)
    keep_awake(True)
    try:
        size = sha = None
        fails = 0
        while True:  # đọc thông tin file (cũng có thể lỗi mạng)
            try:
                size, sha = remote_info(session, url)
                break
            except requests.RequestException as e:
                fails += 1
                if fails >= max_fails:
                    raise DownloadError(f"Không kết nối được máy chủ tải model: {e.__class__.__name__}") from e
                log(f"  Chưa kết nối được ({e.__class__.__name__}), thử lại sau 10 giây...")
                wait(10)

        have = part.stat().st_size if part.exists() else 0
        if size and have > size:  # phần dở lạ (vd. file khác) -> tải lại từ đầu
            part.unlink()
            have = 0
        if have:
            log(f"  Đã có {_gb(have)} từ lần tải trước — tải tiếp từ chỗ dở.")
        if size:
            check_space(dest.parent, size - have)

        fails = 0
        while not size or have < size:
            headers = {"Range": f"bytes={have}-"} if have else {}
            got = 0
            try:
                with session.get(url, headers=headers, stream=True, timeout=TIMEOUT) as r:
                    if r.status_code == 416 and size and have >= size:
                        break
                    if r.status_code in (401, 403, 404):
                        raise DownloadError(f"Máy chủ từ chối tải (mã {r.status_code}). Báo người hỗ trợ.")
                    r.raise_for_status()
                    if r.status_code == 200 and have:  # máy chủ không hỗ trợ tải tiếp -> tải lại từ đầu
                        have = 0
                    if size is None:
                        size = int(r.headers.get("content-length", 0)) + have or None
                    mode = "ab" if have else "wb"
                    t0, last, base = time.time(), 0.0, have
                    with open(part, mode) as f:
                        for chunk in r.iter_content(CHUNK):
                            if not chunk:
                                continue
                            f.write(chunk)
                            have += len(chunk)
                            got += len(chunk)
                            now = time.time()
                            if now - last >= 1:
                                speed = (have - base) / max(now - t0, 1e-6)
                                eta = f", còn ~{int((size - have) / speed / 60) + 1} phút" if size and speed > 0 else ""
                                pct = f" ({have * 100 // size}%)" if size else ""
                                log(f"\r  {_gb(have)} / {_gb(size) if size else '?'}{pct}, "
                                    f"{speed / 1e6:.1f} MB/s{eta}      ", end="")
                                last = now
                if size is None:  # máy chủ không cho biết dung lượng: hết luồng = xong
                    size = have
            except DownloadError:
                raise
            except OSError as e:  # gồm cả lỗi mạng của requests (là OSError) và lỗi ghi đĩa
                if _is_disk_full(e):
                    raise DownloadError("Ổ đĩa đầy trong lúc tải. Dọn bớt file rồi bấm đúp lại cai-dat.bat "
                                        "(phần đã tải được giữ lại).") from e
                fails = 0 if got else fails + 1
                if fails >= max_fails:
                    raise DownloadError(
                        f"Mạng bị ngắt nhiều lần liền ({e.__class__.__name__}). Kiểm tra mạng rồi bấm đúp lại "
                        f"cai-dat.bat — phần đã tải ({_gb(have)}) được giữ lại, sẽ tải tiếp từ chỗ dở."
                    ) from e
                delay = min(60, 5 * max(fails, 1))
                log(f"\n  Mạng bị ngắt ({e.__class__.__name__}). Đã tải {_gb(have)}; tự thử lại sau {delay} giây...")
                wait(delay)
        log("")

        if size and part.stat().st_size != size:
            raise DownloadError(f"File tải về không đủ dung lượng ({_gb(part.stat().st_size)} / {_gb(size)}). "
                                "Bấm đúp lại cai-dat.bat để tải tiếp.")
        if sha:
            log("  Đang kiểm tra file tải về có nguyên vẹn không (khoảng 1 phút)...")
            if sha256_of(part, log) != sha:
                part.unlink()
                raise DownloadError("File tải về bị hỏng (mã kiểm tra không khớp) — đã xóa. "
                                    "Bấm đúp lại cai-dat.bat để tải lại.")
        part.replace(dest)
        return dest
    finally:
        keep_awake(False)

