"""Ponto de entrada CLI do IAWallpaper."""

import argparse
import os
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication

from iawallpaper.app import IAWallpaperApp
from iawallpaper.paths import Paths


def _acquire_single_instance(lock_path: Path) -> bool:
    """Impede duas instâncias simultâneas do wallpaper no mesmo usuário."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists():
        try:
            old_pid = int(lock_path.read_text(encoding="utf-8").strip())
            import psutil
            if psutil.pid_exists(old_pid) and old_pid != os.getpid():
                return False
        except Exception:
            pass
    try:
        lock_path.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="IAWallpaper — Wallpaper dinâmico com avatar waifu cognitivo.")
    parser.add_argument("--preview", action="store_true", help="Abre em janela interativa de preview em vez de trás dos ícones.")
    parser.add_argument("--studio", action="store_true", help="Abre a Central de Controle junto com o wallpaper.")
    parser.add_argument("--monitor", action="store_true", help="Abre o Monitor Neural ao vivo.")
    parser.add_argument("--test", action="store_true", help="Modo teste (decisões e sussurros acelerados).")
    parser.add_argument("--time", type=float, default=None, help="Simula hora fixa do dia (0..24).")
    parser.add_argument("--weather", type=str, default=None, help="Simula clima (clear|cloudy|rain|storm|snow|fog).")
    args = parser.parse_args(argv)

    paths = Paths()
    lock_file = paths.data_dir / "iawallpaper.lock"
    if not _acquire_single_instance(lock_file):
        print("IAWallpaper já está em execução.", file=sys.stderr)
        return 0

    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)

    wp = IAWallpaperApp(
        paths=paths,
        override_mode="preview" if args.preview else None,
        override_hour=args.time,
        override_weather=args.weather,
        test_mode=args.test,
    )
    wp.start(show_studio=args.studio or args.preview, show_monitor=args.monitor)

    try:
        return qt_app.exec()
    finally:
        try:
            lock_file.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
