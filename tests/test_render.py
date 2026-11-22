"""Testes offscreen da camada render (atmosfera, partículas, avatar, cenas dia/noite/chuva e hit-test)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from iawallpaper.core.emotion import EmotionState
from iawallpaper.core.persona import load_persona
from iawallpaper.render.atmosphere import compute_atmosphere
from iawallpaper.render.canvas import WallpaperCanvas
from iawallpaper.sense.circadian import compute_circadian
from iawallpaper.sense.weather import WeatherState


def _ensure_qapp():
    return QApplication.instance() or QApplication([])


def test_atmosphere_varies_by_time_and_weather():
    day_clear = compute_atmosphere(compute_circadian(12.0), WeatherState(condition="clear"))
    night_clear = compute_atmosphere(compute_circadian(23.0), WeatherState(condition="clear"))
    storm_flash = compute_atmosphere(compute_circadian(23.0), WeatherState(condition="storm", intensity=1.0), lightning=0.9)

    assert day_clear.sky_top[2] > night_clear.sky_top[2]
    assert night_clear.star_alpha > 0.7
    assert night_clear.window_glow_alpha > 0.7
    assert storm_flash.sky_mid[0] > night_clear.sky_mid[0]


def test_canvas_renders_non_empty_frames_and_hit_tests():
    _ensure_qapp()
    mira = load_persona("mira")
    canvas = WallpaperCanvas(mira)

    canvas.circadian = compute_circadian(18.0)
    canvas.weather = WeatherState(condition="clear", temperature_c=24.0)
    canvas.emotion = EmotionState(mood="happy", label="Radiante", valence=0.8, arousal=0.7, blush=0.4)
    canvas.scene.set_whisper("O pôr do sol hoje está incrível ✨", 1.0)
    img_sunset = canvas.render_to_image(1280, 720)
    assert not img_sunset.isNull()
    assert img_sunset.width() == 1280 and img_sunset.height() == 720
    # Hitboxes da cabeça e corpo preenchidas após render
    assert not canvas.avatar.head_rect.isEmpty()
    assert not canvas.avatar.body_rect.isEmpty()

    head_c = canvas.avatar.head_rect.center()
    assert canvas.avatar.hit_test(head_c.x(), head_c.y()) == "head"

    # Testa modo noite chuvosa + modo foco com óculos
    canvas.circadian = compute_circadian(23.0)
    canvas.weather = WeatherState(condition="rain", intensity=0.9, temperature_c=17.0)
    canvas.avatar.outfit = "focus"
    canvas.particles.emit_mood_burst("heart", head_c.x(), head_c.y(), count=6)
    img_rain = canvas.render_to_image(1280, 720)
    assert not img_rain.isNull()
    # Garante que os dois frames são visualmente diferentes
    assert img_sunset.pixelColor(200, 120) != img_rain.pixelColor(200, 120)


def test_avatar_crossfade_and_sprite_resolution(tmp_path):
    _ensure_qapp()
    from PySide6.QtGui import QColor, QImage

    sdir = tmp_path / "sprites"
    sdir.mkdir()
    for name, color in (("casual.png", QColor(100, 150, 255, 255)), ("casual_shy.png", QColor(255, 120, 180, 255)), ("focus.png", QColor(80, 220, 180, 255))):
        img = QImage(64, 96, QImage.Format_ARGB32)
        img.fill(color)
        img.save(str(sdir / name))

    mira = load_persona("mira")
    canvas = WallpaperCanvas(mira, sprite_dirs=[sdir], render_style="portrait")
    assert canvas.avatar.available_sprite_keys() == {"casual", "casual_shy", "focus"}

    # Render inicial em calm -> escolhe casual
    canvas.emotion = EmotionState(mood="calm", label="Serena")
    canvas.render_to_image(320, 240)
    assert canvas.avatar._current_sprite_key == "casual"

    # Muda para shy -> inicia crossfade para casual_shy
    canvas.emotion = EmotionState(mood="shy", label="Corada", blush=0.8)
    canvas.render_to_image(320, 240)
    assert canvas.avatar._current_sprite_key == "casual_shy"
    assert canvas.avatar._sprite_fade_t < 1.0

    # Avança animação -> conclui crossfade
    for _ in range(25):
        canvas.step_animation(0.04)
    assert canvas.avatar._sprite_fade_t == 1.0

    # Troca traje para focus -> escolhe focus
    canvas.avatar.outfit = "focus"
    canvas.render_to_image(320, 240)
    assert canvas.avatar._current_sprite_key == "focus"


def test_world_sprite_locomotion_emotes_and_stage(tmp_path):
    _ensure_qapp()
    from PySide6.QtGui import QColor, QImage

    sdir = tmp_path / "world_sprites"
    sdir.mkdir()
    for name, color in (("sprite_idle.png", QColor(90, 140, 255, 255)), ("sprite_walk1.png", QColor(120, 200, 255, 255)), ("sprite_sit.png", QColor(200, 150, 255, 255))):
        img = QImage(64, 96, QImage.Format_ARGB32)
        img.fill(color)
        img.save(str(sdir / name))

    mira = load_persona("mira")
    canvas = WallpaperCanvas(mira, sprite_dirs=[sdir], render_style="world_sprite")
    assert canvas.avatar.has_world_sprites()

    # Chama para caminhar até a escrivaninha
    hs = canvas.scene.stage.hotspots["desk"]
    canvas.avatar.walk_to(hs.x, hs.y, arrive_action="sit_work")
    canvas.avatar.show_emote("heart")
    assert canvas.avatar.action == "walk"

    # Simula caminhada até chegar
    for _ in range(90):
        canvas.step_animation(0.05)
    assert canvas.avatar.action == "sit_work"
    assert abs(canvas.avatar.pos_x - hs.x) < 0.02

    # Renderiza sob chuva (ativa guarda-chuva + ondas no piso + reflexo molhado sem erros)
    canvas.weather = WeatherState(condition="rain", intensity=0.9)
    img = canvas.render_to_image(640, 360)
    assert not img.isNull()
    assert canvas.avatar._current_sprite_key == "sprite_sit"


def test_trim_sprite_pixmap_removes_bottom_padding():
    _ensure_qapp()
    from PySide6.QtGui import QColor, QImage, QPixmap
    from iawallpaper.render.avatar import trim_sprite_pixmap

    img = QImage(100, 120, QImage.Format_RGBA8888)
    img.fill(QColor(0, 0, 0, 0))
    for y in range(20, 80):
        for x in range(30, 70):
            img.setPixelColor(x, y, QColor(200, 120, 240, 255))
    trimmed = trim_sprite_pixmap(QPixmap.fromImage(img))
    # Altura deve terminar exatamente em y=79 (sem os 40px transparentes abaixo dos pés!)
    assert trimmed.height() <= 63
    assert trimmed.width() <= 46
