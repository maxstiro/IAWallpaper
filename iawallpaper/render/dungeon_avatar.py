"""DUNGEON AVATAR — Gerador 3D procedural de waifu estilizada estilo Dungeon Squad (compatível 100% com VrmModel).

Constrói em memória (em < 40 ms, sem precisar pré-renderizar vídeos nem depender de arquivos externos) um
modelo 3D completo com esqueleto humanoide VRM 1.0, skinning suave, SpringBones (rabo-de-cavalo / mechas /
capa dupla esvoaçante), expressões faciais por morph targets (blink / happy / relaxed / shy / angry) e
proporções estilizadas icônicas de *Dungeon Squad* (~4.2 cabeças, rosto anime delicado com franja longa e
olhos grandes luminosos, cintura ampulheta, busto farto esculpido, quadris largos e coxas grossas, botas de
salto alto, halo celestial dourado giratório, chamas arcanas nas mãos e cajado/espada modular na mão esquerda).
"""

import math
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw

from ..core.persona import Persona
from .vrm_loader import (
    VrmMaterial,
    VrmModel,
    VrmNode,
    VrmPrimitive,
    VrmSkin,
    VrmSpringChain,
)


def _norm_rows(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.maximum(n, 1e-6)


class _MeshBuilder:
    """Acumulador de geometria 3D skinned com pesos ósseos suaves e cálculo automático de normais."""

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
        n_seg: int = 24,
        shape_fn: Callable[[float, float], tuple[float, float]] | None = None,
        cap_bottom: bool = False,
        cap_top: bool = False,
    ) -> None:
        ring_list = list(rings)
        if cap_bottom and ring_list:
            c0, rx0, rz0, v0, tx0, j0, j1, w1 = ring_list[0]
            ring_list.insert(0, (c0 - np.array([0.0, 0.004, 0.0], dtype=np.float32), 0.002, 0.002, v0, tx0, j0, j1, w1))
        if cap_top and ring_list:
            c1, rx1, rz1, v1, tx1, j0, j1, w1 = ring_list[-1]
            ring_list.append((c1 + np.array([0.0, 0.004, 0.0], dtype=np.float32), 0.002, 0.002, v1, tx1, j0, j1, w1))

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
        n_lat: int = 16,
        n_lon: int = 24,
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
        arch_z: float = 0.015,
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

    def add_torus(
        self,
        center: tuple[float, float, float],
        major_r: float,
        minor_r: float,
        joint_idx: int,
        n_major: int = 36,
        n_minor: int = 10,
        plane: str = "xy",
    ) -> None:
        cx, cy, cz = center
        pos = np.zeros((n_major + 1, n_minor + 1, 3), dtype=np.float32)
        uv = np.zeros((n_major + 1, n_minor + 1, 2), dtype=np.float32)
        jts = np.zeros((n_major + 1, n_minor + 1, 4), dtype=np.float32)
        wts = np.zeros((n_major + 1, n_minor + 1, 4), dtype=np.float32)

        for i in range(n_major + 1):
            u = i / n_major
            th = u * math.tau
            ct, st = math.cos(th), math.sin(th)
            for j in range(n_minor + 1):
                v = j / n_minor
                ph = v * math.tau
                cp, sp = math.cos(ph), math.sin(ph)
                rr = major_r + minor_r * cp
                if plane == "xy":
                    x = cx + rr * ct
                    y = cy + rr * st
                    z = cz + minor_r * sp
                else:
                    x = cx + rr * ct
                    y = cy + minor_r * sp
                    z = cz + rr * st
                pos[i, j] = (x, y, z)
                uv[i, j] = (u, v)
                jts[i, j] = (float(joint_idx), 0.0, 0.0, 0.0)
                wts[i, j] = (1.0, 0.0, 0.0, 0.0)

        self.add_grid(pos, uv, jts, wts, wrap_u=True, flip_winding=False)

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
# Texturas procedurais crisp de alta leitura para Pixel-Art 3D
# ─────────────────────────────────────────────────────────────────────────────


def _make_anime_face_texture(
    skin_rgb: tuple[int, int, int],
    eye_rgb: tuple[int, int, int],
    hair_rgb: tuple[int, int, int],
) -> np.ndarray:
    """Textura facial anime estilo Dungeon Squad: olhos grandes e brilhantes + bochechas rosadas limpas."""
    w, h = 512, 512
    img = Image.new("RGBA", (w, h), (*skin_rgb, 255))

    # Olhos posicionados na faixa média-baixa do rosto (estética fofa de Titan / Priestess / Valkyrie!)
    eye_cy = int(h * 0.60)
    eye_dx = int(w * 0.066)
    cx = w // 2

    # Blush rosado suave nas bochechas
    blush = (min(255, skin_rgb[0] + 10), max(0, skin_rgb[1] - 46), max(0, skin_rgb[2] - 34), 125)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for sign in (-1, 1):
        bx = cx + sign * int(w * 0.095)
        by = eye_cy + int(h * 0.072)
        od.ellipse([bx - 24, by - 11, bx + 24, by + 11], fill=blush)
    img = Image.alpha_composite(img, overlay)
    d = ImageDraw.Draw(img)

    er, eg, eb = eye_rgb
    iris_dark = (max(0, int(er * 0.36)), max(0, int(eg * 0.36)), max(0, int(eb * 0.44)), 255)
    iris_mid = (min(255, int(er * 1.08)), min(255, int(eg * 1.08)), min(255, int(eb * 1.12)), 255)
    iris_glow = (min(255, er + 105), min(255, eg + 105), min(255, eb + 110), 255)
    lash_col = (22, 12, 32, 255)

    for sign in (-1, 1):
        ex = cx + sign * eye_dx
        # Esclera branca limpa
        d.ellipse([ex - 21, eye_cy - 30, ex + 21, eye_cy + 27], fill=(252, 252, 255, 255))
        # Íris vertical grande tipo joia
        d.ellipse([ex - 17, eye_cy - 25, ex + 17, eye_cy + 25], fill=iris_dark)
        d.ellipse([ex - 15, eye_cy - 14, ex + 15, eye_cy + 22], fill=iris_mid)
        d.ellipse([ex - 11, eye_cy + 2, ex + 11, eye_cy + 20], fill=iris_glow)
        # Pupila
        d.ellipse([ex - 7, eye_cy - 8, ex + 7, eye_cy + 7], fill=(16, 10, 26, 255))
        # Brilhos catchlight crisp
        d.ellipse([ex - 12, eye_cy - 19, ex - 2, eye_cy - 8], fill=(255, 255, 255, 255))
        d.ellipse([ex + 4, eye_cy + 7, ex + 11, eye_cy + 14], fill=(255, 255, 255, 240))
        # Cílio superior bem definido
        d.arc([ex - 24, eye_cy - 34, ex + 24, eye_cy + 14], start=190, end=350, fill=lash_col, width=9)

    # Boca minúscula suave (em Dungeon Squad o rosto é limpo, foco total nos olhos!)
    my = eye_cy + int(h * 0.115)
    d.arc([cx - 8, my - 3, cx + 8, my + 6], start=15, end=165, fill=(190, 104, 118, 255), width=3)

    # Fundo de cabelo atrás/topo
    d.rectangle([0, 0, w, int(h * 0.36)], fill=(*hair_rgb, 255))
    d.rectangle([0, 0, int(w * 0.25), h], fill=(*hair_rgb, 255))
    d.rectangle([int(w * 0.75), 0, w, h], fill=(*hair_rgb, 255))
    return np.array(img, dtype=np.uint8)


def _make_bodysuit_torso_texture(
    skin_rgb: tuple[int, int, int],
    suit_rgb: tuple[int, int, int],
    trim_rgb: tuple[int, int, int],
    accent_rgb: tuple[int, int, int],
    style: str = "astral",
) -> np.ndarray:
    """Textura esculpida do tronco/quadris: bodysuit cavado / armadura / corset com recorte natural no colo."""
    w, h = 512, 512
    img = Image.new("RGBA", (w, h), (*skin_rgb, 255))
    d = ImageDraw.Draw(img)
    cx = w // 2

    suit = (*suit_rgb, 255)
    trim = (*trim_rgb, 255)
    accent = (*accent_rgb, 255)

    # Base pélvica traseira + frente em V cavado destacando quadris e coxas!
    d.rectangle([0, 0, w, int(h * 0.22)], fill=suit)
    hip_cut_l = [(cx - 128, int(h * 0.03)), (cx - 42, int(h * 0.03)), (cx - 28, int(h * 0.32)), (cx - 144, int(h * 0.32))]
    hip_cut_r = [(cx + 42, int(h * 0.03)), (cx + 128, int(h * 0.03)), (cx + 144, int(h * 0.32)), (cx + 28, int(h * 0.32))]
    d.polygon(hip_cut_l, fill=(*skin_rgb, 255))
    d.polygon(hip_cut_r, fill=(*skin_rgb, 255))

    front_panel = [
        (cx - 38, 0),
        (cx + 38, 0),
        (cx + 52, int(h * 0.42)),
        (cx + 84, int(h * 0.64)),
        (cx - 84, int(h * 0.64)),
        (cx - 52, int(h * 0.42)),
    ]
    d.polygon(front_panel, fill=suit)

    # Costas cobertas até a altura das escápulas
    d.rectangle([0, 0, int(w * 0.22), int(h * 0.72)], fill=suit)
    d.rectangle([int(w * 0.78), 0, w, int(h * 0.72)], fill=suit)

    if style == "priestess":
        d.rectangle([0, int(h * 0.34), w, int(h * 0.41)], fill=trim)
        d.line([(cx - 38, 0), (cx - 52, int(h * 0.42)), (cx - 84, int(h * 0.64))], fill=trim, width=8)
        d.line([(cx + 38, 0), (cx + 52, int(h * 0.42)), (cx + 84, int(h * 0.64))], fill=trim, width=8)
    elif style == "valkyrie":
        d.rectangle([0, int(h * 0.28), w, int(h * 0.62)], fill=suit)
        d.rectangle([0, int(h * 0.31), w, int(h * 0.37)], fill=trim)
        d.line([(cx, int(h * 0.12)), (cx, int(h * 0.64))], fill=trim, width=7)
    else:
        d.line([(cx - 38, 0), (cx - 52, int(h * 0.42)), (cx - 84, int(h * 0.64))], fill=accent, width=7)
        d.line([(cx + 38, 0), (cx + 52, int(h * 0.42)), (cx + 84, int(h * 0.64))], fill=accent, width=7)
        d.polygon([(cx, int(h * 0.30)), (cx + 20, int(h * 0.38)), (cx, int(h * 0.46)), (cx - 20, int(h * 0.38))], fill=trim)

    # Gargantilha fina delicada no pescoço (deixa colo aberto e elegante!)
    d.rectangle([0, int(h * 0.87), w, int(h * 0.92)], fill=suit)
    d.rectangle([0, int(h * 0.89), w, int(h * 0.91)], fill=trim)
    return np.array(img, dtype=np.uint8)


def _make_bust_texture(
    skin_rgb: tuple[int, int, int],
    suit_rgb: tuple[int, int, int],
    trim_rgb: tuple[int, int, int],
    accent_rgb: tuple[int, int, int],
) -> np.ndarray:
    w, h = 256, 256
    img = Image.new("RGBA", (w, h), (*skin_rgb, 255))
    d = ImageDraw.Draw(img)
    split_y = int(h * 0.52)
    d.rectangle([0, split_y, w, h], fill=(*suit_rgb, 255))
    d.rectangle([0, split_y - 7, w, split_y + 5], fill=(*trim_rgb, 255))
    d.line([(0, split_y + 20), (w, split_y + 20)], fill=(*accent_rgb, 255), width=5)
    return np.array(img, dtype=np.uint8)


def _make_leg_texture(
    skin_rgb: tuple[int, int, int],
    boot_rgb: tuple[int, int, int],
    trim_rgb: tuple[int, int, int],
    accent_rgb: tuple[int, int, int],
    style: str = "astral",
) -> np.ndarray:
    w, h = 256, 512
    img = Image.new("RGBA", (w, h), (*skin_rgb, 255))
    d = ImageDraw.Draw(img)
    cx = w // 2

    boot_top = int(h * 0.55) if style != "priestess" else int(h * 0.48)
    d.rectangle([0, 0, w, boot_top], fill=(*boot_rgb, 255))
    d.polygon(
        [(cx - 56, boot_top - 10), (cx, boot_top + 42), (cx + 56, boot_top - 10)],
        fill=(*boot_rgb, 255),
    )
    d.line([(0, boot_top), (cx - 56, boot_top - 10), (cx, boot_top + 42), (cx + 56, boot_top - 10), (w, boot_top)], fill=(*trim_rgb, 255), width=8)
    d.line([(cx, int(h * 0.08)), (cx, boot_top + 24)], fill=(*accent_rgb, 255), width=8)
    if style in ("valkyrie", "priestess"):
        gy = int(h * 0.74)
        d.rectangle([0, gy, w, gy + 13], fill=(*boot_rgb, 255))
        d.rectangle([0, gy + 4, w, gy + 8], fill=(*trim_rgb, 255))
    return np.array(img, dtype=np.uint8)


def _make_arm_texture(
    skin_rgb: tuple[int, int, int],
    glove_rgb: tuple[int, int, int],
    trim_rgb: tuple[int, int, int],
    accent_rgb: tuple[int, int, int],
) -> np.ndarray:
    w, h = 256, 256
    img = Image.new("RGBA", (w, h), (*skin_rgb, 255))
    d = ImageDraw.Draw(img)
    glove_start = int(h * 0.44)
    d.rectangle([0, glove_start, w, h], fill=(*glove_rgb, 255))
    d.rectangle([0, glove_start - 5, w, glove_start + 7], fill=(*trim_rgb, 255))
    d.line([(w // 2, glove_start + 14), (w // 2, h - 18)], fill=(*accent_rgb, 255), width=6)
    return np.array(img, dtype=np.uint8)


def _make_cape_texture(
    outer_rgb: tuple[int, int, int],
    inner_rgb: tuple[int, int, int],
    trim_rgb: tuple[int, int, int],
) -> np.ndarray:
    """Capa escura elegante estilo Titan_idle: obsidiana escura nos dois lados com forro sombrio e barra dourada!"""
    w, h = 256, 256
    img = Image.new("RGBA", (w, h), (*outer_rgb, 255))
    d = ImageDraw.Draw(img)
    # Interior mais rico mas AINDA escuro (destaca as coxas claras em alto contraste — igual Titan_idle!)
    d.rectangle([w // 2, 0, w, h], fill=(*inner_rgb, 255))
    # Bordas laterais e barra inferior douradas refinadas
    d.rectangle([0, int(h * 0.87), w, h], fill=(*trim_rgb, 255))
    d.rectangle([w // 2 - 14, 0, w // 2 + 14, h], fill=(*trim_rgb, 255))
    d.rectangle([0, 0, 12, h], fill=(*trim_rgb, 255))
    d.rectangle([w - 12, 0, w, h], fill=(*trim_rgb, 255))
    return np.array(img, dtype=np.uint8)


# ─────────────────────────────────────────────────────────────────────────────
# Paletas modulares por traje / persona
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_outfit_palette(persona: Persona, outfit_key: str) -> dict[str, object]:
    hr, hg, hb = persona.hair_color
    er, eg, eb = persona.eye_color

    if outfit_key in ("focus", "cozy"):
        style = "priestess"
        suit = (36, 26, 54)
        boot = (26, 20, 40)
        trim = (242, 198, 92)
        accent = (196, 128, 255)
        cape_out = (26, 20, 44)
        cape_in = (58, 36, 92)
        halo_col = (1.0, 0.88, 0.44)
        flame_col = (0.76, 0.45, 1.0)
        skin = (252, 226, 212)
    elif outfit_key in ("casual", "rainy"):
        style = "valkyrie"
        suit = (44, 48, 66)
        boot = (32, 36, 52)
        trim = (232, 204, 128)
        accent = (102, 218, 255)
        cape_out = (22, 38, 86)
        cape_in = (34, 58, 122)
        halo_col = (1.0, 0.94, 0.68)
        flame_col = (0.48, 0.92, 1.0)
        skin = (252, 224, 210)
    else:
        style = "astral"
        suit = (22, 20, 30)
        boot = (20, 18, 28)
        trim = (242, 198, 94)
        accent = (118, 242, 255)
        cape_out = (20, 18, 28)
        cape_in = (44, 36, 52)
        halo_col = (1.0, 0.96, 0.80)
        flame_col = (0.52, 0.96, 1.0)
        skin = (248, 224, 214)

    if persona.id == "nyx":
        hair = (224, 196, 232) if style == "astral" else (190, 52, 88)
        eye = (255, 78, 128)
        accent = (255, 86, 142) if style != "astral" else (255, 118, 176)
        flame_col = (1.0, 0.36, 0.64)
        halo_col = (1.0, 0.84, 0.42)
    elif persona.id == "mira":
        hair = (238, 236, 246) if style == "astral" else (min(255, hr + 48), min(255, hg + 45), min(255, hb + 52))
        eye = (max(80, er), max(115, eg), min(255, eb + 30))
    else:
        hair = (min(255, max(40, hr)), min(255, max(40, hg)), min(255, max(40, hb)))
        eye = (er, eg, eb)

    return {
        "style": style,
        "skin": skin,
        "hair": hair,
        "eye": eye,
        "suit": suit,
        "boot": boot,
        "trim": trim,
        "accent": accent,
        "cape_out": cape_out,
        "cape_in": cape_in,
        "halo_col": halo_col,
        "flame_col": flame_col,
    }


def build_dungeon_squad_model(persona: Persona, outfit_key: str = "starlight") -> VrmModel:
    """Constrói um `VrmModel` 3D estilizado de alta arte no padrão *Dungeon Squad* pronto para GPU."""
    pal = _resolve_outfit_palette(persona, outfit_key)
    style = str(pal["style"])
    skin_rgb = pal["skin"]
    hair_rgb = pal["hair"]
    eye_rgb = pal["eye"]
    suit_rgb = pal["suit"]
    boot_rgb = pal["boot"]
    trim_rgb = pal["trim"]
    accent_rgb = pal["accent"]
    cape_out = pal["cape_out"]
    cape_in = pal["cape_in"]
    halo_col = pal["halo_col"]
    flame_col = pal["flame_col"]

    # ── 1. Hierarquia de Ossos VRM 1.0 (~4.2 cabeças, curvas acentuadas!) ──
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

    b_hips = _add_bone("hips", (0.0, 0.56, 0.0), None)
    b_spine = _add_bone("spine", (0.0, 0.67, 0.0), "hips")
    b_chest = _add_bone("chest", (0.0, 0.78, 0.0), "spine")
    b_uchest = _add_bone("upperChest", (0.0, 0.87, 0.0), "chest")
    b_neck = _add_bone("neck", (0.0, 0.94, 0.0), "upperChest")
    b_head = _add_bone("head", (0.0, 0.99, 0.0), "neck")

    b_l_sh = _add_bone("leftShoulder", (0.055, 0.90, 0.0), "upperChest")
    b_l_ua = _add_bone("leftUpperArm", (0.125, 0.89, 0.0), "leftShoulder")
    b_l_la = _add_bone("leftLowerArm", (0.285, 0.89, 0.0), "leftUpperArm")
    b_l_hd = _add_bone("leftHand", (0.435, 0.89, 0.0), "leftLowerArm")

    b_r_sh = _add_bone("rightShoulder", (-0.055, 0.90, 0.0), "upperChest")
    b_r_ua = _add_bone("rightUpperArm", (-0.125, 0.89, 0.0), "rightShoulder")
    b_r_la = _add_bone("rightLowerArm", (-0.285, 0.89, 0.0), "rightUpperArm")
    b_r_hd = _add_bone("rightHand", (-0.435, 0.89, 0.0), "rightLowerArm")

    b_l_ul = _add_bone("leftUpperLeg", (0.095, 0.54, 0.0), "hips")
    b_l_ll = _add_bone("leftLowerLeg", (0.100, 0.28, 0.0), "leftUpperLeg")
    b_l_ft = _add_bone("leftFoot", (0.100, 0.055, 0.015), "leftLowerLeg")

    b_r_ul = _add_bone("rightUpperLeg", (-0.095, 0.54, 0.0), "hips")
    b_r_ll = _add_bone("rightLowerLeg", (-0.100, 0.28, 0.0), "rightUpperLeg")
    b_r_ft = _add_bone("rightFoot", (-0.100, 0.055, 0.015), "rightLowerLeg")

    # Rabo-de-cavalo esvoaçante arqueando graciosamente para trás/lado (sem jamais atravessar a capa!)
    b_pt0 = _add_bone("ponytail_0", (0.04, 1.24, -0.15), "head")
    b_pt1 = _add_bone("ponytail_1", (0.20, 0.98, -0.27), "ponytail_0")
    b_pt2 = _add_bone("ponytail_2", (0.34, 0.64, -0.32), "ponytail_1")
    b_pt3 = _add_bone("ponytail_3", (0.42, 0.28, -0.30), "ponytail_2")

    b_hl0 = _add_bone("hair_l_0", (0.12, 1.12, 0.045), "head")
    b_hl1 = _add_bone("hair_l_1", (0.13, 0.94, 0.035), "hair_l_0")
    b_hr0 = _add_bone("hair_r_0", (-0.12, 1.12, 0.045), "head")
    b_hr1 = _add_bone("hair_r_1", (-0.13, 0.94, 0.035), "hair_r_0")

    # Abas da capa abertas em V largo para emoldurar e revelar 100% o vão entre as coxas!
    b_cl0 = _add_bone("cape_l_0", (0.14, 0.89, -0.10), "upperChest")
    b_cl1 = _add_bone("cape_l_1", (0.28, 0.60, -0.15), "cape_l_0")
    b_cl2 = _add_bone("cape_l_2", (0.44, 0.20, -0.19), "cape_l_1")

    b_cr0 = _add_bone("cape_r_0", (-0.14, 0.89, -0.10), "upperChest")
    b_cr1 = _add_bone("cape_r_1", (-0.28, 0.60, -0.15), "cape_r_0")
    b_cr2 = _add_bone("cape_r_2", (-0.44, 0.20, -0.19), "cape_r_1")

    b_halo = _add_bone("halo_ring", (0.0, 1.18, -0.19), "upperChest")

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

    # ── 2. Materiais ──
    hr_f, hg_f, hb_f = hair_rgb[0] / 255.0, hair_rgb[1] / 255.0, hair_rgb[2] / 255.0
    sr_f, sg_f, sb_f = skin_rgb[0] / 255.0, skin_rgb[1] / 255.0, skin_rgb[2] / 255.0
    tr_f, tg_f, tb_f = trim_rgb[0] / 255.0, trim_rgb[1] / 255.0, trim_rgb[2] / 255.0

    materials = [
        VrmMaterial(0, "ds_face", "face", (1.0, 1.0, 1.0, 1.0), (0.86, 0.76, 0.80), _make_anime_face_texture(skin_rgb, eye_rgb, hair_rgb)),
        VrmMaterial(1, "ds_torso", "tops", (1.0, 1.0, 1.0, 1.0), (0.72, 0.64, 0.78), _make_bodysuit_torso_texture(skin_rgb, suit_rgb, trim_rgb, accent_rgb, style)),
        VrmMaterial(2, "ds_bust", "skin", (1.0, 1.0, 1.0, 1.0), (0.80, 0.68, 0.76), _make_bust_texture(skin_rgb, suit_rgb, trim_rgb, accent_rgb)),
        VrmMaterial(3, "ds_legs", "bottoms", (1.0, 1.0, 1.0, 1.0), (0.76, 0.66, 0.78), _make_leg_texture(skin_rgb, boot_rgb, trim_rgb, accent_rgb, style)),
        VrmMaterial(4, "ds_arms", "skin", (1.0, 1.0, 1.0, 1.0), (0.78, 0.68, 0.76), _make_arm_texture(skin_rgb, suit_rgb, trim_rgb, accent_rgb)),
        VrmMaterial(5, "ds_hair", "hair", (hr_f, hg_f, hb_f, 1.0), (hr_f * 0.60, hg_f * 0.58, min(1.0, hb_f * 0.74)), None, double_sided=True),
        VrmMaterial(6, "ds_cape", "cape", (1.0, 1.0, 1.0, 1.0), (0.56, 0.52, 0.66), _make_cape_texture(cape_out, cape_in, trim_rgb), double_sided=True),
        VrmMaterial(7, "ds_gold", "gold", (tr_f, tg_f, tb_f, 1.0), (tr_f * 0.62, tg_f * 0.50, tb_f * 0.34), None),
        VrmMaterial(8, "ds_halo_emissive", "emissive", (halo_col[0], halo_col[1], halo_col[2], 1.0), (1.0, 0.92, 0.68), None, double_sided=True),
        VrmMaterial(9, "ds_flame_emissive", "emissive", (flame_col[0], flame_col[1], flame_col[2], 1.0), (0.8, 0.95, 1.0), None, double_sided=True),
        VrmMaterial(10, "ds_eyelid", "skin", (sr_f, sg_f, sb_f, 1.0), (sr_f * 0.85, sg_f * 0.78, sb_f * 0.80), None),
    ]

    primitives: list[VrmPrimitive] = []

    # ── 3. Tronco Ampulheta Esculpido ──
    mb_torso = _MeshBuilder(material_index=1)

    def _torso_shape(theta: float, v: float) -> tuple[float, float]:
        back = max(0.0, -math.cos(theta))
        hip_zone = math.exp(-((v - 0.16) / 0.14) ** 2)
        return (1.0, 1.0 + back * 0.26 * hip_zone)

    torso_rings = [
        (np.array([0.0, 0.45, 0.0], dtype=np.float32), 0.120, 0.095, 0.00, -0.005, b_hips, b_hips, 0.0),
        (np.array([0.0, 0.50, 0.0], dtype=np.float32), 0.168, 0.124, 0.10, -0.012, b_hips, b_hips, 0.0),
        (np.array([0.0, 0.56, 0.0], dtype=np.float32), 0.174, 0.128, 0.20, -0.014, b_hips, b_spine, 0.15),
        (np.array([0.0, 0.63, 0.0], dtype=np.float32), 0.120, 0.092, 0.32, -0.006, b_hips, b_spine, 0.65),
        (np.array([0.0, 0.70, 0.0], dtype=np.float32), 0.086, 0.072, 0.44,  0.002, b_spine, b_chest, 0.30),
        (np.array([0.0, 0.77, 0.0], dtype=np.float32), 0.108, 0.086, 0.58,  0.005, b_chest, b_chest, 0.0),
        (np.array([0.0, 0.85, 0.0], dtype=np.float32), 0.122, 0.092, 0.72,  0.002, b_chest, b_uchest, 0.65),
        (np.array([0.0, 0.91, 0.0], dtype=np.float32), 0.108, 0.076, 0.82, -0.004, b_uchest, b_neck, 0.25),
        (np.array([0.0, 0.95, 0.0], dtype=np.float32), 0.045, 0.044, 0.90, -0.004, b_neck, b_head, 0.25),
        (np.array([0.0, 1.02, 0.0], dtype=np.float32), 0.042, 0.042, 1.00, -0.004, b_neck, b_head, 0.75),
    ]
    mb_torso.add_loft(torso_rings, n_seg=28, shape_fn=_torso_shape, cap_bottom=True, cap_top=True)
    primitives.append(mb_torso.build(mesh_index=len(primitives)))

    # ── 4. Busto Voluptuoso Esculpido ──
    mb_bust = _MeshBuilder(material_index=2)
    for sign in (-1.0, 1.0):
        def _bust_deform(x: float, y: float, z: float, u: float, v: float, s: float = sign) -> tuple[float, float, float]:
            drop = -0.014 * max(0.0, z / 0.095)
            flare = s * 0.012 * max(0.0, z / 0.095)
            return (x + flare, y + drop, z)

        mb_bust.add_ellipsoid(
            center=(sign * 0.068, 0.822, 0.088),
            radii=(0.082, 0.084, 0.092),
            joint_idx=b_chest,
            n_lat=14,
            n_lon=20,
            deform_fn=_bust_deform,
            joint_b=b_uchest,
            weight_b_fn=lambda v: 0.30 * v,
        )
    primitives.append(mb_bust.build(mesh_index=len(primitives)))

    # ── 5. Coxas Grossas Voluptuosas, Panturrilhas e Botas de Salto Alto ──
    mb_legs = _MeshBuilder(material_index=3)
    for side, j_ul, j_ll, j_ft in ((1.0, b_l_ul, b_l_ll, b_l_ft), (-1.0, b_r_ul, b_r_ll, b_r_ft)):
        lx = side * 0.098

        def _thigh_shape(theta: float, v: float, s: float = side) -> tuple[float, float]:
            outer = max(0.0, s * math.sin(theta))
            thigh_bulge = math.exp(-((v - 0.78) / 0.18) ** 2)
            calf_back = max(0.0, -math.cos(theta)) * math.exp(-((v - 0.34) / 0.14) ** 2)
            return (1.0 + outer * 0.25 * thigh_bulge, 1.0 + calf_back * 0.22)

        leg_rings = [
            (np.array([lx, 0.005, 0.032], dtype=np.float32), 0.036, 0.068, 0.00, 0.012, j_ft, j_ft, 0.0),
            (np.array([lx, 0.055, 0.012], dtype=np.float32), 0.038, 0.044, 0.08, 0.000, j_ft, j_ll, 0.35),
            (np.array([lx, 0.125, 0.000], dtype=np.float32), 0.042, 0.045, 0.20, -0.004, j_ll, j_ll, 0.0),
            (np.array([lx, 0.215, 0.000], dtype=np.float32), 0.058, 0.062, 0.36, -0.008, j_ll, j_ll, 0.0),
            (np.array([lx, 0.285, 0.004], dtype=np.float32), 0.062, 0.064, 0.50,  0.004, j_ll, j_ul, 0.50),
            (np.array([lx, 0.365, 0.004], dtype=np.float32), 0.085, 0.089, 0.64,  0.002, j_ul, j_ul, 0.0),
            (np.array([lx, 0.455, 0.002], dtype=np.float32), 0.106, 0.110, 0.80, -0.004, j_ul, b_hips, 0.18),
            (np.array([lx * 0.92, 0.540, 0.000], dtype=np.float32), 0.108, 0.112, 0.94, -0.008, j_ul, b_hips, 0.58),
            (np.array([lx * 0.78, 0.580, 0.000], dtype=np.float32), 0.086, 0.090, 1.00, -0.006, b_hips, b_hips, 0.0),
        ]
        mb_legs.add_loft(leg_rings, n_seg=22, shape_fn=_thigh_shape, cap_bottom=True, cap_top=True)
        mb_legs.add_diamond_spike((lx, 0.055, -0.030), (0.0, -1.0, -0.08), 0.055, 0.015, j_ft)
    primitives.append(mb_legs.build(mesh_index=len(primitives)))

    # ── 6. Braços Delicados e Mãos com Luvas Longas ──
    mb_arms = _MeshBuilder(material_index=4)
    for side, j_sh, j_ua, j_la, j_hd in (
        (1.0, b_l_sh, b_l_ua, b_l_la, b_l_hd),
        (-1.0, b_r_sh, b_r_ua, b_r_la, b_r_hd),
    ):
        arm_stations = [
            (0.115, 0.042, 0.042, 0.00, j_sh, j_ua, 0.60),
            (0.165, 0.038, 0.038, 0.20, j_ua, j_ua, 0.00),
            (0.235, 0.034, 0.034, 0.42, j_ua, j_la, 0.15),
            (0.285, 0.031, 0.031, 0.56, j_ua, j_la, 0.55),
            (0.355, 0.029, 0.029, 0.74, j_la, j_la, 0.00),
            (0.425, 0.023, 0.021, 0.90, j_la, j_hd, 0.70),
            (0.470, 0.030, 0.017, 0.97, j_hd, j_hd, 0.00),
            (0.505, 0.016, 0.011, 1.00, j_hd, j_hd, 0.00),
        ]
        n_r = len(arm_stations)
        n_seg = 14
        pos = np.zeros((n_r, n_seg + 1, 3), dtype=np.float32)
        uv = np.zeros((n_r, n_seg + 1, 2), dtype=np.float32)
        jts = np.zeros((n_r, n_seg + 1, 4), dtype=np.float32)
        wts = np.zeros((n_r, n_seg + 1, 4), dtype=np.float32)
        for r, (x_off, ry, rz, v_c, j0, j1, w1) in enumerate(arm_stations):
            for c in range(n_seg + 1):
                u = c / n_seg
                ang = u * math.tau
                pos[r, c] = (side * x_off, 0.89 + math.cos(ang) * ry, math.sin(ang) * rz)
                uv[r, c] = (u, v_c)
                jts[r, c] = (float(j0), float(j1), 0.0, 0.0)
                wts[r, c] = (1.0 - w1, w1, 0.0, 0.0)
        mb_arms.add_grid(pos, uv, jts, wts, wrap_u=True, flip_winding=(side < 0))
    primitives.append(mb_arms.build(mesh_index=len(primitives)))

    # ── 7. Cabeça Anime Fofa e Compacta (estilo Titan / Priestess!) ──
    mb_head = _MeshBuilder(material_index=0)

    def _head_deform(x: float, y: float, z: float, u: float, v: float) -> tuple[float, float, float]:
        chin_t = max(0.0, (0.40 - v) / 0.40)
        x_scale = 1.0 - 0.28 * (chin_t ** 1.35)
        z_scale = 1.0 - 0.16 * (chin_t ** 1.35)
        if z > 0.0:
            z *= 0.93
        return (x * x_scale, y, z * z_scale)

    mb_head.add_ellipsoid(
        center=(0.0, 1.125, 0.008),
        radii=(0.138, 0.144, 0.134),
        joint_idx=b_head,
        n_lat=22,
        n_lon=32,
        deform_fn=_head_deform,
    )
    primitives.append(mb_head.build(mesh_index=len(primitives)))

    # ── 7b. Pálpebras animadas por Morph Target (blink / happy / sleepy!) ──
    mb_lid = _MeshBuilder(material_index=10)
    for sign in (-1.0, 1.0):
        mb_lid.add_ellipsoid(
            center=(sign * 0.050, 1.114, 0.118),
            radii=(0.034, 0.025, 0.015),
            joint_idx=b_head,
            n_lat=8,
            n_lon=12,
        )
    lid_prim = mb_lid.build(mesh_index=len(primitives))
    open_pos = lid_prim.positions.copy()
    closed_pos = lid_prim.positions.copy()
    open_pos[:, 2] -= 0.036
    open_pos[:, 1] += 0.012
    closed_pos[:, 2] += 0.008
    lid_prim.positions = open_pos
    lid_prim.morph_deltas = [closed_pos - open_pos]
    lid_mesh_idx = len(primitives)
    primitives.append(lid_prim)

    # ── 8. Cabelo Anime Volumoso (Franja Longa Fofa + Mechas Laterais + Rabo-de-Cavalo Esvoaçante!) ──
    mb_hair = _MeshBuilder(material_index=5)
    mb_hair.add_ellipsoid(
        center=(0.0, 1.148, -0.014),
        radii=(0.156, 0.152, 0.152),
        joint_idx=b_head,
        n_lat=16,
        n_lon=24,
        deform_fn=lambda x, y, z, u, v: (x, y if v > 0.25 else y + 0.03, z if z < 0.075 else 0.075),
    )

    # Franja espessa cobrindo toda a testa até logo acima dos olhos (estilo Titan_idle & Valkyrie!)
    bang_configs = [
        (-0.098, 0.046, 1.095, 0.132),
        (-0.048, 0.045, 1.122, 0.150),
        (0.000,  0.046, 1.112, 0.154),
        (0.048,  0.045, 1.122, 0.150),
        (0.098,  0.046, 1.095, 0.132),
    ]
    for bx, bw, bot_y, front_z in bang_configs:
        pts = [
            (np.array([bx * 0.62, 1.280, 0.040], dtype=np.float32), bw * 0.75, 1.0, b_head, b_head, 0.0),
            (np.array([bx * 0.88, 1.210, front_z * 0.94], dtype=np.float32), bw * 0.95, 1.1, b_head, b_head, 0.0),
            (np.array([bx, bot_y + 0.036, front_z], dtype=np.float32), bw * 0.88, 0.92, b_head, b_head, 0.0),
            (np.array([bx * 1.02, bot_y, front_z * 0.96], dtype=np.float32), bw * 0.26, 0.45, b_head, b_head, 0.0),
        ]
        mb_hair.add_ribbon(pts, n_across=4, thickness=0.022, arch_z=0.012)

    # Mechas laterais abraçando delicadamente o contorno das bochechas
    for sign, j0, j1 in ((1.0, b_hl0, b_hl1), (-1.0, b_hr0, b_hr1)):
        pts = [
            (np.array([sign * 0.125, 1.20, 0.048], dtype=np.float32), 0.036, 1.0, b_head, j0, 0.35),
            (np.array([sign * 0.140, 1.09, 0.062], dtype=np.float32), 0.040, 1.0, j0, j0, 0.0),
            (np.array([sign * 0.142, 0.97, 0.052], dtype=np.float32), 0.030, 0.8, j0, j1, 0.70),
            (np.array([sign * 0.126, 0.88, 0.038], dtype=np.float32), 0.010, 0.4, j1, j1, 0.0),
        ]
        mb_hair.add_ribbon(pts, n_across=4, thickness=0.020, arch_z=0.010, side_axis=np.array([0.0, 0.0, 1.0], dtype=np.float32))

    # Rabo-de-cavalo alto arqueando para trás e para o lado (sem nunca furar a capa!)
    top_knot = [
        (np.array([0.01, 1.25, -0.09], dtype=np.float32), 0.054, 1.1, b_head, b_pt0, 0.35),
        (np.array([0.04, 1.35, -0.14], dtype=np.float32), 0.064, 1.25, b_pt0, b_pt0, 0.0),
        (np.array([0.11, 1.22, -0.22], dtype=np.float32), 0.088, 1.2, b_pt0, b_pt1, 0.50),
        (np.array([0.24, 0.92, -0.28], dtype=np.float32), 0.110, 1.1, b_pt1, b_pt2, 0.45),
        (np.array([0.36, 0.58, -0.31], dtype=np.float32), 0.088, 0.9, b_pt2, b_pt3, 0.55),
        (np.array([0.44, 0.24, -0.28], dtype=np.float32), 0.032, 0.45, b_pt3, b_pt3, 0.0),
        (np.array([0.47, 0.12, -0.25], dtype=np.float32), 0.008, 0.20, b_pt3, b_pt3, 0.0),
    ]
    mb_hair.add_ribbon(top_knot, n_across=5, thickness=0.038, arch_z=0.018)

    tail_2 = [
        (np.array([-0.03, 1.22, -0.13], dtype=np.float32), 0.068, 1.0, b_head, b_pt0, 0.45),
        (np.array([0.06, 0.96, -0.23], dtype=np.float32), 0.086, 0.95, b_pt0, b_pt1, 0.65),
        (np.array([0.17, 0.64, -0.27], dtype=np.float32), 0.072, 0.80, b_pt1, b_pt2, 0.70),
        (np.array([0.26, 0.30, -0.25], dtype=np.float32), 0.024, 0.42, b_pt2, b_pt3, 0.85),
    ]
    mb_hair.add_ribbon(tail_2, n_across=4, thickness=0.028, arch_z=0.012)
    primitives.append(mb_hair.build(mesh_index=len(primitives)))

    # ── 9. Capa Dupla Dramática Escura em V Largo (revela 100% as coxas + barra dourada elegante!) ──
    mb_cape = _MeshBuilder(material_index=6)
    # Manto delicado apenas sobre os ombros/nuca (acima do decote!)
    cape_shawl = [
        (np.array([0.0, 0.895, -0.025], dtype=np.float32), 0.152, 0.095, 0.00, -0.022, b_uchest, b_uchest, 0.0),
        (np.array([0.0, 0.935, -0.022], dtype=np.float32), 0.145, 0.090, 0.55, -0.020, b_uchest, b_neck, 0.25),
        (np.array([0.0, 0.962, -0.018], dtype=np.float32), 0.088, 0.070, 1.00, -0.016, b_uchest, b_neck, 0.45),
    ]
    mb_cape.add_loft(cape_shawl, n_seg=22)

    # Abas longas escuras abrindo amplamente pelas laterais (deixam silhueta limpa entre as coxas!)
    for sign, j0, j1, j2 in ((1.0, b_cl0, b_cl1, b_cl2), (-1.0, b_cr0, b_cr1, b_cr2)):
        cape_pts = [
            (np.array([sign * 0.13, 0.89, -0.09], dtype=np.float32), 0.072, 1.0, b_uchest, j0, 0.55),
            (np.array([sign * 0.23, 0.66, -0.14], dtype=np.float32), 0.092, 0.9, j0, j1, 0.50),
            (np.array([sign * 0.36, 0.36, -0.18], dtype=np.float32), 0.118, 0.8, j1, j2, 0.55),
            (np.array([sign * 0.48, 0.07, -0.20], dtype=np.float32), 0.100, 0.6, j2, j2, 0.0),
            (np.array([sign * 0.53, 0.01, -0.21], dtype=np.float32), 0.036, 0.4, j2, j2, 0.0),
        ]
        mb_cape.add_ribbon(cape_pts, n_across=5, thickness=0.013, arch_z=0.014)
    primitives.append(mb_cape.build(mesh_index=len(primitives)))

    # ── 10. Ornamentos Dourados + Arma Modular na MÃO ESQUERDA (nunca atrapalha o aceno da direita!) ──
    mb_gold = _MeshBuilder(material_index=7)
    # Presilha dourada no alto do rabo-de-cavalo (Titan_idle!)
    mb_gold.add_ellipsoid((0.02, 1.295, -0.10), (0.044, 0.032, 0.038), b_head, n_lat=10, n_lon=14)
    # Broche dourado elegante no fecho da capa (garganta)
    mb_gold.add_diamond_spike((0.0, 0.915, 0.068), (0.0, -1.0, 0.25), 0.045, 0.022, b_uchest)

    if style == "priestess":
        # Cajado Crescente Dourado erguido na mão ESQUERDA (Image 4!)
        staff_rings = [
            (np.array([0.46, 0.08, 0.04], dtype=np.float32), 0.015, 0.015, 0.0, 0.0, b_l_hd, b_l_hd, 0.0),
            (np.array([0.46, 1.38, 0.04], dtype=np.float32), 0.017, 0.017, 1.0, 0.0, b_l_hd, b_l_hd, 0.0),
        ]
        mb_gold.add_loft(staff_rings, n_seg=10, cap_bottom=True, cap_top=True)
        mb_gold.add_torus((0.46, 1.48, 0.04), 0.118, 0.022, b_l_hd, n_major=24, n_minor=8, plane="xy")
        mb_gold.add_diamond_spike((0.46, 1.59, 0.04), (0.0, 1.0, 0.0), 0.10, 0.030, b_l_hd)
    elif style == "valkyrie":
        # Espada Rúnica elegante na mão ESQUERDA (Image 5!)
        mb_gold.add_diamond_spike((0.47, 0.89, 0.04), (0.30, 0.94, 0.14), 0.66, 0.038, b_l_hd)
        mb_gold.add_diamond_spike((0.47, 0.89, 0.04), (-0.92, 0.35, 0.0), 0.11, 0.020, b_l_hd)
        mb_gold.add_diamond_spike((0.47, 0.89, 0.04), (0.92, -0.35, 0.0), 0.11, 0.020, b_l_hd)
    primitives.append(mb_gold.build(mesh_index=len(primitives)))

    # ── 11. Halo Celestial Luminoso atrás da Cabeça (Titan_idle + Image 3 + Image 6!) ──
    mb_halo = _MeshBuilder(material_index=8)
    halo_c = (0.0, 1.185, -0.185)
    mb_halo.add_torus(halo_c, 0.295, 0.016, b_halo, n_major=42, n_minor=8, plane="xy")
    for deg, slen in ((0.0, 0.10), (90.0, 0.12), (180.0, 0.10), (270.0, 0.09), (45.0, 0.065), (135.0, 0.065), (225.0, 0.065), (315.0, 0.065)):
        rad = math.radians(deg)
        bx = halo_c[0] + math.cos(rad) * 0.295
        by = halo_c[1] + math.sin(rad) * 0.295
        mb_halo.add_diamond_spike((bx, by, halo_c[2]), (math.cos(rad), math.sin(rad), 0.0), slen, 0.020, b_halo)
    primitives.append(mb_halo.build(mesh_index=len(primitives)))

    # ── 12. Chamas Arcanas Brilhantes Flutuando sobre as Palmas (Titan_idle!) ──
    mb_flames = _MeshBuilder(material_index=9)
    for sign, j_hd in ((1.0, b_l_hd), (-1.0, b_r_hd)):
        if style == "priestess" and sign > 0:
            mb_flames.add_ellipsoid((0.46, 1.48, 0.04), (0.046, 0.046, 0.046), j_hd, n_lat=8, n_lon=10)
            continue
        if style == "valkyrie" and sign > 0:
            continue
        hx = sign * 0.475
        mb_flames.add_diamond_spike((hx, 0.92, 0.02), (sign * 0.20, 0.95, 0.12), 0.15, 0.032, j_hd)
        mb_flames.add_diamond_spike((hx + sign * 0.042, 0.90, -0.01), (sign * 0.44, 0.86, -0.10), 0.11, 0.024, j_hd)
        mb_flames.add_diamond_spike((hx - sign * 0.032, 0.91, 0.04), (-sign * 0.18, 0.94, 0.22), 0.10, 0.022, j_hd)
    primitives.append(mb_flames.build(mesh_index=len(primitives)))

    # ── 13. Expressões faciais & SpringBones ──
    expressions = {
        "blink": [(lid_mesh_idx, 0, 1.0)],
        "happy": [(lid_mesh_idx, 0, 0.30)],
        "relaxed": [(lid_mesh_idx, 0, 0.48)],
        "angry": [],
        "sad": [(lid_mesh_idx, 0, 0.25)],
        "surprised": [],
    }
    springs = [
        VrmSpringChain(joints=[b_pt0, b_pt1, b_pt2, b_pt3], stiffness=0.85, drag=0.45),
        VrmSpringChain(joints=[b_hl0, b_hl1], stiffness=1.1, drag=0.5),
        VrmSpringChain(joints=[b_hr0, b_hr1], stiffness=1.1, drag=0.5),
        VrmSpringChain(joints=[b_cl0, b_cl1, b_cl2], stiffness=0.75, drag=0.42),
        VrmSpringChain(joints=[b_cr0, b_cr1, b_cr2], stiffness=0.75, drag=0.42),
    ]

    return VrmModel(
        name=f"DungeonSquad_{persona.id}_{style}",
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
        height=1.42,
        min_y=0.0,
    )
