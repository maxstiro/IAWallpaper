"""Windows 10/11 OS sensing: processo ativo, ociosidade, tela cheia, cursor, telemetria e atalho de pânico."""

import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import threading
import winreg

import psutil

from ..log import log

try:
    import pywintypes
    import win32api
    import win32con
    import win32gui
    import win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

SHELL_CLASSES = {
    "Progman",
    "WorkerW",
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
    "NotifyIconOverflowWindow",
}
DESKTOP_INTERACT_CLASSES = {
    "SysListView32",
    "SHELLDLL_DefView",
    "Progman",
    "WorkerW",
}

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000
WM_HOTKEY = 0x0312
HOTKEY_ID = 0x1A77
VK_LBUTTON = 0x01

AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_VALUE = "IAWallpaper"


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def idle_seconds() -> float:
    """Tempo em segundos desde a última entrada de teclado ou mouse."""
    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        now = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
        return ((now - info.dwTime) & 0xFFFFFFFF) / 1000.0
    except Exception:
        return 0.0


def active_process() -> str:
    """Nome do executável em primeiro plano (minúsculo). Nunca lê título nem conteúdo."""
    if not HAS_WIN32:
        return "unknown.exe"
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return "desktop"
        cls = win32gui.GetClassName(hwnd)
        if cls in SHELL_CLASSES:
            return "desktop"
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid <= 0:
            return "unknown.exe"
        return psutil.Process(pid).name().lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, ValueError, pywintypes.error, OSError):
        return "unknown.exe"


def is_fullscreen() -> bool:
    """Detecta jogos ou vídeos em tela cheia (para auto-pausa estilo Wallpaper Engine)."""
    if not HAS_WIN32:
        return False
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return False
        if win32gui.GetClassName(hwnd) in SHELL_CLASSES:
            return False
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        if ctypes.windll.user32.IsZoomed(hwnd) and (style & (win32con.WS_CAPTION | win32con.WS_THICKFRAME)):
            return False
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        m_left, m_top, m_right, m_bottom = win32api.GetMonitorInfo(monitor)["Monitor"]
        return left <= m_left and top <= m_top and right >= m_right and bottom >= m_bottom
    except Exception:
        return False


def cursor_position() -> tuple[int, int]:
    """Posição atual do cursor em pixels físicos."""
    try:
        pt = _POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
            return int(pt.x), int(pt.y)
    except Exception:
        pass
    return 0, 0


def is_left_mouse_down() -> bool:
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
    except Exception:
        return False


def is_cursor_over_desktop(own_hwnd: int = 0) -> bool:
    """Retorna True se o cursor está sobre o desktop vazio ou sobre a janela do wallpaper."""
    if not HAS_WIN32:
        return True
    try:
        x, y = cursor_position()
        hwnd = win32gui.WindowFromPoint((x, y))
        if not hwnd:
            return False
        if own_hwnd and hwnd == own_hwnd:
            return True
        cls = win32gui.GetClassName(hwnd)
        return cls in DESKTOP_INTERACT_CLASSES
    except Exception:
        return False


def set_no_activate(hwnd: int) -> None:
    """Garante que a janela nunca roube foco nem apareça no Alt+Tab."""
    if not HAS_WIN32 or not hwnd:
        return
    try:
        ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        ex |= win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TOOLWINDOW
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex)
    except Exception:
        pass


def system_telemetry() -> dict[str, float]:
    """Leitura leve de CPU e RAM (sem travar a thread principal)."""
    try:
        cpu = psutil.cpu_percent(interval=None) / 100.0
        ram = psutil.virtual_memory().percent / 100.0
        return {"cpu": max(0.0, min(1.0, cpu)), "ram": max(0.0, min(1.0, ram))}
    except Exception:
        return {"cpu": 0.0, "ram": 0.0}


def autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    py = Path(sys.executable)
    pyw = py.with_name("pythonw.exe")
    if pyw.exists():
        py = pyw
    entry = Path(__file__).resolve().parents[2] / "main.py"
    return f'"{py}" "{entry}"'


def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as key:
            return winreg.QueryValueEx(key, AUTOSTART_VALUE)[0] == autostart_command()
    except OSError:
        return False


def set_autostart(enabled: bool) -> bool:
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as key:
            if enabled:
                winreg.SetValueEx(key, AUTOSTART_VALUE, 0, winreg.REG_SZ, autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError as err:
        log(f"[plataforma] erro ao alterar autostart: {err}")
        return False


def start_panic_hotkey(callback) -> bool:
    """Registra atalho global Ctrl+Alt+Shift+W para esconder/pausar imediatamente."""
    ready = threading.Event()
    res = {"ok": False}

    def loop():
        user32 = ctypes.windll.user32
        res["ok"] = bool(
            user32.RegisterHotKey(
                None, HOTKEY_ID, MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_NOREPEAT, ord("W")
            )
        )
        ready.set()
        if not res["ok"]:
            log("[plataforma] atalho de pânico Ctrl+Alt+Shift+W indisponível")
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                callback()

    threading.Thread(target=loop, daemon=True, name="iawallpaper-hotkey").start()
    ready.wait(1.5)
    return res["ok"]
