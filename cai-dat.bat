@echo off
chcp 65001 >nul
title Cài đặt Số hóa Lưu trữ
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\cai-dat.ps1"
