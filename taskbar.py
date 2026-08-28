"""
작업 표시줄 실측 · 잠금/전체화면 감지 · DPI — Win32 만 모아 둔 모듈. UI 와 무관.

- 빈 공간 측정: 작업 표시줄을 캡처해 «내용이 없는 열» 이 이어진 구간을 찾는다.
  배경색은 행별 «중앙값» (평균은 아이콘·글자에 끌려 올라가 배경 픽셀까지 내용으로 잡힌다).
- 우리 창은 WDA_EXCLUDEFROMCAPTURE 로 캡처에서 빠져 있어, 보이는 채로 재도 자기 자신을 세지 않는다.
- 잠금 감지: WTSINFOEXW.SessionFlags (0=LOCK, 오프셋 16 — Level(4)+pad(4) 뒤). 시계만 뜬 잠금 화면(LockApp)도 잡는다.
"""
import ctypes
from ctypes import wintypes

from PIL import Image, ImageChops, ImageGrab

CONTENT_DIFF = 28       # 배경과 이만큼(0~255) 다르면 '내용 있는 픽셀'

user32 = ctypes.windll.user32
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = wintypes.HWND
user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.GetParent.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.SetWindowPos.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
user32.OpenInputDesktop.restype = wintypes.HANDLE
user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
user32.CloseDesktop.argtypes = [wintypes.HANDLE]
user32.GetWindowLongW.restype = wintypes.LONG
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.restype = wintypes.LONG
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
wtsapi32 = ctypes.windll.wtsapi32
wtsapi32.WTSQuerySessionInformationW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_int,
                                                 ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
wtsapi32.WTSFreeMemory.argtypes = [ctypes.c_void_p]

SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x0001, 0x0002, 0x0010, 0x0040
HWND_TOPMOST = -1
GWL_EXSTYLE, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = -20, 0x00000080, 0x08000000
WDA_EXCLUDEFROMCAPTURE = 0x11


def make_dpi_aware():
    """캡처 좌표·창 좌표·GetWindowRect 가 전부 물리 픽셀로 일치하도록. 배율(1.0=96dpi)을 돌려준다."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
    try:
        return user32.GetDpiForSystem() / 96.0
    except Exception:
        return 1.0


def win_rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def taskbar():
    return user32.FindWindowW("Shell_TrayWnd", None)


def session_locked():
    """잠금 중이면 True — 그때 캡처하면 잠금 화면 배경을 재게 된다."""
    try:
        buf, n = ctypes.c_void_p(), wintypes.DWORD()
        if wtsapi32.WTSQuerySessionInformationW(None, 0xFFFFFFFF, 25, ctypes.byref(buf), ctypes.byref(n)):
            flags = ctypes.cast(buf.value + 16, ctypes.POINTER(wintypes.DWORD))[0]
            wtsapi32.WTSFreeMemory(buf)
            if flags == 0:
                return True
    except Exception:
        pass
    h = user32.OpenInputDesktop(0, False, 0x0001)   # 보안 데스크톱(PIN 입력)이면 실패한다 — 보조
    if not h:
        return True
    user32.CloseDesktop(h)
    return False


def fullscreen_app_active():
    """게임·동영상·프레젠테이션처럼 전체화면 앱이 앞에 있으면 True (작업 표시줄도 그때 숨는다)."""
    try:
        state = ctypes.c_int()
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) == 0:
            return state.value in (2, 3, 4)  # QUNS_BUSY / RUNNING_D3D_FULL_SCREEN / PRESENTATION_MODE
    except Exception:
        pass
    return False


def taskbar_signature():
    """앱을 열고 닫으면 바뀌는 값들 — 이게 변하면 빈 공간을 다시 잰다."""
    tb = taskbar()
    parts = [win_rect(tb)]
    for cls in ("ReBarWindow32", "TrayNotifyWnd"):
        child = user32.FindWindowExW(tb, None, cls, None)
        parts.append(win_rect(child) if child else None)
    return tuple(parts)


def measure_free_gaps(min_width):
    """작업 표시줄 캡처 → 비어 있는 열이 min_width 이상 이어진 구간들 [(x0, x1), ...] (왼쪽부터) 과 배경색."""
    left, top, right, bottom = win_rect(taskbar())
    img = ImageGrab.grab(bbox=(left, top, right, bottom)).convert("RGB")
    w, h = img.size
    raw = img.tobytes()
    med = bytearray()
    for y in range(h):
        row = raw[y * w * 3:(y + 1) * w * 3]
        for c in range(3):
            med.append(sorted(row[c::3])[w // 2])
    row_bg = Image.frombytes("RGB", (1, h), bytes(med)).resize((w, h), Image.NEAREST)
    r, g, b = ImageChops.difference(img, row_bg).split()
    diff = ImageChops.lighter(ImageChops.lighter(r, g), b).point(lambda v: 255 if v > CONTENT_DIFF else 0)
    content = [v > 0 for v in diff.resize((w, 1), Image.BOX).tobytes()]
    bg = tuple(sorted(med[c::3])[h // 2] for c in range(3))
    gaps, run_start = [], None
    for x, filled in enumerate(list(content) + [True]):
        if not filled and run_start is None:
            run_start = x
        elif filled and run_start is not None:
            if x - run_start >= min_width:
                gaps.append((left + run_start, left + x))
            run_start = None
    return gaps, bg


def make_toolwindow(hwnd):
    """작업 표시줄 버튼 없음 + 포커스 안 뺏음."""
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)


def exclude_from_capture(hwnd):
    """우리 창을 화면 캡처에서 제외 (Win10 2004+). 실패하면 False."""
    try:
        return bool(user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE))
    except Exception:
        return False


def place(hwnd, x, y, w, h):
    user32.SetWindowPos(hwnd, HWND_TOPMOST, x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)


def raise_topmost(hwnd):
    """위치·크기 그대로, z-order 만 위로 (다시 그리지 않으므로 깜빡이지 않는다)."""
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


def message_box(text, title, flags=0x40):
    user32.MessageBoxW(None, text, title, flags)
