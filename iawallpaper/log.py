"""Logger leve em memória + arquivo opcional, sem dependências externas."""

from collections import deque
from datetime import datetime
from pathlib import Path
import threading

_LOCK = threading.Lock()
_RING: deque[str] = deque(maxlen=400)
_LOG_FILE: Path | None = None
_ECHO_STDOUT = False


def configure_log(log_file: Path | None = None, echo: bool = False) -> None:
    """Configura destino de arquivo e eco no stdout."""
    global _LOG_FILE, _ECHO_STDOUT
    with _LOCK:
        _LOG_FILE = Path(log_file) if log_file else None
        _ECHO_STDOUT = bool(echo)
        if _LOG_FILE is not None:
            _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    """Registra uma linha com timestamp no buffer circular e no arquivo (se ativo)."""
    stamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {msg}"
    with _LOCK:
        _RING.append(line)
        if _ECHO_STDOUT:
            print(line, flush=True)
        if _LOG_FILE is not None:
            try:
                with open(_LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass


def recent_logs(limit: int = 80) -> list[str]:
    """Retorna as últimas linhas registradas."""
    with _LOCK:
        return list(_RING)[-limit:]
