"""AVATAR — Personagem waifu articulada com esqueleto 2D real de 18 ossos (FK + AutoRigger Spine2D), sombra aterrada e reflexo.

Camadas de realismo e integração ao cenário:
1. Esqueleto real de 18 ossos (`CharacterSkeleton`): joelhos dobram de verdade ao caminhar/sentar,
   braços erguem para acenar, alongar, digitar e segurar o guarda-chuva diretamente na mão direita (`forearm_r.end`),
   com física de mola no cabelo/saia e auto-aterramento matemático (`max(foot_y) == 0.0`).
2. `AutoRigger` (`build_rig_from_apose`): recorta automaticamente um sprite A-pose limpo (`rig_base.png`)
   em 10 peças RGBA com juntas circulares sobrepostas e proporções calibradas 1:1.
3. Sombra dupla aterrada sob a sola dos pés (oclusão de contato + sombra direcional) + reflexo articulado
   no piso molhado durante a chuva.
4. Fallbacks elegantes: multi-banda Live2D para sprites legados (`sprite_*.png`) e avatar vetorial
   também 100% guiado pelo esqueleto de 18 ossos caso nenhum PNG tenha sido gerado ainda.
"""

import math
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)

from ..core.emotion import EmotionState
from ..core.persona import Persona
from ..log import log
from ..mathutil import clamp, lerp, smoothstep
from .atmosphere import AtmospherePalette
from .character_pack import CharacterPack, ResolvedClip, load_character_pack, vector_to_compass8
from .rig_cutter import AutoRiggedCharacter, RigPart, build_rig_from_apose
from .skeleton import BoneWorld, CharacterSkeleton
from .sprite_clip import SpriteClip, load_clips_from_dirs
from .world_stage import WorldStage


def trim_sprite_pixmap(pm: QPixmap, alpha_threshold: int = 14) -> QPixmap:
    """Recorta margens transparentes para que a base (y=height) encoste EXATAMENTE na sola dos pés."""
    if pm.isNull():
        return pm
    img = pm.toImage().convertToFormat(QImage.Format_RGBA8888)
    w, h = img.width(), img.height()
    ptr = img.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, w, 4))
    ys, xs = np.where(arr[:, :, 3] > alpha_threshold)
    if len(xs) == 0 or len(ys) == 0:
        return pm
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    rx0 = max(0, x0 - 2)
    ry0 = max(0, y0 - 2)
    rx1 = min(w - 1, x1 + 2)
    ry1 = min(h - 1, y1)
    return pm.copy(QRect(rx0, ry0, rx1 - rx0 + 1, ry1 - ry0 + 1))


# Ordem anatômica Z das 10 peças articuladas (fundo -> frente) para juntas limpas sem pop
_SKELETAL_Z_ORDER: tuple[tuple[str, str], ...] = (
    ("upper_arm_l", "upper_arm_l"),
    ("forearm_l",   "forearm_l"),
    ("thigh_l",     "thigh_l"),
    ("shin_l",      "shin_l"),
    ("thigh_r",     "thigh_r"),
    ("shin_r",      "shin_r"),
    ("torso",       "pelvis"),
    ("head",        "head"),
    ("upper_arm_r", "upper_arm_r"),
    ("forearm_r",   "forearm_r"),
)


class AvatarRig:
    """Personagem waifu madura e articulada habitando o cenário 2.5D do wallpaper."""

    def __init__(
        self,
        persona: Persona,
        sprite_dirs: list[Path] | Path | None = None,
        render_style: str = "world_sprite",
        vrm_path: Path | None = None,
        live2d_dir: Path | None = None,
        character_dir: Path | None = None,
    ):
        self.persona = persona
        self.sprite_dirs = self._normalize_dirs(sprite_dirs)
        self.render_style: str = render_style  # "world_sprite" | "live2d_25d" | "vrm_3d" | "portrait"
        self.outfit: str = "base"
        self.action: str = "idle"              # idle | walk | run | sit_floor | sit_chair | sit_work | lie | sleep | wave | interact | spin | dance | stretch

        # Motor Oficial Wan 2.2 · 8 Direções + Grafo de Poses + Sincronia Matemática de Passos (Milestone 18)
        self.character_dir: Path | None = None
        self._char_pack: CharacterPack | None = None
        self.compass_dir: str = "SE"           # S | SE | L | NE | N | NO | O | SO
        self._running: bool = False
        self._trans_resolved: ResolvedClip | None = None
        self._trans_time: float = 0.0
        self._pending_action: str | None = None
        self._prev_clip_flip: bool = False
        self._prev_clip_h: float = 0.0
        self._last_drawn_frame: QPixmap | None = None
        self._last_drawn_flip: bool = False
        self._last_drawn_h: float = 0.0
        self._current_pack_sig: tuple[str, bool, bool] | None = None

        # Motor 2.5D Live2D / Spine2D em GPU (Arte 2D pura deformada em malha elástica contínua!)
        self.live2d_dir: Path | None = None
        self._live2d_renderer = None

        # Motor 3D HD estilo Tree of Savior (640x800 MSAA 4x, com modo Pixel-Art opcional)
        self.vrm_path: Path | None = None
        self.vrm_dynamic_recolor: bool = True
        self.vrm_pixel_art: bool = False
        self._builtin_dungeon_squad: bool = False
        self._active_archetype: str = "elfa_loira"
        self._ds_built_key: tuple[str, str, str] | None = None
        self._vrm_model = None
        self._vrm_animator = None
        self._vrm_renderer = None
        self._move_dx: float = 0.0
        self._move_dy: float = 0.0

        # Esqueleto real de 18 ossos + rig recortado + banco de clipes RGBA animados quadro-a-quadro (Wan 2.2)
        self.skeleton = CharacterSkeleton()
        self._rig: AutoRiggedCharacter | None = None
        self._clips: dict[str, SpriteClip] = {}
        self._clip_time: float = 0.0
        self._current_clip_key: str | None = None
        self._prev_clip_frame: QPixmap | None = None
        self._clip_fade_t: float = 1.0

        # Posição e navegação no chão 2.5D (ancorada no plano aberto estilo Tree of Savior / Ragnarok Online)
        self.pos_x: float = 0.52
        self.pos_y: float = 0.78
        self.target_x: float = 0.52
        self.target_y: float = 0.78
        self._waypoints: list[tuple[float, float]] = []
        self._arrive_action: str = "idle"
        self._clip_fade_dur: float = 0.22
        self.facing: int = 1                   # -1 esquerda, +1 direita
        self.move_dir: str = "front"           # "side" | "back" | "front" (orientação 4-vias estilo RO/ToS!)
        self.walk_speed: float = 0.115
        self.walk_phase: float = 0.0
        self._step_emit_accum: float = 0.0
        self.pending_footstep: tuple[float, float] | None = None

        # Estado climático mais recente (alimenta esqueleto de chuva/vento)
        self._last_raining: bool = False
        self._last_wind: float = 6.0

        # Temporizador para micro-animações complexas (alongar, acenar, admirar)
        self.time: float = 0.0
        self.action_timer: float = 0.0
        self.look_x: float = 0.0
        self.look_y: float = 0.0
        self.target_look_x: float = 0.0
        self.target_look_y: float = 0.0

        # Física de pulo / mola
        self.bounce_y: float = 0.0
        self.bounce_vy: float = 0.0
        self.tilt_deg: float = 0.0
        self.tilt_v: float = 0.0

        # Piscar natural
        self._blink_timer: float = 2.6
        self.blink_amount: float = 0.0

        # Balão de emote estilo Ragnarok Online / Pokémon NDS
        self.emote_kind: str = ""
        self.emote_life: float = 0.0
        self.emote_max: float = 2.6

        # Carinho & hitboxes dinâmicos guiados pelo esqueleto
        self.caress_glow: float = 0.0
        self.head_rect = QRectF()
        self.body_rect = QRectF()

        # Cache de sprites RGBA + peças tingidas
        self._sprites: dict[str, QPixmap] = {}
        self._tint_cache: dict[tuple, QPixmap] = {}
        self._current_sprite_key: str | None = None
        self._prev_sprite: QPixmap | None = None
        self._sprite_fade_t: float = 1.0
        self.reload_sprites()
        if character_dir is not None:
            self.set_character_pack(character_dir, outfit_id=self.outfit)
        if live2d_dir is not None:
            self.set_live2d_rig(live2d_dir)
        if vrm_path is not None:
            self.set_vrm_model(vrm_path)
        elif self.render_style == "vrm_3d":
            self.set_vrm_model("dungeon_squad")

    def has_character_pack(self) -> bool:
        return self._char_pack is not None and self._char_pack.has_clips()

    def set_character_pack(self, char_dir: Path | str | None, outfit_id: str | None = None) -> bool:
        """Carrega um `CharacterPack` Wan 2.2 padronizado (8 direções, reversão temporal e stride sync)."""
        self._char_pack = None
        self.character_dir = None
        self._trans_resolved = None
        self._pending_action = None
        self._current_pack_sig = None
        if not char_dir:
            return False
        p = Path(char_dir)
        pack = load_character_pack(p, outfit_id=outfit_id or self.outfit or "base")
        if pack is None:
            return False
        self._char_pack = pack
        self.character_dir = p
        log(
            f"[character_pack] Pack Wan 2.2 carregado: {pack.name} ({pack.outfit_id}) "
            f"· {len(pack.clips)} clipes · {len(pack.portraits)} retratos"
        )
        return True

    def has_live2d(self) -> bool:
        return self._live2d_renderer is not None

    def set_live2d_rig(self, rig_dir: Path | str | None) -> bool:
        """Carrega rig 2.5D Live2D/Spine2D (malha elástica contínua sobre arte 2D pura do ComfyUI)."""
        if self._live2d_renderer is not None:
            self._live2d_renderer.release()
            self._live2d_renderer = None
        self.live2d_dir = None
        if not rig_dir:
            return False
        p = Path(rig_dir)
        if not (p.is_dir() and (p / "base.png").is_file()):
            return False
        try:
            from .live2d_mesh import load_live2d_rig_from_dir

            rend = load_live2d_rig_from_dir(p, width=640, height=800)
            if rend is None:
                return False
            self._live2d_renderer = rend
            self.live2d_dir = p
            log(f"[live2d] Motor Live2D 2.5D carregado: {p.name} ({len(rend.front_mesh.indices) // 3} tris elásticos)")
            return True
        except Exception as exc:
            log(f"[live2d] Falha ao carregar rig Live2D 2.5D ({p}): {exc}")
            return False

    def _rebuild_builtin_dungeon_squad(self, archetype_id: str | None = None) -> bool:
        """Constrói/atualiza em tempo real um dos 4 arquétipos base em HD (sobre malha studio VRM ou fallback procedural)."""
        arch = archetype_id or self._active_archetype or "elfa_loira"
        prev_anim = self._vrm_animator
        if self._vrm_renderer is not None:
            self._vrm_renderer.release()
        self._vrm_model = None
        self._vrm_animator = None
        self._vrm_renderer = None
        try:
            from ..paths import Paths
            from .dungeon_avatar import build_dungeon_squad_model
            from .vrm_animator import VrmAnimator
            from .vrm_renderer import VrmRenderer
            from .vrm_sculptor import GIRL_ARCHETYPES, build_sculpted_vrm_girl

            vrm_dir = Paths().vrm_generated_dir
            if arch in GIRL_ARCHETYPES and (vrm_dir / "Victoria_Rubin.vrm").is_file():
                # Camada base limpa (`base` = roupa de baixo simples) sobre malha studio 100% íntegra!
                model = build_sculpted_vrm_girl(vrm_dir, archetype_id=arch, outfit_key="base")
            else:
                model = build_dungeon_squad_model(self.persona, self.outfit, archetype_id=arch if arch in GIRL_ARCHETYPES else "elfa_loira")

            animator = VrmAnimator(model)
            if prev_anim is not None:
                animator.time = prev_anim.time
                animator.walk_phase = prev_anim.walk_phase
                animator.yaw_deg = prev_anim.yaw_deg
                animator.target_yaw_deg = prev_anim.target_yaw_deg
            renderer = VrmRenderer(model, width=640, height=800, samples=4, pixel_art=self.vrm_pixel_art, pixel_size=(152, 190))
            self._vrm_model = model
            self._vrm_animator = animator
            self._vrm_renderer = renderer
            self._builtin_dungeon_squad = True
            self._active_archetype = arch
            self._ds_built_key = (self.persona.id, self.outfit, arch)
            self.vrm_path = Path(arch)
            log(f"[vrm] Avatar 3D HD construído: {model.name} (pixel_art={self.vrm_pixel_art})")
            return True
        except Exception as err:
            log(f"[vrm] Falha ao construir avatar 3D ({arch}): {err}")
            return False

    def set_vrm_model(self, path: Path | str | None) -> bool:
        """Carrega um dos 4 arquétipos base HD (`elfa_loira`, `humana_ruiva`, `androide_rosa`, `vampira_negra`) ou `.vrm` externo."""
        if path is not None:
            key = str(path).strip().lower()
            if key in ("elfa_loira", "humana_ruiva", "androide_rosa", "vampira_negra"):
                return self._rebuild_builtin_dungeon_squad(archetype_id=key)
            if key in ("dungeon_squad", "builtin:dungeon_squad"):
                return self._rebuild_builtin_dungeon_squad(archetype_id="elfa_loira")

        self._builtin_dungeon_squad = False
        self._ds_built_key = None
        if self._vrm_renderer is not None:
            self._vrm_renderer.release()
        self._vrm_model = None
        self._vrm_animator = None
        self._vrm_renderer = None
        self.vrm_path = None
        if path is None or not Path(path).is_file():
            return False
        try:
            from .vrm_animator import VrmAnimator
            from .vrm_loader import load_vrm
            from .vrm_renderer import VrmRenderer

            model = load_vrm(Path(path))
            animator = VrmAnimator(model)
            animator.stylized_proportions = self.vrm_pixel_art
            renderer = VrmRenderer(model, width=640, height=800, samples=4, pixel_art=self.vrm_pixel_art, pixel_size=(152, 190))
            self._vrm_model = model
            self._vrm_animator = animator
            self._vrm_renderer = renderer
            self.vrm_path = Path(path)
            log(f"[vrm] Modelo 3D carregado: {self.vrm_path.name} ({len(model.humanoid_bones)} ossos, {len(model.expressions)} expressões)")
            return True
        except Exception as err:
            log(f"[vrm] Falha ao carregar {path}: {err}")
            return False

    def has_vrm_3d(self) -> bool:
        return self._vrm_renderer is not None and self._vrm_animator is not None

    @staticmethod
    def _normalize_dirs(dirs: list[Path] | Path | None) -> list[Path]:
        if dirs is None:
            return []
        if isinstance(dirs, (list, tuple)):
            return [Path(d) for d in dirs if d is not None]
        return [Path(dirs)]

    def set_persona(self, persona: Persona, sprite_dirs: list[Path] | Path | None = None) -> None:
        self.persona = persona
        self.sprite_dirs = self._normalize_dirs(sprite_dirs)
        self._current_sprite_key = None
        self._prev_sprite = None
        self._sprite_fade_t = 1.0
        self.reload_sprites()

    def reload_sprites(self) -> None:
        """Carrega clipes animados RGBA (`clip_*.webp`), sprites PNG e constrói fallback esquelético."""
        self._sprites.clear()
        self._tint_cache.clear()
        self._rig = None
        self._clips = load_clips_from_dirs(self.sprite_dirs)
        self._current_clip_key = None
        self._prev_clip_frame = None
        self._clip_fade_t = 1.0

        for folder in self.sprite_dirs:
            if not folder.exists():
                continue
            for png in folder.glob("*.png"):
                pm = QPixmap(str(png))
                if not pm.isNull():
                    key = png.stem.lower()
                    if key.startswith(("sprite_", "rig_")):
                        self._sprites[key] = trim_sprite_pixmap(pm)
                    else:
                        self._sprites[key] = pm

        for rig_key in ("rig_base", "sprite_apose", "sprite_rig"):
            if rig_key in self._sprites:
                rig = build_rig_from_apose(self._sprites[rig_key])
                if rig is not None:
                    self._rig = rig
                    self.skeleton.set_proportions(rig.proportions)
                    break

        if self._rig is None:
            self.skeleton.set_proportions(None)

    def available_sprite_keys(self) -> set[str]:
        return set(self._sprites.keys())

    def available_clip_keys(self) -> set[str]:
        keys = set(self._clips.keys())
        if self._char_pack is not None:
            keys |= self._char_pack.available_keys()
        return keys

    def has_animated_clips(self) -> bool:
        return bool(self._clips) or self.has_character_pack()

    def has_world_sprites(self) -> bool:
        return self.has_animated_clips() or self._rig is not None or any(k.startswith("sprite_") for k in self._sprites)

    def has_skeletal_rig(self) -> bool:
        return self._rig is not None

    def walk_to(self, tx: float, ty: float, arrive_action: str = "idle", run: bool = False) -> None:
        self._waypoints.clear()
        cx, cy = WorldStage.clamp_walkable(tx, ty)
        self.target_x = cx
        self.target_y = cy
        self._arrive_action = arrive_action
        self._running = bool(run)
        dist = math.hypot(cx - self.pos_x, cy - self.pos_y)
        if dist > 0.015:
            self._trans_resolved = None
            self._pending_action = None
            self.action = "run" if self._running else "walk"
            self.compass_dir = vector_to_compass8(cx - self.pos_x, cy - self.pos_y)
            if abs(cx - self.pos_x) > 0.005:
                self.facing = 1 if cx > self.pos_x else -1
        else:
            self._running = False
            self.trigger_action(arrive_action)

    def walk_path(self, points: list[tuple[float, float]], arrive_action: str = "idle", run: bool = False) -> None:
        """Encadeia múltiplos waypoints sem parar nem exibir `idle` entre curvas de direção."""
        clamped = [WorldStage.clamp_walkable(px, py) for px, py in points]
        if not clamped:
            return
        first_x, first_y = clamped[0]
        self.walk_to(first_x, first_y, arrive_action=arrive_action, run=run)
        self._waypoints = list(clamped[1:])

    def trigger_action(self, action: str) -> None:
        if self._char_pack is not None and action != self.action:
            trans = self._char_pack.resolve_transition(self.action, action, self.compass_dir)
            if trans is not None:
                self._trans_resolved = trans
                self._trans_time = 0.0
                self._pending_action = action
                self.action_timer = 0.0
                return
        self._trans_resolved = None
        self._pending_action = None
        self.action = action
        self.action_timer = 0.0

    def show_emote(self, kind: str, duration: float = 2.6) -> None:
        self.emote_kind = kind
        self.emote_life = 0.0
        self.emote_max = max(0.8, duration)

    def impulse(self, vy: float = -210.0, tilt: float = 0.0) -> None:
        self.bounce_vy += vy
        self.tilt_v += tilt

    def set_look_target(self, nx: float, ny: float) -> None:
        self.target_look_x = clamp(nx, -1.0, 1.0)
        self.target_look_y = clamp(ny, -1.0, 1.0)

    def hit_test(self, x: float, y: float) -> str | None:
        if self.head_rect.contains(QPointF(x, y)):
            return "head"
        if self.body_rect.contains(QPointF(x, y)):
            return "body"
        return None

    def _resolve_world_sprite_key(self, mood: str, asleep: bool) -> str | None:
        candidates: list[str] = []
        if asleep or self.action == "sleep":
            candidates.extend([f"sprite_{self.outfit}_sleep", "sprite_sleep", "sprite_sit", "sprite_idle"])
        elif self.action == "walk":
            frame = "walk1" if int(self.walk_phase / math.pi) % 2 == 0 else "walk2"
            candidates.extend([f"sprite_{self.outfit}_{frame}", f"sprite_{frame}", "sprite_walk1", f"sprite_{self.outfit}", "sprite_idle"])
        elif self.action in ("sit_work", "sit_relax"):
            candidates.extend([f"sprite_{self.outfit}_sit", "sprite_sit", f"sprite_{self.outfit}", "sprite_idle"])
        elif self.action in ("wave", "stretch") or mood in ("happy", "affectionate"):
            candidates.extend([f"sprite_{self.outfit}_happy", "sprite_happy", f"sprite_{self.outfit}", "sprite_idle"])
        elif mood in ("shy", "pouty", "sleepy"):
            candidates.extend([f"sprite_{self.outfit}_{mood}", f"sprite_{mood}", f"sprite_{self.outfit}", "sprite_idle"])
        else:
            candidates.extend([f"sprite_{self.outfit}", "sprite_idle"])
        for k in candidates:
            if k in self._sprites:
                return k
        return None

    def _resolve_portrait_sprite_key(self, mood: str) -> str | None:
        mood_aliases = [mood]
        if mood == "affectionate":
            mood_aliases.append("happy")
        elif mood == "cozy":
            mood_aliases.append("calm")
        for m in mood_aliases:
            k = f"{self.outfit}_{m}"
            if k in self._sprites:
                return k
        if self.outfit in self._sprites:
            return self.outfit
        for m in mood_aliases:
            for base_k in (f"casual_{m}", m):
                if base_k in self._sprites:
                    return base_k
        for fallback in ("casual", "default", "base"):
            if fallback in self._sprites:
                return fallback
        return None

    def _get_tinted_sprite(self, sprite: QPixmap, atmosphere: AtmospherePalette) -> QPixmap:
        tr, tg, tb = atmosphere.avatar_tint
        tint_alpha = int(atmosphere.avatar_tint_alpha * 105)
        cache_key = (id(sprite), tr // 8, tg // 8, tb // 8, tint_alpha // 6)
        cached = self._tint_cache.get(cache_key)
        if cached is not None:
            return cached
        tinted = QPixmap(sprite.size())
        tinted.fill(Qt.transparent)
        tp = QPainter(tinted)
        tp.setRenderHint(QPainter.SmoothPixmapTransform, True)
        tp.drawPixmap(0, 0, sprite)
        tp.setCompositionMode(QPainter.CompositionMode_SourceAtop)
        tp.fillRect(tinted.rect(), QColor(tr, tg, tb, tint_alpha))
        tp.end()
        if len(self._tint_cache) >= 48:
            self._tint_cache.clear()
        self._tint_cache[cache_key] = tinted
        return tinted

    def update(
        self,
        dt: float,
        emotion: EmotionState,
        caressing: bool = False,
        asleep: bool = False,
        wind_speed: float | None = None,
        raining: bool | None = None,
    ) -> None:
        dt = clamp(dt, 0.0, 0.1)
        self.time += dt
        self.action_timer += dt
        self.pending_footstep = None

        if wind_speed is not None:
            self._last_wind = wind_speed
        if raining is not None:
            self._last_raining = raining

        prev_x = self.pos_x
        prev_y = self.pos_y
        dx = self.target_x - self.pos_x
        dy = self.target_y - self.pos_y
        dist = math.hypot(dx, dy)
        clip_speed_mul = 1.0

        # Troca de outfit 1:1 no CharacterPack caso a pasta do traje exista
        if (
            self._char_pack is not None
            and self.character_dir is not None
            and self.outfit != self._char_pack.outfit_id
            and (self.character_dir / "outfits" / self.outfit / "clips").is_dir()
        ):
            self.set_character_pack(self.character_dir, outfit_id=self.outfit)

        # Avança transição do Grafo de Poses (normal ou reversa!) quando ativa
        if self._trans_resolved is not None:
            self._trans_time += dt * self._trans_resolved.speed_mul
            if self._trans_time >= self._trans_resolved.clip.duration:
                next_act = self._pending_action or self.action
                self._trans_resolved = None
                self._pending_action = None
                self.action = next_act
                self._clip_time = 0.0
                self.action_timer = 0.0

        # Avança automaticamente para o próximo waypoint da rota sem passar por `idle`!
        while self._waypoints and dist <= 0.016 and not caressing:
            nx, ny = self._waypoints.pop(0)
            self.target_x, self.target_y = nx, ny
            dx = self.target_x - self.pos_x
            dy = self.target_y - self.pos_y
            dist = math.hypot(dx, dy)

        if dist > 0.008 and not caressing:
            self._trans_resolved = None
            self._pending_action = None
            self.action = "run" if self._running else "walk"
            self.compass_dir = vector_to_compass8(dx, dy)
            depth_mul = WorldStage.depth_scale(self.pos_y)

            if self._char_pack is not None and self.render_style == "world_sprite":
                # Sincronia matemática exata passo-chão (`stride_ratio` acoplado a `clip_fps` -> ZERO patinação!)
                resolved_move = self._char_pack.resolve_action(self.action, self.compass_dir)
                if resolved_move is not None:
                    synced_speed = self._char_pack.synced_walk_speed_norm(resolved_move, depth_mul)
                    # Só desacelera ao chegar no ÚLTIMO waypoint (curvas intermediárias mantêm passo contínuo!)
                    decel = 1.0 if self._waypoints else clamp(dist / 0.045, 0.48, 1.0)
                    actual_speed = synced_speed * decel
                    clip_speed_mul = resolved_move.speed_mul * clamp(actual_speed / max(synced_speed, 1e-4), 0.65, 1.35)
                    step_dist = min(dist, actual_speed * dt)
                    step_period = max(0.24, (resolved_move.clip.duration / max(clip_speed_mul, 0.25)) * 0.5)
                else:
                    speed_mul = 1.0 if self._waypoints else clamp(dist / 0.055, 0.38, 1.0)
                    clip_speed_mul = clamp(0.75 + 0.35 * speed_mul, 0.72, 1.12)
                    step_dist = min(dist, self.walk_speed * depth_mul * speed_mul * dt)
                    step_period = 0.34
            else:
                speed_mul = clamp(dist / 0.055, 0.38, 1.0)
                run_mul = 1.45 if self._running else 1.0
                clip_speed_mul = clamp(0.75 + 0.35 * speed_mul, 0.72, 1.12) * run_mul
                step_dist = min(dist, self.walk_speed * run_mul * depth_mul * speed_mul * dt)
                step_period = 0.34 / run_mul

            self.pos_x += (dx / dist) * step_dist
            self.pos_y += (dy / dist) * step_dist
            self._move_dx = dx / dist
            self._move_dy = dy / dist

            # Orientação direcional legada (mantida em sincronia com `compass_dir` para Live2D/VRM)
            vx_vis = dx * 1.77
            vy_vis = dy
            if abs(vx_vis) >= abs(vy_vis) * 1.35:
                self.move_dir = "side"
                if abs(dx) > 0.002:
                    self.facing = 1 if dx > 0 else -1
            elif dy < 0.0:
                self.move_dir = "back"
                if abs(dx) > 0.004:
                    self.facing = 1 if dx > 0 else -1
            else:
                self.move_dir = "front"
                if abs(dx) > 0.004:
                    self.facing = 1 if dx > 0 else -1

            self.walk_phase += dt * (9.5 * clamp(dist / 0.055, 0.38, 1.0) + 2.2)
            self._step_emit_accum += dt
            if self._step_emit_accum >= step_period:
                self._step_emit_accum = 0.0
                self.pending_footstep = (self.pos_x, self.pos_y)
        else:
            if self.action in ("walk", "run"):
                self._running = False
                self.trigger_action(self._arrive_action)
            self.move_dir = "front"
            self._move_dx = 0.0
            self._move_dy = 0.0
            if asleep and self._trans_resolved is None:
                self.action = "sleep"
            elif self.action in ("stretch", "wave", "dance", "spin", "interact") and self.action_timer > 4.2:
                self.action = "idle"
                self.action_timer = 0.0
            if not self.has_animated_clips() and abs(self.look_x) > 0.42 and self.action not in ("sleep", "sit_work"):
                self.facing = 1 if self.look_x > 0 else -1

        vel_x = (self.pos_x - prev_x) / max(dt, 1e-4)

        follow = clamp(dt * 6.5, 0.0, 1.0)
        self.look_x += (self.target_look_x - self.look_x) * follow
        self.look_y += (self.target_look_y - self.look_y) * follow

        self.bounce_vy += (-165.0 * self.bounce_y - 12.5 * self.bounce_vy) * dt
        self.bounce_y = clamp(self.bounce_y + self.bounce_vy * dt, -48.0, 16.0)
        self.tilt_v += (-85.0 * self.tilt_deg - 9.0 * self.tilt_v) * dt
        self.tilt_deg = clamp(self.tilt_deg + self.tilt_v * dt, -11.0, 11.0)

        target_glow = 1.0 if caressing else 0.0
        self.caress_glow += (target_glow - self.caress_glow) * clamp(dt * 5.0, 0.0, 1.0)

        if self._sprite_fade_t < 1.0:
            self._sprite_fade_t = min(1.0, self._sprite_fade_t + dt / 0.36)
            if self._sprite_fade_t >= 1.0:
                self._prev_sprite = None

        self._clip_time += dt * clip_speed_mul
        if self._clip_fade_t < 1.0:
            self._clip_fade_t = min(1.0, self._clip_fade_t + dt / max(self._clip_fade_dur, 0.05))
            if self._clip_fade_t >= 1.0:
                self._prev_clip_frame = None

        if self.emote_kind:
            self.emote_life += dt
            if self.emote_life >= self.emote_max:
                self.emote_kind = ""

        if asleep or self.action == "sleep":
            self.blink_amount = lerp(self.blink_amount, 1.0, clamp(dt * 4.0, 0.0, 1.0))
        elif caressing:
            self.blink_amount = lerp(self.blink_amount, 0.9, clamp(dt * 7.0, 0.0, 1.0))
        else:
            self._blink_timer -= dt
            if self._blink_timer <= 0.0:
                if self._blink_timer > -0.14:
                    self.blink_amount = math.sin((-self._blink_timer / 0.14) * math.pi)
                else:
                    self.blink_amount = 0.0
                    self._blink_timer = 2.4 + abs(math.sin(self.time * 1.9)) * 3.0
            else:
                self.blink_amount = max(0.0, self.blink_amount - dt * 8.0)

        # Atualiza o motor 2.5D Live2D/Spine2D em GPU (arte 2D pura com malha elástica contínua!)
        if self._live2d_renderer is not None:
            self._live2d_renderer.update(
                dt=dt,
                action=self.action,
                walk_phase=self.walk_phase,
                action_timer=self.action_timer,
                emotion=emotion,
                blink_amount=self.blink_amount,
                look_x=self.look_x,
                look_y=self.look_y,
                facing=self.facing,
                move_dir=self.move_dir,
                move_dx=self._move_dx,
                move_dy=self._move_dy,
                wind_speed=self._last_wind,
                asleep=asleep,
                caressing=caressing,
            )

        # Atualiza o motor 3D VRM (giro 360°, expressões faciais LIF, piscar, look-at e SpringBones!)
        if self._vrm_animator is not None:
            self._vrm_animator.update(
                dt=dt,
                action=self.action,
                walk_phase=self.walk_phase,
                action_timer=self.action_timer,
                emotion=emotion,
                blink_amount=self.blink_amount,
                look_x=self.look_x,
                look_y=self.look_y,
                move_dx=self._move_dx,
                move_dy=self._move_dy,
                wind_speed=self._last_wind,
                asleep=asleep,
                raining=self._last_raining,
                caressing=caressing,
            )

        # Atualiza o esqueleto real de 18 ossos (fallback 2D)
        self.skeleton.update(
            dt=dt,
            action=self.action,
            walk_phase=self.walk_phase,
            action_timer=self.action_timer,
            look_x=self.look_x * self.facing,
            look_y=self.look_y,
            vel_x=vel_x * self.facing,
            wind_speed=self._last_wind,
            asleep=asleep,
            raining=self._last_raining,
            caressing=caressing,
        )

    def paint(
        self,
        painter: QPainter,
        canvas_w: int,
        canvas_h: int,
        x_ratio: float,
        scale: float,
        emotion: EmotionState,
        atmosphere: AtmospherePalette,
        parallax_x: float = 0.0,
        parallax_y: float = 0.0,
        wind: float = 0.0,
        asleep: bool = False,
        raining: bool = False,
        stage: WorldStage | None = None,
        sun_x_norm: float = 0.5,
    ) -> None:
        self._last_raining = raining
        self._last_wind = wind

        if self.render_style == "portrait":
            self._paint_portrait_mode(
                painter, canvas_w, canvas_h, x_ratio, scale, emotion, atmosphere, parallax_x, parallax_y, asleep
            )
            return

        depth = WorldStage.depth_scale(self.pos_y)
        if stage is not None:
            foot_x, foot_y = stage.screen_pos(self.pos_x, self.pos_y, canvas_w, canvas_h, parallax_x, parallax_y)
        else:
            foot_x = self.pos_x * canvas_w - parallax_x * 14.0
            foot_y = self.pos_y * canvas_h - parallax_y * 5.0

        u = (canvas_h / 1080.0) * scale * depth
        is_walking = self.action == "walk"
        breath = math.sin(self.time * (1.35 if asleep else 2.25))

        # Prioridade 0A: Motor 2.5D Live2D / Spine2D em GPU (Arte 2D pura com malha elástica contínua!)
        if self.render_style == "live2d_25d" and self._live2d_renderer is not None:
            lift = max(0.0, -self.bounce_y)
            self._paint_grounded_shadow(painter, foot_x, foot_y, u, lift, sun_x_norm)
            self._paint_rpg_ground_aura(painter, foot_x, foot_y, u, atmosphere)
            draw_y = foot_y - lift + max(0.0, self.bounce_y) * 0.35
            self._paint_live2d_25d(painter, foot_x, foot_y, draw_y, u, atmosphere, raining)
        # Prioridade 0B: Motor 3D Cel-Shaded em GPU (VRM 0.x/1.0 — 360° real, expressões faciais e trajes dinâmicos!)
        elif self.render_style in ("vrm_3d", "live2d_25d") and self._vrm_renderer is not None and self._vrm_animator is not None:
            lift = max(0.0, -self.bounce_y)
            self._paint_grounded_shadow(painter, foot_x, foot_y, u, lift, sun_x_norm)
            self._paint_rpg_ground_aura(painter, foot_x, foot_y, u, atmosphere)
            draw_y = foot_y - lift + max(0.0, self.bounce_y) * 0.35
            self._paint_vrm_3d(painter, foot_x, foot_y, draw_y, u, atmosphere, raining, sun_x_norm)
        elif self.render_style == "world_sprite" and self._char_pack is not None:
            # Prioridade Oficial (Milestone 18): CharacterPack Wan 2.2 · 8 Direções + Grafo de Poses + Step Sync!
            resolved = self._trans_resolved or self._char_pack.resolve_action(
                "sleep" if asleep else self.action, self.compass_dir
            )
            if resolved is not None:
                sig = (resolved.key, resolved.flip_x, resolved.reverse)
                play_t = self._trans_time if self._trans_resolved is not None else self._clip_time
                if sig != self._current_pack_sig:
                    keep_stride_phase = False
                    if self._current_pack_sig is not None:
                        prev_k, prev_flip, prev_rev = self._current_pack_sig
                        keep_stride_phase = (
                            self._trans_resolved is None
                            and prev_k.startswith(("walk_", "run_"))
                            and resolved.key.startswith(("walk_", "run_"))
                        )
                        is_seam_trans = prev_k.startswith("trans_") or resolved.key.startswith("trans_")
                        if self._last_drawn_frame is not None and not self._last_drawn_frame.isNull():
                            # Usa o EXATO último frame desenhado na tela (nunca um frame errado de `_clip_time`!)
                            self._prev_clip_frame = self._last_drawn_frame
                            self._prev_clip_flip = self._last_drawn_flip
                            self._prev_clip_h = self._last_drawn_h
                            self._clip_fade_t = 0.0
                            self._clip_fade_dur = 0.06 if is_seam_trans else (0.11 if keep_stride_phase else 0.16)
                        else:
                            prev_c = self._char_pack.clips.get(prev_k)
                            if prev_c is not None:
                                self._prev_clip_frame = prev_c.frame_at(self._clip_time, reverse=prev_rev)
                                self._prev_clip_flip = prev_flip
                                self._prev_clip_h = 0.0
                                self._clip_fade_t = 0.0
                                self._clip_fade_dur = 0.14
                    self._current_pack_sig = sig
                    if self._trans_resolved is None and not keep_stride_phase:
                        self._clip_time = 0.0
                        play_t = 0.0
                lift = max(0.0, -self.bounce_y)
                self._paint_grounded_shadow(painter, foot_x, foot_y, u, lift, sun_x_norm)
                self._paint_rpg_ground_aura(painter, foot_x, foot_y, u, atmosphere)
                draw_y = foot_y - lift + max(0.0, self.bounce_y) * 0.35
                self._paint_character_pack_clip(
                    painter, resolved, play_t, foot_x, foot_y, draw_y, u, atmosphere, raining
                )
        else:
            # Prioridade 1: Clipes RGBA animados quadro-a-quadro (Wan 2.2 FirstLastFrameToVideo)
            clip_key = self._resolve_clip_key("sleepy" if asleep else emotion.mood, asleep)
            if clip_key is not None:
                if clip_key != self._current_clip_key:
                    if self._current_clip_key is not None and self._current_clip_key in self._clips:
                        self._prev_clip_frame = self._clips[self._current_clip_key].frame_at(self._clip_time)
                        self._clip_fade_t = 0.0
                    self._current_clip_key = clip_key
                    self._clip_time = 0.0
                lift = max(0.0, -self.bounce_y)
                self._paint_grounded_shadow(painter, foot_x, foot_y, u, lift, sun_x_norm)
                self._paint_rpg_ground_aura(painter, foot_x, foot_y, u, atmosphere)
                draw_y = foot_y - lift + max(0.0, self.bounce_y) * 0.35
                self._paint_animated_clip(
                    painter, self._clips[clip_key], foot_x, foot_y, draw_y, u, atmosphere, raining
                )
            elif self._rig is not None:
                lift = max(0.0, -self.bounce_y)
                self._paint_grounded_shadow(painter, foot_x, foot_y, u, lift, sun_x_norm)
                draw_y = foot_y - lift + max(0.0, self.bounce_y) * 0.35
                self._paint_skeletal_rig(
                    painter, self._rig, self.skeleton.bones, foot_x, foot_y, draw_y, u, emotion, atmosphere, asleep, raining
                )
            else:
                stride_hop = abs(math.sin(self.walk_phase)) * 8.5 * u if is_walking else 0.0
                music_bob = abs(math.sin(self.time * 5.2)) * 5.5 * u if self.action == "music_sway" else 0.0
                lift = stride_hop + music_bob + max(0.0, -self.bounce_y)
                self._paint_grounded_shadow(painter, foot_x, foot_y, u, lift, sun_x_norm)
                draw_y = foot_y - lift + max(0.0, self.bounce_y) * 0.35

                sprite_key = self._resolve_world_sprite_key("sleepy" if asleep else emotion.mood, asleep)
                if sprite_key is not None:
                    if sprite_key != self._current_sprite_key:
                        if self._current_sprite_key is not None and self._current_sprite_key in self._sprites:
                            self._prev_sprite = self._sprites[self._current_sprite_key]
                            self._sprite_fade_t = 0.0
                        self._current_sprite_key = sprite_key
                    self._paint_multiband_ai_sprite(
                        painter, self._sprites[sprite_key], foot_x, foot_y, draw_y, u, breath, is_walking, emotion, atmosphere, wind, raining
                    )
                else:
                    self._paint_skeletal_procedural(
                        painter, self.skeleton.bones, foot_x, draw_y, u, emotion, atmosphere, asleep, raining
                    )

        if self.emote_kind:
            self._paint_ro_emote_balloon(painter, self.head_rect.center().x(), self.head_rect.top() - 8 * u, u)

    def _paint_live2d_25d(
        self,
        painter: QPainter,
        foot_x: float,
        foot_y: float,
        draw_y: float,
        u: float,
        atmosphere: AtmospherePalette,
        raining: bool,
    ) -> None:
        """Renderiza o avatar 2.5D Live2D/Spine2D (malha elástica contínua sobre arte 2D pura) ancorado em `draw_y`."""
        if self._live2d_renderer is None:
            return
        pm = self._live2d_renderer.render_pixmap(atmosphere=atmosphere, outfit_key=self.outfit, camera_focus="full")
        if pm.isNull():
            return

        frame_h = 465.0 * u
        frame_w = frame_h * (pm.width() / max(pm.height(), 1))
        foot_v = self._live2d_renderer.last_foot_v
        top_offset = -frame_h * foot_v

        if raining:
            painter.save()
            painter.translate(foot_x, foot_y + 2 * u)
            painter.scale(1.0, -0.32)
            painter.setOpacity(0.20)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(QRectF(-frame_w * 0.5, top_offset, frame_w, frame_h), pm, QRectF(pm.rect()))
            painter.restore()

        painter.save()
        if self.caress_glow > 0.05:
            rim_r, rim_g, rim_b = atmosphere.rim_light
            aura = QRadialGradient(QPointF(foot_x, draw_y - frame_h * 0.44), frame_h * 0.42)
            aura.setColorAt(0.0, QColor(rim_r, rim_g, rim_b, int(92 * self.caress_glow)))
            aura.setColorAt(1.0, QColor(rim_r, rim_g, rim_b, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(aura)
            painter.drawEllipse(QPointF(foot_x, draw_y - frame_h * 0.44), frame_h * 0.34, frame_h * 0.42)

        painter.translate(foot_x, draw_y)
        painter.rotate(self.tilt_deg)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(QRectF(-frame_w * 0.5, top_offset, frame_w, frame_h), pm, QRectF(pm.rect()))
        painter.restore()

        body_h = frame_h * 0.78
        if raining and self.action not in ("sleep", "sit_work"):
            self._paint_umbrella(painter, foot_x + 14 * u, draw_y - body_h * 1.04, u, atmosphere)

        self.body_rect = QRectF(foot_x - frame_w * 0.28, draw_y - body_h, frame_w * 0.56, body_h)
        self.head_rect = QRectF(foot_x - frame_w * 0.22, draw_y - body_h * 1.02, frame_w * 0.44, body_h * 0.26)

    def _paint_vrm_3d(
        self,
        painter: QPainter,
        foot_x: float,
        foot_y: float,
        draw_y: float,
        u: float,
        atmosphere: AtmospherePalette,
        raining: bool,
        sun_x_norm: float,
    ) -> None:
        """Renderiza o avatar 3D (HD Pixel-Art Nearest-Neighbor estilo Dungeon Squad ou MToon suave) ancorado em `draw_y`."""
        if self._builtin_dungeon_squad and self._ds_built_key != (self.persona.id, self.outfit, self._active_archetype):
            self._rebuild_builtin_dungeon_squad()
        if self._vrm_renderer is None or self._vrm_animator is None:
            return
        pm = self._vrm_renderer.render_pixmap(
            animator=self._vrm_animator,
            atmosphere=atmosphere,
            persona=self.persona,
            outfit_key=self.outfit,
            sun_x_norm=sun_x_norm,
            dynamic_recolor=self.vrm_dynamic_recolor,
        )
        if pm.isNull():
            return

        # Altura total do FBO projetada na escala Tree of Savior / Dungeon Squad
        use_smooth = not getattr(self._vrm_renderer, "pixel_art", False)
        frame_h = (495.0 if self._builtin_dungeon_squad else 465.0) * u
        frame_w = frame_h * (pm.width() / max(pm.height(), 1))
        foot_v = self._vrm_renderer.last_foot_v
        top_offset = -frame_h * foot_v

        # Reflexo 3D animado no piso molhado durante a chuva!
        if raining:
            painter.save()
            painter.translate(foot_x, foot_y + 2 * u)
            painter.scale(1.0, -0.32)
            painter.setOpacity(0.18)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, use_smooth)
            painter.drawPixmap(QRectF(-frame_w * 0.5, top_offset, frame_w, frame_h), pm, QRectF(pm.rect()))
            painter.restore()

        painter.save()
        if self.caress_glow > 0.05:
            rim_r, rim_g, rim_b = atmosphere.rim_light
            aura = QRadialGradient(QPointF(foot_x, draw_y - frame_h * 0.42), frame_h * 0.42)
            aura.setColorAt(0.0, QColor(rim_r, rim_g, rim_b, int(92 * self.caress_glow)))
            aura.setColorAt(1.0, QColor(rim_r, rim_g, rim_b, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(aura)
            painter.drawEllipse(QPointF(foot_x, draw_y - frame_h * 0.42), frame_h * 0.34, frame_h * 0.42)

        painter.translate(foot_x, draw_y)
        painter.rotate(self.tilt_deg)
        # Nearest-Neighbor (`SmoothPixmapTransform=False`) preserva blocos de pixel nítidos estilo Dungeon Squad!
        painter.setRenderHint(QPainter.SmoothPixmapTransform, use_smooth)
        painter.drawPixmap(QRectF(-frame_w * 0.5, top_offset, frame_w, frame_h), pm, QRectF(pm.rect()))
        painter.restore()

        body_h = frame_h * 0.78
        if raining and self.action not in ("sleep", "sit_work"):
            self._paint_umbrella(painter, foot_x + 14 * u, draw_y - body_h * 1.04, u, atmosphere)

        self.body_rect = QRectF(foot_x - frame_w * 0.28, draw_y - body_h, frame_w * 0.56, body_h)
        self.head_rect = QRectF(foot_x - frame_w * 0.22, draw_y - body_h * 1.02, frame_w * 0.44, body_h * 0.26)

    def _resolve_clip_key(self, mood: str, asleep: bool) -> str | None:
        if not self._clips:
            return None
        candidates: list[str] = []
        if asleep or self.action == "sleep":
            candidates.extend(["clip_sleep", "clip_sit", "clip_idle", "clip_wave"])
        elif self.action == "walk":
            if self.move_dir == "side":
                candidates.extend(["clip_walk_side", "clip_walk", "clip_idle", "clip_wave"])
            elif self.move_dir == "back":
                candidates.extend(["clip_walk_back", "clip_walk_side", "clip_walk", "clip_idle"])
            else:
                candidates.extend(["clip_walk", "clip_walk_side", "clip_idle", "clip_wave"])
        elif self.action in ("dance", "music_sway", "stretch"):
            candidates.extend(["clip_dance", "clip_wave", "clip_idle"])
        elif self.action == "wave":
            candidates.extend(["clip_wave", "clip_dance", "clip_idle"])
        elif self.action in ("sit_work", "sit_relax"):
            candidates.extend(["clip_sit", "clip_idle", "clip_wave"])
        else:
            candidates.extend(["clip_idle", "clip_wave", "clip_dance"])
        for k in candidates:
            if k in self._clips:
                return k
        return next(iter(self._clips.keys()))

    def _paint_rpg_ground_aura(self, painter: QPainter, foot_x: float, foot_y: float, u: float, atmo: AtmospherePalette) -> None:
        """Círculo mágico celeste/dourado sob os pés (sutil em ações mágicas, aceno, dança ou carinho)."""
        intense = self.action in ("wave", "dance", "music_sway", "stretch") or self.caress_glow > 0.1 or bool(self.emote_kind)
        if not intense:
            return
        strength = 0.88 if self.action in ("dance", "music_sway") else 0.65
        pulse = 0.92 + 0.08 * math.sin(self.time * 4.2)
        ar, ag, ab = self.persona.accent_color
        c_outer = QColor(245, 206, 112)
        c_inner = QColor(ar, ag, ab)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(foot_x, foot_y + 2 * u)

        # Halo arcano no chão
        rx, ry = 76 * u * pulse, 23 * u * pulse
        glow = QRadialGradient(QPointF(0, 0), rx)
        glow.setColorAt(0.0, QColor(c_inner.red(), c_inner.green(), c_inner.blue(), int(55 * strength)))
        glow.setColorAt(0.65, QColor(c_outer.red(), c_outer.green(), c_outer.blue(), int(85 * strength)))
        glow.setColorAt(1.0, QColor(c_outer.red(), c_outer.green(), c_outer.blue(), 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(0, 0), rx, ry)

        # Anéis rúnicos duplos + hexagrama giratório em perspectiva 2.5D
        r1x, r1y = 62 * u, 18.5 * u
        r2x, r2y = 48 * u, 14.5 * u
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(255, 110, 175, int(175 * strength)), 1.8 * u))
        painter.drawEllipse(QPointF(0, 0), r1x, r1y)
        painter.setPen(QPen(QColor(195, 125, 255, int(145 * strength)), 1.3 * u))
        painter.drawEllipse(QPointF(0, 0), r2x, r2y)

        # Hexagrama (dois triângulos sobrepostos girando)
        rot = self.time * (1.8 if intense else 0.55)
        painter.setPen(QPen(QColor(255, 150, 210, int(150 * strength)), 1.2 * u))
        for offset in (0.0, math.pi / 3.0):
            pts = [
                QPointF(math.cos(rot + offset + k * (math.tau / 3.0)) * r2x, math.sin(rot + offset + k * (math.tau / 3.0)) * r2y)
                for k in range(3)
            ]
            for k in range(3):
                painter.drawLine(pts[k], pts[(k + 1) % 3])

        # 6 glifos/brasas arcanas orbitando o círculo externo
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 210, 235, int(225 * strength)))
        for i in range(6):
            ang = -rot * 1.2 + i * (math.tau / 6.0)
            px = math.cos(ang) * r1x
            py = math.sin(ang) * r1y
            painter.drawEllipse(QPointF(px, py), 2.8 * u, 2.2 * u)
        painter.restore()

    def _paint_character_pack_clip(
        self,
        painter: QPainter,
        resolved: ResolvedClip,
        play_t: float,
        foot_x: float,
        foot_y: float,
        draw_y: float,
        u: float,
        atmosphere: AtmospherePalette,
        raining: bool,
    ) -> None:
        """Renderiza um `ResolvedClip` do `CharacterPack` Wan 2.2 com espelhamento 8->5, reversão temporal e crossfade limpo."""
        frame = resolved.clip.frame_at(play_t, reverse=resolved.reverse, loop=resolved.loop)
        if frame.isNull():
            return

        # Altura projetada calibrada 1:1 com `CharacterPack.synced_walk_speed_norm` e `height_scale` de postura!
        target_h = 385.0 * u * resolved.height_scale
        aspect = frame.width() / max(frame.height(), 1)
        target_w = target_h * aspect
        sx = -1.0 if resolved.flip_x else 1.0
        run_tilt = (3.5 * (-1.0 if resolved.flip_x else 1.0)) if self.action == "run" else 0.0

        # 1. Reflexo no piso molhado em dias de chuva
        if raining:
            painter.save()
            painter.translate(foot_x, foot_y + 2 * u)
            painter.scale(sx, -0.32)
            painter.setOpacity(0.18)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(QRectF(-target_w * 0.5, -target_h, target_w, target_h), frame, QRectF(frame.rect()))
            painter.restore()

        # 2. Aura sutil de carinho
        painter.save()
        if self.caress_glow > 0.05:
            rim_r, rim_g, rim_b = atmosphere.rim_light
            aura = QRadialGradient(QPointF(foot_x, draw_y - target_h * 0.50), target_h * 0.52)
            aura.setColorAt(0.0, QColor(rim_r, rim_g, rim_b, int(92 * self.caress_glow)))
            aura.setColorAt(1.0, QColor(rim_r, rim_g, rim_b, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(aura)
            painter.drawEllipse(QPointF(foot_x, draw_y - target_h * 0.50), target_h * 0.40, target_h * 0.52)

        painter.translate(foot_x, draw_y)
        painter.rotate(self.tilt_deg + run_tilt)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        tinted_curr = self._get_tinted_sprite(frame, atmosphere)
        dst = QRectF(-target_w * 0.5, -target_h, target_w, target_h)
        if self._prev_clip_frame is not None and self._clip_fade_t < 1.0:
            ease = smoothstep(0.0, 1.0, self._clip_fade_t)
            prev_t = self._get_tinted_sprite(self._prev_clip_frame, atmosphere)
            prev_h = self._prev_clip_h if self._prev_clip_h > 1.0 else target_h
            prev_w = prev_h * (prev_t.width() / max(prev_t.height(), 1))
            prev_sx = -1.0 if self._prev_clip_flip else 1.0
            painter.save()
            painter.scale(prev_sx, 1.0)
            painter.setOpacity(1.0 - ease)
            painter.drawPixmap(QRectF(-prev_w * 0.5, -prev_h, prev_w, prev_h), prev_t, QRectF(prev_t.rect()))
            painter.restore()

            painter.save()
            painter.scale(sx, 1.0)
            painter.setOpacity(ease)
            painter.drawPixmap(dst, tinted_curr, QRectF(tinted_curr.rect()))
            painter.restore()
            painter.setOpacity(1.0)
        else:
            painter.scale(sx, 1.0)
            painter.drawPixmap(dst, tinted_curr, QRectF(tinted_curr.rect()))
        painter.restore()

        # Memoriza o frame exato desenhado para crossfade 100% livre de flickering na próxima emenda!
        self._last_drawn_frame = frame
        self._last_drawn_flip = resolved.flip_x
        self._last_drawn_h = target_h

        if raining and self.action not in ("sleep", "lie", "sit_work"):
            self._paint_umbrella(painter, foot_x + (18 * u * sx), draw_y - target_h * 1.02, u, atmosphere)

        self.body_rect = QRectF(foot_x - target_w * 0.36, draw_y - target_h * 0.96, target_w * 0.72, target_h * 0.96)
        self.head_rect = QRectF(foot_x - target_w * 0.28, draw_y - target_h * 0.98, target_w * 0.56, target_h * 0.28)

    def _paint_animated_clip(
        self,
        painter: QPainter,
        clip: SpriteClip,
        foot_x: float,
        foot_y: float,
        draw_y: float,
        u: float,
        atmosphere: AtmospherePalette,
        raining: bool,
    ) -> None:
        """Renderiza o frame atual do clipe RGBA animado (Wan 2.2) ancorado nos pés, com crossfade e reflexo."""
        frame = clip.frame_at(self._clip_time)
        if frame.isNull():
            return

        # Proporção natural estilo Tree of Savior / Ragnarok Online no cenário aberto
        target_h = 345.0 * u
        aspect = frame.width() / max(frame.height(), 1)
        target_w = target_h * aspect
        # Espelha horizontalmente APENAS nos clipes direcionais (perfil/costas) — preserva assimetria do cabelo/presilha de frente!
        is_directional = clip.name in ("clip_walk_side", "clip_walk_back")
        sx = (-1.0 if self.facing < 0 else 1.0) if is_directional else 1.0
        # Cadência vertical sutil sincronizada ao passo durante caminhada (elimina sensação de deslizar)
        step_bob = abs(math.sin(self._clip_time * math.pi * 2.0)) * 3.5 * u if self.action == "walk" else 0.0
        draw_y = draw_y - step_bob

        # 1. Reflexo animado no piso molhado quando está chovendo!
        if raining:
            painter.save()
            painter.translate(foot_x, foot_y + 2 * u)
            painter.scale(sx, -0.32)
            painter.setOpacity(0.18)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(QRectF(-target_w * 0.5, -target_h, target_w, target_h), frame, QRectF(frame.rect()))
            painter.restore()

        # 2. Aura sutil de carinho
        painter.save()
        if self.caress_glow > 0.05:
            rim_r, rim_g, rim_b = atmosphere.rim_light
            aura = QRadialGradient(QPointF(foot_x, draw_y - target_h * 0.52), target_h * 0.52)
            aura.setColorAt(0.0, QColor(rim_r, rim_g, rim_b, int(92 * self.caress_glow)))
            aura.setColorAt(1.0, QColor(rim_r, rim_g, rim_b, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(aura)
            painter.drawEllipse(QPointF(foot_x, draw_y - target_h * 0.52), target_h * 0.40, target_h * 0.52)

        painter.translate(foot_x, draw_y)
        painter.rotate(self.tilt_deg)
        painter.scale(sx, 1.0)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        tinted_curr = self._get_tinted_sprite(frame, atmosphere)
        dst = QRectF(-target_w * 0.5, -target_h, target_w, target_h)
        if self._prev_clip_frame is not None and self._clip_fade_t < 1.0:
            ease = smoothstep(0.0, 1.0, self._clip_fade_t)
            prev_t = self._get_tinted_sprite(self._prev_clip_frame, atmosphere)
            prev_w = target_h * (prev_t.width() / max(prev_t.height(), 1))
            painter.setOpacity(1.0 - ease)
            painter.drawPixmap(QRectF(-prev_w * 0.5, -target_h, prev_w, target_h), prev_t, QRectF(prev_t.rect()))
            painter.setOpacity(ease)
            painter.drawPixmap(dst, tinted_curr, QRectF(tinted_curr.rect()))
            painter.setOpacity(1.0)
        else:
            painter.drawPixmap(dst, tinted_curr, QRectF(tinted_curr.rect()))
        painter.restore()

        if raining and self.action not in ("sleep", "sit_work"):
            self._paint_umbrella(painter, foot_x + self.facing * 18 * u, draw_y - target_h * 1.02, u, atmosphere)

        self.body_rect = QRectF(foot_x - target_w * 0.36, draw_y - target_h * 0.96, target_w * 0.72, target_h * 0.96)
        self.head_rect = QRectF(foot_x - target_w * 0.28, draw_y - target_h * 0.98, target_w * 0.56, target_h * 0.28)

    def _draw_rig_parts(
        self,
        painter: QPainter,
        rig: AutoRiggedCharacter,
        bones: dict[str, BoneWorld],
        target_h: float,
        atmosphere: AtmospherePalette,
    ) -> None:
        """Desenha as 10 peças RGBA recortadas ligadas aos respectivos ossos FK."""
        px_scale = target_h / max(float(rig.src_height), 1.0)
        for part_name, bone_name in _SKELETAL_Z_ORDER:
            part = rig.parts.get(part_name)
            bone = bones.get(bone_name)
            if part is None or bone is None:
                continue
            tinted = self._get_tinted_sprite(part.pixmap, atmosphere)
            # Conversão de convenção de ângulo (skeleton -> Qt QPainter clockwise):
            # Ossos ascendentes (torso/cabeça): +delta; descendentes (pernas/braços): -delta!
            delta = bone.angle_deg - part.rest_angle
            rot_qt = delta if part.upward else -delta

            painter.save()
            painter.translate(bone.x * target_h, bone.y * target_h)
            painter.rotate(rot_qt)
            dst = QRectF(
                -part.pivot_x * px_scale,
                -part.pivot_y * px_scale,
                tinted.width() * px_scale,
                tinted.height() * px_scale,
            )
            painter.drawPixmap(dst, tinted, QRectF(tinted.rect()))
            painter.restore()

    def _paint_skeletal_rig(
        self,
        painter: QPainter,
        rig: AutoRiggedCharacter,
        bones: dict[str, BoneWorld],
        foot_x: float,
        foot_y: float,
        draw_y: float,
        u: float,
        emotion: EmotionState,
        atmosphere: AtmospherePalette,
        asleep: bool,
        raining: bool,
    ) -> None:
        """Renderiza a personagem articulada pelo esqueleto de 18 ossos em escala humana 1:1 no terraço."""
        target_h = 445.0 * u
        sx = -1.0 if self.facing < 0 else 1.0

        # 1. Reflexo articulado no piso molhado durante a chuva!
        if raining:
            painter.save()
            painter.translate(foot_x, foot_y + 2 * u)
            painter.scale(sx, -0.30)
            painter.setOpacity(0.16)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            self._draw_rig_parts(painter, rig, bones, target_h, atmosphere)
            painter.restore()

        # 2. Aura sutil de carinho
        painter.save()
        if self.caress_glow > 0.05:
            pelvis = bones["pelvis"]
            aura_cx = foot_x + sx * pelvis.x * target_h
            aura_cy = draw_y + (pelvis.y - 0.12) * target_h
            rim_r, rim_g, rim_b = atmosphere.rim_light
            aura = QRadialGradient(QPointF(aura_cx, aura_cy), target_h * 0.52)
            aura.setColorAt(0.0, QColor(rim_r, rim_g, rim_b, int(92 * self.caress_glow)))
            aura.setColorAt(1.0, QColor(rim_r, rim_g, rim_b, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(aura)
            painter.drawEllipse(QPointF(aura_cx, aura_cy), target_h * 0.40, target_h * 0.52)

        # 3. Corpo articulado real (10 peças ligadas aos ossos FK)
        painter.translate(foot_x, draw_y)
        painter.rotate(self.tilt_deg)
        painter.scale(sx, 1.0)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self._draw_rig_parts(painter, rig, bones, target_h, atmosphere)

        # Rubor dinâmico acompanhando o osso da cabeça quando tímida ou recebendo carinho
        blush_a = clamp(max(emotion.blush, self.caress_glow * 0.9), 0.0, 1.0)
        if blush_a > 0.35 and "head" in bones:
            hb = bones["head"]
            cx_h = (hb.x + hb.end_x) * 0.5 * target_h
            cy_h = lerp(hb.y, hb.end_y, 0.46) * target_h
            painter.save()
            painter.translate(cx_h, cy_h)
            painter.rotate(hb.angle_deg)
            painter.setPen(Qt.NoPen)
            for sgn in (-1.0, 1.0):
                bg = QRadialGradient(QPointF(sgn * 13 * u, 0), 12 * u)
                bg.setColorAt(0.0, QColor(255, 115, 155, int(75 * blush_a)))
                bg.setColorAt(1.0, QColor(255, 115, 155, 0))
                painter.setBrush(bg)
                painter.drawEllipse(QPointF(sgn * 13 * u, 0), 12 * u, 7 * u)
            painter.restore()
        painter.restore()

        # 4. Guarda-chuva ancorado EXATAMENTE na mão direita (`forearm_r.end`) quando chove!
        if raining and self.action not in ("sleep", "sit_work") and "forearm_r" in bones:
            hr = bones["forearm_r"]
            hand_sx = foot_x + sx * hr.end_x * target_h
            hand_sy = draw_y + hr.end_y * target_h
            self._paint_umbrella(painter, hand_sx, hand_sy - 72 * u, u, atmosphere)

        # 5. Hitboxes dinâmicos seguindo os ossos da cabeça e pelve (carinho, cliques e emotes precisos!)
        hb = bones["head"]
        head_cx = foot_x + sx * ((hb.x + hb.end_x) * 0.5 * target_h)
        head_top = draw_y + min(hb.y, hb.end_y) * target_h - 14 * u
        head_h = max(68 * u, abs(hb.end_y - hb.y) * target_h + 26 * u)
        self.head_rect = QRectF(head_cx - 46 * u, head_top, 92 * u, head_h)

        pb = bones["pelvis"]
        body_cx = foot_x + sx * pb.x * target_h
        self.body_rect = QRectF(body_cx - 66 * u, head_top, 132 * u, max(120 * u, draw_y - head_top))

    def _paint_grounded_shadow(self, painter: QPainter, foot_x: float, foot_y: float, u: float, lift: float, sun_x_norm: float) -> None:
        """Sombra de contato colada aos pés + sombra direcional projetada no chão (elimina sensação de flutuação!)."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        sh_scale = clamp(1.0 - lift / (125.0 * max(u, 0.1)), 0.55, 1.0)
        dir_shift = (0.5 - sun_x_norm) * 58.0 * u

        # Sombra direcional longa e suave no chão do terraço
        cast_g = QRadialGradient(QPointF(foot_x + dir_shift * 0.55, foot_y + 4 * u), 84 * u * sh_scale)
        cast_g.setColorAt(0.0, QColor(6, 10, 22, int(112 * sh_scale)))
        cast_g.setColorAt(0.65, QColor(6, 10, 22, int(48 * sh_scale)))
        cast_g.setColorAt(1.0, QColor(6, 10, 22, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(cast_g)
        painter.drawEllipse(QPointF(foot_x + dir_shift * 0.55, foot_y + 4 * u), 82 * u * sh_scale, 19 * u * sh_scale)

        # Sombra de oclusão densa colada exatamente sob a sola dos sapatos
        ao_g = QRadialGradient(QPointF(foot_x, foot_y + 1 * u), 48 * u * sh_scale)
        ao_g.setColorAt(0.0, QColor(4, 6, 16, int(185 * sh_scale)))
        ao_g.setColorAt(0.65, QColor(4, 6, 16, int(95 * sh_scale)))
        ao_g.setColorAt(1.0, QColor(4, 6, 16, 0))
        painter.setBrush(ao_g)
        painter.drawEllipse(QPointF(foot_x, foot_y + 1 * u), 46 * u * sh_scale, 11 * u * sh_scale)
        painter.restore()

    def _draw_multiband_pixmap(
        self,
        painter: QPainter,
        tinted: QPixmap,
        target_w: float,
        target_h: float,
        u: float,
        breath: float,
        is_walking: bool,
        wind: float,
        opacity: float = 1.0,
    ) -> None:
        """Fallback multi-banda Live2D para sprites legados (quando ainda não existe rig_base.png)."""
        sw, sh = tinted.width(), tinted.height()
        t = self.time
        breeze = math.sin(t * 2.1) * (1.2 + wind * 0.08) * u

        if is_walking:
            hip_x = math.sin(self.walk_phase) * 3.8 * u
            torso_rot = math.sin(self.walk_phase) * 3.6 + 2.5
            head_rot = math.sin(self.walk_phase - 0.55) * 4.2
            leg_shear = math.sin(self.walk_phase) * 0.055
            stretch_y = 1.0
        elif self.action == "music_sway":
            hip_x = math.sin(t * 5.2) * 5.2 * u
            torso_rot = math.sin(t * 5.2) * 4.8
            head_rot = -math.sin(t * 5.2 - 0.4) * 5.5
            leg_shear = math.sin(t * 5.2) * 0.025
            stretch_y = 1.0
        elif self.action == "stretch":
            arch = math.sin(clamp(self.action_timer / 4.0, 0.0, 1.0) * math.pi)
            hip_x = 0.0
            torso_rot = -arch * 3.2
            head_rot = -arch * 4.5
            leg_shear = 0.0
            stretch_y = 1.0 + arch * 0.048
        elif self.action == "wave":
            wave_s = math.sin(t * 8.5)
            hip_x = math.sin(t * 3.0) * 2.5 * u
            torso_rot = wave_s * 3.4
            head_rot = wave_s * 4.8 + self.look_x * 3.0
            leg_shear = 0.0
            stretch_y = 1.0 + 0.015 * abs(wave_s)
        else:
            hip_x = math.sin(t * 1.15) * 1.6 * u
            torso_rot = math.sin(t * 1.15) * 1.3 + breeze * 0.15
            head_rot = self.look_x * 4.0 + math.sin(t * 1.5 - 0.6) * 1.6
            leg_shear = 0.0
            stretch_y = 1.0

        bands = [
            (0.60, 1.00, 0.0,           0.0,       leg_shear, 1.0),
            (0.31, 0.64, hip_x,         torso_rot, 0.0,       (1.0 + breath * 0.014) * stretch_y),
            (0.00, 0.35, hip_x * 1.35 + breeze * 0.35, torso_rot * 0.6 + head_rot, 0.0, (1.0 + breath * 0.010) * stretch_y),
        ]

        painter.setOpacity(opacity)
        for v0, v1, ox, rot_deg, shear_x, sy_mul in bands:
            painter.save()
            pivot_y = -target_h * (1.0 - v1)
            painter.translate(ox, pivot_y)
            if rot_deg != 0.0:
                painter.rotate(rot_deg)
            if shear_x != 0.0:
                painter.shear(shear_x, 0.0)
            painter.scale(1.0, sy_mul)
            band_h = target_h * (v1 - v0)
            dst = QRectF(-target_w * 0.5, -band_h, target_w, band_h)
            src = QRectF(0.0, sh * v0, sw, sh * (v1 - v0))
            painter.drawPixmap(dst, tinted, src)
            painter.restore()
        painter.setOpacity(1.0)

    def _paint_multiband_ai_sprite(
        self,
        painter: QPainter,
        sprite: QPixmap,
        foot_x: float,
        foot_y: float,
        draw_y: float,
        u: float,
        breath: float,
        is_walking: bool,
        emotion: EmotionState,
        atmosphere: AtmospherePalette,
        wind: float,
        raining: bool,
    ) -> None:
        target_h = 435.0 * u
        aspect = sprite.width() / max(sprite.height(), 1)
        target_w = target_h * aspect

        if raining:
            painter.save()
            painter.translate(foot_x, foot_y + 2 * u)
            painter.scale(-1.0 if self.facing < 0 else 1.0, -0.32)
            painter.setOpacity(0.16)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(QRectF(-target_w * 0.5, -target_h, target_w, target_h), sprite, QRectF(sprite.rect()))
            painter.restore()

        painter.save()
        if self.caress_glow > 0.05:
            rim_r, rim_g, rim_b = atmosphere.rim_light
            aura = QRadialGradient(QPointF(foot_x, draw_y - target_h * 0.55), target_h * 0.55)
            aura.setColorAt(0.0, QColor(rim_r, rim_g, rim_b, int(95 * self.caress_glow)))
            aura.setColorAt(1.0, QColor(rim_r, rim_g, rim_b, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(aura)
            painter.drawEllipse(QPointF(foot_x, draw_y - target_h * 0.55), target_h * 0.42, target_h * 0.55)

        painter.translate(foot_x, draw_y)
        painter.rotate(self.tilt_deg)
        sx = -1.0 if self.facing < 0 else 1.0
        sy = 0.94 if self.action in ("sit_work", "sit_relax") else 1.0
        painter.scale(sx, sy)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        tinted_curr = self._get_tinted_sprite(sprite, atmosphere)
        if self._prev_sprite is not None and self._sprite_fade_t < 1.0:
            ease = smoothstep(0.0, 1.0, self._sprite_fade_t)
            tinted_prev = self._get_tinted_sprite(self._prev_sprite, atmosphere)
            self._draw_multiband_pixmap(painter, tinted_prev, target_w, target_h, u, breath, is_walking, wind, opacity=1.0 - ease)
            self._draw_multiband_pixmap(painter, tinted_curr, target_w, target_h, u, breath, is_walking, wind, opacity=ease)
        else:
            self._draw_multiband_pixmap(painter, tinted_curr, target_w, target_h, u, breath, is_walking, wind, opacity=1.0)
        painter.restore()

        if raining and self.action not in ("sleep", "sit_work"):
            self._paint_umbrella(painter, foot_x + self.facing * 12 * u, draw_y - target_h * 1.05, u, atmosphere)

        self.body_rect = QRectF(foot_x - target_w * 0.40, draw_y - target_h * 0.96, target_w * 0.80, target_h * 0.96)
        self.head_rect = QRectF(foot_x - target_w * 0.34, draw_y - target_h * 0.98, target_w * 0.68, target_h * 0.28)

    def _draw_capsule_bone(self, painter: QPainter, bone: BoneWorld, H: float, thickness: float, fill: QColor, outline: QColor) -> None:
        p0 = QPointF(bone.x * H, bone.y * H)
        p1 = QPointF(bone.end_x * H, bone.end_y * H)
        pen = QPen(outline, thickness + 2.4, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(p0, p1)
        pen_in = QPen(fill, thickness, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen_in)
        painter.drawLine(p0, p1)

    def _paint_skeletal_procedural(
        self,
        painter: QPainter,
        bones: dict[str, BoneWorld],
        foot_x: float,
        draw_y: float,
        u: float,
        emotion: EmotionState,
        atmosphere: AtmospherePalette,
        asleep: bool,
        raining: bool,
    ) -> None:
        """Avatar anime maduro vetorial 100% guiado pelo esqueleto de 18 ossos (funciona mesmo sem PNG!)."""
        H = 390.0 * u
        sx = -1.0 if self.facing < 0 else 1.0
        outfit_cfg = self.persona.outfits.get(self.outfit) or self.persona.outfits["casual"]
        hair = QColor(*self.persona.hair_color)
        hair_hi = QColor(*self.persona.hair_highlight)
        eye_c = QColor(*self.persona.eye_color)
        skin = QColor(*self.persona.skin_color)
        c_prim = QColor(*outfit_cfg["primary"])
        c_trim = QColor(*outfit_cfg["trim"])
        rim_c = QColor(*atmosphere.rim_light)
        ink = QColor(42, 34, 54, 210)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(foot_x, draw_y)
        painter.rotate(self.tilt_deg)
        painter.scale(sx, 1.0)

        # Cabelo traseiro com física de mola (`hair_back`)
        hb_back = bones["hair_back"]
        bh = QPainterPath()
        bh.moveTo((hb_back.x - 0.08) * H, hb_back.y * H)
        bh.quadTo((hb_back.end_x - 0.14) * H, lerp(hb_back.y, hb_back.end_y, 0.6) * H, (hb_back.end_x - 0.09) * H, hb_back.end_y * H)
        bh.lineTo((hb_back.end_x + 0.09) * H, hb_back.end_y * H)
        bh.quadTo((hb_back.end_x + 0.14) * H, lerp(hb_back.y, hb_back.end_y, 0.6) * H, (hb_back.x + 0.08) * H, hb_back.y * H)
        bh.closeSubpath()
        painter.setBrush(hair.darker(112))
        painter.setPen(QPen(rim_c, 1.4 * u))
        painter.drawPath(bh)

        # Braço esquerdo (atrás do tronco)
        self._draw_capsule_bone(painter, bones["upper_arm_l"], H, 12 * u, skin.darker(104), ink)
        self._draw_capsule_bone(painter, bones["forearm_l"], H, 10.5 * u, skin.darker(104), ink)

        # Pernas articuladas (coxas + canelas + sapatos)
        for thigh_k, shin_k, shade in (("thigh_l", "shin_l", 106), ("thigh_r", "shin_r", 100)):
            tb = bones[thigh_k]
            sb = bones[shin_k]
            self._draw_capsule_bone(painter, tb, H, 19 * u, skin.darker(shade), ink)
            self._draw_capsule_bone(painter, sb, H, 14 * u, c_prim.darker(140 if shade > 100 else 128), ink)
            painter.setPen(Qt.NoPen)
            painter.setBrush(c_prim.darker(160))
            painter.drawEllipse(QPointF(sb.end_x * H + 4 * u, sb.end_y * H - 4 * u), 10 * u, 6 * u)

        # Tronco + vestido + saia com física de mola
        pel = bones["pelvis"]
        ch = bones["chest"]
        sk = bones["skirt"]
        dress = QPainterPath()
        dress.moveTo((ch.end_x - 0.075) * H, ch.end_y * H)
        dress.lineTo((ch.end_x + 0.075) * H, ch.end_y * H)
        dress.quadTo((pel.x + 0.06) * H, pel.y * H, (sk.end_x + 0.11) * H, sk.end_y * H)
        dress.lineTo((sk.end_x - 0.11) * H, sk.end_y * H)
        dress.quadTo((pel.x - 0.06) * H, pel.y * H, (ch.end_x - 0.075) * H, ch.end_y * H)
        dress.closeSubpath()
        painter.setBrush(c_prim)
        painter.setPen(QPen(c_trim, 1.5 * u))
        painter.drawPath(dress)

        # Cabeça articulada no osso `head`
        hd = bones["head"]
        painter.save()
        painter.translate((hd.x + hd.end_x) * 0.5 * H, (hd.y + hd.end_y) * 0.5 * H)
        painter.rotate(hd.angle_deg)
        painter.setBrush(skin)
        painter.setPen(QPen(QColor(82, 60, 68, 150), 1.4 * u))
        painter.drawEllipse(QPointF(0, 0), 30 * u, 32 * u)
        for sign in (-1, 1):
            ex = sign * 11.5 * u + 2 * u
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255))
            painter.drawEllipse(QPointF(ex, 2 * u), 7.0 * u, 8.0 * u * (1.0 - self.blink_amount))
            if self.blink_amount < 0.7:
                painter.setBrush(eye_c)
                painter.drawEllipse(QPointF(ex + 1 * u, 2 * u), 5.0 * u, 6.0 * u * (1.0 - self.blink_amount))
        bangs = QPainterPath()
        bangs.moveTo(-32 * u, -6 * u)
        bangs.cubicTo(-34 * u, -44 * u, 34 * u, -44 * u, 32 * u, -6 * u)
        bangs.lineTo(22 * u, 9 * u)
        bangs.lineTo(0, -10 * u)
        bangs.lineTo(-22 * u, 9 * u)
        bangs.closeSubpath()
        painter.setBrush(hair_hi)
        painter.setPen(QPen(rim_c, 1.2 * u))
        painter.drawPath(bangs)
        painter.restore()

        # Braço direito (na frente do tronco: aceno, guarda-chuva, digitação!)
        self._draw_capsule_bone(painter, bones["upper_arm_r"], H, 12.5 * u, skin, ink)
        self._draw_capsule_bone(painter, bones["forearm_r"], H, 11 * u, skin, ink)
        painter.restore()

        if raining and self.action not in ("sleep", "sit_work"):
            hr = bones["forearm_r"]
            self._paint_umbrella(painter, foot_x + sx * hr.end_x * H, draw_y + hr.end_y * H - 68 * u, u, atmosphere)

        hd = bones["head"]
        head_cx = foot_x + sx * ((hd.x + hd.end_x) * 0.5 * H)
        head_top = draw_y + min(hd.y, hd.end_y) * H - 14 * u
        self.head_rect = QRectF(head_cx - 42 * u, head_top, 84 * u, 78 * u)
        self.body_rect = QRectF(foot_x - 54 * u, head_top, 108 * u, max(120 * u, draw_y - head_top))

    def _paint_umbrella(self, painter: QPainter, cx: float, cy: float, u: float, atmo: AtmospherePalette) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(cx, cy)
        painter.rotate(-8 * self.facing)
        painter.setPen(QPen(QColor(225, 232, 245, 220), 2.5 * u))
        painter.drawLine(QPointF(0, -6 * u), QPointF(0, 82 * u))
        dome = QPainterPath()
        dome.moveTo(-72 * u, 8 * u)
        dome.cubicTo(-58 * u, -48 * u, 58 * u, -48 * u, 72 * u, 8 * u)
        dome.quadTo(35 * u, -2 * u, 0, 6 * u)
        dome.quadTo(-35 * u, -2 * u, -72 * u, 8 * u)
        g = QLinearGradient(0, -40 * u, 0, 10 * u)
        g.setColorAt(0.0, QColor(175, 224, 255, 220))
        g.setColorAt(1.0, QColor(115, 178, 242, 170))
        painter.setBrush(g)
        painter.setPen(QPen(QColor(235, 248, 255, 225), 1.8 * u))
        painter.drawPath(dome)
        painter.restore()

    def _paint_ro_emote_balloon(self, painter: QPainter, cx: float, cy: float, u: float) -> None:
        t = clamp(self.emote_life / max(self.emote_max, 0.01))
        pop = smoothstep(0.0, 0.14, t) * (1.0 - smoothstep(0.82, 1.0, t))
        if pop <= 0.02:
            return
        sc = (0.75 + 0.30 * pop) * u
        bob = math.sin(self.time * 6.5) * 3.0 * u

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setOpacity(pop)
        painter.translate(cx, cy - 26 * u + bob)

        bw, bh = 54 * sc, 42 * sc
        rect = QRectF(-bw * 0.5, -bh * 0.5, bw, bh)
        painter.setBrush(QColor(255, 255, 255, 242))
        painter.setPen(QPen(QColor(62, 74, 112, 230), 2.0 * sc))
        painter.drawRoundedRect(rect, 12 * sc, 12 * sc)
        tail = QPainterPath()
        tail.moveTo(-6 * sc, bh * 0.5 - 1)
        tail.lineTo(0, bh * 0.5 + 9 * sc)
        tail.lineTo(6 * sc, bh * 0.5 - 1)
        painter.drawPath(tail)

        k = self.emote_kind
        if k == "heart":
            s = 14 * sc
            hp = QPainterPath()
            hp.moveTo(0, s * 0.45)
            hp.cubicTo(-s * 0.75, -s * 0.15, -s * 0.6, -s * 0.75, 0, -s * 0.25)
            hp.cubicTo(s * 0.6, -s * 0.75, s * 0.75, -s * 0.15, 0, s * 0.45)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 86, 146))
            painter.drawPath(hp)
        elif k == "exclamation":
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 110, 68))
            painter.drawRoundedRect(QRectF(-3 * sc, -13 * sc, 6 * sc, 16 * sc), 3 * sc, 3 * sc)
            painter.drawEllipse(QPointF(0, 9 * sc), 3.4 * sc, 3.4 * sc)
        elif k == "music":
            painter.setPen(QPen(QColor(68, 152, 255), 2.4 * sc))
            painter.setBrush(QColor(68, 152, 255))
            painter.drawEllipse(QPointF(-5 * sc, 7 * sc), 4.5 * sc, 3.5 * sc)
            painter.drawLine(QPointF(-1 * sc, 6 * sc), QPointF(-1 * sc, -10 * sc))
            painter.drawLine(QPointF(-1 * sc, -10 * sc), QPointF(8 * sc, -7 * sc))
        elif k == "sparkle":
            s = 13 * sc
            sp = QPainterPath()
            sp.moveTo(0, -s)
            sp.quadTo(0, 0, s, 0)
            sp.quadTo(0, 0, 0, s)
            sp.quadTo(0, 0, -s, 0)
            sp.quadTo(0, 0, 0, -s)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 198, 46))
            painter.drawPath(sp)
        else:
            font = QFont("Segoe UI", max(9, int(12 * sc)))
            font.setBold(True)
            painter.setFont(font)
            txt = "Zzz" if k == "zzz" else ("?" if k == "question" else "...")
            painter.setPen(QColor(72, 92, 168))
            painter.drawText(rect, Qt.AlignCenter, txt)
        painter.restore()

    def _paint_portrait_mode(
        self,
        painter: QPainter,
        canvas_w: int,
        canvas_h: int,
        x_ratio: float,
        scale: float,
        emotion: EmotionState,
        atmosphere: AtmospherePalette,
        parallax_x: float,
        parallax_y: float,
        asleep: bool,
    ) -> None:
        breath = math.sin(self.time * (1.45 if asleep else 2.25))
        sway = math.sin(self.time * 1.1) * (1.2 if not asleep else 0.4)
        anchor_x = canvas_w * x_ratio + parallax_x * 18.0
        anchor_y = canvas_h * 0.985 + self.bounce_y + parallax_y * 8.0
        key = self._resolve_portrait_sprite_key("sleepy" if asleep else emotion.mood)
        if key is None:
            self._paint_skeletal_procedural(
                painter, self.skeleton.bones, anchor_x, anchor_y - 20, (canvas_h / 1080.0) * scale * 1.3, emotion, atmosphere, asleep, False
            )
            return
        if key != self._current_sprite_key:
            if self._current_sprite_key is not None and self._current_sprite_key in self._sprites:
                self._prev_sprite = self._sprites[self._current_sprite_key]
                self._sprite_fade_t = 0.0
            self._current_sprite_key = key
        sprite = self._sprites[key]
        target_h = canvas_h * 0.76 * scale
        target_w = target_h * (sprite.width() / max(sprite.height(), 1))
        painter.save()
        painter.translate(anchor_x, anchor_y)
        painter.rotate(self.tilt_deg + sway * 0.45 + self.look_x * 1.8)
        painter.scale(1.0 - breath * 0.006, 1.0 + breath * 0.011)
        draw_rect = QRectF(-target_w * 0.5, -target_h, target_w, target_h)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(draw_rect, self._get_tinted_sprite(sprite, atmosphere), QRectF(sprite.rect()))
        painter.restore()
        self.body_rect = QRectF(anchor_x - target_w * 0.36, anchor_y - target_h * 0.94, target_w * 0.72, target_h * 0.92)
        self.head_rect = QRectF(anchor_x - target_w * 0.28, anchor_y - target_h * 0.96, target_w * 0.56, target_h * 0.30)
