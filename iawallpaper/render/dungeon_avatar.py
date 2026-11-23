"""DUNGEON AVATAR — Gerador 3D estilizado de alta definição (Tree of Savior × Curvas Maduras).

Constrói em memória (em < 120 ms, 100% compatível com `VrmModel`, `VrmAnimator` e `VrmRenderer`)
avatares 3D detalhados com:
- Proporções elegantes (~4.8 cabeças) equilibrando legibilidade facial de *Tree of Savior* com
  curvas maduras (busto esculpido, cintura fina ampulheta, quadris largos e coxas grossas).
- Rosto anime 1024×1024 pintado com camadas suaves (olhos em gradiente tipo joia, cílios superiores
  arqueados, sobrancelhas expressivas, rubor difuso nas bochechas/nariz, sorriso brilhante) +
  geometria facial esculpida (queixo delicado, nariz anime sutil, orelhas élficas longas em 3D).
- Cabelo multicamadas ondulado com textura pintada de fios (512×512) + anel de brilho anime e
  física `SpringBone`.
- Arquétipos base modulares para as 4 garotas iniciais:
  1. `elfa_loira` (Lyra — Elfa Loira: orelhas élficas longas, pele bronzeada dourada, olhos esmeralda,
     cabelos loiros ondulados, corpete marrom com rendas brancas, saia fenda frontal com laço e botas).
  2. `humana_ruiva` (Freya — Humana Ruiva: pele clara corada, trança lateral ruiva cobre, olhos verde-oliva,
     corpete preto e filigrana dourada com saia longa).
  3. `androide_rosa` (Airi — Androide Rosa: cabelo rosa-pastel ondulado com franja assimétrica, olhos safira,
     choker de renda e traje cyber-idol rosa/branco brilhante).
  4. `vampira_negra` (Lilith — Vampira Cabelos Pretos: cabelo preto-esmeralda em rabo baixo, sardas sutis,
     olhos jade/carmesim, camisa branca ajustada e minissaia plissada preta).
"""

from dataclasses import dataclass
import math
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..core.persona import Persona
from .vrm_loader import (
    VrmMaterial,
    VrmModel,
    VrmNode,
    VrmPrimitive,
    VrmSkin,
    VrmSpringChain,
)


@dataclass(frozen=True)
class AvatarArchetype:
    id: str
    label: str
    skin_rgb: tuple[int, int, int]
    skin_shade: tuple[float, float, float]
    blush_rgb: tuple[int, int, int]
    hair_rgb: tuple[int, int, int]
    hair_root_rgb: tuple[int, int, int]
    hair_tip_rgb: tuple[int, int, int]
    hair_shade: tuple[float, float, float]
    eye_rgb: tuple[int, int, int]
    brow_rgb: tuple[int, int, int]
    lip_rgb: tuple[int, int, int]
    suit_rgb: tuple[int, int, int]
    trim_rgb: tuple[int, int, int]
    accent_rgb: tuple[int, int, int]
    boot_rgb: tuple[int, int, int]
    skirt_rgb: tuple[int, int, int]
    elf_ears: bool = False
    freckles: bool = False
    hair_style: str = "wavy_long"  # wavy_long | side_braid | asym_pink | low_ponytail
    outfit_style: str = "elf_corset"  # elf_corset | gold_corset | cyber_idol | blouse_skirt


ARCHETYPES: dict[str, AvatarArchetype] = {
    "elfa_loira": AvatarArchetype(
        id="elfa_loira",
        label="Lyra — Elfa Loira",
        skin_rgb=(232, 168, 130),
        skin_shade=(0.76, 0.48, 0.40),
        blush_rgb=(228, 86, 74),
        hair_rgb=(246, 218, 150),
        hair_root_rgb=(210, 168, 96),
        hair_tip_rgb=(254, 236, 186),
        hair_shade=(0.74, 0.56, 0.36),
        eye_rgb=(42, 188, 92),
        brow_rgb=(156, 108, 62),
        lip_rgb=(222, 118, 106),
        suit_rgb=(84, 50, 38),
        trim_rgb=(248, 244, 236),
        accent_rgb=(218, 172, 92),
        boot_rgb=(76, 46, 36),
        skirt_rgb=(72, 42, 32),
        elf_ears=True,
        freckles=False,
        hair_style="wavy_long",
        outfit_style="elf_corset",
    ),
    "humana_ruiva": AvatarArchetype(
        id="humana_ruiva",
        label="Freya — Humana Ruiva",
        skin_rgb=(248, 210, 192),
        skin_shade=(0.82, 0.58, 0.54),
        blush_rgb=(236, 98, 96),
        hair_rgb=(208, 96, 52),
        hair_root_rgb=(146, 54, 28),
        hair_tip_rgb=(236, 134, 78),
        hair_shade=(0.66, 0.32, 0.24),
        eye_rgb=(112, 152, 68),
        brow_rgb=(146, 62, 36),
        lip_rgb=(228, 118, 116),
        suit_rgb=(32, 26, 34),
        trim_rgb=(234, 188, 92),
        accent_rgb=(246, 206, 114),
        boot_rgb=(34, 26, 34),
        skirt_rgb=(28, 24, 32),
        elf_ears=False,
        freckles=False,
        hair_style="side_braid",
        outfit_style="gold_corset",
    ),
    "androide_rosa": AvatarArchetype(
        id="androide_rosa",
        label="Airi — Androide Rosa",
        skin_rgb=(252, 224, 214),
        skin_shade=(0.86, 0.66, 0.68),
        blush_rgb=(244, 118, 152),
        hair_rgb=(250, 166, 194),
        hair_root_rgb=(220, 118, 154),
        hair_tip_rgb=(255, 204, 222),
        hair_shade=(0.78, 0.48, 0.62),
        eye_rgb=(68, 156, 246),
        brow_rgb=(208, 108, 140),
        lip_rgb=(242, 128, 146),
        suit_rgb=(248, 198, 216),
        trim_rgb=(255, 244, 250),
        accent_rgb=(110, 222, 255),
        boot_rgb=(244, 236, 246),
        skirt_rgb=(242, 178, 204),
        elf_ears=False,
        freckles=False,
        hair_style="asym_pink",
        outfit_style="cyber_idol",
    ),
    "vampira_negra": AvatarArchetype(
        id="vampira_negra",
        label="Lilith — Vampira",
        skin_rgb=(244, 212, 198),
        skin_shade=(0.80, 0.58, 0.58),
        blush_rgb=(224, 102, 98),
        hair_rgb=(42, 48, 46),
        hair_root_rgb=(24, 28, 30),
        hair_tip_rgb=(68, 76, 70),
        hair_shade=(0.30, 0.34, 0.38),
        eye_rgb=(76, 148, 126),
        brow_rgb=(54, 46, 44),
        lip_rgb=(212, 114, 112),
        suit_rgb=(242, 244, 248),
        trim_rgb=(218, 224, 234),
        accent_rgb=(188, 52, 86),
        boot_rgb=(26, 24, 30),
        skirt_rgb=(26, 26, 32),
        elf_ears=False,
        freckles=True,
        hair_style="low_ponytail",
        outfit_style="blouse_skirt",
    ),
}


def _norm_rows(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.maximum(n, 1e-6)


class _MeshBuilder:
    """Acumulador de geometria 3D skinned de alta densidade com normais suaves."""

    def __init__(self, material_index: int, skin_index: int = 0):
        self.material_index = material_index
        self.skin_index = skin_index
        self._pos: list[np.ndarray] = []
        self._norm: list[np.ndarray] = []
        self._uv: list[np.ndarray] = []
        self._joints: list[np.ndarray] = []
        self._weights: list[np.ndarray] = []
        self._indices: list[np.ndarray] = []
        self._vcount = 0

    def add_grid(
        self,
        pos_grid: np.ndarray,
        uv_grid: np.ndarray,
        joints_grid: np.ndarray,
        weights_grid: np.ndarray,
        wrap_u: bool = True,
        flip_winding: bool = False,
        custom_normals: np.ndarray | None = None,
    ) -> None:
        rows, cols, _ = pos_grid.shape
        v_start = self._vcount

        if custom_normals is not None:
            norms = custom_normals.reshape(-1, 3).astype(np.float32)
        else:
            dr = np.zeros_like(pos_grid)
            dr[1:-1] = pos_grid[2:] - pos_grid[:-2]
            dr[0] = pos_grid[1] - pos_grid[0]
            dr[-1] = pos_grid[-1] - pos_grid[-2]

            dc = np.zeros_like(pos_grid)
            if wrap_u:
                dc[:, 1:-1] = pos_grid[:, 2:] - pos_grid[:, :-2]
                dc[:, 0] = pos_grid[:, 1] - pos_grid[:, -2]
                dc[:, -1] = pos_grid[:, 1] - pos_grid[:, -2]
            else:
                dc[:, 1:-1] = pos_grid[:, 2:] - pos_grid[:, :-2]
                dc[:, 0] = pos_grid[:, 1] - pos_grid[:, 0]
                dc[:, -1] = pos_grid[:, -1] - pos_grid[:, -2]

            n_grid = np.cross(dc, dr)
            if flip_winding:
                n_grid = -n_grid
            norms = _norm_rows(n_grid.reshape(-1, 3)).astype(np.float32)

        idx_list: list[int] = []
        for r in range(rows - 1):
            for c in range(cols - 1):
                i00 = v_start + r * cols + c
                i01 = i00 + 1
                i10 = i00 + cols
                i11 = i10 + 1
                if not flip_winding:
                    idx_list.extend([i00, i01, i11, i00, i11, i10])
                else:
                    idx_list.extend([i00, i11, i01, i00, i10, i11])

        self._pos.append(pos_grid.reshape(-1, 3).astype(np.float32))
        self._norm.append(norms)
        self._uv.append(uv_grid.reshape(-1, 2).astype(np.float32))
        self._joints.append(joints_grid.reshape(-1, 4).astype(np.float32))
        self._weights.append(weights_grid.reshape(-1, 4).astype(np.float32))
        self._indices.append(np.array(idx_list, dtype=np.uint32))
        self._vcount += rows * cols

    def add_loft(
        self,
        rings: list[tuple[np.ndarray, float, float, float, float, int, int, float]],
        n_seg: int = 32,
        shape_fn: Callable[[float, float], tuple[float, float]] | None = None,
        cap_bottom: bool = False,
        cap_top: bool = False,
    ) -> None:
        ring_list = list(rings)
        if cap_bottom and ring_list:
            c0, _, _, v0, tx0, j0, j1, w1 = ring_list[0]
            ring_list.insert(0, (c0 - np.array([0.0, 0.003, 0.0], dtype=np.float32), 0.002, 0.002, v0, tx0, j0, j1, w1))
        if cap_top and ring_list:
            c1, _, _, v1, tx1, j0, j1, w1 = ring_list[-1]
            ring_list.append((c1 + np.array([0.0, 0.003, 0.0], dtype=np.float32), 0.002, 0.002, v1, tx1, j0, j1, w1))

        n_r = len(ring_list)
        n_c = n_seg + 1
        pos = np.zeros((n_r, n_c, 3), dtype=np.float32)
        uv = np.zeros((n_r, n_c, 2), dtype=np.float32)
        jts = np.zeros((n_r, n_c, 4), dtype=np.float32)
        wts = np.zeros((n_r, n_c, 4), dtype=np.float32)

        for r, (center, rx, rz, v_coord, z_off, j0, j1, w1) in enumerate(ring_list):
            w0 = 1.0 - w1
            for c in range(n_c):
                u = c / n_seg
                theta = (u - 0.5) * math.tau
                sx = math.sin(theta)
                cz = math.cos(theta)
                m_x, m_z = shape_fn(theta, v_coord) if shape_fn else (1.0, 1.0)
                pos[r, c, 0] = center[0] + sx * rx * m_x
                pos[r, c, 1] = center[1]
                pos[r, c, 2] = center[2] + z_off + cz * rz * m_z
                uv[r, c, 0] = u
                uv[r, c, 1] = v_coord
                jts[r, c] = (float(j0), float(j1), 0.0, 0.0)
                wts[r, c] = (w0, w1, 0.0, 0.0)

        self.add_grid(pos, uv, jts, wts, wrap_u=True, flip_winding=False)

    def add_ellipsoid(
        self,
        center: tuple[float, float, float],
        radii: tuple[float, float, float],
        joint_idx: int,
        n_lat: int = 24,
        n_lon: int = 36,
        deform_fn: Callable[[float, float, float, float, float], tuple[float, float, float]] | None = None,
        joint_b: int = 0,
        weight_b_fn: Callable[[float], float] | None = None,
    ) -> None:
        cx, cy, cz = center
        rx, ry, rz = radii
        pos = np.zeros((n_lat + 1, n_lon + 1, 3), dtype=np.float32)
        uv = np.zeros((n_lat + 1, n_lon + 1, 2), dtype=np.float32)
        jts = np.zeros((n_lat + 1, n_lon + 1, 4), dtype=np.float32)
        wts = np.zeros((n_lat + 1, n_lon + 1, 4), dtype=np.float32)

        for r in range(n_lat + 1):
            v = r / n_lat
            phi = (v - 0.5) * math.pi
            cp = math.cos(phi)
            sp = math.sin(phi)
            wb = weight_b_fn(v) if weight_b_fn else 0.0
            for c in range(n_lon + 1):
                u = c / n_lon
                theta = (u - 0.5) * math.tau
                x = math.sin(theta) * cp * rx
                y = sp * ry
                z = math.cos(theta) * cp * rz
                if deform_fn is not None:
                    x, y, z = deform_fn(x, y, z, u, v)
                pos[r, c] = (cx + x, cy + y, cz + z)
                uv[r, c] = (u, 1.0 - v)
                jts[r, c] = (float(joint_idx), float(joint_b), 0.0, 0.0)
                wts[r, c] = (1.0 - wb, wb, 0.0, 0.0)

        self.add_grid(pos, uv, jts, wts, wrap_u=True, flip_winding=False)

    def add_ribbon(
        self,
        spine_pts: list[tuple[np.ndarray, float, float, int, int, float]],
        n_across: int = 6,
        thickness: float = 0.018,
        arch_z: float = 0.014,
        side_axis: np.ndarray | None = None,
    ) -> None:
        if side_axis is None:
            side_axis = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        side_axis = side_axis / max(float(np.linalg.norm(side_axis)), 1e-6)

        n_r = len(spine_pts)
        n_c = n_across * 2 + 1
        pos = np.zeros((n_r, n_c, 3), dtype=np.float32)
        uv = np.zeros((n_r, n_c, 2), dtype=np.float32)
        jts = np.zeros((n_r, n_c, 4), dtype=np.float32)
        wts = np.zeros((n_r, n_c, 4), dtype=np.float32)

        for r, (pt, half_w, thick_mul, j0, j1, w1) in enumerate(spine_pts):
            if r == 0:
                tang = spine_pts[1][0] - pt
            elif r == n_r - 1:
                tang = pt - spine_pts[r - 1][0]
            else:
                tang = spine_pts[r + 1][0] - spine_pts[r - 1][0]
            tang = tang / max(float(np.linalg.norm(tang)), 1e-6)
            norm_out = np.cross(side_axis, tang)
            n_len = float(np.linalg.norm(norm_out))
            if n_len < 1e-5:
                norm_out = np.array([0.0, 0.0, 1.0], dtype=np.float32)
            else:
                norm_out /= n_len
            right_v = np.cross(tang, norm_out)
            right_v /= max(float(np.linalg.norm(right_v)), 1e-6)

            v_coord = r / max(n_r - 1, 1)
            th = thickness * thick_mul
            w0 = 1.0 - w1
            for c in range(n_c):
                u = c / (n_c - 1)
                ang = u * math.tau
                lx = math.cos(ang) * half_w
                lz = math.sin(ang) * th + (1.0 - (math.cos(ang) ** 2)) * arch_z * thick_mul
                pos[r, c] = pt + right_v * lx + norm_out * lz
                uv[r, c] = (u, v_coord)
                jts[r, c] = (float(j0), float(j1), 0.0, 0.0)
                wts[r, c] = (w0, w1, 0.0, 0.0)

        self.add_grid(pos, uv, jts, wts, wrap_u=True, flip_winding=False)

    def add_elf_ear(self, side: float, base_xyz: tuple[float, float, float], joint_idx: int) -> None:
        """Esculpe uma orelha élfica longa, curva e pontiaguda em 3D (ícone da Lyra / Elfa Loira!)."""
        bx, by, bz = base_xyz
        # 8 seções da base até a ponta afiada apontando para fora (+X*side), levemente para cima (+Y) e trás (-Z)
        stations = [
            (0.000, 0.000,  0.000, 0.026, 0.015),
            (0.028, 0.008, -0.006, 0.028, 0.014),
            (0.062, 0.022, -0.016, 0.025, 0.012),
            (0.098, 0.038, -0.026, 0.020, 0.010),
            (0.132, 0.056, -0.036, 0.014, 0.007),
            (0.162, 0.074, -0.044, 0.008, 0.005),
            (0.184, 0.088, -0.050, 0.002, 0.002),
        ]
        n_r = len(stations)
        n_seg = 14
        pos = np.zeros((n_r, n_seg + 1, 3), dtype=np.float32)
        uv = np.zeros((n_r, n_seg + 1, 2), dtype=np.float32)
        jts = np.zeros((n_r, n_seg + 1, 4), dtype=np.float32)
        wts = np.zeros((n_r, n_seg + 1, 4), dtype=np.float32)

        for r, (dx, dy, dz, ry, rz) in enumerate(stations):
            v_c = r / max(n_r - 1, 1)
            for c in range(n_seg + 1):
                u = c / n_seg
                ang = u * math.tau
                ly = math.cos(ang) * ry
                lz = math.sin(ang) * rz
                # Sulco côncavo sutil na frente da orelha (+Z)
                if lz > 0 and 0.15 < v_c < 0.78:
                    lz *= 0.45
                pos[r, c] = (bx + side * dx, by + dy + ly, bz + dz + lz)
                # UV mapeia v_c=0 (base pele) -> v_c=1 (ponta rosada luminosa!)
                uv[r, c] = (u, v_c)
                jts[r, c] = (float(joint_idx), 0.0, 0.0, 0.0)
                wts[r, c] = (1.0, 0.0, 0.0, 0.0)

        self.add_grid(pos, uv, jts, wts, wrap_u=True, flip_winding=(side < 0))

    def add_open_skirt(
        self,
        y_top: float,
        y_bot: float,
        rx_top: float,
        rz_top: float,
        rx_bot: float,
        rz_bot: float,
        slit_half_angle_deg: float,
        j_hips: int,
        j_l_leg: int,
        j_r_leg: int,
        n_rows: int = 10,
        n_cols: int = 36,
        pleats: int = 0,
    ) -> None:
        """Gera uma saia 3D fluida aberta na frente (ou plissada fechada se slit=0) com dobra orgânica nas coxas."""
        slit_rad = math.radians(slit_half_angle_deg)
        # Ângulo 0 = frente (+Z); varremos de +slit_rad até 2*pi - slit_rad (deixando fenda frontal limpa!)
        pos = np.zeros((n_rows, n_cols, 3), dtype=np.float32)
        uv = np.zeros((n_rows, n_cols, 2), dtype=np.float32)
        jts = np.zeros((n_rows, n_cols, 4), dtype=np.float32)
        wts = np.zeros((n_rows, n_cols, 4), dtype=np.float32)

        for r in range(n_rows):
            v = r / max(n_rows - 1, 1)  # 0 = cintura, 1 = barra inferior
            y = y_top + (y_bot - y_top) * v
            # Curva graciosa de saia (abre suavemente sobre os quadris)
            ease = v ** 0.85
            rx = rx_top + (rx_bot - rx_top) * ease
            rz = rz_top + (rz_bot - rz_top) * ease
            # Na fenda frontal, a abertura cresce ligeiramente para baixo (V invertido elegante!)
            cur_slit = slit_rad * (0.45 + 0.72 * v)
            for c in range(n_cols):
                u = c / max(n_cols - 1, 1)
                theta = cur_slit + u * (math.tau - 2.0 * cur_slit)
                wave = 1.0 + (0.045 * math.sin(theta * pleats) * v if pleats > 0 else 0.018 * math.sin(theta * 5.0) * v)
                x = math.sin(theta) * rx * wave
                z = math.cos(theta) * rz * wave
                pos[r, c] = (x, y, z)
                uv[r, c] = (u, v)
                # Peso suave de quadril + perna correspondente na barra inferior para acompanhar passos!
                w_leg = 0.42 * (v ** 1.3)
                leg_j = j_l_leg if x >= 0 else j_r_leg
                jts[r, c] = (float(j_hips), float(leg_j), 0.0, 0.0)
                wts[r, c] = (1.0 - w_leg, w_leg, 0.0, 0.0)

        self.add_grid(pos, uv, jts, wts, wrap_u=(slit_half_angle_deg <= 0.1), flip_winding=True)

    def add_diamond_spike(
        self,
        base_pos: tuple[float, float, float],
        direction: tuple[float, float, float],
        length: float,
        width: float,
        joint_idx: int,
    ) -> None:
        b = np.array(base_pos, dtype=np.float32)
        d = np.array(direction, dtype=np.float32)
        d /= max(float(np.linalg.norm(d)), 1e-6)
        up = np.array([0.0, 0.0, 1.0], dtype=np.float32) if abs(d[2]) < 0.9 else np.array([1.0, 0.0, 0.0], dtype=np.float32)
        s1 = np.cross(d, up)
        s1 /= max(float(np.linalg.norm(s1)), 1e-6)
        s2 = np.cross(d, s1)

        rings_pts = [
            (b, 0.002),
            (b + d * (length * 0.28), width),
            (b + d * length, 0.002),
        ]
        n_seg = 6
        pos = np.zeros((3, n_seg + 1, 3), dtype=np.float32)
        uv = np.zeros((3, n_seg + 1, 2), dtype=np.float32)
        jts = np.zeros((3, n_seg + 1, 4), dtype=np.float32)
        wts = np.zeros((3, n_seg + 1, 4), dtype=np.float32)
        for r, (c_pt, rad) in enumerate(rings_pts):
            for c in range(n_seg + 1):
                ang = (c / n_seg) * math.tau
                pos[r, c] = c_pt + (s1 * math.cos(ang) + s2 * math.sin(ang)) * rad
                uv[r, c] = (c / n_seg, r / 2.0)
                jts[r, c] = (float(joint_idx), 0.0, 0.0, 0.0)
                wts[r, c] = (1.0, 0.0, 0.0, 0.0)
        self.add_grid(pos, uv, jts, wts, wrap_u=True, flip_winding=False)

    def build(self, mesh_index: int, morph_deltas: list[np.ndarray] | None = None) -> VrmPrimitive:
        return VrmPrimitive(
            mesh_index=mesh_index,
            skin_index=self.skin_index,
            material_index=self.material_index,
            positions=np.vstack(self._pos) if self._pos else np.zeros((0, 3), dtype=np.float32),
            normals=np.vstack(self._norm) if self._norm else np.zeros((0, 3), dtype=np.float32),
            uvs=np.vstack(self._uv) if self._uv else np.zeros((0, 2), dtype=np.float32),
            joints=np.vstack(self._joints) if self._joints else np.zeros((0, 4), dtype=np.float32),
            weights=np.vstack(self._weights) if self._weights else np.zeros((0, 4), dtype=np.float32),
            indices=np.concatenate(self._indices) if self._indices else np.zeros((0,), dtype=np.uint32),
            morph_deltas=morph_deltas or [],
        )


# ─────────────────────────────────────────────────────────────────────────────
# Texturas Pictóricas 1024×1024 estilo Tree of Savior (Rosto, Cabelo, Roupas)
# ─────────────────────────────────────────────────────────────────────────────


def _make_tos_face_texture(arch: AvatarArchetype) -> np.ndarray:
    """Textura facial anime HD 1024×1024 pintada em camadas (olhos tipo joia, cílios alados, blush suave e sorriso!)."""
    w, h = 1024, 1024
    sr, sg, sb = arch.skin_rgb
    img = Image.new("RGBA", (w, h), (sr, sg, sb, 255))

    cx = w // 2
    eye_cy = int(h * 0.565)
    eye_dx = int(w * 0.068)

    # 1. Sombreamento suave de têmporas, queixo e ponte do nariz (estilo ilustração pintada!)
    shade_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade_layer)
    warm_sh = (max(0, sr - 38), max(0, sg - 52), max(0, sb - 48), 90)
    # Sombra delicada sob o queixo e nas bordas do rosto
    sd.ellipse([cx - 190, int(h * 0.72), cx + 190, int(h * 0.94)], fill=(max(0, sr - 26), max(0, sg - 36), max(0, sb - 32), 68))
    # Sombreamento quente suave nas pálpebras superiores
    for sign in (-1, 1):
        ex = cx + sign * eye_dx
        sd.ellipse([ex - 48, eye_cy - 52, ex + 48, eye_cy - 10], fill=warm_sh)
    shade_layer = shade_layer.filter(ImageFilter.GaussianBlur(radius=14))
    img = Image.alpha_composite(img, shade_layer)

    # 2. Blush difuso rosado atravessando bochechas e ponte do nariz (assinatura das 4 referências!)
    blush_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blush_layer)
    br, bg, bb = arch.blush_rgb
    for sign in (-1, 1):
        bx = cx + sign * int(w * 0.080)
        by = eye_cy + int(h * 0.056)
        bd.ellipse([bx - 56, by - 26, bx + 56, by + 28], fill=(br, bg, bb, 155))
    # Ponte do nariz levemente corada
    bd.ellipse([cx - 46, eye_cy + int(h * 0.036), cx + 46, eye_cy + int(h * 0.068)], fill=(br, bg, bb, 108))
    blush_layer = blush_layer.filter(ImageFilter.GaussianBlur(radius=18))
    img = Image.alpha_composite(img, blush_layer)

    # Sardas delicadas (Vampira / opcional)
    if arch.freckles:
        fd = ImageDraw.Draw(img)
        fcol = (max(0, sr - 58), max(0, sg - 68), max(0, sb - 64), 165)
        for sign in (-1, 1):
            for fx, fy in ((54, 42), (72, 48), (64, 58), (86, 44), (92, 56), (48, 54)):
                fd.ellipse([cx + sign * fx - 3, eye_cy + fy - 3, cx + sign * fx + 3, eye_cy + fy + 3], fill=fcol)

    # 3. Olhos Anime HD Expressivos (cat-eye com íris multicamadas + cílios alados + brilhos triplos!)
    d = ImageDraw.Draw(img)
    er, eg, eb = arch.eye_rgb
    iris_ring = (max(0, int(er * 0.28)), max(0, int(eg * 0.30)), max(0, int(eb * 0.34)), 255)
    iris_deep = (max(0, int(er * 0.56)), max(0, int(eg * 0.58)), max(0, int(eb * 0.62)), 255)
    iris_mid = (min(255, int(er * 1.06)), min(255, int(eg * 1.06)), min(255, int(eb * 1.04)), 255)
    iris_glow = (min(255, er + 108), min(255, eg + 115), min(255, eb + 75), 255)
    lash_col = (26, 14, 22, 255)
    crease_col = (max(0, sr - 72), max(0, sg - 84), max(0, sb - 76), 210)
    brow_col = (*arch.brow_rgb, 245)

    for sign in (-1, 1):
        ex = cx + sign * eye_dx
        # Forma amendoada levemente inclinada para fora (expressão sedutora e viva de 8d09d44e.jpg!)
        sclera_pts = [
            (ex - sign * 34, eye_cy + 10),
            (ex - sign * 24, eye_cy - 18),
            (ex, eye_cy - 28),
            (ex + sign * 28, eye_cy - 20),
            (ex + sign * 40, eye_cy - 6),
            (ex + sign * 30, eye_cy + 20),
            (ex, eye_cy + 26),
            (ex - sign * 22, eye_cy + 22),
        ]
        d.polygon(sclera_pts, fill=(252, 250, 250, 255))
        # Sombra suave no topo da esclera sob os cílios
        d.polygon(
            [
                (ex - sign * 30, eye_cy - 2),
                (ex - sign * 22, eye_cy - 18),
                (ex, eye_cy - 28),
                (ex + sign * 28, eye_cy - 20),
                (ex + sign * 38, eye_cy - 6),
                (ex + sign * 26, eye_cy - 4),
                (ex, eye_cy - 8),
            ],
            fill=(210, 214, 228, 255),
        )

        # Íris grande e vibrante (recortada sutilmente sob a pálpebra superior)
        ix = ex - sign * 2
        iy = eye_cy + 1
        d.ellipse([ix - 27, iy - 25, ix + 27, iy + 26], fill=iris_ring)
        d.ellipse([ix - 23, iy - 21, ix + 23, iy + 22], fill=iris_deep)
        d.ellipse([ix - 20, iy - 10, ix + 20, iy + 20], fill=iris_mid)
        # Crescente luminoso inferior da íris (dá efeito joia anime!)
        d.ellipse([ix - 15, iy + 3, ix + 15, iy + 18], fill=iris_glow)
        # Pupila nítida
        d.ellipse([ix - 10, iy - 9, ix + 10, iy + 9], fill=(18, 12, 20, 255))
        # 3 pontos de brilho catchlight
        d.ellipse([ix - 15, iy - 16, ix - 3, iy - 4], fill=(255, 255, 255, 255))
        d.ellipse([ix + 6, iy + 6, ix + 14, iy + 14], fill=(255, 255, 255, 235))
        d.ellipse([ix + 8, iy - 13, ix + 13, iy - 8], fill=(255, 255, 255, 210))

        # Cílio superior espesso + puxado cat-eye externo (dá charme imediato ao rosto!)
        upper_lash = [
            (ex - sign * 35, eye_cy + 5),
            (ex - sign * 24, eye_cy - 21),
            (ex, eye_cy - 31),
            (ex + sign * 28, eye_cy - 24),
            (ex + sign * 48, eye_cy - 18),  # ponta puxada do cílio alado!
            (ex + sign * 39, eye_cy - 7),
            (ex + sign * 26, eye_cy - 13),
            (ex, eye_cy - 19),
            (ex - sign * 21, eye_cy - 12),
        ]
        d.polygon(upper_lash, fill=lash_col)
        # Delineado inferior delicado
        d.line([(ex - sign * 18, eye_cy + 24), (ex + sign * 26, eye_cy + 20)], fill=(72, 42, 48, 220), width=4)
        # Dobra fina da pálpebra acima do olho
        d.line(
            [(ex - sign * 24, eye_cy - 33), (ex, eye_cy - 41), (ex + sign * 28, eye_cy - 33)],
            fill=crease_col,
            width=4,
        )
        # Sobrancelha expressiva arqueada (suavemente inclinada para dentro — charme da Lyra!)
        brow_pts = [
            (ex - sign * 32, eye_cy - 58),
            (ex - sign * 6, eye_cy - 68),
            (ex + sign * 28, eye_cy - 61),
            (ex + sign * 42, eye_cy - 53),
            (ex + sign * 26, eye_cy - 52),
            (ex - sign * 6, eye_cy - 58),
            (ex - sign * 30, eye_cy - 50),
        ]
        d.polygon(brow_pts, fill=brow_col)

    # 4. Narizinho anime suave (ponto de sombra delicado + brilho na ponta)
    ny = eye_cy + int(h * 0.056)
    d.arc([cx - 10, ny - 6, cx + 10, ny + 8], start=25, end=155, fill=(max(0, sr - 74), max(0, sg - 82), max(0, sb - 74), 200), width=4)
    d.ellipse([cx - 5, ny - 10, cx + 5, ny - 3], fill=(min(255, sr + 28), min(255, sg + 26), min(255, sb + 24), 130))

    # 5. Sorriso caloroso brilhante com lábios macios (exatamente como 8d09d44e.jpg!)
    my = eye_cy + int(h * 0.118)
    lr, lg, lb = arch.lip_rgb
    # Lábio inferior cheio suave
    d.ellipse([cx - 28, my - 2, cx + 28, my + 24], fill=(lr, lg, lb, 215))
    # Interior do sorriso alegre + leve brilho dos dentes superiores
    d.polygon([(cx - 26, my - 1), (cx, my + 3), (cx + 26, my - 1), (cx + 16, my + 12), (cx, my + 14), (cx - 16, my + 12)], fill=(158, 56, 66, 255))
    d.polygon([(cx - 20, my), (cx, my + 3), (cx + 20, my), (cx + 14, my + 7), (cx - 14, my + 7)], fill=(252, 246, 246, 255))
    # Linha fina do lábio superior
    d.line([(cx - 30, my - 3), (cx, my + 2), (cx + 30, my - 3)], fill=(122, 46, 52, 240), width=5)
    # Brilho gloss branco suave no lábio inferior
    d.ellipse([cx - 11, my + 12, cx + 11, my + 19], fill=(255, 232, 228, 195))

    # Cor de cabelo na parte traseira/topo oculta sob a peruca 3D
    d.rectangle([0, 0, w, int(h * 0.30)], fill=(*arch.hair_root_rgb, 255))
    d.rectangle([0, 0, int(w * 0.24), h], fill=(*arch.hair_root_rgb, 255))
    d.rectangle([int(w * 0.76), 0, w, h], fill=(*arch.hair_root_rgb, 255))

    return np.array(img, dtype=np.uint8)


def _make_ear_texture(arch: AvatarArchetype) -> np.ndarray:
    """Textura das orelhas élficas: base no tom de pele -> ponta rosada translúcida iluminada (8d09d44e.jpg!)."""
    w, h = 128, 256
    sr, sg, sb = arch.skin_rgb
    br, bg, bb = arch.blush_rgb
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    for y in range(h):
        t = y / max(h - 1, 1)  # 0=base -> 1=ponta
        # Gradiente quente para a ponta rosada-coral das orelhas élficas!
        k = (t ** 1.35) * 0.72
        r = int(sr * (1.0 - k) + min(255, br + 18) * k)
        g = int(sg * (1.0 - k) + bg * k)
        b = int(sb * (1.0 - k) + bb * k)
        arr[y, :, 0] = np.clip(r, 0, 255)
        arr[y, :, 1] = np.clip(g, 0, 255)
        arr[y, :, 2] = np.clip(b, 0, 255)
        arr[y, :, 3] = 255
    return arr


def _make_painted_hair_texture(arch: AvatarArchetype) -> np.ndarray:
    """Textura pintada de fios de cabelo 512×512 (raízes ricas -> ondas luminosas -> pontas suaves + faixa de brilho!)."""
    w, h = 512, 512
    rr, rg, rb = arch.hair_root_rgb
    mr, mg, mb = arch.hair_rgb
    tr, tg, tb = arch.hair_tip_rgb

    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]

    # Gradiente vertical raiz -> meio -> ponta
    top_k = np.clip(ys / 0.35, 0.0, 1.0)
    bot_k = np.clip((ys - 0.55) / 0.45, 0.0, 1.0)
    base_r = rr * (1.0 - top_k) + mr * top_k
    base_g = rg * (1.0 - top_k) + mg * top_k
    base_b = rb * (1.0 - top_k) + mb * top_k
    base_r = base_r * (1.0 - bot_k) + tr * bot_k
    base_g = base_g * (1.0 - bot_k) + tg * bot_k
    base_b = base_b * (1.0 - bot_k) + tb * bot_k

    # Fios longitudinais pintados (múltiplas frequências harmônicas para textura orgânica de pincel!)
    strands = (
        0.55 * np.sin(xs * math.tau * 18.0 + np.sin(ys * 6.0) * 0.4)
        + 0.30 * np.sin(xs * math.tau * 37.0 + 1.2)
        + 0.15 * np.sin(xs * math.tau * 71.0 + 2.5)
    )
    strand_mul = 1.0 + strands * 0.085

    # Faixa suave de brilho especular anime (angel ring em y ~ 0.24..0.38)
    wave_y = 0.30 + 0.025 * np.sin(xs * math.tau * 6.0)
    shine = np.exp(-((ys - wave_y) / 0.055) ** 2) * (0.65 + 0.35 * np.clip(strands + 0.5, 0.0, 1.0))

    r_ch = np.clip(base_r * strand_mul + shine * 46.0, 0, 255).astype(np.uint8)
    g_ch = np.clip(base_g * strand_mul + shine * 44.0, 0, 255).astype(np.uint8)
    b_ch = np.clip(base_b * strand_mul + shine * 34.0, 0, 255).astype(np.uint8)
    a_ch = np.full((h, w), 255, dtype=np.uint8)
    return np.stack([r_ch, g_ch, b_ch, a_ch], axis=-1)


def _make_corset_torso_texture(arch: AvatarArchetype, outfit_key: str) -> np.ndarray:
    """Textura 1024×1024 do tronco: suporta camada base limpa (`base` = roupa de baixo simples) ou trajes sobrepostos."""
    w, h = 1024, 1024
    sr, sg, sb = arch.skin_rgb
    img = Image.new("RGBA", (w, h), (sr, sg, sb, 255))
    cx = w // 2  # u=0.50 = frente (+Z); y=0 base (quadris/virilha), y=h topo (pescoço)!

    # Sombreamento anatômico suave de pele (clavículas, linha abdominal, umbigo e cintura!)
    sh_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh_layer)
    sk_sh = (max(0, sr - 40), max(0, sg - 52), max(0, sb - 48), 110)
    sk_hi = (min(255, sr + 28), min(255, sg + 26), min(255, sb + 24), 95)
    # Clavículas
    sd.line([(cx - 108, int(h * 0.78)), (cx - 18, int(h * 0.80))], fill=sk_sh, width=10)
    sd.line([(cx + 108, int(h * 0.78)), (cx + 18, int(h * 0.80))], fill=sk_sh, width=10)
    sd.ellipse([cx - 24, int(h * 0.79), cx + 24, int(h * 0.85)], fill=sk_sh)
    # Sulco abdominal delicado + umbigo sutil (y ~ 0.30)
    sd.line([(cx, int(h * 0.32)), (cx, int(h * 0.56))], fill=(max(0, sr - 26), max(0, sg - 36), max(0, sb - 32), 75), width=8)
    sd.ellipse([cx - 10, int(h * 0.29), cx + 10, int(h * 0.32)], fill=(max(0, sr - 58), max(0, sg - 68), max(0, sb - 62), 145))
    # Brilho suave no abdômen e clavículas
    sd.ellipse([cx - 56, int(h * 0.36), cx + 56, int(h * 0.54)], fill=sk_hi)
    sh_layer = sh_layer.filter(ImageFilter.GaussianBlur(radius=9))
    img = Image.alpha_composite(img, sh_layer)
    d = ImageDraw.Draw(img)

    if outfit_key == "base":
        # Roupa de baixo simples e limpa para validar corpo/proporções antes de vestir camadas!
        u_col = (246, 240, 236, 255)
        u_trim = (218, 196, 186, 255)
        u_band = (232, 222, 218, 255)
        # Calcinha simples de corte clássico em V suave + elástico delicado nos quadris
        d.rectangle([0, 0, w, int(h * 0.14)], fill=u_col)
        # Recorte lateral das pernas na frente (destaca a curva do quadril!)
        d.polygon([(cx - 235, int(h * 0.02)), (cx - 72, int(h * 0.02)), (cx - 52, int(h * 0.17)), (cx - 255, int(h * 0.17))], fill=(sr, sg, sb, 255))
        d.polygon([(cx + 72, int(h * 0.02)), (cx + 235, int(h * 0.02)), (cx + 255, int(h * 0.17)), (cx + 52, int(h * 0.17))], fill=(sr, sg, sb, 255))
        # Triângulo frontal e traseiro da calcinha + cós fino contínuo
        d.polygon([(cx - 66, 0), (cx + 66, 0), (cx + 128, int(h * 0.18)), (cx - 128, int(h * 0.18))], fill=u_col)
        d.rectangle([0, int(h * 0.15), w, int(h * 0.19)], fill=u_col)
        d.line([(0, int(h * 0.19)), (w, int(h * 0.19))], fill=u_trim, width=8)
        # Faixa traseira e alças finas do top/sutiã simples (y ~ 0.52..0.58)
        d.rectangle([0, int(h * 0.52), w, int(h * 0.58)], fill=u_band)
        d.line([(0, int(h * 0.52)), (w, int(h * 0.52))], fill=u_trim, width=5)
        d.line([(0, int(h * 0.58)), (w, int(h * 0.58))], fill=u_trim, width=5)
        # Alças finas nos ombros
        d.rectangle([cx - 148, int(h * 0.58), cx - 126, int(h * 0.80)], fill=u_col)
        d.rectangle([cx + 126, int(h * 0.58), cx + 148, int(h * 0.80)], fill=u_col)
        return np.array(img, dtype=np.uint8)

    suit = (*arch.suit_rgb, 255)
    suit_dark = (max(0, arch.suit_rgb[0] - 26), max(0, arch.suit_rgb[1] - 22), max(0, arch.suit_rgb[2] - 20), 255)
    trim = (*arch.trim_rgb, 255)
    acc = (*arch.accent_rgb, 255)

    if arch.outfit_style == "blouse_skirt":
        # Camisa branca ajustada com decote em V + botões (Vampira)
        d.rectangle([0, int(h * 0.24), w, int(h * 0.82)], fill=suit)
        # Recorte V frontal revelando pescoço e colo
        d.polygon([(cx - 88, int(h * 0.82)), (cx + 88, int(h * 0.82)), (cx, int(h * 0.56))], fill=(sr, sg, sb, 255))
        d.line([(cx - 88, int(h * 0.82)), (cx, int(h * 0.56)), (cx + 88, int(h * 0.82))], fill=trim, width=10)
        d.line([(cx, int(h * 0.24)), (cx, int(h * 0.56))], fill=(180, 186, 198, 255), width=6)
        # Saia/cós preto na base
        d.rectangle([0, 0, w, int(h * 0.28)], fill=(*arch.skirt_rgb, 255))
    else:
        # Corpete fantasia estilo Elfa Loira (8d09d44e.jpg!) / Humana Ruiva / Androide Rosa
        # Base pélvica/faixa inferior + laterais altas
        d.rectangle([0, 0, w, int(h * 0.22)], fill=suit_dark)
        # Laterais do quadril livres (destacam coxas curvas pela fenda da saia!)
        d.polygon([(cx - 240, int(h * 0.02)), (cx - 82, int(h * 0.02)), (cx - 64, int(h * 0.26)), (cx - 256, int(h * 0.26))], fill=(sr, sg, sb, 255))
        d.polygon([(cx + 82, int(h * 0.02)), (cx + 240, int(h * 0.02)), (cx + 256, int(h * 0.26)), (cx + 64, int(h * 0.26))], fill=(sr, sg, sb, 255))

        # Corpo principal do corpete (da cintura até sob o busto, e subindo pelas laterais/costas!)
        d.rectangle([0, int(h * 0.22), w, int(h * 0.58)], fill=suit)
        # Costas e alças laterais do corpete (deixando o decote generoso no peito!)
        d.rectangle([0, int(h * 0.56), int(w * 0.34), int(h * 0.78)], fill=suit)
        d.rectangle([int(w * 0.66), int(h * 0.56), w, int(h * 0.78)], fill=suit)

        # Babado de renda branca ondulada contornando o decote/alças (assinatura 8d09d44e.jpg!)
        for bx in range(int(w * 0.30), int(w * 0.71), 22):
            by = int(h * 0.56)
            d.ellipse([bx - 14, by - 12, bx + 14, by + 16], fill=trim)
        d.line([(int(w * 0.33), int(h * 0.56)), (int(w * 0.33), int(h * 0.79))], fill=trim, width=18)
        d.line([(int(w * 0.67), int(h * 0.56)), (int(w * 0.67), int(h * 0.79))], fill=trim, width=18)

        # Painel frontal central do corpete com cadarços cruzados (lacing!) e costura dourada
        d.rectangle([cx - 72, int(h * 0.24), cx + 72, int(h * 0.56)], fill=suit_dark)
        d.line([(cx - 72, int(h * 0.24)), (cx - 72, int(h * 0.56))], fill=acc, width=7)
        d.line([(cx + 72, int(h * 0.24)), (cx + 72, int(h * 0.56))], fill=acc, width=7)
        # Cadarços cruzados X-X-X na barriga!
        for k in range(4):
            y0 = int(h * (0.28 + k * 0.068))
            y1 = int(h * (0.34 + k * 0.068))
            d.line([(cx - 46, y0), (cx + 46, y1)], fill=acc, width=7)
            d.line([(cx + 46, y0), (cx - 46, y1)], fill=acc, width=7)
            d.ellipse([cx - 52, y0 - 6, cx - 40, y0 + 6], fill=trim)
            d.ellipse([cx + 40, y0 - 6, cx + 52, y0 + 6], fill=trim)

        # Faixa de cinto e laço frontal na cintura
        d.rectangle([0, int(h * 0.21), w, int(h * 0.27)], fill=suit_dark)
        d.line([(0, int(h * 0.21)), (w, int(h * 0.21))], fill=acc, width=6)
        d.line([(0, int(h * 0.27)), (w, int(h * 0.27))], fill=acc, width=6)

    return np.array(img, dtype=np.uint8)


def _make_bust_texture(arch: AvatarArchetype, outfit_key: str = "base") -> np.ndarray:
    """Textura 512×512 do busto esculpido: decote luminoso + sutiã simples (`base`) ou bojo do corpete!"""
    w, h = 512, 512
    sr, sg, sb = arch.skin_rgb
    img = Image.new("RGBA", (w, h), (sr, sg, sb, 255))

    hl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hl)
    hd.ellipse([w // 2 - 92, int(h * 0.14), w // 2 + 92, int(h * 0.42)], fill=(min(255, sr + 32), min(255, sg + 32), min(255, sb + 30), 115))
    hl = hl.filter(ImageFilter.GaussianBlur(radius=22))
    img = Image.alpha_composite(img, hl)
    d = ImageDraw.Draw(img)

    if outfit_key == "base":
        # Sutiã/top simples delicado (creme-marfim com renda fina) deixando proporções 100% visíveis!
        u_col = (246, 240, 236, 255)
        u_trim = (218, 196, 186, 255)
        split_y = int(h * 0.44)
        d.rectangle([0, split_y, w, h], fill=u_col)
        for rx in range(0, w + 20, 22):
            d.ellipse([rx - 13, split_y - 10, rx + 13, split_y + 10], fill=u_col)
        d.line([(0, split_y + 10), (w, split_y + 10)], fill=u_trim, width=5)
        return np.array(img, dtype=np.uint8)

    if arch.outfit_style == "blouse_skirt":
        d.rectangle([0, int(h * 0.18), w, h], fill=(*arch.suit_rgb, 255))
    else:
        split_y = int(h * 0.56)
        d.rectangle([0, split_y, w, h], fill=(*arch.suit_rgb, 255))
        for rx in range(0, w + 24, 28):
            d.ellipse([rx - 18, split_y - 16, rx + 18, split_y + 14], fill=(*arch.trim_rgb, 255))
        d.line([(0, split_y + 12), (w, split_y + 12)], fill=(*arch.accent_rgb, 255), width=6)

    return np.array(img, dtype=np.uint8)


def _make_skirt_texture(arch: AvatarArchetype) -> np.ndarray:
    """Textura 512×512 da saia fantasia: tecido rico com borda creme/dourada e dobras pintadas."""
    w, h = 512, 512
    r, g, b = arch.skirt_rgb
    img = Image.new("RGBA", (w, h), (r, g, b, 255))
    d = ImageDraw.Draw(img)
    for x in range(0, w, 32):
        d.rectangle([x, 0, x + 10, h], fill=(max(0, r - 14), max(0, g - 12), max(0, b - 12), 255))
    d.rectangle([0, 0, 26, h], fill=(*arch.trim_rgb, 255))
    d.rectangle([w - 26, 0, w, h], fill=(*arch.trim_rgb, 255))
    d.rectangle([0, h - 32, w, h], fill=(*arch.trim_rgb, 255))
    d.line([(28, 0), (28, h - 32)], fill=(*arch.accent_rgb, 255), width=6)
    d.line([(w - 28, 0), (w - 28, h - 32)], fill=(*arch.accent_rgb, 255), width=6)
    d.line([(0, h - 34), (w, h - 34)], fill=(*arch.accent_rgb, 255), width=6)
    return np.array(img, dtype=np.uint8)


def _make_leg_texture(arch: AvatarArchetype, outfit_key: str = "base") -> np.ndarray:
    """Textura 512×1024 das pernas: pele limpa com sombreamento sutil no joelho (`base`) ou botas fantasia!"""
    w, h = 512, 1024
    sr, sg, sb = arch.skin_rgb
    img = Image.new("RGBA", (w, h), (sr, sg, sb, 255))
    cx = w // 2

    # Sombreamento anatômico sutil nos joelhos e brilho nas coxas
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh)
    sd.ellipse([cx - 38, int(h * 0.47), cx + 38, int(h * 0.53)], fill=(max(0, sr - 22), max(0, sg - 30), max(0, sb - 26), 90))
    sd.ellipse([cx - 46, int(h * 0.65), cx + 46, int(h * 0.88)], fill=(min(255, sr + 24), min(255, sg + 22), min(255, sb + 20), 85))
    sh = sh.filter(ImageFilter.GaussianBlur(radius=16))
    img = Image.alpha_composite(img, sh)

    if outfit_key == "base":
        return np.array(img, dtype=np.uint8)

    d = ImageDraw.Draw(img)
    boot_top = int(h * 0.48)
    br, bg, bb = arch.boot_rgb
    b_dark = (max(0, br - 24), max(0, bg - 20), max(0, bb - 18), 255)
    d.rectangle([0, 0, w, boot_top], fill=(br, bg, bb, 255))
    d.rectangle([0, boot_top - 48, w, boot_top + 12], fill=b_dark)
    d.rectangle([0, boot_top + 8, w, boot_top + 22], fill=(*arch.trim_rgb, 255))
    d.rectangle([cx - 34, boot_top - 34, cx + 34, boot_top - 6], fill=(*arch.accent_rgb, 255))
    d.rectangle([cx - 22, boot_top - 26, cx + 22, boot_top - 14], fill=b_dark)
    for k in range(5):
        yk = int(h * (0.10 + k * 0.065))
        d.line([(cx - 24, yk), (cx + 24, yk + 26)], fill=(*arch.accent_rgb, 255), width=6)
        d.line([(cx + 24, yk), (cx - 24, yk + 26)], fill=(*arch.accent_rgb, 255), width=6)
    return np.array(img, dtype=np.uint8)


def _make_arm_texture(arch: AvatarArchetype, outfit_key: str = "base") -> np.ndarray:
    """Textura 512×512 dos braços: pele limpa (`base`) ou luvas/mangas do traje."""
    w, h = 512, 512
    sr, sg, sb = arch.skin_rgb
    img = Image.new("RGBA", (w, h), (sr, sg, sb, 255))
    if outfit_key == "base":
        return np.array(img, dtype=np.uint8)
    d = ImageDraw.Draw(img)
    if arch.outfit_style == "blouse_skirt":
        d.rectangle([0, 0, w, int(h * 0.62)], fill=(*arch.suit_rgb, 255))
        d.rectangle([0, int(h * 0.58), w, int(h * 0.64)], fill=(*arch.trim_rgb, 255))
    else:
        glove_start = int(h * 0.62)
        br, bg, bb = arch.boot_rgb
        d.rectangle([0, glove_start, w, h], fill=(br, bg, bb, 255))
        d.rectangle([0, glove_start - 14, w, glove_start + 16], fill=(max(0, br - 20), max(0, bg - 16), max(0, bb - 14), 255))
        d.line([(0, glove_start + 16), (w, glove_start + 16)], fill=(*arch.accent_rgb, 255), width=7)
    return np.array(img, dtype=np.uint8)


def _make_eyelid_texture(arch: AvatarArchetype) -> np.ndarray:
    """Pálpebra na cor exata da pele com cílio curvo fofo para piscar/sorrir de olhos fechados!"""
    w, h = 128, 128
    img = Image.new("RGBA", (w, h), (*arch.skin_rgb, 255))
    d = ImageDraw.Draw(img)
    d.arc([16, 48, w - 16, 98], start=15, end=165, fill=(28, 16, 22, 255), width=8)
    return np.array(img, dtype=np.uint8)


def _resolve_archetype(persona: Persona, archetype_id: str | None = None) -> AvatarArchetype:
    if archetype_id and archetype_id in ARCHETYPES:
        return ARCHETYPES[archetype_id]
    # Mapeamento padrão das personas enquanto refinamos a Elfa Loira como modelo principal!
    if persona.id in ARCHETYPES:
        return ARCHETYPES[persona.id]
    if persona.id == "nyx":
        return ARCHETYPES["vampira_negra"]
    return ARCHETYPES["elfa_loira"]


def build_dungeon_squad_model(
    persona: Persona,
    outfit_key: str = "base",
    archetype_id: str | None = None,
) -> VrmModel:
    """Constrói um `VrmModel` 3D de alta definição estilo Tree of Savior para qualquer um dos 4 arquétipos base."""
    arch = _resolve_archetype(persona, archetype_id)
    is_base_layer = outfit_key == "base"

    # ── 1. Hierarquia de Ossos VRM 1.0 (~4.8 cabeças, altura 1.48 m) ──
    nodes: list[VrmNode] = []
    world_pos: list[np.ndarray] = []
    name_to_idx: dict[str, int] = {}

    def _add_bone(name: str, wpos: tuple[float, float, float], parent_name: str | None) -> int:
        idx = len(nodes)
        wp = np.array(wpos, dtype=np.float32)
        if parent_name is None:
            p_idx = -1
            local_t = wp.copy()
        else:
            p_idx = name_to_idx[parent_name]
            local_t = wp - world_pos[p_idx]
            nodes[p_idx].children.append(idx)
        nodes.append(VrmNode(index=idx, name=name, parent=p_idx, translation=local_t))
        world_pos.append(wp)
        name_to_idx[name] = idx
        return idx

    b_hips = _add_bone("hips", (0.0, 0.62, 0.0), None)
    b_spine = _add_bone("spine", (0.0, 0.74, 0.0), "hips")
    b_chest = _add_bone("chest", (0.0, 0.86, 0.0), "spine")
    b_uchest = _add_bone("upperChest", (0.0, 0.96, 0.0), "chest")
    b_neck = _add_bone("neck", (0.0, 1.04, 0.0), "upperChest")
    b_head = _add_bone("head", (0.0, 1.10, 0.0), "neck")

    b_l_sh = _add_bone("leftShoulder", (0.060, 0.99, 0.0), "upperChest")
    b_l_ua = _add_bone("leftUpperArm", (0.138, 0.98, 0.0), "leftShoulder")
    b_l_la = _add_bone("leftLowerArm", (0.310, 0.98, 0.0), "leftUpperArm")
    b_l_hd = _add_bone("leftHand", (0.470, 0.98, 0.0), "leftLowerArm")

    b_r_sh = _add_bone("rightShoulder", (-0.060, 0.99, 0.0), "upperChest")
    b_r_ua = _add_bone("rightUpperArm", (-0.138, 0.98, 0.0), "rightShoulder")
    b_r_la = _add_bone("rightLowerArm", (-0.310, 0.98, 0.0), "rightUpperArm")
    b_r_hd = _add_bone("rightHand", (-0.470, 0.98, 0.0), "rightLowerArm")

    b_l_ul = _add_bone("leftUpperLeg", (0.098, 0.60, 0.0), "hips")
    b_l_ll = _add_bone("leftLowerLeg", (0.100, 0.31, 0.0), "leftUpperLeg")
    b_l_ft = _add_bone("leftFoot", (0.100, 0.058, 0.015), "leftLowerLeg")

    b_r_ul = _add_bone("rightUpperLeg", (-0.098, 0.60, 0.0), "hips")
    b_r_ll = _add_bone("rightLowerLeg", (-0.100, 0.31, 0.0), "rightUpperLeg")
    b_r_ft = _add_bone("rightFoot", (-0.100, 0.058, 0.015), "rightLowerLeg")

    # Cadeias SpringBone para cabelos longos ondulados (centro, esquerda, direita e mechas frontais!)
    b_hc0 = _add_bone("hair_c_0", (0.0, 1.24, -0.15), "head")
    b_hc1 = _add_bone("hair_c_1", (0.0, 0.96, -0.20), "hair_c_0")
    b_hc2 = _add_bone("hair_c_2", (0.0, 0.66, -0.22), "hair_c_1")

    b_hl0 = _add_bone("hair_l_0", (0.13, 1.22, -0.04), "head")
    b_hl1 = _add_bone("hair_l_1", (0.16, 0.96, -0.07), "hair_l_0")
    b_hl2 = _add_bone("hair_l_2", (0.18, 0.68, -0.10), "hair_l_1")

    b_hr0 = _add_bone("hair_r_0", (-0.13, 1.22, -0.04), "head")
    b_hr1 = _add_bone("hair_r_1", (-0.16, 0.96, -0.07), "hair_r_0")
    b_hr2 = _add_bone("hair_r_2", (-0.18, 0.68, -0.10), "hair_r_1")

    humanoid_bones = {
        "hips": b_hips, "spine": b_spine, "chest": b_chest, "upperChest": b_uchest,
        "neck": b_neck, "head": b_head,
        "leftShoulder": b_l_sh, "leftUpperArm": b_l_ua, "leftLowerArm": b_l_la, "leftHand": b_l_hd,
        "rightShoulder": b_r_sh, "rightUpperArm": b_r_ua, "rightLowerArm": b_r_la, "rightHand": b_r_hd,
        "leftUpperLeg": b_l_ul, "leftLowerLeg": b_l_ll, "leftFoot": b_l_ft,
        "rightUpperLeg": b_r_ul, "rightLowerLeg": b_r_ll, "rightFoot": b_r_ft,
    }

    n_joints = len(nodes)
    inv_bind = np.repeat(np.eye(4, dtype=np.float32)[None, :, :], n_joints, axis=0)
    for j in range(n_joints):
        inv_bind[j, :3, 3] = -world_pos[j]
    skin = VrmSkin(joints=list(range(n_joints)), inv_bind_matrices=inv_bind)

    # ── 2. Materiais Pictóricos HD (1024×1024 / 512×512) ──
    tr_f, tg_f, tb_f = arch.trim_rgb[0] / 255.0, arch.trim_rgb[1] / 255.0, arch.trim_rgb[2] / 255.0
    ar_f, ag_f, ab_f = arch.accent_rgb[0] / 255.0, arch.accent_rgb[1] / 255.0, arch.accent_rgb[2] / 255.0

    materials = [
        VrmMaterial(0, "tos_face", "face", (1.0, 1.0, 1.0, 1.0), arch.skin_shade, _make_tos_face_texture(arch)),
        VrmMaterial(1, "tos_torso", "skin", (1.0, 1.0, 1.0, 1.0), arch.skin_shade, _make_corset_torso_texture(arch, outfit_key)),
        VrmMaterial(2, "tos_bust", "skin", (1.0, 1.0, 1.0, 1.0), arch.skin_shade, _make_bust_texture(arch, outfit_key)),
        VrmMaterial(3, "tos_legs", "skin", (1.0, 1.0, 1.0, 1.0), arch.skin_shade, _make_leg_texture(arch, outfit_key)),
        VrmMaterial(4, "tos_arms", "skin", (1.0, 1.0, 1.0, 1.0), arch.skin_shade, _make_arm_texture(arch, outfit_key)),
        VrmMaterial(5, "tos_hair", "hair", (1.0, 1.0, 1.0, 1.0), arch.hair_shade, _make_painted_hair_texture(arch), double_sided=True),
        VrmMaterial(6, "tos_skirt", "bottoms", (1.0, 1.0, 1.0, 1.0), (0.58, 0.44, 0.44), _make_skirt_texture(arch), double_sided=True),
        VrmMaterial(7, "tos_lace", "tops", (tr_f, tg_f, tb_f, 1.0), (0.80, 0.76, 0.78), None, double_sided=True),
        VrmMaterial(8, "tos_gold", "gold", (ar_f, ag_f, ab_f, 1.0), (ar_f * 0.60, ag_f * 0.48, ab_f * 0.34), None),
        VrmMaterial(9, "tos_ears", "skin", (1.0, 1.0, 1.0, 1.0), arch.skin_shade, _make_ear_texture(arch)),
        VrmMaterial(10, "tos_eyelid", "face", (1.0, 1.0, 1.0, 1.0), arch.skin_shade, _make_eyelid_texture(arch)),
    ]

    primitives: list[VrmPrimitive] = []

    # ── 3. Tronco Ampulheta Esculpido (Alta Densidade 36 segmentos!) ──
    mb_torso = _MeshBuilder(material_index=1)

    def _torso_shape(theta: float, v: float) -> tuple[float, float]:
        back = max(0.0, -math.cos(theta))
        hip_zone = math.exp(-((v - 0.16) / 0.15) ** 2)
        return (1.0, 1.0 + back * 0.28 * hip_zone)

    torso_rings = [
        (np.array([0.0, 0.50, 0.0], dtype=np.float32), 0.122, 0.096, 0.00, -0.005, b_hips, b_hips, 0.0),
        (np.array([0.0, 0.56, 0.0], dtype=np.float32), 0.172, 0.126, 0.10, -0.012, b_hips, b_hips, 0.0),
        (np.array([0.0, 0.62, 0.0], dtype=np.float32), 0.176, 0.128, 0.20, -0.014, b_hips, b_spine, 0.15),
        (np.array([0.0, 0.70, 0.0], dtype=np.float32), 0.116, 0.090, 0.32, -0.005, b_hips, b_spine, 0.65),
        (np.array([0.0, 0.77, 0.0], dtype=np.float32), 0.088, 0.072, 0.44,  0.002, b_spine, b_chest, 0.32),
        (np.array([0.0, 0.85, 0.0], dtype=np.float32), 0.112, 0.088, 0.58,  0.004, b_chest, b_chest, 0.0),
        (np.array([0.0, 0.93, 0.0], dtype=np.float32), 0.128, 0.094, 0.72,  0.002, b_chest, b_uchest, 0.65),
        (np.array([0.0, 1.00, 0.0], dtype=np.float32), 0.118, 0.076, 0.83, -0.004, b_uchest, b_neck, 0.25),
        (np.array([0.0, 1.05, 0.0], dtype=np.float32), 0.045, 0.044, 0.91, -0.004, b_neck, b_head, 0.25),
        (np.array([0.0, 1.13, 0.0], dtype=np.float32), 0.042, 0.042, 1.00, -0.004, b_neck, b_head, 0.75),
    ]
    mb_torso.add_loft(torso_rings, n_seg=36, shape_fn=_torso_shape, cap_bottom=True, cap_top=True)
    primitives.append(mb_torso.build(mesh_index=len(primitives)))

    # ── 4. Busto Voluptuoso Esculpido Suavemente ──
    mb_bust = _MeshBuilder(material_index=2)
    for sign in (-1.0, 1.0):
        def _bust_deform(x: float, y: float, z: float, u: float, v: float, s: float = sign) -> tuple[float, float, float]:
            drop = -0.016 * max(0.0, z / 0.10)
            flare = s * 0.014 * max(0.0, z / 0.10)
            return (x + flare, y + drop, z)

        mb_bust.add_ellipsoid(
            center=(sign * 0.070, 0.902, 0.090),
            radii=(0.086, 0.088, 0.096),
            joint_idx=b_chest,
            n_lat=20,
            n_lon=28,
            deform_fn=_bust_deform,
            joint_b=b_uchest,
            weight_b_fn=lambda v: 0.28 * v,
        )
    primitives.append(mb_bust.build(mesh_index=len(primitives)))

    # ── 5. Coxas Curvas Voluptuosas, Panturrilhas e Botas Fantasia ──
    mb_legs = _MeshBuilder(material_index=3)
    for side, j_ul, j_ll, j_ft in ((1.0, b_l_ul, b_l_ll, b_l_ft), (-1.0, b_r_ul, b_r_ll, b_r_ft)):
        lx = side * 0.100

        def _thigh_shape(theta: float, v: float, s: float = side) -> tuple[float, float]:
            outer = max(0.0, s * math.sin(theta))
            thigh_bulge = math.exp(-((v - 0.78) / 0.18) ** 2)
            calf_back = max(0.0, -math.cos(theta)) * math.exp(-((v - 0.34) / 0.14) ** 2)
            return (1.0 + outer * 0.24 * thigh_bulge, 1.0 + calf_back * 0.22)

        leg_rings = [
            (np.array([lx, 0.005, 0.036], dtype=np.float32), 0.038, 0.070, 0.00, 0.012, j_ft, j_ft, 0.0),
            (np.array([lx, 0.060, 0.012], dtype=np.float32), 0.038, 0.044, 0.08, 0.000, j_ft, j_ll, 0.35),
            (np.array([lx, 0.140, 0.000], dtype=np.float32), 0.043, 0.046, 0.20, -0.004, j_ll, j_ll, 0.0),
            (np.array([lx, 0.240, 0.000], dtype=np.float32), 0.058, 0.062, 0.36, -0.008, j_ll, j_ll, 0.0),
            (np.array([lx, 0.315, 0.004], dtype=np.float32), 0.062, 0.064, 0.50,  0.004, j_ll, j_ul, 0.50),
            (np.array([lx, 0.405, 0.004], dtype=np.float32), 0.086, 0.090, 0.64,  0.002, j_ul, j_ul, 0.0),
            (np.array([lx, 0.505, 0.002], dtype=np.float32), 0.106, 0.110, 0.80, -0.004, j_ul, b_hips, 0.18),
            (np.array([lx * 0.92, 0.595, 0.000], dtype=np.float32), 0.108, 0.112, 0.94, -0.008, j_ul, b_hips, 0.58),
            (np.array([lx * 0.78, 0.640, 0.000], dtype=np.float32), 0.088, 0.092, 1.00, -0.006, b_hips, b_hips, 0.0),
        ]
        mb_legs.add_loft(leg_rings, n_seg=28, shape_fn=_thigh_shape, cap_bottom=True, cap_top=True)
        if not is_base_layer:
            mb_legs.add_diamond_spike((lx, 0.058, -0.030), (0.0, -1.0, -0.08), 0.058, 0.016, j_ft)
    primitives.append(mb_legs.build(mesh_index=len(primitives)))

    # ── 6. Braços Delicados e Luvas de Aventureira ──
    mb_arms = _MeshBuilder(material_index=4)
    for side, j_sh, j_ua, j_la, j_hd in (
        (1.0, b_l_sh, b_l_ua, b_l_la, b_l_hd),
        (-1.0, b_r_sh, b_r_ua, b_r_la, b_r_hd),
    ):
        arm_stations = [
            (0.125, 0.044, 0.044, 0.00, j_sh, j_ua, 0.60),
            (0.180, 0.039, 0.039, 0.20, j_ua, j_ua, 0.00),
            (0.255, 0.035, 0.035, 0.42, j_ua, j_la, 0.15),
            (0.310, 0.032, 0.032, 0.56, j_ua, j_la, 0.55),
            (0.385, 0.031, 0.031, 0.74, j_la, j_la, 0.00),
            (0.455, 0.025, 0.023, 0.90, j_la, j_hd, 0.70),
            (0.500, 0.032, 0.018, 0.97, j_hd, j_hd, 0.00),
            (0.535, 0.017, 0.011, 1.00, j_hd, j_hd, 0.00),
        ]
        n_r = len(arm_stations)
        n_seg = 18
        pos = np.zeros((n_r, n_seg + 1, 3), dtype=np.float32)
        uv = np.zeros((n_r, n_seg + 1, 2), dtype=np.float32)
        jts = np.zeros((n_r, n_seg + 1, 4), dtype=np.float32)
        wts = np.zeros((n_r, n_seg + 1, 4), dtype=np.float32)
        for r, (x_off, ry, rz, v_c, j0, j1, w1) in enumerate(arm_stations):
            for c in range(n_seg + 1):
                u = c / n_seg
                ang = u * math.tau
                pos[r, c] = (side * x_off, 0.98 + math.cos(ang) * ry, math.sin(ang) * rz)
                uv[r, c] = (u, v_c)
                jts[r, c] = (float(j0), float(j1), 0.0, 0.0)
                wts[r, c] = (1.0 - w1, w1, 0.0, 0.0)
        mb_arms.add_grid(pos, uv, jts, wts, wrap_u=True, flip_winding=(side < 0))
    primitives.append(mb_arms.build(mesh_index=len(primitives)))

    # ── 7. Cabeça Anime HD Esculpida (36×48, queixo delicado + nariz anime sutil!) ──
    mb_head = _MeshBuilder(material_index=0)

    def _head_deform(x: float, y: float, z: float, u: float, v: float) -> tuple[float, float, float]:
        # Queixo anime em V macio na parte inferior (v < 0.42)
        chin_t = max(0.0, (0.42 - v) / 0.42)
        x_scale = 1.0 - 0.30 * (chin_t ** 1.38)
        z_scale = 1.0 - 0.14 * (chin_t ** 1.35)
        # Bochechas macias e femininas (v ~ 0.36..0.52)
        cheek = math.exp(-((v - 0.42) / 0.10) ** 2) * max(0.0, z / 0.14)
        x_scale += 0.045 * cheek
        # Narizinho anime sutil e arrebitado em 3D (visível no perfil 3/4 sem sujar a frente!)
        du = (u - 0.50) / 0.026
        dv = (v - 0.38) / 0.045
        nose = 0.014 * math.exp(-(du * du + dv * dv)) if z > 0 else 0.0
        # Leve achatamento frontal na zona dos olhos para máxima legibilidade!
        z_out = z * (0.94 if z > 0 else 1.0) * z_scale + nose
        return (x * x_scale, y, z_out)

    mb_head.add_ellipsoid(
        center=(0.0, 1.245, 0.008),
        radii=(0.142, 0.152, 0.138),
        joint_idx=b_head,
        n_lat=36,
        n_lon=48,
        deform_fn=_head_deform,
    )
    primitives.append(mb_head.build(mesh_index=len(primitives)))

    # ── 7b. Pálpebras animadas por Morph Target (piscar suave + sorriso feliz!) ──
    mb_lid = _MeshBuilder(material_index=10)
    for sign in (-1.0, 1.0):
        mb_lid.add_ellipsoid(
            center=(sign * 0.052, 1.224, 0.123),
            radii=(0.036, 0.025, 0.014),
            joint_idx=b_head,
            n_lat=10,
            n_lon=14,
        )
    lid_prim = mb_lid.build(mesh_index=len(primitives))
    open_pos = lid_prim.positions.copy()
    closed_pos = lid_prim.positions.copy()
    open_pos[:, 2] -= 0.036
    open_pos[:, 1] += 0.012
    closed_pos[:, 2] += 0.009
    lid_prim.positions = open_pos
    lid_prim.morph_deltas = [closed_pos - open_pos]
    lid_mesh_idx = len(primitives)
    primitives.append(lid_prim)

    # ── 7c. Orelhas Élficas Longas em 3D (assinatura da Lyra / Elfa Loira!) ──
    if arch.elf_ears:
        mb_ears = _MeshBuilder(material_index=9)
        mb_ears.add_elf_ear(1.0, (0.122, 1.225, -0.008), b_head)
        mb_ears.add_elf_ear(-1.0, (-0.122, 1.225, -0.008), b_head)
        primitives.append(mb_ears.build(mesh_index=len(primitives)))

    # ── 8. Cabelo Multicamadas Pintado à Mão (Ondulado Longo p/ Elfa Loira + suporte aos 4 estilos!) ──
    mb_hair = _MeshBuilder(material_index=5)
    # Volume macio do topo/coroa do cabelo
    mb_hair.add_ellipsoid(
        center=(0.0, 1.275, -0.014),
        radii=(0.156, 0.154, 0.154),
        joint_idx=b_head,
        n_lat=22,
        n_lon=32,
        deform_fn=lambda x, y, z, u, v: (x, y if v > 0.28 else y + 0.035, z if z < 0.088 else 0.088),
    )

    # Coroa penteada para trás com ondas suaves + mechas soltas emoldurando a testa (estilo 8d09d44e.jpg!)
    if arch.hair_style == "wavy_long":
        # Mechas onduladas puxadas suavemente para trás nas laterais da testa (mostrando os olhos verdes e sobrancelhas!)
        for sign in (-1.0, 1.0):
            crown_wave = [
                (np.array([sign * 0.015, 1.405, 0.068], dtype=np.float32), 0.045, 1.0, b_head, b_head, 0.0),
                (np.array([sign * 0.082, 1.372, 0.095], dtype=np.float32), 0.056, 1.15, b_head, b_head, 0.0),
                (np.array([sign * 0.140, 1.305, 0.065], dtype=np.float32), 0.050, 1.05, b_head, b_head, 0.0),
                (np.array([sign * 0.154, 1.240, 0.005], dtype=np.float32), 0.044, 0.90, b_head, b_head, 0.0),
            ]
            mb_hair.add_ribbon(crown_wave, n_across=5, thickness=0.024, arch_z=0.014)

            # Mecha fina solta caindo em S delicado na têmpora/bochecha (detalhe encantador da Elfa!)
            wisp = [
                (np.array([sign * 0.065, 1.365, 0.118], dtype=np.float32), 0.020, 0.85, b_head, b_head, 0.0),
                (np.array([sign * 0.105, 1.295, 0.122], dtype=np.float32), 0.022, 0.85, b_head, b_head, 0.0),
                (np.array([sign * 0.132, 1.205, 0.102], dtype=np.float32), 0.018, 0.70, b_head, b_head, 0.0),
                (np.array([sign * 0.125, 1.125, 0.082], dtype=np.float32), 0.008, 0.40, b_head, b_head, 0.0),
            ]
            mb_hair.add_ribbon(wisp, n_across=4, thickness=0.013, arch_z=0.008)

            # Mecha longa ondulada caindo atrás da orelha élfica sobre o ombro/peito!
            j0, j1, j2 = (b_hl0, b_hl1, b_hl2) if sign > 0 else (b_hr0, b_hr1, b_hr2)
            side_lock = [
                (np.array([sign * 0.135, 1.26, -0.02], dtype=np.float32), 0.048, 1.0, b_head, j0, 0.40),
                (np.array([sign * 0.172, 1.11, -0.03], dtype=np.float32), 0.060, 1.05, j0, j1, 0.35),
                (np.array([sign * 0.195, 0.96,  0.01], dtype=np.float32), 0.064, 1.0, j1, j1, 0.0),
                (np.array([sign * 0.185, 0.80,  0.03], dtype=np.float32), 0.052, 0.85, j1, j2, 0.65),
                (np.array([sign * 0.210, 0.66,  0.00], dtype=np.float32), 0.024, 0.50, j2, j2, 0.0),
            ]
            mb_hair.add_ribbon(side_lock, n_across=5, thickness=0.026, arch_z=0.014)
    else:
        # Franja cheia versátil para Ruiva / Androide Rosa / Vampira
        for bx, bw, bot_y, fz in ((-0.095, 0.044, 1.22, 0.138), (-0.045, 0.044, 1.25, 0.152), (0.005, 0.046, 1.24, 0.155), (0.055, 0.044, 1.25, 0.152), (0.100, 0.044, 1.22, 0.138)):
            pts = [
                (np.array([bx * 0.62, 1.395, 0.045], dtype=np.float32), bw * 0.78, 1.0, b_head, b_head, 0.0),
                (np.array([bx * 0.88, 1.325, fz * 0.94], dtype=np.float32), bw * 0.95, 1.1, b_head, b_head, 0.0),
                (np.array([bx, bot_y + 0.035, fz], dtype=np.float32), bw * 0.85, 0.9, b_head, b_head, 0.0),
                (np.array([bx * 1.03, bot_y, fz * 0.96], dtype=np.float32), bw * 0.25, 0.45, b_head, b_head, 0.0),
            ]
            mb_hair.add_ribbon(pts, n_across=4, thickness=0.020, arch_z=0.011)

    # 7 mechas longas onduladas nas costas (leque volumoso que ondula com vento e caminhada 360°!)
    back_specs = [
        (-0.145, -0.095, 0.072, 0.60, b_hr0, b_hr1, b_hr2, -0.03),
        (-0.095, -0.145, 0.078, 0.54, b_hr0, b_hr1, b_hr2,  0.02),
        (-0.045, -0.165, 0.082, 0.48, b_hc0, b_hc1, b_hc2, -0.02),
        ( 0.000, -0.172, 0.086, 0.46, b_hc0, b_hc1, b_hc2,  0.025),
        ( 0.045, -0.165, 0.082, 0.48, b_hc0, b_hc1, b_hc2, -0.02),
        ( 0.095, -0.145, 0.078, 0.54, b_hl0, b_hl1, b_hl2,  0.02),
        ( 0.145, -0.095, 0.072, 0.60, b_hl0, b_hl1, b_hl2, -0.03),
    ]
    for bx, bz, bw, end_y, j0, j1, j2, sway_w in back_specs:
        pts = [
            (np.array([bx * 0.72, 1.32, bz * 0.85], dtype=np.float32), bw * 0.82, 1.0, b_head, j0, 0.35),
            (np.array([bx * 1.02, 1.15, bz * 1.12], dtype=np.float32), bw * 1.05, 1.1, j0, j0, 0.0),
            (np.array([bx * 1.18 + sway_w, 0.96, bz * 1.24 - 0.02], dtype=np.float32), bw * 1.15, 1.0, j0, j1, 0.65),
            (np.array([bx * 1.28 - sway_w, 0.76, bz * 1.22 - 0.03], dtype=np.float32), bw * 0.98, 0.85, j1, j2, 0.55),
            (np.array([bx * 1.35 + sway_w, end_y + 0.08, bz * 1.15 - 0.02], dtype=np.float32), bw * 0.55, 0.60, j2, j2, 0.0),
            (np.array([bx * 1.38, end_y, bz * 1.10], dtype=np.float32), bw * 0.12, 0.28, j2, j2, 0.0),
        ]
        mb_hair.add_ribbon(pts, n_across=5, thickness=0.028, arch_z=0.014)
    primitives.append(mb_hair.build(mesh_index=len(primitives)))

    # ── 9–11. Camadas externas de roupa (omitidas no modo `base` = roupa de baixo limpa para fácil incrementação!) ──
    if not is_base_layer:
        mb_skirt = _MeshBuilder(material_index=6)
        if arch.outfit_style == "blouse_skirt":
            mb_skirt.add_open_skirt(
                y_top=0.73, y_bot=0.45, rx_top=0.118, rz_top=0.095, rx_bot=0.225, rz_bot=0.175,
                slit_half_angle_deg=0.0, j_hips=b_hips, j_l_leg=b_l_ul, j_r_leg=b_r_ul, pleats=14,
            )
        else:
            mb_skirt.add_open_skirt(
                y_top=0.72, y_bot=0.34, rx_top=0.124, rz_top=0.098, rx_bot=0.245, rz_bot=0.195,
                slit_half_angle_deg=34.0, j_hips=b_hips, j_l_leg=b_l_ul, j_r_leg=b_r_ul, pleats=0,
            )
        primitives.append(mb_skirt.build(mesh_index=len(primitives)))

        mb_lace = _MeshBuilder(material_index=7)
        if arch.outfit_style != "blouse_skirt":
            for sign in (-1.0, 1.0):
                ruffle = [
                    (np.array([sign * 0.110, 0.94, 0.075], dtype=np.float32), 0.026, 0.85, b_uchest, b_uchest, 0.0),
                    (np.array([sign * 0.132, 0.99, 0.042], dtype=np.float32), 0.032, 0.95, b_uchest, b_uchest, 0.0),
                    (np.array([sign * 0.128, 1.01, -0.020], dtype=np.float32), 0.030, 0.90, b_uchest, b_uchest, 0.0),
                    (np.array([sign * 0.105, 0.96, -0.072], dtype=np.float32), 0.024, 0.80, b_uchest, b_uchest, 0.0),
                ]
                mb_lace.add_ribbon(ruffle, n_across=4, thickness=0.011, arch_z=0.008)
        primitives.append(mb_lace.build(mesh_index=len(primitives)))

        mb_gold = _MeshBuilder(material_index=8)
        mb_gold.add_ellipsoid((0.0, 0.715, 0.095), (0.024, 0.020, 0.018), b_hips, n_lat=8, n_lon=12)
        for sign in (-1.0, 1.0):
            mb_gold.add_diamond_spike((sign * 0.016, 0.715, 0.098), (sign * 0.88, 0.18, 0.18), 0.068, 0.020, b_hips)
            mb_gold.add_diamond_spike((sign * 0.010, 0.708, 0.098), (sign * 0.32, -0.92, 0.15), 0.115, 0.016, b_hips)
        primitives.append(mb_gold.build(mesh_index=len(primitives)))

    # ── 12. Expressões & SpringBones ──
    expressions = {
        "blink": [(lid_mesh_idx, 0, 1.0)],
        "happy": [(lid_mesh_idx, 0, 0.25)],
        "relaxed": [(lid_mesh_idx, 0, 0.45)],
        "angry": [],
        "sad": [(lid_mesh_idx, 0, 0.22)],
        "surprised": [],
    }
    springs = [
        VrmSpringChain(joints=[b_hc0, b_hc1, b_hc2], stiffness=0.82, drag=0.45),
        VrmSpringChain(joints=[b_hl0, b_hl1, b_hl2], stiffness=0.86, drag=0.46),
        VrmSpringChain(joints=[b_hr0, b_hr1, b_hr2], stiffness=0.86, drag=0.46),
    ]

    return VrmModel(
        name=f"DungeonSquad_{arch.id}_{outfit_key}",
        is_vrm1=True,
        nodes=nodes,
        roots=[b_hips],
        skins=[skin],
        materials=materials,
        primitives=primitives,
        humanoid_bones=humanoid_bones,
        expressions=expressions,
        springs=springs,
        constraints=[],
        height=1.48,
        min_y=0.0,
    )
