"""DESKTOP HOST — Ancora a janela do wallpaper atrás dos ícones no Windows 10 e Windows 11 24H2+ (Raised Desktop).

Estratégia dual (idêntica às correções modernas de Wallpaper Engine / Lively Wallpaper):
1. Envia mensagem 0x052C ao Progman para garantir a camada WorkerW.
2. Detecta Windows 11 24H2+ (Raised Desktop): Progman tem WS_EX_NOREDIRECTIONBITMAP ou
   contém diretamente SHELLDLL_DefView + WorkerW como filhos. Nesse modo, a janela do
   wallpaper recebe WS_EX_LAYERED, faz SetParent(hwnd, progman) e posiciona-se logo abaixo
   de SHELLDLL_DefView via SetWindowPos(hwnd, shell_defview, ...).
3. Em Windows 10 / 11 anterior à 24H2: encontra o WorkerW irmão logo após o dono de
   SHELLDLL_DefView e faz SetParent(hwnd, workerw).
4. Se nenhum host desktop existir (ex: sessão headless ou preview), reporta fallback limpo.
"""

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from ..log import log

SMTO_NORMAL = 0x0000
WM_SPAWN_WORKER = 0x052C

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_NOREDIRECTIONBITMAP = 0x00200000

LWA_ALPHA = 0x00000002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_FRAMECHANGED = 0x0020
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
HWND_BOTTOM = 1

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
SM_CXSCREEN = 0
SM_CYSCREEN = 1


@dataclass
class DesktopAttachment:
    attached: bool
    mode: str                 # "win11_raised" | "classic_workerw" | "fallback"
    parent_hwnd: int = 0
    shell_view_hwnd: int = 0
    workerw_hwnd: int = 0
    rect: tuple[int, int, int, int] = (0, 0, 1920, 1080)


def primary_monitor_rect() -> tuple[int, int, int, int]:
    """Retorna (x, y, width, height) do monitor primário em pixels físicos."""
    try:
        user32 = ctypes.windll.user32
        w = int(user32.GetSystemMetrics(SM_CXSCREEN))
        h = int(user32.GetSystemMetrics(SM_CYSCREEN))
        if w > 0 and h > 0:
            return (0, 0, w, h)
    except Exception:
        pass
    return (0, 0, 1920, 1080)


def virtual_desktop_rect() -> tuple[int, int, int, int]:
    """Retorna (x, y, width, height) cobrindo todos os monitores."""
    try:
        user32 = ctypes.windll.user32
        x = int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN))
        y = int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
        w = int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
        h = int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
        if w > 0 and h > 0:
            return (x, y, w, h)
    except Exception:
        pass
    return primary_monitor_rect()


def _find_classic_workerw(user32) -> tuple[int, int]:
    """Localiza (shell_view_hwnd, workerw_hwnd) no modelo clássico Win10/Win11 <24H2."""
    holder = {"defview": 0, "workerw": 0}

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_cb(hwnd, _lp):
        defview = user32.FindWindowExW(hwnd, 0, "SHELLDLL_DefView", None)
        if defview:
            holder["defview"] = int(defview)
            worker = user32.FindWindowExW(0, hwnd, "WorkerW", None)
            if worker:
                holder["workerw"] = int(worker)
            return False
        return True

    user32.EnumWindows(enum_cb, 0)
    return holder["defview"], holder["workerw"]


def attach_to_desktop(hwnd: int, rect: tuple[int, int, int, int] | None = None) -> DesktopAttachment:
    """Ancora o HWND da janela do wallpaper atrás dos ícones da área de trabalho."""
    target_rect = rect or primary_monitor_rect()
    if not hwnd:
        return DesktopAttachment(False, "fallback", rect=target_rect)
    try:
        user32 = ctypes.windll.user32
        progman = int(user32.FindWindowW("Progman", None))
        if not progman:
            log("[desktop_host] Progman não encontrado; operando em modo janela/fallback.")
            return DesktopAttachment(False, "fallback", rect=target_rect)

        # Dispara criação/organização do WorkerW
        result = ctypes.c_ulong(0)
        user32.SendMessageTimeoutW(progman, WM_SPAWN_WORKER, 0x0000000D, 0x00000001, SMTO_NORMAL, 1000, ctypes.byref(result))
        user32.SendMessageTimeoutW(progman, WM_SPAWN_WORKER, 0, 0, SMTO_NORMAL, 1000, ctypes.byref(result))

        progman_ex = int(user32.GetWindowLongW(progman, GWL_EXSTYLE))
        child_defview = int(user32.FindWindowExW(progman, 0, "SHELLDLL_DefView", None))
        child_workerw = int(user32.FindWindowExW(progman, 0, "WorkerW", None))

        is_raised = bool(progman_ex & WS_EX_NOREDIRECTIONBITMAP) or (child_defview and child_workerw)
        x, y, w, h = target_rect

        if is_raised and child_defview:
            # Windows 11 24H2+ Raised Desktop
            ex = int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
            ex |= WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
            user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)

            style = int(user32.GetWindowLongW(hwnd, GWL_STYLE))
            style = (style & ~WS_POPUP) | WS_CHILD
            user32.SetWindowLongW(hwnd, GWL_STYLE, style)

            user32.SetParent(hwnd, progman)
            # Posiciona imediatamente abaixo de SHELLDLL_DefView (atrás dos ícones, acima do WorkerW)
            user32.SetWindowPos(
                hwnd,
                child_defview,
                x,
                y,
                w,
                h,
                SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_FRAMECHANGED,
            )
            log(f"[desktop_host] Ancorado em Windows 11 Raised Desktop (Progman={hex(progman)}, DefView={hex(child_defview)})")
            return DesktopAttachment(
                attached=True,
                mode="win11_raised",
                parent_hwnd=progman,
                shell_view_hwnd=child_defview,
                workerw_hwnd=child_workerw,
                rect=target_rect,
            )

        # Modo clássico Windows 10 / 11 (< 24H2)
        defview, workerw = _find_classic_workerw(user32)
        if workerw:
            ex = int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
            ex |= WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)

            user32.SetParent(hwnd, workerw)
            user32.SetWindowPos(
                hwnd,
                0,
                x,
                y,
                w,
                h,
                SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_FRAMECHANGED,
            )
            log(f"[desktop_host] Ancorado em WorkerW clássico ({hex(workerw)})")
            return DesktopAttachment(
                attached=True,
                mode="classic_workerw",
                parent_hwnd=workerw,
                shell_view_hwnd=defview,
                workerw_hwnd=workerw,
                rect=target_rect,
            )

        log("[desktop_host] Nenhum WorkerW disponível; usando fallback inferior.")
        user32.SetWindowPos(hwnd, HWND_BOTTOM, x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)
        return DesktopAttachment(False, "fallback", rect=target_rect)
    except Exception as err:
        log(f"[desktop_host] Erro ao ancorar no desktop: {err}")
        return DesktopAttachment(False, "fallback", rect=target_rect)


def detach_from_desktop(hwnd: int) -> None:
    """Desacopla a janela do desktop e pede redesenho limpo do shell do Windows."""
    if not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        user32.SetParent(hwnd, 0)
        progman = user32.FindWindowW("Progman", None)
        if progman:
            user32.InvalidateRect(progman, None, True)
            user32.UpdateWindow(progman)
    except Exception as err:
        log(f"[desktop_host] Erro ao desacoplar: {err}")
