"""Testes de integração ponta-a-ponta da aplicação completa em modo Qt offscreen."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from iawallpaper.app import IAWallpaperApp
from iawallpaper.config import Settings
from iawallpaper.paths import Paths


def _ensure_qapp():
    return QApplication.instance() or QApplication([])


def test_full_app_lifecycle_and_learning(tmp_path: Path):
    _ensure_qapp()
    paths = Paths(base_dir=Path(__file__).resolve().parent.parent, data_dir=tmp_path / "memory")
    app = IAWallpaperApp(
        paths=paths,
        override_mode="preview",
        override_hour=21.5,
        override_weather="rain",
        test_mode=True,
        enable_tray=False,
        enable_hotkey=False,
    )

    # Executa múltiplos ciclos de think + frame + carinho
    app._trigger_caress()
    for _ in range(8):
        app._tick_think()
        app._tick_frame()

    snap = app.telemetry_snapshot()
    assert snap["persona"] == "Mira"
    assert snap["affinity"] > 12.0
    assert snap["outfit"] == "rainy"
    assert snap["brain"]["neurons"] > 350

    # Troca para Nyx e modo pôr do sol limpo
    app.apply_settings(
        Settings(
            persona_id="nyx",
            mode="preview",
            time_override_hour=18.0,
            weather_mode="clear",
            test_mode=True,
        )
    )
    app._tick_think()
    assert app.persona.id == "nyx"

    # Monitor neural atualiza sem exceções
    app.neural_monitor.refresh(app.telemetry_snapshot())
    assert "Nyx" in app.neural_monitor.header_lbl.text()

    # Salva tudo atomicamente e encerra limpo
    app.save_all()
    assert (paths.persona_memory("nyx").brain).exists()
    assert (paths.persona_memory("nyx").drives).exists()
    assert paths.settings_file.exists()
    app.shutdown()
