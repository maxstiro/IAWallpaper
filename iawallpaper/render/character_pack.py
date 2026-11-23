"""CHARACTER PACK — Motor 8-Direções, Grafo de Poses-Âncora, Reversão Temporal e Sincronia Matemática de Passos.

Implementa a arquitetura Wan 2.2 de máximo reaproveitamento (`Milestone 18`):
1. **8 Direções via 5 Ângulos Canônicos Espelhados**:
   - Canônicos: `"S"`, `"SE"`, `"L"`, `"NE"`, `"N"` (frente, diagonal frente-dir, perfil dir, diagonal costas-dir, costas).
   - Espelhados em 0 ms: `"SO"` = `SE` espelhado, `"O"` = `L` espelhado, `"NO"` = `NE` espelhado.
   - Fallback inteligente por Tier (no Tier 0, apenas `SE` + `NE` já cobrem todas as 8 direções!).
2. **Reversão Temporal de Transições (`play_reverse=True`)**:
   - `idle -> sit_floor` usa `trans_sit_floor` normal; `sit_floor -> idle` usa `trans_sit_floor` **reverso** (0s de geração!).
   - `idle -> sit_chair` usa `trans_sit_chair` normal; `sit_chair -> idle` usa `trans_sit_chair` **reverso**.
   - `sit_floor -> lie` usa `trans_lie` normal; `lie -> sit_floor` usa `trans_lie` **reverso**.
3. **Sincronia Matemática de Passos (`stride_ratio`)**:
   - Acopla a velocidade real de deslocamento na tela ao comprimento da passada do clipe (`stride_ratio * avatar_h * depth / cycle_s`),
     modulando `clip_fps` conforme aceleração/desaceleração -> **ZERO patinação dos pés!**
4. **Expressões Desacopladas (`portraits/`)**:
   - Carrega os 6 retratos estáticos 2D (`happy`, `shy`, `pouty`, `sleepy`, `focused`, `affectionate`) sem multiplicar vídeos.
"""

from dataclasses import dataclass, field
import json
import math
from pathlib import Path

from PySide6.QtGui import QPixmap

from .sprite_clip import SpriteClip, load_sprite_clip

# As 8 direções cardeais e colaterais oficiais
COMPASS_8: tuple[str, ...] = ("S", "SE", "L", "NE", "N", "NO", "O", "SO")

# Mapeamento: Direção Real (8) -> (Ângulo Canônico (5), precisa_espelhar_horizontal)
DIRECTION_TO_CANONICAL: dict[str, tuple[str, bool]] = {
    "S":  ("S",  False),
    "SE": ("SE", False),
    "L":  ("L",  False),
    "NE": ("NE", False),
    "N":  ("N",  False),
    "NO": ("NE", True),
    "O":  ("L",  True),
    "SO": ("SE", True),
}

# Fallback ordenado por ângulo canônico caso os clipes do Tier 1/2 ainda estejam assando em background
CANONICAL_FALLBACKS: dict[str, tuple[str, ...]] = {
    "S":  ("S", "SE", "L", "NE", "N"),
    "SE": ("SE", "L", "S", "NE", "N"),
    "L":  ("L", "SE", "NE", "S", "N"),
    "NE": ("NE", "N", "L", "SE", "S"),
    "N":  ("N", "NE", "L", "SE", "S"),
}

# Mapa de transições do Grafo de Poses: (estado_origem, estado_destino) -> (clip_key, reverse)
POSE_TRANSITIONS: dict[tuple[str, str], tuple[str, bool]] = {
    ("idle",      "sit_floor"): ("trans_sit_floor", False),
    ("sit_floor", "idle"):      ("trans_sit_floor", True),
    ("idle",      "sit_chair"): ("trans_sit_chair", False),
    ("sit_chair", "idle"):      ("trans_sit_chair", True),
    ("idle",      "sit_work"):  ("trans_sit_chair", False),
    ("sit_work",  "idle"):      ("trans_sit_chair", True),
    ("sit_floor", "lie"):       ("trans_lie",       False),
    ("lie",       "sit_floor"): ("trans_lie",       True),
    ("idle",      "lie"):       ("trans_lie",       False),
    ("lie",       "idle"):      ("trans_lie",       True),
    ("idle",      "sleep"):     ("trans_lie",       False),
    ("sleep",     "idle"):      ("trans_lie",       True),
}


def vector_to_compass8(dx: float, dy: float, aspect_x: float = 1.77) -> str:
    """Converte vetor de movimento na tela (+dx = Leste/direita, +dy = Sul/câmera, -dy = Norte/fundo) na direção 8-vias exata."""
    if math.hypot(dx, dy) < 1e-6:
        return "S"
    vx = dx * aspect_x
    vy = dy
    # atan2(vx, vy): 0° = Sul (+y), +45° = SE, +90° = Leste (+x), +135° = NE, ±180° = Norte (-y), -135° = NO, -90° = Oeste (-x), -45° = SO
    ang = (math.degrees(math.atan2(vx, vy)) + 360.0) % 360.0
    sector = int(((ang + 22.5) % 360.0) // 45.0)
    return COMPASS_8[sector]


@dataclass(frozen=True)
class ClipMeta:
    key: str
    tier: int = 0
    fps: float = 16.0
    frames: int = 25
    stride_ratio: float = 0.0   # fração da altura do personagem percorrida por ciclo completo (0 = parado no lugar!)
    loop: bool = True


# Clipes de postura/transição cujo `height_scale` deve acompanhar exatamente a proporção de recorte (`clip.height / ref_stand_h`)
_PROPORTIONAL_HEIGHT_KEYS: frozenset[str] = frozenset({
    "sit_floor_SE",
    "sit_chair_SE",
    "lie_SE",
    "trans_sit_floor",
    "trans_sit_chair",
    "trans_lie",
})

# Fallback caso um pack sintético (ex: teste unitário) tenha todos os clipes com altura idêntica
CLIP_HEIGHT_SCALE: dict[str, float] = {
    "sit_floor_SE": 0.78,
    "sit_chair_SE": 0.90,
    "lie_SE":       0.70,
    "trans_lie":    0.78,
}


@dataclass(frozen=True)
class ResolvedClip:
    clip: SpriteClip
    key: str
    flip_x: bool = False
    reverse: bool = False
    speed_mul: float = 1.0
    stride_ratio: float = 0.0
    loop: bool = True
    height_scale: float = 1.0


@dataclass
class CharacterPack:
    """Pacote completo de uma personagem + outfit carregado de `assets/generated/characters/<char>/outfits/<outfit>/`."""
    character_id: str
    name: str
    outfit_id: str
    root_dir: Path
    clips: dict[str, SpriteClip] = field(default_factory=dict)
    clip_meta: dict[str, ClipMeta] = field(default_factory=dict)
    portraits: dict[str, QPixmap] = field(default_factory=dict)
    default_stride_ratio: float = 0.62

    def has_clips(self) -> bool:
        return bool(self.clips)

    def available_keys(self) -> set[str]:
        return set(self.clips.keys())

    def _ref_standing_height(self) -> float:
        """Altura de recorte de referência (em pixels) da personagem em pé na câmera 448×640 do pack."""
        # Prioriza clipes assados na mesma câmera do CharacterPipeline (garante emenda 0.0px em trans_sit/trans_lie!)
        samples = [
            float(self.clips[k].height)
            for k in ("trans_sit_floor", "wave_SE", "interact_SE", "walk_S", "walk_SE", "walk_N", "spin_SE")
            if k in self.clips and self.clips[k].height > 0
        ]
        if samples:
            samples.sort()
            return samples[len(samples) // 2]
        for k in ("idle_SE", "idle"):
            if k in self.clips and self.clips[k].height > 0:
                return float(self.clips[k].height)
        return 0.0

    def _height_scale_for(self, key: str, clip: SpriteClip) -> float:
        """Calcula escala vertical pixel-exata para posturas/transições (0.0px de pulo de zoom nas emendas!)."""
        if key not in _PROPORTIONAL_HEIGHT_KEYS:
            return 1.0
        ref_h = self._ref_standing_height()
        if ref_h > 0.0 and clip.height > 0:
            ratio = clip.height / ref_h
            # Só usa fallback fixo se o clipe tiver exatamente a mesma altura artificial (ex: sprite sintético de teste)
            if abs(ratio - 1.0) > 0.015 or key in ("trans_sit_floor", "trans_sit_chair"):
                return max(0.55, min(1.08, ratio))
        return CLIP_HEIGHT_SCALE.get(key, 1.0)

    def resolve_transition(self, src_action: str, dst_action: str, compass_dir: str = "SE") -> ResolvedClip | None:
        """Retorna o clipe de transição (normal ou reverso!) se existir no pack."""
        standing = ("idle", "walk", "run", "wave", "interact", "spin", "dance", "stretch")
        norm_src = "idle" if src_action in standing else src_action
        norm_dst = "idle" if dst_action in standing else dst_action
        spec = POSE_TRANSITIONS.get((src_action, dst_action)) or POSE_TRANSITIONS.get((norm_src, norm_dst))
        if spec is None:
            return None
        tkey, is_rev = spec
        clip = self.clips.get(tkey) or self.clips.get(f"clip_{tkey}")
        if clip is None:
            return None
        _, flip_x = DIRECTION_TO_CANONICAL.get(compass_dir, ("SE", False))
        return ResolvedClip(
            clip=clip,
            key=tkey,
            flip_x=flip_x,
            reverse=is_rev,
            speed_mul=1.0,
            stride_ratio=0.0,
            loop=False,
            height_scale=self._height_scale_for(tkey, clip),
        )

    def resolve_action(self, action: str, compass_dir: str = "SE") -> ResolvedClip | None:
        """Resolve o melhor clipe disponível para `(action, compass_dir)` aplicando espelhamento 8->5 e fallback de Tier."""
        if not self.clips:
            return None

        canon, flip_x = DIRECTION_TO_CANONICAL.get(compass_dir, ("SE", False))
        fallbacks = CANONICAL_FALLBACKS.get(canon, ("SE", "NE", "S", "L", "N"))

        def _get(k: str) -> SpriteClip | None:
            return self.clips.get(k) or self.clips.get(f"clip_{k}")

        def _meta_stride(k: str, fallback: float) -> float:
            m = self.clip_meta.get(k) or self.clip_meta.get(k.replace("clip_", "", 1))
            return m.stride_ratio if (m is not None and m.stride_ratio > 0.0) else fallback

        # 1. Caminhada nas 8 direções (usa os 5 ângulos canônicos com espelhamento + fallback suave!)
        if action == "walk":
            for ang in fallbacks:
                k = f"walk_{ang}"
                c = _get(k)
                if c is not None:
                    return ResolvedClip(
                        clip=c,
                        key=k,
                        flip_x=flip_x,
                        reverse=False,
                        speed_mul=1.0,
                        stride_ratio=_meta_stride(k, self.default_stride_ratio),
                        loop=True,
                    )
            # Fallback para clipe legado `walk_side` / `walk`
            for leg in ("walk_side", "walk", "idle_SE", "idle"):
                c = _get(leg)
                if c is not None:
                    return ResolvedClip(clip=c, key=leg, flip_x=flip_x, stride_ratio=self.default_stride_ratio)

        # 2. Corrida nas 8 direções (usa `run_<ang>` se disponível, ou reaproveita `walk_<ang>` a 1.45× FPS!)
        if action == "run":
            for ang in fallbacks:
                k = f"run_{ang}"
                c = _get(k)
                if c is not None:
                    return ResolvedClip(
                        clip=c,
                        key=k,
                        flip_x=flip_x,
                        reverse=False,
                        speed_mul=1.0,
                        stride_ratio=_meta_stride(k, self.default_stride_ratio * 1.42),
                        loop=True,
                    )
            # Reaproveitamento automático: acelera `walk` para 1.45× antes do Tier 2 assar!
            w_res = self.resolve_action("walk", compass_dir)
            if w_res is not None:
                return ResolvedClip(
                    clip=w_res.clip,
                    key=w_res.key,
                    flip_x=w_res.flip_x,
                    reverse=False,
                    speed_mul=1.45,
                    stride_ratio=w_res.stride_ratio * 1.38,
                    loop=True,
                )

        # 3. Posturas, ações expressivas e idle (sempre preservando orientação esquerda/direita atual!)
        alias_map: dict[str, tuple[str, ...]] = {
            "idle":       ("idle_SE", "idle_S", "idle"),
            "wave":       ("wave_SE", "wave_S", "wave", "idle_SE", "idle"),
            "interact":   ("interact_SE", "wave_SE", "idle_SE", "idle"),
            "spin":       ("spin_SE", "dance_SE", "dance", "wave_SE", "idle_SE"),
            "dance":      ("spin_SE", "dance_SE", "dance", "wave_SE", "idle_SE"),
            "sit_floor":  ("sit_floor_SE", "sit_chair_SE", "sit", "idle_SE", "idle"),
            "sit_chair":  ("sit_chair_SE", "sit_floor_SE", "sit", "idle_SE", "idle"),
            "sit_work":   ("sit_chair_SE", "sit_floor_SE", "sit", "idle_SE", "idle"),
            "sit_relax":  ("sit_floor_SE", "sit_chair_SE", "sit", "idle_SE", "idle"),
            "lie":        ("lie_SE", "sleep_SE", "sleep", "sit_floor_SE", "idle_SE"),
            "sleep":      ("lie_SE", "sleep_SE", "sleep", "sit_floor_SE", "idle_SE"),
            "stretch":    ("wave_SE", "idle_SE", "idle"),
        }
        # Em idle/wave/posturas, mantém orientação natural (não espelha idle frontal se não precisar)
        posture_flip = flip_x if compass_dir in ("NO", "O", "SO") else False
        for cand in alias_map.get(action, ("idle_SE", "idle")):
            c = _get(cand)
            if c is not None:
                return ResolvedClip(
                    clip=c,
                    key=cand,
                    flip_x=posture_flip,
                    reverse=False,
                    speed_mul=1.0,
                    stride_ratio=0.0,
                    loop=True,
                    height_scale=self._height_scale_for(cand, c),
                )

        # Último fallback: primeiro clipe disponível
        first_k, first_c = next(iter(self.clips.items()))
        return ResolvedClip(clip=first_c, key=first_k, flip_x=False, stride_ratio=0.0)

    def synced_walk_speed_norm(self, resolved: ResolvedClip, depth_scale: float, aspect_x: float = 1.77) -> float:
        """Calcula a velocidade normalizada exata (unidades de tela X/s) sincronizada ao tamanho do passo do clipe!

        Fórmula física:
        - Altura projetada da personagem na tela (normalizada em Y): `h_norm ≈ 0.36 * depth_scale`
        - Distância horizontal percorrida por ciclo completo em fração da tela X: `(h_norm * stride_ratio) / aspect_x`
        - Velocidade exata (tela/s): `dist_per_cycle / (clip.duration / speed_mul)` -> ZERO patinação!
        """
        if resolved.stride_ratio <= 0.0:
            return 0.085 * depth_scale
        h_norm = 0.36 * depth_scale
        cycle_s = max(resolved.clip.duration / max(resolved.speed_mul, 0.25), 0.35)
        dist_x_per_cycle = (h_norm * resolved.stride_ratio) / max(aspect_x, 1.0)
        return dist_x_per_cycle / cycle_s

    def portrait_for_mood(self, mood: str) -> QPixmap | None:
        """Retorna o retrato 2D expressivo desacoplado correspondente ao humor atual da rede LIF."""
        for key in (mood, "happy" if mood == "affectionate" else "calm", "happy", "idle"):
            if key in self.portraits:
                return self.portraits[key]
        return next(iter(self.portraits.values()), None)


def load_character_pack(char_dir: Path, outfit_id: str = "base") -> CharacterPack | None:
    """Carrega um `CharacterPack` padronizado de `characters/<char_id>/outfits/<outfit_id>/`."""
    char_dir = Path(char_dir)
    if not char_dir.is_dir():
        return None

    char_meta = {}
    cj = char_dir / "character.json"
    if cj.is_file():
        try:
            char_meta = json.loads(cj.read_text(encoding="utf-8"))
        except Exception:
            char_meta = {}

    char_id = str(char_meta.get("id") or char_dir.name).lower()
    char_name = str(char_meta.get("name") or char_id.capitalize())

    outfits_root = char_dir / "outfits"
    outfit_dir = outfits_root / outfit_id
    if not outfit_dir.is_dir():
        outfit_dir = outfits_root / "base"
        outfit_id = "base"
    if not outfit_dir.is_dir():
        return None

    # Lê manifest.json do outfit (metadados de stride_ratio, fps e tier!)
    clip_meta: dict[str, ClipMeta] = {}
    default_stride = 0.62
    mj = outfit_dir / "manifest.json"
    if mj.is_file():
        try:
            mdata = json.loads(mj.read_text(encoding="utf-8"))
            default_stride = float(mdata.get("default_stride_ratio", 0.62))
            for k, info in (mdata.get("clips") or {}).items():
                if isinstance(info, dict):
                    clip_meta[k] = ClipMeta(
                        key=k,
                        tier=int(info.get("tier", 0)),
                        fps=float(info.get("fps", 16.0)),
                        frames=int(info.get("frames", 25)),
                        stride_ratio=float(info.get("stride_ratio", 0.0)),
                        loop=bool(info.get("loop", True)),
                    )
        except Exception:
            pass

    # Carrega todos os clipes RGBA da pasta `clips/`
    clips: dict[str, SpriteClip] = {}
    clips_dir = outfit_dir / "clips"
    if clips_dir.is_dir():
        for ext in ("*.webp", "*.gif"):
            for fp in sorted(clips_dir.glob(ext)):
                stem = fp.stem
                clean_k = stem[5:] if stem.lower().startswith("clip_") else stem
                clip = load_sprite_clip(fp)
                if clip is not None and clip.frames:
                    # Aplica FPS do manifesto se registrado (mantém cadência 16 FPS exata!)
                    if clean_k in clip_meta and clip_meta[clean_k].fps > 1.0:
                        clip.fps = clip_meta[clean_k].fps
                    clips[clean_k] = clip

    if not clips:
        return None

    # Carrega retratos 2D expressivos desacoplados (`portraits/*.png`)
    portraits: dict[str, QPixmap] = {}
    pdir = char_dir / "portraits"
    if pdir.is_dir():
        for fp in sorted(pdir.glob("*.png")):
            pm = QPixmap(str(fp))
            if not pm.isNull():
                portraits[fp.stem.lower().replace("portrait_", "", 1)] = pm

    return CharacterPack(
        character_id=char_id,
        name=char_name,
        outfit_id=outfit_id,
        root_dir=outfit_dir,
        clips=clips,
        clip_meta=clip_meta,
        portraits=portraits,
        default_stride_ratio=default_stride,
    )
