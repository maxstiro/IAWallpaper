"""Camada plataforma: integração nativa Windows 10/11 (host de wallpaper atrás dos ícones e sensores do SO)."""

from .desktop_host import (
    DesktopAttachment,
    attach_to_desktop,
    detach_from_desktop,
    primary_monitor_rect,
    virtual_desktop_rect,
)
from .windows import (
    active_process,
    cursor_position,
    idle_seconds,
    is_autostart_enabled,
    is_cursor_over_desktop,
    is_fullscreen,
    is_left_mouse_down,
    set_autostart,
    set_no_activate,
    start_panic_hotkey,
    system_telemetry,
)

__all__ = [
    "DesktopAttachment",
    "attach_to_desktop",
    "detach_from_desktop",
    "primary_monitor_rect",
    "virtual_desktop_rect",
    "active_process",
    "cursor_position",
    "idle_seconds",
    "is_autostart_enabled",
    "is_cursor_over_desktop",
    "is_fullscreen",
    "is_left_mouse_down",
    "set_autostart",
    "set_no_activate",
    "start_panic_hotkey",
    "system_telemetry",
]
