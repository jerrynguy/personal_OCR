# Cài đặt "Số hóa Lưu trữ" — KHÔNG chạy file này trực tiếp: bấm đúp cai-dat.bat ở thư mục gốc.
# Chạy lại bao nhiêu lần cũng được: phần nào đã có thì bỏ qua (dùng cả khi cập nhật app).

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = Join-Path $Root 'backend\.venv\Scripts\python.exe'

function Buoc($so, $ten) {
    Write-Host ''
    Write-Host "=== Bước $so/7: $ten ===" -ForegroundColor Cyan
}

function Dung($msg) {
    Write-Host ''
    Write-Host "LỖI: $msg" -ForegroundColor Red
    Write-Host 'Hãy chụp màn hình cửa sổ này và gửi cho người hỗ trợ.' -ForegroundColor Red
    Read-Host 'Bấm Enter để đóng'
    exit 1
}

function Chay([string]$moTa, [scriptblock]$lenh) {
    & $lenh
    if ($LASTEXITCODE -ne 0) { Dung "$moTa (mã lỗi $LASTEXITCODE)" }
}

function Co($lenh) {
    return [bool](Get-Command $lenh -ErrorAction SilentlyContinue)
}

Write-Host '=============================================' -ForegroundColor Green
Write-Host '   CÀI ĐẶT SỐ HÓA LƯU TRỮ' -ForegroundColor Green
Write-Host '   Lần đầu mất khoảng 30-60 phút (cần mạng).' -ForegroundColor Green
Write-Host '   Đừng đóng cửa sổ này cho đến khi báo XONG.' -ForegroundColor Green
Write-Host '=============================================' -ForegroundColor Green

# ---------------------------------------------------------------- 1
Buoc 1 'Kiểm tra Python 3.12 và Node.js'
$coPython = $false
if (Co 'py') {
    $null = & py -3.12 -c "print(1)" 2>$null
    $coPython = ($LASTEXITCODE -eq 0)
}
$thieu = @()
if (-not $coPython) { $thieu += 'Python 3.12' }
if (-not (Co 'node')) { $thieu += 'Node.js' }
if ($thieu.Count -gt 0) {
    if (Co 'winget') {
        Write-Host "Máy chưa có: $($thieu -join ', '). Đang tự cài..." -ForegroundColor Yellow
        if ($thieu -contains 'Python 3.12') {
            winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
        }
        if ($thieu -contains 'Node.js') {
            winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
        }
        Write-Host ''
        Write-Host 'Đã cài xong phần mềm cần thiết.' -ForegroundColor Green
        Write-Host 'Hãy ĐÓNG cửa sổ này rồi bấm đúp LẠI cai-dat.bat để cài tiếp.' -ForegroundColor Yellow
        Read-Host 'Bấm Enter để đóng'
        exit 0
    }
    Dung "Máy chưa có $($thieu -join ', '). Cài theo hướng dẫn mục 'Nếu cai-dat.bat báo thiếu Python / Node.js' trong README rồi chạy lại."
}
Write-Host 'Đã có Python 3.12 và Node.js.'

# ---------------------------------------------------------------- 2
Buoc 2 'Tạo môi trường Python riêng cho app'
if (Test-Path $Py) {
    Write-Host 'Đã có, bỏ qua.'
} else {
    Chay 'tạo môi trường Python' { py -3.12 -m venv backend\.venv }
}

# ---------------------------------------------------------------- 3
Buoc 3 'Cài thư viện Python (lần đầu khoảng 10 phút)'
Chay 'cập nhật pip' { & $Py -m pip install --upgrade pip }
Chay 'cài thư viện' { & $Py -m pip install -r backend\requirements.txt }
Chay 'cài VietOCR' { & $Py -m pip install --no-deps vietocr==0.3.13 }

# ---------------------------------------------------------------- 4
Buoc 4 'Tải model đọc chữ (OCR, khoảng 400 MB)'
Chay 'tải model OCR' { & $Py backend\scripts\download_models.py }

# ---------------------------------------------------------------- 5
Buoc 5 'Tải bộ chạy AI (llama.cpp) phù hợp với máy'
$coLlama = Get-ChildItem -Path 'models\llama.cpp' -Recurse -Filter 'llama-server.exe' -ErrorAction SilentlyContinue
if ($coLlama) {
    Write-Host 'Đã có, bỏ qua.'
} else {
    Chay 'tải llama.cpp' { & $Py backend\scripts\download_llama_cpp.py --auto }
}

# ---------------------------------------------------------------- 6
Buoc 6 'Model AI mặc định (gpt-oss-20b, khoảng 12 GB)'
$null = & $Py -c "import sys; sys.path.insert(0, 'backend'); from app.llm import active_model_path; active_model_path()" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host 'Đã có model AI, bỏ qua.'
} else {
    Write-Host 'Đang tải model AI 12 GB — có thể mất 20-60 phút tùy mạng. Nhớ cắm sạc.' -ForegroundColor Yellow
    Write-Host 'Mạng ngắt thì app tự thử lại. Lỡ đóng cửa sổ: bấm đúp lại cai-dat.bat, tải TIẾP từ chỗ dở.' -ForegroundColor Yellow
    Chay 'tải model AI' { & $Py backend\scripts\download_llm.py --repo lmstudio-community/gpt-oss-20b-GGUF --file gpt-oss-20b-MXFP4.gguf }
}

# ---------------------------------------------------------------- 7
Buoc 7 'Dựng giao diện'
Push-Location frontend
Chay 'cài thư viện giao diện' { npm install --no-audit --no-fund }
Chay 'dựng giao diện' { npm run build }
Pop-Location

Write-Host ''
Write-Host '=============================================' -ForegroundColor Green
Write-Host '   CÀI ĐẶT XONG!' -ForegroundColor Green
Write-Host '   Từ giờ chỉ cần bấm đúp mo-app.bat để mở app.' -ForegroundColor Green
Write-Host '=============================================' -ForegroundColor Green
Read-Host 'Bấm Enter để đóng'
