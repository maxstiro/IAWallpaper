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


def test_character_skeleton_poses_and_ground_pinning():
    from iawallpaper.render.skeleton import CharacterSkeleton

    skel = CharacterSkeleton()

    # 1. Caminhada: auto-aterramento exato em y == 0.0 e joelhos dobrando para trás
    max_shin_bend = 0.0
    for step in range(40):
        bones = skel.update(dt=0.05, action="walk", walk_phase=step * 0.35, action_timer=step * 0.05)
        lowest_foot = max(bones["shin_l"].end_y, bones["shin_r"].end_y)
        assert abs(lowest_foot) < 1e-5
        max_shin_bend = max(max_shin_bend, abs(skel.pose.shin_l), abs(skel.pose.shin_r))
    assert max_shin_bend > 18.0

    # 2. Aceno: mão direita sobe acima da linha do peito/pescoço
    for step in range(30):
        bones = skel.update(dt=0.05, action="wave", walk_phase=0.0, action_timer=step * 0.05)
    assert bones["forearm_r"].end_y < bones["neck"].y

    # 3. Sentada trabalhando: coxas dobram fortemente para frente
    for step in range(30):
        skel.update(dt=0.05, action="sit_work", walk_phase=0.0, action_timer=step * 0.05)
    assert skel.pose.thigh_l > 45.0
    assert skel.pose.shin_l < -45.0


def test_auto_rigger_cuts_synthetic_apose_and_renders(tmp_path):
    _ensure_qapp()
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
    from iawallpaper.render.rig_cutter import build_rig_from_apose

    # Desenha uma silhueta sintética limpa em A-pose (cabeça, tronco, braços afastados, pernas separadas)
    img = QImage(240, 420, QImage.Format_RGBA8888)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(235, 200, 220, 255))
    # Cabeça + pescoço
    p.drawEllipse(QPointF(120, 46), 24, 28)
    p.drawRect(112, 70, 16, 22)
    # Tronco
    p.drawRoundedRect(92, 92, 56, 118, 12, 12)
    # Braços afastados em A-pose (com vão transparente claro entre braço e cintura!)
    p.setPen(QPen(QColor(235, 200, 220, 255), 16, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(92, 102), QPointF(42, 222))
    p.drawLine(QPointF(148, 102), QPointF(198, 222))
    # Pernas separadas até os pés (y=404)
    p.setPen(QPen(QColor(180, 160, 230, 255), 22, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(104, 208), QPointF(96, 404))
    p.drawLine(QPointF(136, 208), QPointF(144, 404))
    p.end()

    rig = build_rig_from_apose(QPixmap.fromImage(img))
    assert rig is not None
    expected = {"head", "torso", "upper_arm_l", "forearm_l", "upper_arm_r", "forearm_r", "thigh_l", "shin_l", "thigh_r", "shin_r"}
    assert expected.issubset(set(rig.parts.keys()))

    # Salva como rig_base.png e valida renderização esquelética completa no WallpaperCanvas
    sdir = tmp_path / "rig_persona"
    sdir.mkdir()
    img.save(str(sdir / "rig_base.png"))

    mira = load_persona("mira")
    canvas = WallpaperCanvas(mira, sprite_dirs=[sdir], render_style="world_sprite")
    assert canvas.avatar.has_skeletal_rig()

    for act in ("walk", "wave", "stretch", "sit_work"):
        canvas.avatar.trigger_action(act)
        canvas.weather = WeatherState(condition="rain" if act == "walk" else "clear", intensity=0.8)
        for _ in range(10):
            canvas.step_animation(0.04)
        frame = canvas.render_to_image(640, 360)
        assert not frame.isNull()
        assert not canvas.avatar.head_rect.isEmpty()


def test_animated_sprite_clip_webp_playback_and_crossfade(tmp_path):
    _ensure_qapp()
    from PIL import Image, ImageDraw
    from iawallpaper.render.sprite_clip import load_sprite_clip

    # Gera um clipe RGBA animado sintético em WEBP (6 frames com movimento visível)
    cdir = tmp_path / "clips_persona"
    cdir.mkdir()
    for clip_name, base_rgb in (("clip_idle.webp", (110, 170, 255)), ("clip_wave.webp", (255, 130, 195))):
        frames = []
        for i in range(6):
            im = Image.new("RGBA", (120, 180), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            # Corpo + pés constantes em y=160 e braço subindo nos frames
            d.ellipse([42, 24, 78, 60], fill=(*base_rgb, 255))
            d.rectangle([40, 62, 80, 160], fill=(*base_rgb, 255))
            d.line([(80, 75), (105, 75 - i * 8)], fill=(255, 220, 230, 255), width=8)
            frames.append(im)
        frames[0].save(cdir / clip_name, save_all=True, append_images=frames[1:], duration=83, loop=0)

    clip = load_sprite_clip(cdir / "clip_wave.webp")
    assert clip is not None
    assert len(clip.frames) == 6
    assert clip.height <= 145  # recortado na sola dos pés (remove os 20px transparentes inferiores!)

    mira = load_persona("mira")
    canvas = WallpaperCanvas(mira, sprite_dirs=[cdir], render_style="world_sprite")
    assert canvas.avatar.has_animated_clips()
    assert {"clip_idle", "clip_wave"}.issubset(canvas.avatar.available_clip_keys())

    canvas.avatar.trigger_action("idle")
    canvas.render_to_image(480, 270)
    assert canvas.avatar._current_clip_key == "clip_idle"

    # Alterna para wave -> ativa crossfade e aura mágica no piso
    canvas.avatar.trigger_action("wave")
    canvas.render_to_image(480, 270)
    assert canvas.avatar._current_clip_key == "clip_wave"
    assert canvas.avatar._clip_fade_t < 1.0
    for _ in range(15):
        canvas.step_animation(0.04)
    assert canvas.avatar._clip_fade_t == 1.0
    out = canvas.render_to_image(480, 270)
    assert not out.isNull()


def test_directional_walk_facing_selects_side_back_front(tmp_path):
    _ensure_qapp()
    from PIL import Image, ImageDraw

    cdir = tmp_path / "dir_clips"
    cdir.mkdir()
    for clip_name in ("clip_idle.webp", "clip_walk.webp", "clip_walk_side.webp", "clip_walk_back.webp"):
        im = Image.new("RGBA", (96, 140), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle([28, 20, 68, 130], fill=(160, 190, 255, 255))
        im.save(cdir / clip_name, save_all=True, append_images=[im.copy()], duration=83, loop=0)

    mira = load_persona("mira")
    canvas = WallpaperCanvas(mira, sprite_dirs=[cdir], render_style="world_sprite")

    # 1. Caminhando para a direita -> move_dir == "side", facing == +1, usa clip_walk_side
    canvas.avatar.pos_x, canvas.avatar.pos_y = 0.35, 0.88
    canvas.avatar.walk_to(0.70, 0.88)
    canvas.step_animation(0.05)
    canvas.render_to_image(480, 270)
    assert canvas.avatar.move_dir == "side"
    assert canvas.avatar.facing == 1
    assert canvas.avatar._current_clip_key == "clip_walk_side"

    # 2. Caminhando para a esquerda -> move_dir == "side", facing == -1
    canvas.avatar.walk_to(0.28, 0.88)
    canvas.step_animation(0.05)
    canvas.render_to_image(480, 270)
    assert canvas.avatar.move_dir == "side"
    assert canvas.avatar.facing == -1
    assert canvas.avatar._current_clip_key == "clip_walk_side"

    # 3. Caminhando para o fundo (em direção à árvore) -> move_dir == "back", usa clip_walk_back
    canvas.avatar.pos_x, canvas.avatar.pos_y = 0.54, 0.90
    canvas.avatar.walk_to(0.54, 0.71)
    canvas.step_animation(0.05)
    canvas.render_to_image(480, 270)
    assert canvas.avatar.move_dir == "back"
    assert canvas.avatar._current_clip_key == "clip_walk_back"

    # 4. Caminhando para frente (em direção à câmera) -> move_dir == "front", usa clip_walk
    canvas.avatar.pos_x, canvas.avatar.pos_y = 0.54, 0.72
    canvas.avatar.walk_to(0.54, 0.92)
    canvas.step_animation(0.05)
    canvas.render_to_image(480, 270)
    assert canvas.avatar.move_dir == "front"
    assert canvas.avatar._current_clip_key == "clip_walk"


def test_vrm_3d_engine_loads_animates_360_and_renders():
    _ensure_qapp()
    from iawallpaper.paths import Paths

    paths = Paths()
    vrm_file = paths.resolve_vrm_model()
    if vrm_file is None:
        return  # Ambiente CI sem arquivo .vrm local (fallback permanece coberto pelos demais testes)

    mira = load_persona("mira")
    canvas = WallpaperCanvas(mira, render_style="vrm_3d", vrm_path=vrm_file)
    assert canvas.avatar.has_vrm_3d()

    # Caminha para a direita -> yaw gira para ~+90°
    canvas.avatar.pos_x, canvas.avatar.pos_y = 0.35, 0.88
    canvas.avatar.walk_to(0.75, 0.88)
    for _ in range(20):
        canvas.step_animation(0.05)
    assert 40.0 < canvas.avatar._vrm_animator.yaw_deg < 140.0

    # Acena com humor feliz -> expressão facial 'happy' ativa e frame RGBA renderizado sem erros
    canvas.emotion = EmotionState(mood="happy", label="Radiante", valence=0.9)
    canvas.avatar.trigger_action("wave")
    for _ in range(12):
        canvas.step_animation(0.05)
    assert canvas.avatar._vrm_animator.expr_weights.get("happy", 0.0) > 0.4
    img = canvas.render_to_image(640, 360)
    assert not img.isNull()
    assert not canvas.avatar.head_rect.isEmpty()


def test_dungeon_squad_pixel_art_3d_outfits_and_360():
    _ensure_qapp()
    from pathlib import Path

    mira = load_persona("mira")
    canvas = WallpaperCanvas(mira, render_style="vrm_3d", vrm_path=Path("elfa_loira"))
    assert canvas.avatar.has_vrm_3d()
    assert canvas.avatar._builtin_dungeon_squad is True
    assert canvas.avatar._vrm_renderer.pixel_art is False

    # Valida renderização HD dos 4 arquétipos base (Elfa Loira, Humana Ruiva, Androide Rosa, Vampira)
    for aid in ("elfa_loira", "humana_ruiva", "androide_rosa", "vampira_negra"):
        assert canvas.avatar.set_vrm_model(aid) is True
        img = canvas.render_to_image(640, 360)
        assert not img.isNull()
        assert aid in canvas.avatar._vrm_model.name

    # Valida giro 360° suave caminhando para a direita
    canvas.avatar.set_vrm_model("elfa_loira")
    canvas.avatar.pos_x, canvas.avatar.pos_y = 0.35, 0.88
    canvas.avatar.walk_to(0.75, 0.88)
    for _ in range(18):
        canvas.step_animation(0.05)
    assert 40.0 < canvas.avatar._vrm_animator.yaw_deg < 140.0
    img_walk = canvas.render_to_image(640, 360)
    assert not img_walk.isNull()
