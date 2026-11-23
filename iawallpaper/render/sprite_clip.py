"""SPRITE CLIP — Carregador e reprodutor de clipes RGBA animados quadro-a-quadro (WEBP/GIF via Wan 2.2 + isnet-anime).

Garante animação fluida estilo Tree of Savior / Ragnarok Online (zero efeito marionete!):
- Carrega todos os frames RGBA de arquivos `.webp` ou `.gif` via Pillow.
- Calcula uma bounding box unificada entre todos os frames do clipe com trava exata na sola dos pés
  (linha inferior do pé mais baixo = base do recorte), eliminando flutuação e jitter vertical.
- Reproduz em loop contínuo suave com suporte a crossfade entre clipes e cache de tingimento atmosférico.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtGui import QImage, QPixmap


@dataclass
class SpriteClip:
    name: str
    frames: list[QPixmap]
    fps: float = 12.0
    width: int = 0
    height: int = 0

    @property
    def duration(self) -> float:
        return len(self.frames) / max(self.fps, 1.0)

    def frame_at(self, time_s: float) -> QPixmap:
        if not self.frames:
            return QPixmap()
        idx = int(time_s * self.fps) % len(self.frames)
        return self.frames[idx]


def _pil_rgba_to_qpixmap(im: Image.Image) -> QPixmap:
    rgba = im.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimg = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimg)


def load_sprite_clip(path: Path, alpha_threshold: int = 16) -> SpriteClip | None:
    """Carrega um clipe animado RGBA (`.webp` ou `.gif`) e recorta todos os frames com linha de pés unificada."""
    if not path.exists():
        return None
    raw_frames: list[np.ndarray] = []
    durations_ms: list[int] = []

    try:
        with Image.open(path) as im:
            n_frames = getattr(im, "n_frames", 1)
            for i in range(n_frames):
                im.seek(i)
                arr = np.asarray(im.convert("RGBA"), dtype=np.uint8)
                raw_frames.append(arr.copy())
                dur = im.info.get("duration", 83)
                if isinstance(dur, (int, float)) and dur > 10:
                    durations_ms.append(int(dur))
    except Exception:
        return None

    if not raw_frames:
        return None

    h, w, _ = raw_frames[0].shape
    # Bounding box unificada entre todos os frames para manter posição estável e pés ancorados na base!
    min_x, max_x = w - 1, 0
    min_y, max_y = h - 1, 0
    found_any = False
    for arr in raw_frames:
        ys, xs = np.where(arr[:, :, 3] > alpha_threshold)
        if len(xs) > 0:
            found_any = True
            min_x = min(min_x, int(xs.min()))
            max_x = max(max_x, int(xs.max()))
            min_y = min(min_y, int(ys.min()))
            max_y = max(max_y, int(ys.max()))

    if not found_any:
        return None

    x0 = max(0, min_x - 3)
    x1 = min(w - 1, max_x + 3)
    y0 = max(0, min_y - 3)
    y1 = min(h - 1, max_y)  # 0px abaixo da sola dos pés!

    qframes: list[QPixmap] = []
    for arr in raw_frames:
        crop = arr[y0 : y1 + 1, x0 : x1 + 1]
        qframes.append(_pil_rgba_to_qpixmap(Image.fromarray(crop, mode="RGBA")))

    avg_ms = sum(durations_ms) / len(durations_ms) if durations_ms else 83.3
    fps = max(6.0, min(30.0, 1000.0 / max(avg_ms, 20.0)))
    return SpriteClip(
        name=path.stem.lower(),
        frames=qframes,
        fps=fps,
        width=x1 - x0 + 1,
        height=y1 - y0 + 1,
    )


def load_clips_from_dirs(dirs: list[Path]) -> dict[str, SpriteClip]:
    """Carrega todos os clipes animados `clip_*.webp` e `clip_*.gif` das pastas de assets da persona."""
    clips: dict[str, SpriteClip] = {}
    for folder in dirs:
        if not folder.exists():
            continue
        for ext in ("*.webp", "*.gif"):
            for fp in sorted(folder.glob(ext)):
                stem = fp.stem.lower()
                if not stem.startswith("clip_"):
                    continue
                clip = load_sprite_clip(fp)
                if clip is not None and clip.frames:
                    clips[stem] = clip
    return clips
