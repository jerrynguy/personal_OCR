@echo off
chcp 65001 >nul
title Số hóa Lưu trữ - ĐỪNG ĐÓNG CỬA SỔ NÀY khi đang dùng app
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo Chưa cài đặt app. Hãy bấm đúp file cai-dat.bat trước.
  echo.
  pause
  exit /b 1
)
echo.
echo  Đang mở Số hóa Lưu trữ... Trình duyệt sẽ tự mở sau vài giây.
echo  ĐỪNG ĐÓNG cửa sổ này khi đang dùng app. Dùng xong thì đóng cửa sổ này.
echo.
".venv\Scripts\python.exe" scripts\run_server.py
echo.
echo  App đã tắt. Nếu có dòng báo lỗi ở trên, hãy chụp màn hình gửi người hỗ trợ.
pause
