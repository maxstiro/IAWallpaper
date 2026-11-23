"""Gera um mosaico visual (showcase) mostrando expressões, trajes e horários do cenário da persona."""

import argparse
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QFontDatabase, QPixmap
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iawallpaper.core.emotion import EmotionState
from iawallpaper.core.persona import load_persona
from iawallpaper.paths import Paths
from iawallpaper.render.canvas import WallpaperCanvas
from iawallpaper.render.rig_cutter import build_rig_from_apose
from iawallpaper.sense.circadian import compute_circadian
from iawallpaper.sense.weather import WeatherState


def render_showcase(persona_id: str, scene_id: str, out_path: Path) -> Path:
    app = QApplication.instance() or QApplication([])
    for f in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"):
        if Path(f).exists():
            QFontDatabase.addApplicationFont(f)

    paths = Paths(base_dir=ROOT)
    persona = load_persona(persona_id, personas_dir=paths.personas_dir)
    canvas = WallpaperCanvas(
        persona,
        sprite_dirs=[paths.persona_assets(persona.id), paths.persona_generated_assets(persona.id)],
        scene_dirs=[paths.scene_assets(scene_id), paths.scene_generated_assets(scene_id)],
    )

    shots = [
        ("Dia · Foco (Oculos/Dev)", 10.5, "clear", "focus", "focused", "Concentrada", "Foco total no codigo!"),
        ("Por do Sol · Casual Feliz", 18.0, "clear", "casual", "happy", "Radiante", "O por do sol esta lindo!"),
        ("Chuva · Moletom Aconchegante", 16.0, "rain", "rainy", "shy", "Corada", "Chuva la fora e paz aqui..."),
        ("Noite · Pijama / Sonolenta", 23.5, "clear", "nightwear", "sleepy", "Sonolenta", "Ja esta tarde... Zzz"),
    ]

    tiles: list[Image.Image] = []
    tmp_dir = out_path.parent
    tmp_dir.mkdir(parents=True, exist_ok=True)

    for idx, (caption, hour, cond, outfit, mood, label, whisper) in enumerate(shots):
        canvas.circadian = compute_circadian(hour)
        canvas.weather = WeatherState(condition=cond, intensity=0.85 if cond != "clear" else 0.0, temperature_c=21.0)
        canvas.avatar.outfit = outfit
        canvas.emotion = EmotionState(mood=mood, label=label, valence=0.7, arousal=0.5, blush=0.7 if mood == "shy" else 0.2)
        canvas.asleep = False
        canvas.affinity = 58.0
        canvas.activity = "PROGRAMMING" if outfit == "focus" else "IDLE"
        canvas.scene.set_whisper(whisper, 1.0)
        # Primeiro render aciona o crossfade para o novo cenário/traje; depois avança 1.8s para concluir
        canvas.render_to_image(960, 540)
        for _ in range(36):
            canvas.step_animation(0.05)
        img = canvas.render_to_image(960, 540)
        tfile = tmp_dir / f"_tile_{idx}.png"
        img.save(str(tfile))
        with Image.open(tfile) as im:
            tiles.append(im.convert("RGB").copy())
        tfile.unlink(missing_ok=True)

    grid = Image.new("RGB", (1920, 1080), (10, 14, 24))
    positions = [(0, 0), (960, 0), (0, 540), (960, 540)]
    for tile, pos in zip(tiles, positions):
        grid.paste(tile, pos)

    # Divisória fina elegante entre os 4 painéis
    draw = ImageDraw.Draw(grid)
    draw.line([(960, 0), (960, 1080)], fill=(120, 175, 255), width=3)
    draw.line([(0, 540), (1920, 540)], fill=(120, 175, 255), width=3)
    grid.save(out_path, format="PNG")
    return out_path


def render_strip(persona_id: str, names: list[str], out_path: Path) -> Path:
    """Monta faixa visual lado a lado de sprites gerados para validar consistência de identidade."""
    paths = Paths(base_dir=ROOT)
    gdir = paths.persona_generated_assets(persona_id)
    imgs = []
    for n in names:
        p = gdir / f"{n}.png"
        if p.exists():
            with Image.open(p) as im:
                rgba = im.convert("RGBA").resize((360, 526), Image.Resampling.LANCZOS)
                bg = Image.new("RGBA", rgba.size, (20, 26, 46, 255))
                imgs.append((n, Image.alpha_composite(bg, rgba).convert("RGB")))
    if not imgs:
        raise FileNotFoundError(f"Nenhum sprite encontrado em {gdir}")
    strip = Image.new("RGB", (360 * len(imgs), 526), (16, 20, 36))
    draw = ImageDraw.Draw(strip)
    for i, (label, im) in enumerate(imgs):
        strip.paste(im, (i * 360, 0))
        draw.rectangle([i * 360 + 8, 8, i * 360 + 210, 34], fill=(12, 16, 30))
        draw.text((i * 360 + 16, 14), label, fill=(235, 245, 255))
        if i > 0:
            draw.line([(i * 360, 0), (i * 360, 526)], fill=(90, 140, 220), width=2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    strip.save(out_path, format="PNG")
    return out_path


def render_world_showcase(
    persona_id: str,
    scene_id: str,
    out_path: Path,
    render_style: str = "live2d_25d",
    vrm_name: str = "",
) -> Path:
    """Renderiza mosaico 2x2 no modo Mundo Vivo 2.5D (Motor 2.5D Live2D/Spine2D, 3D VRM ou Clipes Wan 2.2)."""
    app = QApplication.instance() or QApplication([])
    for f in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"):
        if Path(f).exists():
            QFontDatabase.addApplicationFont(f)

    paths = Paths(base_dir=ROOT)
    persona = load_persona(persona_id, personas_dir=paths.personas_dir)
    vrm_p = paths.resolve_vrm_model(vrm_name) if render_style == "vrm_3d" else None
    l2d_p = paths.resolve_live2d_rig(vrm_name or "elfa_loira") if render_style == "live2d_25d" else None
    canvas = WallpaperCanvas(
        persona,
        sprite_dirs=[paths.persona_assets(persona.id), paths.persona_generated_assets(persona.id)],
        scene_dirs=[paths.scene_assets(scene_id), paths.scene_generated_assets(scene_id)],
        render_style=render_style,
        vrm_path=vrm_p,
        live2d_dir=l2d_p,
    )
    canvas.avatar.vrm_dynamic_recolor = False  # preserva as cores nativas do VRM no showcase

    shots = [
        (10.5, "clear", "overlook", "idle", "base", "happy", "Radiante", "sparkle", "IDLE", "Manha ensolarada — Elfa Loira 2D (Motor Live2D/Spine2D)!"),
        (18.0, "clear", "lantern", "wave", "base", "affectionate", "Carinhosa", "heart", "IDLE", "Por do sol — Sorriso 2D real & aceno elastico!"),
        (16.0, "rain", "garden_l", "walk", "base", "cozy", "Aconchegada", "music", "MUSIC", "Chuva suave — Caminhada fluida & reflexo molhado!"),
        (23.5, "clear", "music_spot", "dance", "base", "happy", "Animada", "sparkle", "IDLE", "Noite magica — Danca Live2D sob a lua e vaga-lumes!"),
    ]

    tiles: list[Image.Image] = []
    tmp_dir = out_path.parent
    tmp_dir.mkdir(parents=True, exist_ok=True)

    for idx, (hour, cond, spot, act, outfit, mood, label, emote, activity, whisper) in enumerate(shots):
        canvas.circadian = compute_circadian(hour)
        canvas.weather = WeatherState(condition=cond, intensity=0.9 if cond != "clear" else 0.0, temperature_c=20.0)
        canvas.avatar.outfit = outfit
        canvas.emotion = EmotionState(mood=mood, label=label, valence=0.8, arousal=0.5, blush=0.4)
        canvas.asleep = act == "sleep"
        canvas.affinity = 65.0
        canvas.activity = activity

        hs = canvas.scene.stage.hotspots[spot]
        canvas.avatar.pos_x = hs.x
        canvas.avatar.pos_y = hs.y
        if act == "walk":
            canvas.avatar.target_x = min(0.84, hs.x + 0.14)
            canvas.avatar.target_y = hs.y + 0.03
            canvas.avatar.action = "walk"
            canvas.avatar.facing = 1
            canvas.scene.stage.spawn_footstep(hs.x - 0.02, hs.y, raining=(cond == "rain"))
        else:
            canvas.avatar.target_x = hs.x
            canvas.avatar.target_y = hs.y
            canvas.avatar.action = act
        canvas.avatar.show_emote(emote, duration=5.0)
        canvas.scene.set_whisper(whisper, 1.0)

        canvas.render_to_image(960, 540)
        for _ in range(36):
            canvas.step_animation(0.05)
        if act == "walk":
            canvas.avatar.pos_x = hs.x + 0.06
            canvas.avatar.target_x = hs.x + 0.22
            canvas.avatar.action = "walk"
            canvas.avatar.walk_phase = 1.15
            canvas.avatar.update(0.05, canvas.emotion, raining=(cond == "rain"))
        elif act in ("stretch", "dance"):
            canvas.avatar.action = act
            canvas.avatar.action_timer = 1.0
            for _ in range(12):
                canvas.avatar.update(0.05, canvas.emotion, raining=False)
        elif act == "wave":
            canvas.avatar.action = "wave"
            canvas.avatar.action_timer = 0.85
            for _ in range(12):
                canvas.avatar.update(0.05, canvas.emotion, raining=False)
        canvas.avatar.emote_life = 0.7
        # Posiciona no pico da pose animada do clipe para o frame estatico do mosaico
        if canvas.avatar.has_animated_clips():
            canvas.avatar._clip_time = 0.95 if act in ("wave", "dance") else 0.55
        img = canvas.render_to_image(960, 540)
        tfile = tmp_dir / f"_wtile_{idx}.png"
        img.save(str(tfile))
        with Image.open(tfile) as im:
            tiles.append(im.convert("RGB").copy())
        tfile.unlink(missing_ok=True)

    grid = Image.new("RGB", (1920, 1080), (10, 14, 24))
    for tile, pos in zip(tiles, [(0, 0), (960, 0), (0, 540), (960, 540)]):
        grid.paste(tile, pos)
    draw = ImageDraw.Draw(grid)
    draw.line([(960, 0), (960, 1080)], fill=(120, 175, 255), width=3)
    draw.line([(0, 540), (1920, 540)], fill=(120, 175, 255), width=3)
    grid.save(out_path, format="PNG")
    return out_path


def _qpixmap_to_pil(pm: QPixmap) -> Image.Image:
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    pm.save(buf, "PNG")
    import io
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


def render_rig_parts_sheet(persona_id: str, out_path: Path) -> Path:
    """Salva grade diagnóstica das 10 peças RGBA recortadas pelo AutoRigger com marcador de pivô."""
    app = QApplication.instance() or QApplication([])
    paths = Paths(base_dir=ROOT)
    gdir = paths.persona_generated_assets(persona_id)
    src = gdir / "rig_base.png"
    if not src.exists():
        raise FileNotFoundError(f"rig_base.png não encontrado em {gdir}")

    rig = build_rig_from_apose(QPixmap(str(src)))
    if rig is None:
        raise RuntimeError("AutoRigger falhou ao recortar rig_base.png")

    order = ["head", "torso", "upper_arm_l", "forearm_l", "upper_arm_r", "forearm_r", "thigh_l", "shin_l", "thigh_r", "shin_r"]
    cell_w, cell_h = 240, 280
    cols, rows = 5, 2
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (24, 30, 48))
    draw = ImageDraw.Draw(sheet)

    for idx, name in enumerate(order):
        r, c = divmod(idx, cols)
        ox, oy = c * cell_w, r * cell_h
        draw.rectangle([ox + 2, oy + 2, ox + cell_w - 3, oy + cell_h - 3], outline=(76, 98, 148), width=1)
        part = rig.parts.get(name)
        if part is not None:
            im = _qpixmap_to_pil(part.pixmap)
            sc = min((cell_w - 28) / max(im.width, 1), (cell_h - 52) / max(im.height, 1), 1.0)
            nw, nh = max(1, int(im.width * sc)), max(1, int(im.height * sc))
            resized = im.resize((nw, nh), Image.Resampling.LANCZOS)
            px = ox + (cell_w - nw) // 2
            py = oy + 34 + (cell_h - 44 - nh) // 2
            sheet.paste(resized, (px, py), resized)
            # Cruz vermelha no pivô da junta
            jx = int(px + part.pivot_x * sc)
            jy = int(py + part.pivot_y * sc)
            draw.line([(jx - 8, jy), (jx + 8, jy)], fill=(255, 70, 95), width=2)
            draw.line([(jx, jy - 8), (jx, jy + 8)], fill=(255, 70, 95), width=2)
            draw.text((ox + 10, oy + 10), f"{name} ({part.rest_angle:+.0f}d)", fill=(235, 245, 255))
        else:
            draw.text((ox + 10, oy + 10), f"{name} (MISSING)", fill=(255, 110, 110))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, format="PNG")
    return out_path


def render_animated_gif(
    persona_id: str,
    scene_id: str,
    out_path: Path,
    width: int = 720,
    height: int = 405,
    fps: int = 20,
    render_style: str = "live2d_25d",
    vrm_name: str = "",
) -> Path:
    """Renderiza GIF animado fluido em 20 FPS demonstrando motor Live2D/Spine2D, caminhada, cabelo fluido e aceno."""
    app = QApplication.instance() or QApplication([])
    for f in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"):
        if Path(f).exists():
            QFontDatabase.addApplicationFont(f)

    paths = Paths(base_dir=ROOT)
    persona = load_persona(persona_id, personas_dir=paths.personas_dir)
    vrm_p = paths.resolve_vrm_model(vrm_name) if render_style == "vrm_3d" else None
    l2d_p = paths.resolve_live2d_rig(vrm_name or "elfa_loira") if render_style == "live2d_25d" else None
    canvas = WallpaperCanvas(
        persona,
        sprite_dirs=[paths.persona_assets(persona.id), paths.persona_generated_assets(persona.id)],
        scene_dirs=[paths.scene_assets(scene_id), paths.scene_generated_assets(scene_id)],
        render_style=render_style,
        vrm_path=vrm_p,
        live2d_dir=l2d_p,
    )
    canvas.avatar.vrm_dynamic_recolor = False
    canvas.avatar.outfit = "base"

    canvas.circadian = compute_circadian(17.8)  # Golden hour cinematográfico na praça!
    canvas.weather = WeatherState(condition="clear", intensity=0.0, temperature_c=23.0, wind_speed=8.0)
    canvas.emotion = EmotionState(mood="happy", label="Radiante", valence=0.88, arousal=0.6, blush=0.35)
    canvas.asleep = False
    canvas.affinity = 78.0
    canvas.activity = "IDLE"

    # Demonstração completa: Direita -> Subindo de Costas -> Esquerda -> Aceno -> Dança 360° Tree of Savior!
    canvas.avatar.pos_x = 0.36
    canvas.avatar.pos_y = 0.90
    canvas.avatar.walk_to(0.68, 0.89, arrive_action="idle")
    canvas.scene.set_whisper("Passeando em Live2D 2.5D pela praca...", 1.0)
    canvas.render_to_image(width, height)
    for _ in range(20):
        canvas.step_animation(0.05)
    canvas.avatar.pos_x = 0.36
    canvas.avatar.pos_y = 0.90
    canvas.avatar.walk_to(0.68, 0.89, arrive_action="idle")
    canvas.avatar._clip_time = 0.0

    frames: list[Image.Image] = []
    dt = 1.0 / fps
    total_frames = int(fps * 8.0)  # 160 frames = 8 segundos fluidos @ 20 FPS

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_frame = out_path.parent / "_gif_frame.png"

    for i in range(total_frames):
        if i == int(fps * 1.9):
            canvas.avatar.walk_to(canvas.avatar.pos_x - 0.05, 0.72, arrive_action="idle")
            canvas.scene.set_whisper("Subindo os degraus (vista costas 2D)...", 1.0)
        elif i == int(fps * 3.4):
            canvas.avatar.walk_to(0.42, 0.85, arrive_action="wave")
            canvas.scene.set_whisper("Voltando para o centro da praca...", 1.0)
        elif i == int(fps * 5.0):
            canvas.avatar.target_x = canvas.avatar.pos_x
            canvas.avatar.target_y = canvas.avatar.pos_y
            canvas.avatar.trigger_action("wave")
            canvas.avatar.show_emote("heart", duration=1.8)
            canvas.scene.set_whisper("Oi! Piscar & sorriso 2D pintados a mao!", 1.0)
        elif i == int(fps * 6.4):
            canvas.avatar.trigger_action("dance")
            canvas.avatar.show_emote("sparkle", duration=2.0)
            canvas.scene.set_whisper("Danca elastica estilo Live2D / Spine2D!", 1.0)

        # Sub-steps de 25ms para física de mola e cabelo ultra suaves
        sub = 2
        for _ in range(sub):
            canvas.step_animation(dt / sub)

        qimg = canvas.render_to_image(width, height)
        qimg.save(str(tmp_frame))
        with Image.open(tmp_frame) as im:
            frames.append(im.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT))

    tmp_frame.unlink(missing_ok=True)
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=int(1000 / fps),
        loop=0,
        optimize=True,
    )
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--persona", default="mira")
    parser.add_argument("--scene", default="sky_sanctuary")
    parser.add_argument("--style", choices=("live2d_25d", "vrm_3d", "world_sprite"), default="live2d_25d")
    parser.add_argument("--vrm", default="elfa_loira", help="Arquétipo HD ('elfa_loira'|'humana_ruiva'|'androide_rosa'|'vampira_negra') ou caminho .vrm.")
    parser.add_argument("--mode", choices=("world", "scenes", "expressions", "outfits", "sprites", "rig_parts", "gif"), default="world")
    parser.add_argument("--out", default="showcase.png")
    args = parser.parse_args()
    if args.mode == "world":
        out = render_world_showcase(args.persona, args.scene, Path(args.out), render_style=args.style, vrm_name=args.vrm)
    elif args.mode == "rig_parts":
        out = render_rig_parts_sheet(args.persona, Path(args.out))
    elif args.mode == "gif":
        out = render_animated_gif(args.persona, args.scene, Path(args.out), render_style=args.style, vrm_name=args.vrm)
    elif args.mode == "sprites":
        out = render_strip(args.persona, ["rig_base", "sprite_idle", "sprite_walk1", "sprite_walk2", "sprite_sit", "sprite_happy"], Path(args.out))
    elif args.mode == "expressions":
        out = render_strip(args.persona, ["casual", "casual_happy", "casual_affectionate", "casual_shy", "casual_sleepy", "casual_pouty"], Path(args.out))
    elif args.mode == "outfits":
        out = render_strip(args.persona, ["casual", "focus", "rainy", "cozy", "nightwear", "starlight"], Path(args.out))
    else:
        out = render_showcase(args.persona, args.scene, Path(args.out))
    print("Showcase saved:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
