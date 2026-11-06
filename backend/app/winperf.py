"""Không cho Windows hạ tốc độ tiến trình khi chạy nền.

Windows 10/11 tự đưa tiến trình không có cửa sổ ở phía trước (backend, llama-server) vào
chế độ tiết kiệm điện ("power throttling" / EcoQoS) -> CPU chạy chậm hơn nhiều lần.
Gọi SetProcessInformation(ProcessPowerThrottling) với StateMask = 0 để tắt việc đó.
Trên hệ điều hành khác: không làm gì.
"""

from __future__ import annotations

import sys

PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1
PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION = 0x4
PROCESS_POWER_THROTTLING_INFO_CLASS = 4  # ProcessPowerThrottling


def disable_power_throttling(process_handle=None) -> bool:
    """process_handle=None -> tiến trình hiện tại. Trả về True nếu thành công."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
            _fields_ = [
                ("Version", wintypes.ULONG),
                ("ControlMask", wintypes.ULONG),
                ("StateMask", wintypes.ULONG),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel32.SetProcessInformation.restype = wintypes.BOOL

        mask = PROCESS_POWER_THROTTLING_EXECUTION_SPEED | PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION
        state = PROCESS_POWER_THROTTLING_STATE(PROCESS_POWER_THROTTLING_CURRENT_VERSION, mask, 0)
        handle = wintypes.HANDLE(int(process_handle)) if process_handle is not None else kernel32.GetCurrentProcess()
        ok = kernel32.SetProcessInformation(
            handle, PROCESS_POWER_THROTTLING_INFO_CLASS, ctypes.byref(state), ctypes.sizeof(state)
        )
        return bool(ok)
    except Exception:  # noqa: BLE001 — Windows cũ không có API này: bỏ qua
        return False


def power_status() -> str:
    """Mô tả nguồn điện / chế độ tiết kiệm pin (để cảnh báo người dùng). Rỗng nếu không đọc được."""
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        class SYSTEM_POWER_STATUS(ctypes.Structure):
            _fields_ = [
                ("ACLineStatus", wintypes.BYTE),
                ("BatteryFlag", wintypes.BYTE),
                ("BatteryLifePercent", wintypes.BYTE),
                ("SystemStatusFlag", wintypes.BYTE),
                ("BatteryLifeTime", wintypes.DWORD),
                ("BatteryFullLifeTime", wintypes.DWORD),
            ]

        st = SYSTEM_POWER_STATUS()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st)):
            return ""
        notes = []
        if st.ACLineStatus == 0:
            notes.append("đang chạy bằng PIN (không cắm sạc)")
        if st.SystemStatusFlag == 1:
            notes.append("đang bật chế độ TIẾT KIỆM PIN (Battery saver)")
        return "; ".join(notes)
    except Exception:  # noqa: BLE001
        return ""
