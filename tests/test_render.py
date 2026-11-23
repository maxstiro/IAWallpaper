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


def test_live2d_25d_gpu_mesh_engine(tmp_path):
    _ensure_qapp()
    from PIL import Image, ImageDraw

    # Cria sprite 2D full-body sintético + blink 1:1 + outfit modular 1:1 + vista costas
    rig_dir = tmp_path / "elfa_test"
    rig_dir.mkdir()
    base = Image.new("RGBA", (320, 480), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    # Cabelo longo loiro atrás
    d.ellipse([96, 18, 224, 150], fill=(246, 218, 134, 255))
    d.rectangle([94, 85, 226, 255], fill=(246, 218, 134, 255))
    # Orelhas élficas longas
    d.polygon([(112, 72), (50, 52), (108, 92)], fill=(238, 178, 142, 255))
    d.polygon([(208, 72), (270, 52), (212, 92)], fill=(238, 178, 142, 255))
    # Cabeça + pescoço + tronco curvilíneo
    d.ellipse([116, 36, 204, 128], fill=(238, 178, 142, 255))
    d.rectangle([146, 122, 174, 148], fill=(238, 178, 142, 255))
    d.ellipse([112, 146, 208, 268], fill=(238, 178, 142, 255))
    # Braços separados em A-pose
    d.line([(114, 158), (74, 282)], fill=(238, 178, 142, 255), width=22)
    d.line([(206, 158), (246, 282)], fill=(238, 178, 142, 255), width=22)
    # Pernas separadas até os pés
    d.line([(134, 260), (124, 466)], fill=(238, 178, 142, 255), width=32)
    d.line([(186, 260), (196, 466)], fill=(238, 178, 142, 255), width=32)
    base.save(rig_dir / "base.png")
    base.save(rig_dir / "base_blink.png")
    base.save(rig_dir / "base_happy.png")
    base.save(rig_dir / "base_back.png")

    outfit = Image.new("RGBA", (320, 480), (0, 0, 0, 0))
    ImageDraw.Draw(outfit).rectangle([118, 170, 202, 250], fill=(80, 120, 220, 220))
    outfit.save(rig_dir / "outfit_casual.png")

    mira = load_persona("mira")
    canvas = WallpaperCanvas(mira, render_style="live2d_25d", live2d_dir=rig_dir)
    assert canvas.avatar.has_live2d()
    assert len(canvas.avatar._live2d_renderer.front_mesh.indices) > 300

    for act, outfit_k in (("idle", "base"), ("walk", "casual"), ("wave", "base"), ("dance", "base")):
        canvas.avatar.outfit = outfit_k
        if act == "walk":
            canvas.avatar.walk_to(0.75, 0.85)
        else:
            canvas.avatar.target_x, canvas.avatar.target_y = canvas.avatar.pos_x, canvas.avatar.pos_y
            canvas.avatar.trigger_action(act)
        for _ in range(8):
            canvas.step_animation(0.05)
        frame = canvas.render_to_image(640, 360)
        assert not frame.isNull()
        assert not canvas.avatar.head_rect.isEmpty()


def test_character_pack_8dir_mirroring_reversal_and_step_sync(tmp_path):
    _ensure_qapp()
    import json
    from PIL import Image, ImageDraw
    from iawallpaper.render.character_pack import load_character_pack, vector_to_compass8

    # 1. Bússola 8 direções (compensando 16:9)
    assert vector_to_compass8(0.0, 1.0) == "S"
    assert vector_to_compass8(0.56, 1.0) == "SE"
    assert vector_to_compass8(1.0, 0.0) == "L"
    assert vector_to_compass8(0.56, -1.0) == "NE"
    assert vector_to_compass8(0.0, -1.0) == "N"
    assert vector_to_compass8(-0.56, -1.0) == "NO"
    assert vector_to_compass8(-1.0, 0.0) == "O"
    assert vector_to_compass8(-0.56, 1.0) == "SO"

    # 2. Monta CharacterPack sintético da Arya
    char_dir = tmp_path / "arya"
    outfit_dir = char_dir / "outfits" / "base"
    clips_dir = outfit_dir / "clips"
    clips_dir.mkdir(parents=True)
    (char_dir / "portraits").mkdir(parents=True)

    (char_dir / "character.json").write_text(
        json.dumps({"id": "arya", "name": "Arya", "default_outfit": "base"}), encoding="utf-8"
    )
    (outfit_dir / "manifest.json").write_text(
        json.dumps({
            "character_id": "arya",
            "outfit_id": "base",
            "default_stride_ratio": 0.62,
            "clips": {
                "idle_SE": {"tier": 0, "fps": 16.0, "frames": 4, "stride_ratio": 0.0, "loop": True, "status": "ready"},
                "walk_SE": {"tier": 0, "fps": 16.0, "frames": 4, "stride_ratio": 0.64, "loop": True, "status": "ready"},
                "walk_L": {"tier": 1, "fps": 16.0, "frames": 4, "stride_ratio": 0.72, "loop": True, "status": "ready"},
                "walk_NE": {"tier": 0, "fps": 16.0, "frames": 4, "stride_ratio": 0.60, "loop": True, "status": "ready"},
                "walk_N": {"tier": 1, "fps": 16.0, "frames": 4, "stride_ratio": 0.56, "loop": True, "status": "ready"},
                "sit_floor_SE": {"tier": 1, "fps": 16.0, "frames": 4, "stride_ratio": 0.0, "loop": True, "status": "ready"},
                "trans_sit_floor": {"tier": 2, "fps": 16.0, "frames": 4, "stride_ratio": 0.0, "loop": False, "status": "ready"},
            },
        }),
        encoding="utf-8",
    )

    for cname in ("clip_idle_SE.webp", "clip_walk_SE.webp", "clip_walk_L.webp", "clip_walk_NE.webp", "clip_walk_N.webp", "clip_sit_floor_SE.webp", "clip_trans_sit_floor.webp"):
        frames = []
        for i in range(4):
            im = Image.new("RGBA", (96, 140), (0, 0, 0, 0))
            ImageDraw.Draw(im).rectangle([24, 16 + i * 2, 72, 130], fill=(220 - i * 20, 175, 110 + i * 20, 255))
            frames.append(im)
        frames[0].save(clips_dir / cname, save_all=True, append_images=frames[1:], duration=62, loop=0)

    p_img = Image.new("RGBA", (64, 64), (240, 200, 140, 255))
    p_img.save(char_dir / "portraits" / "happy.png")

    pack = load_character_pack(char_dir, "base")
    assert pack is not None
    assert pack.name == "Arya"
    assert pack.portrait_for_mood("happy") is not None

    # Espelhamento 8->5 canônico + fallback
    assert (pack.resolve_action("walk", "SO").key, pack.resolve_action("walk", "SO").flip_x) == ("walk_SE", True)
    assert (pack.resolve_action("walk", "O").key, pack.resolve_action("walk", "O").flip_x) == ("walk_L", True)
    assert (pack.resolve_action("walk", "NO").key, pack.resolve_action("walk", "NO").flip_x) == ("walk_NE", True)
    assert (pack.resolve_action("walk", "N").key, pack.resolve_action("walk", "N").flip_x) == ("walk_N", False)
    assert pack.resolve_action("walk", "S").key == "walk_SE"  # fallback automático sem walk_S

    # Reaproveitamento de `run` acelerando `walk` em 1.45x
    run_res = pack.resolve_action("run", "O")
    assert run_res.key == "walk_L" and run_res.flip_x is True and run_res.speed_mul == 1.45

    # Transição normal e reversa (0s de geração extra para levantar!)
    tr_down = pack.resolve_transition("idle", "sit_floor", "SE")
    tr_up = pack.resolve_transition("sit_floor", "idle", "SE")
    assert tr_down is not None and tr_down.reverse is False and tr_down.loop is False
    assert tr_up is not None and tr_up.reverse is True and tr_up.loop is False
    assert tr_down.clip.frame_at(0.0, reverse=False, loop=False).toImage() == tr_up.clip.frame_at(9.0, reverse=True, loop=False).toImage()

    # Velocidade sincronizada com profundidade
    v_near = pack.synced_walk_speed_norm(pack.resolve_action("walk", "L"), depth_scale=1.0)
    v_far = pack.synced_walk_speed_norm(pack.resolve_action("walk", "L"), depth_scale=0.6)
    assert v_near > v_far > 0.0

    # Integração completa no WallpaperCanvas (8 direções + corrida + transição reversa)
    mira = load_persona("mira")
    canvas = WallpaperCanvas(mira, render_style="world_sprite", character_dir=char_dir)
    assert canvas.avatar.has_character_pack()

    canvas.avatar.pos_x, canvas.avatar.pos_y = 0.50, 0.90
    canvas.avatar.walk_to(0.50, 0.72)
    canvas.step_animation(0.05)
    img_n = canvas.render_to_image(480, 270)
    assert not img_n.isNull()
    assert canvas.avatar.compass_dir == "N"
    assert canvas.avatar._current_pack_sig == ("walk_N", False, False)

    canvas.avatar.walk_to(0.25, 0.72, run=True)
    canvas.step_animation(0.05)
    canvas.render_to_image(480, 270)
    assert canvas.avatar.action == "run"
    assert canvas.avatar.compass_dir == "O"
    assert canvas.avatar._current_pack_sig == ("walk_L", True, False)

    # Sentar e levantar usando a mesma transição em sentido direto e reverso!
    canvas.avatar.target_x, canvas.avatar.target_y = canvas.avatar.pos_x, canvas.avatar.pos_y
    canvas.avatar.action = "idle"
    canvas.avatar.trigger_action("sit_floor")
    assert canvas.avatar._trans_resolved is not None and canvas.avatar._trans_resolved.reverse is False
    for _ in range(12):
        canvas.step_animation(0.05)
    assert canvas.avatar.action == "sit_floor" and canvas.avatar._trans_resolved is None

    canvas.avatar.trigger_action("idle")
    assert canvas.avatar._trans_resolved is not None and canvas.avatar._trans_resolved.reverse is True
    for _ in range(12):
        canvas.step_animation(0.05)
    assert canvas.avatar.action == "idle" and canvas.avatar._trans_resolved is None
    assert not canvas.render_to_image(480, 270).isNull()
