"""Gera um mosaico visual (showcase) mostrando expressões, trajes e horários do cenário da persona."""

import argparse
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iawallpaper.core.emotion import EmotionState
from iawallpaper.core.persona import load_persona
from iawallpaper.paths import Paths
from iawallpaper.render.canvas import WallpaperCanvas
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--persona", default="mira")
    parser.add_argument("--scene", default="sky_sanctuary")
    parser.add_argument("--mode", choices=("scenes", "expressions", "outfits"), default="scenes")
    parser.add_argument("--out", default="showcase.png")
    args = parser.parse_args()
    if args.mode == "expressions":
        out = render_strip(args.persona, ["casual", "casual_happy", "casual_affectionate", "casual_shy", "casual_sleepy", "casual_pouty"], Path(args.out))
    elif args.mode == "outfits":
        out = render_strip(args.persona, ["casual", "focus", "rainy", "cozy", "nightwear", "starlight"], Path(args.out))
    else:
        out = render_showcase(args.persona, args.scene, Path(args.out))
    print("Showcase saved:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
