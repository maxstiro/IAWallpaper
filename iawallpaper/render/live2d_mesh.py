"""LIVE2D MESH ENGINE — Motor 2.5D de Deformação Elástica Contínua em GPU (Estilo Spine2D / Live2D / NIKKE).

Anima arte 2D pura de estúdio (gerada no ComfyUI ou pintada à mão) sem aspecto 3D e sem juntas recortadas rígidas:
- **Malha Triangular Contínua + Skinning Geodésico**: gera uma malha densa (~3.500–5.000 triângulos) sobre a
  silhueta RGBA e calcula pesos suaves por distância geodésica *dentro da silhueta opaca* (braços nunca puxam
  a cintura, pernas se movem independentemente e cotovelos/joelhos/quadris dobram de forma 100% orgânica!).
- **Deformadores Live2D em Tempo Real na GPU (ModernGL OpenGL 3.3)**:
  1. Giro 2.5D de cabeça (*Head Parallax Turn*) seguindo o cursor do mouse.
  2. Respiração orgânica + mola *soft-body* no busto/tronco (`bust_spring_x/y`).
  3. Ondulação fluida automática nos fios longos de cabelo (`hair_flow_weight` detectado pela cor da coroa!)
     e micro-movimentos expressivos nas orelhas élficas (`ear_weight`).
  4. Expressões faciais 2D reais 1:1 no shader (`base_blink.png` p/ piscar pintado à mão, `base_happy.png` p/
     sorriso radiante, rubor dinâmico por emoção e camada modular de roupas alinhada 1:1 `outfit_*.png`!).
  5. Transição suave frente/3-4 (com giro elástico esquerda ↔ direita) e vista de costas (`base_back.png`)
     ao caminhar para o fundo da praça.
"""

from collections import deque
from dataclasses import dataclass
import math
from pathlib import Path

import moderngl
import numpy as np
from PIL import Image
from PySide6.QtGui import QImage, QPixmap

from ..core.emotion import EmotionState
from ..mathutil import clamp
from .atmosphere import AtmospherePalette

# Ordem fixa dos 12 ossos do esqueleto 2D contínuo
BONE_NAMES: tuple[str, ...] = (
    "hips",         # 0
    "spine",        # 1
    "chest",        # 2
    "head",         # 3
    "upper_arm_l",  # 4  (lado esquerdo da imagem: x < 0.5)
    "forearm_l",    # 5
    "upper_arm_r",  # 6  (lado direito da imagem: x > 0.5)
    "forearm_r",    # 7
    "thigh_l",      # 8
    "shin_l",       # 9
    "thigh_r",      # 10
    "shin_r",       # 11
)
BONE_PARENT: tuple[int, ...] = (-1, 0, 1, 2, 2, 4, 2, 6, 0, 8, 0, 10)
NUM_BONES = len(BONE_NAMES)


@dataclass
class CharacterLandmarks:
    """Marcos anatômicos em UV normalizado [0..1] (0,0 = topo-esquerda; 1,1 = base-direita)."""
    aspect: float          # width / height da imagem recortada
    cx: float              # centro horizontal do corpo (~0.5)
    head_top_y: float
    eye_y: float
    chin_y: float
    shoulder_y: float
    bust_y: float
    waist_y: float
    hip_y: float
    crotch_y: float
    knee_y: float
    ankle_y: float
    shoulder_l: tuple[float, float]
    elbow_l: tuple[float, float]
    hand_l: tuple[float, float]
    shoulder_r: tuple[float, float]
    elbow_r: tuple[float, float]
    hand_r: tuple[float, float]
    hip_l: tuple[float, float]
    knee_l: tuple[float, float]
    foot_l: tuple[float, float]
    hip_r: tuple[float, float]
    knee_r: tuple[float, float]
    foot_r: tuple[float, float]
    bone_pivots: np.ndarray     # (12, 2) em coordenadas de mundo normalizadas (altura = 1.0, pés em y = 0.0)
    bone_ends: np.ndarray       # (12, 2)


@dataclass
class ElasticMeshData:
    """Geometria 2D triangular contínua + pesos geodésicos + máscaras de cabelo/orelhas pronta para GPU."""
    landmarks: CharacterLandmarks
    rgba: np.ndarray            # (H, W, 4) uint8 recortada com 2px de borda transparente
    positions: np.ndarray       # (V, 2) float32 em espaço personagem (x em [-aspect/2, +aspect/2], y em [0=pés, 1=topo])
    uvs: np.ndarray             # (V, 2) float32 [0..1]
    joints: np.ndarray          # (V, 4) float32 índices de ossos
    weights: np.ndarray         # (V, 4) float32 pesos normalizados (soma=1)
    aux: np.ndarray             # (V, 4) float32: (hair_flow_w, ear_w, face_w, bust_w)
    indices: np.ndarray         # (T*3,) uint32


def _uv_to_world(u: float, v: float, aspect: float, cx: float = 0.5) -> tuple[float, float]:
    """Converte UV [0..1] (v=0 topo, v=1 pés) em mundo 2D (x centrado em 0, y=0 nos pés, y=1 no topo)."""
    return ((u - cx) * aspect, 1.0 - v)


def trim_rgba_with_padding(rgba: np.ndarray, pad: int = 4, alpha_thresh: int = 16) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Recorta exatamente a silhueta opaca preservando margem limpa de `pad` px e retorna (cropped, bbox)."""
    h, w, _ = rgba.shape
    mask = rgba[:, :, 3] > alpha_thresh
    if not np.any(mask):
        return rgba.copy(), (0, 0, w, h)
    ys = np.where(np.any(mask, axis=1))[0]
    xs = np.where(np.any(mask, axis=0))[0]
    y0 = max(0, int(ys[0]) - pad)
    y1 = min(h, int(ys[-1]) + 1 + pad)
    x0 = max(0, int(xs[0]) - pad)
    x1 = min(w, int(xs[-1]) + 1 + pad)
    cropped = np.ascontiguousarray(rgba[y0:y1, x0:x1])
    # Limpa borda externa de 1px para evitar sangramento de textura no sampler bilinear
    cropped[0, :, 3] = 0
    cropped[-1, :, 3] = 0
    cropped[:, 0, 3] = 0
    cropped[:, -1, 3] = 0
    return cropped, (x0, y0, x1, y1)


def _row_runs(row_mask: np.ndarray) -> list[tuple[int, int]]:
    """Retorna lista de intervalos contíguos (start, end_inclusive) onde row_mask é True."""
    padded = np.concatenate(([False], row_mask, [False]))
    diff = np.diff(padded.astype(np.int8))
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0] - 1
    return [(int(s), int(e)) for s, e in zip(starts, ends) if (e - s) >= 2]


def analyze_2d_character(rgba: np.ndarray) -> CharacterLandmarks:
    """Detecta automaticamente todos os marcos anatômicos de um sprite 2D full-body RGBA."""
    h, w, _ = rgba.shape
    aspect = w / max(float(h), 1.0)
    alpha = rgba[:, :, 3] > 20

    # Centro horizontal do tronco (mediana na faixa central y = 0.25..0.60)
    mid_ys, mid_xs = np.where(alpha[int(h * 0.22):int(h * 0.62), :])
    cx = float(np.median(mid_xs) / max(w - 1, 1)) if len(mid_xs) else 0.5
    cx = clamp(cx, 0.35, 0.65)
    cx_px = int(cx * w)

    # 1. Detecta a linha da virilha (`crotch_y`): busca abertura transparente CENTRAL (entre coxas, ignorando braços!)
    crotch_y = 0.50
    c_lo = max(0, cx_px - int(w * 0.06))
    c_hi = min(w - 1, cx_px + int(w * 0.06))
    leg_lo = max(0, cx_px - int(w * 0.28))
    leg_hi = min(w - 1, cx_px + int(w * 0.28))
    for y in range(int(h * 0.40), int(h * 0.72)):
        # Verifica se há vão transparente próximo ao eixo central cx com massa de coxa dos dois lados!
        center_slice = alpha[y, c_lo:c_hi + 1]
        if not np.any(~center_slice):
            continue
        left_ok = np.sum(alpha[y, leg_lo:cx_px]) > w * 0.05
        right_ok = np.sum(alpha[y, cx_px:leg_hi]) > w * 0.05
        if left_ok and right_ok:
            # Confirma persistência por 8 linhas (vão real entre coxas!)
            ok = True
            for dy in range(1, min(9, h - y)):
                if not np.any(~alpha[y + dy, c_lo:c_hi + 1]):
                    ok = False
                    break
            if ok:
                crotch_y = y / float(h)
                break

    # Detecta cor do cabelo no topo da cabeça (`y = 0.01..0.08`) para ignorar cabelo atrás do pescoço!
    crown = rgba[int(h * 0.01):int(h * 0.08), int(w * 0.25):int(w * 0.75)]
    crown_px = crown[crown[:, :, 3] > 180][:, :3].astype(np.float32)
    hair_rgb = np.median(crown_px, axis=0) if len(crown_px) > 10 else np.array([235.0, 200.0, 125.0], dtype=np.float32)
    rgb_f = rgba[:, :, :3].astype(np.float32)
    is_hair_px = (np.linalg.norm(rgb_f - hair_rgb[None, None, :], axis=2) < 58.0) & alpha
    non_hair_alpha = alpha & (~is_hair_px)

    # 2. Detecta pescoço (`chin_y`): menor largura de pele/não-cabelo no eixo central entre y = 0.12..0.28
    best_neck_w = w
    chin_y = 0.18
    for y in range(int(h * 0.12), int(h * 0.28)):
        runs = _row_runs(non_hair_alpha[y])
        center_runs = [r for r in runs if r[0] <= cx_px <= r[1]]
        if not center_runs:
            runs = _row_runs(alpha[y])
            center_runs = [r for r in runs if r[0] <= cx_px <= r[1]]
        if not center_runs:
            continue
        rw = center_runs[0][1] - center_runs[0][0]
        if rw < best_neck_w:
            best_neck_w = rw
            chin_y = y / float(h)
    chin_y = clamp(chin_y, 0.13, 0.27)
    eye_y = clamp(chin_y * 0.58, 0.055, 0.18)
    shoulder_y = clamp(chin_y + 0.036, 0.17, 0.31)

    # 3. Cintura (`waist_y`): menor largura do componente central entre ombros+0.08 e virilha-0.05
    best_waist_w = w
    waist_y = shoulder_y + (crotch_y - shoulder_y) * 0.54
    y_ws = int(h * clamp(shoulder_y + 0.08, 0.24, 0.42))
    y_we = int(h * clamp(crotch_y - 0.05, y_ws / h + 0.04, 0.52))
    for y in range(y_ws, max(y_ws + 1, y_we)):
        runs = _row_runs(alpha[y])
        center_runs = [r for r in runs if r[0] <= cx_px <= r[1]]
        if not center_runs:
            continue
        rw = center_runs[0][1] - center_runs[0][0]
        if rw < best_waist_w:
            best_waist_w = rw
            waist_y = y / float(h)
    bust_y = shoulder_y + (waist_y - shoulder_y) * 0.45
    hip_y = waist_y + (crotch_y - waist_y) * 0.68
    knee_y = crotch_y + (0.95 - crotch_y) * 0.48
    ankle_y = 0.94

    # 4. Detecta ombros reais (largura do tronco sem cabelo na linha `shoulder_y`) e braços externos!
    sh_yi = int(clamp(shoulder_y, 0.15, 0.35) * (h - 1))
    sh_runs = _row_runs(non_hair_alpha[sh_yi])
    sh_center = [r for r in sh_runs if r[0] <= cx_px <= r[1]]
    if sh_center:
        sh_lx = clamp(sh_center[0][0] / float(w) + 0.03, 0.16, cx - 0.09)
        sh_rx = clamp(sh_center[0][1] / float(w) - 0.03, cx + 0.09, 0.84)
    else:
        torso_half = max(0.11, (best_waist_w / float(w)) * 0.65)
        sh_lx = clamp(cx - torso_half * 1.15, 0.16, cx - 0.09)
        sh_rx = clamp(cx + torso_half * 1.15, cx + 0.09, 0.84)
    torso_half = max(0.09, (best_waist_w / float(w)) * 0.55)

    def _trace_arm(side: int) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
        sh = (sh_lx if side < 0 else sh_rx, shoulder_y)
        arm_pts: list[tuple[float, float]] = []
        max_reach = abs(sh[0] - cx)
        y0 = int(h * (shoulder_y + 0.05))
        y1 = int(h * min(0.62, crotch_y + 0.06))
        for y in range(y0, y1, max(1, h // 140)):
            runs = _row_runs(alpha[y])
            if len(runs) >= 2:
                cand = runs[0] if side < 0 else runs[-1]
                if (cand[1] - cand[0]) < w * 0.015:
                    continue
                mid_x = 0.5 * (cand[0] + cand[1]) / float(w)
                reach = abs(mid_x - cx)
                # Se a silhueta mais externa recuar bruscamente para dentro (entrou na coxa após a mão acabar!), para!
                if arm_pts and reach < max_reach - 0.085:
                    break
                if (side < 0 and mid_x < cx - torso_half * 1.05) or (side > 0 and mid_x > cx + torso_half * 1.05):
                    arm_pts.append((mid_x, y / float(h)))
                    if reach > max_reach:
                        max_reach = reach
            elif arm_pts:
                # Braço terminou (voltou a ter só 1 componente central)
                break
        if len(arm_pts) >= 4:
            elbow = arm_pts[len(arm_pts) // 2]
            hand = arm_pts[-1]
        else:
            elbow = (clamp(sh[0] + side * 0.12, 0.06, 0.94), shoulder_y + 0.14)
            hand = (clamp(sh[0] + side * 0.24, 0.04, 0.96), shoulder_y + 0.27)
        return sh, elbow, hand

    shoulder_l, elbow_l, hand_l = _trace_arm(-1)
    shoulder_r, elbow_r, hand_r = _trace_arm(+1)

    # 5. Centros reais das pernas esquerda e direita
    def _leg_center_x(y_norm: float, side: int, fallback: float) -> float:
        yi = int(clamp(y_norm, 0.05, 0.98) * (h - 1))
        runs = _row_runs(alpha[yi])
        cands = [r for r in runs if ((0.5 * (r[0] + r[1]) < cx_px) if side < 0 else (0.5 * (r[0] + r[1]) >= cx_px))]
        if cands:
            best = max(cands, key=lambda r: r[1] - r[0])
            return 0.5 * (best[0] + best[1]) / float(w)
        return fallback

    hip_lx = _leg_center_x(crotch_y + 0.04, -1, cx - 0.085)
    hip_rx = _leg_center_x(crotch_y + 0.04, +1, cx + 0.085)
    knee_lx = _leg_center_x(knee_y, -1, hip_lx - 0.01)
    knee_rx = _leg_center_x(knee_y, +1, hip_rx + 0.01)
    foot_lx = _leg_center_x(ankle_y, -1, knee_lx)
    foot_rx = _leg_center_x(ankle_y, +1, knee_rx)

    hip_l = (hip_lx, hip_y)
    knee_l = (knee_lx, knee_y)
    foot_l = (foot_lx, 0.98)
    hip_r = (hip_rx, hip_y)
    knee_r = (knee_rx, knee_y)
    foot_r = (foot_rx, 0.98)

    # 6. Pivôs e pontas dos 12 ossos em coordenadas de mundo (altura = 1.0, pés em y = 0.0)
    uv_segments = [
        ((cx, hip_y),       (cx, waist_y)),       # 0: hips
        ((cx, waist_y),     (cx, bust_y)),        # 1: spine
        ((cx, bust_y),      (cx, chin_y)),        # 2: chest
        ((cx, chin_y),      (cx, 0.04)),          # 3: head
        (shoulder_l,        elbow_l),             # 4: upper_arm_l
        (elbow_l,           hand_l),              # 5: forearm_l
        (shoulder_r,        elbow_r),             # 6: upper_arm_r
        (elbow_r,           hand_r),              # 7: forearm_r
        (hip_l,             knee_l),              # 8: thigh_l
        (knee_l,            foot_l),              # 9: shin_l
        (hip_r,             knee_r),              # 10: thigh_r
        (knee_r,            foot_r),              # 11: shin_r
    ]
    pivots = np.array([_uv_to_world(p[0], p[1], aspect, cx) for p, _ in uv_segments], dtype=np.float32)
    ends = np.array([_uv_to_world(e[0], e[1], aspect, cx) for _, e in uv_segments], dtype=np.float32)

    return CharacterLandmarks(
        aspect=aspect,
        cx=cx,
        head_top_y=0.02,
        eye_y=eye_y,
        chin_y=chin_y,
        shoulder_y=shoulder_y,
        bust_y=bust_y,
        waist_y=waist_y,
        hip_y=hip_y,
        crotch_y=crotch_y,
        knee_y=knee_y,
        ankle_y=ankle_y,
        shoulder_l=shoulder_l,
        elbow_l=elbow_l,
        hand_l=hand_l,
        shoulder_r=shoulder_r,
        elbow_r=elbow_r,
        hand_r=hand_r,
        hip_l=hip_l,
        knee_l=knee_l,
        foot_l=foot_l,
        hip_r=hip_r,
        knee_r=knee_r,
        foot_r=foot_r,
        bone_pivots=pivots,
        bone_ends=ends,
    )


def _compute_geodesic_skinning(
    rgba: np.ndarray,
    lm: CharacterLandmarks,
    uvs: np.ndarray,
    indices: np.ndarray,
    grid_w: int = 72,
    grid_h: int = 108,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Calcula pesos geodésicos suaves dentro da silhueta opaca (zero cortes/juntas quebradas!) + máscaras auxiliares."""
    # Reduz máscara alpha para grade geodésica rápida (<20ms em Python puro!)
    pil_a = Image.fromarray(rgba[:, :, 3], mode="L").resize((grid_w, grid_h), Image.Resampling.BILINEAR)
    occ = np.array(pil_a, dtype=np.uint8) > 10
    # Pequena dilatação de 1px para garantir continuidade em pulsos/tornozelos finos sem unir pernas separadas
    occ_d = occ.copy()
    occ_d[1:, :] |= occ[:-1, :]
    occ_d[:-1, :] |= occ[1:, :]
    occ_d[:, 1:] |= occ[:, :-1]
    occ_d[:, :-1] |= occ[:, 1:]

    # Converte segmentos de osso para coordenadas da grade geodésica
    def _world_to_grid(pt: np.ndarray) -> tuple[float, float]:
        u = pt[0] / max(lm.aspect, 1e-4) + lm.cx
        v = 1.0 - pt[1]
        return clamp(u * (grid_w - 1), 0.0, grid_w - 1.0), clamp(v * (grid_h - 1), 0.0, grid_h - 1.0)

    dist_maps = np.full((NUM_BONES, grid_h, grid_w), 1e4, dtype=np.float32)
    nbrs = ((-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
            (-1, -1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (1, 1, 1.414))

    for bi in range(NUM_BONES):
        x0, y0 = _world_to_grid(lm.bone_pivots[bi])
        x1, y1 = _world_to_grid(lm.bone_ends[bi])
        steps = max(4, int(math.hypot(x1 - x0, y1 - y0) * 1.5))
        dmap = dist_maps[bi]
        q: deque[tuple[int, int]] = deque()
        for s in range(steps + 1):
            t = s / float(steps)
            gx = int(round(x0 + (x1 - x0) * t))
            gy = int(round(y0 + (y1 - y0) * t))
            if 0 <= gx < grid_w and 0 <= gy < grid_h:
                if dmap[gy, gx] > 0.0:
                    dmap[gy, gx] = 0.0
                    q.append((gx, gy))
        # BFS geodésico dentro dos pixels opacos (impede que mão puxe quadril ou perna esq puxe perna dir!)
        while q:
            cx_i, cy_i = q.popleft()
            cd = dmap[cy_i, cx_i]
            for dx, dy, cost in nbrs:
                nx, ny = cx_i + dx, cy_i + dy
                if 0 <= nx < grid_w and 0 <= ny < grid_h and occ_d[ny, nx]:
                    nd = cd + cost
                    if nd < dmap[ny, nx]:
                        dmap[ny, nx] = nd
                        q.append((nx, ny))

    # Amostra distâncias geodésicas em cada vértice da malha
    nv = len(uvs)
    gx_v = np.clip((uvs[:, 0] * (grid_w - 1)).astype(np.int32), 0, grid_w - 1)
    gy_v = np.clip((uvs[:, 1] * (grid_h - 1)).astype(np.int32), 0, grid_h - 1)
    v_dists = dist_maps[:, gy_v, gx_v]  # (NUM_BONES, V)

    # Fallback Euclidiano suave apenas para vértices de borda fora da máscara dilatada
    unreached = np.min(v_dists, axis=0) > 500.0
    if np.any(unreached):
        for bi in range(NUM_BONES):
            x0, y0 = _world_to_grid(lm.bone_pivots[bi])
            x1, y1 = _world_to_grid(lm.bone_ends[bi])
            mx, my = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
            eu = np.hypot(gx_v[unreached] - mx, gy_v[unreached] - my)
            v_dists[bi, unreached] = eu

    # Converte distância geodésica em pesos suaves Gaussianos (sigma calibrado p/ dobra orgânica de carne/tecido!)
    sigma = max(grid_w * 0.145, 7.5)
    raw_w = np.exp(-((v_dists / sigma) ** 2.2))  # (NUM_BONES, V)

    # Suavização Laplaciana nos pesos sobre a conectividade dos triângulos (4 passos -> transições 100% sedosas!)
    tris = indices.reshape(-1, 3)
    deg = np.zeros(nv, dtype=np.float32)
    np.add.at(deg, tris[:, 0], 2.0)
    np.add.at(deg, tris[:, 1], 2.0)
    np.add.at(deg, tris[:, 2], 2.0)
    deg = np.maximum(deg, 1.0)
    for _ in range(4):
        acc = np.zeros_like(raw_w)
        for a, b in ((0, 1), (1, 0), (1, 2), (2, 1), (2, 0), (0, 2)):
            np.add.at(acc.T, tris[:, a], raw_w[:, tris[:, b]].T)
        raw_w = raw_w * 0.45 + (acc / deg[None, :]) * 0.55

    # Seleciona os top-4 ossos mais influentes por vértice e normaliza (soma == 1.0)
    top4 = np.argpartition(-raw_w, 4, axis=0)[:4, :]  # (4, V)
    top_vals = np.take_along_axis(raw_w, top4, axis=0)
    top_sum = np.maximum(np.sum(top_vals, axis=0, keepdims=True), 1e-6)
    top_vals = top_vals / top_sum
    joints = top4.T.astype(np.float32)
    weights = top_vals.T.astype(np.float32)

    # ── Máscaras auxiliares Live2D automáticas: (hair_flow_w, ear_w, face_w, bust_w) ──
    # 1. Detecta cor do cabelo diretamente da coroa superior (y = 0.01..0.08) + restrição estrita acima da cintura!
    #    (Impede 100% que pele bronzeada de braços/coxas receba ondas de cabelo!)
    h_img, w_img, _ = rgba.shape
    crown = rgba[int(h_img * 0.01):int(h_img * 0.08), int(w_img * 0.25):int(w_img * 0.75)]
    crown_px = crown[crown[:, :, 3] > 180][:, :3].astype(np.float32)
    hair_rgb = np.median(crown_px, axis=0) if len(crown_px) > 10 else np.array([235.0, 200.0, 125.0], dtype=np.float32)

    px_x = np.clip((uvs[:, 0] * (w_img - 1)).astype(np.int32), 0, w_img - 1)
    px_y = np.clip((uvs[:, 1] * (h_img - 1)).astype(np.int32), 0, h_img - 1)
    v_rgb = rgba[px_y, px_x, :3].astype(np.float32)
    hair_dist = np.linalg.norm(v_rgb - hair_rgb[None, :], axis=1) / 255.0
    hair_color_sim = np.clip(1.0 - (hair_dist - 0.10) / 0.14, 0.0, 1.0)

    # Apenas mechas soltas LATERAIS abaixo dos olhos e acima do busto/cintura (ZERO risco de pegar renda do sutiã ou pele!)
    dx_center = np.abs(uvs[:, 0] - lm.cx)
    outside_core = np.clip((dx_center - 0.14) / 0.08, 0.0, 1.0)
    drop = np.clip((uvs[:, 1] - (lm.eye_y + 0.02)) / max(lm.waist_y - lm.eye_y, 0.16), 0.0, 1.0)
    above_waist = np.clip(1.0 - np.maximum(0.0, uvs[:, 1] - (lm.bust_y + 0.05)) / 0.065, 0.0, 1.0)
    hair_flow_w = hair_color_sim * outside_core * (drop ** 1.3) * above_waist

    # 2. Orelhas élficas: pixels laterais fora da oval facial na faixa dos olhos/têmporas
    dx_head = np.abs(uvs[:, 0] - lm.cx)
    ear_band = np.exp(-((uvs[:, 1] - (lm.eye_y + 0.005)) / 0.040) ** 2)
    ear_w = np.clip((dx_head - 0.14) / 0.09, 0.0, 1.0) * ear_band * (1.0 - hair_color_sim * 0.7)

    # Suavização Laplaciana (6 passos) em hair_flow_w e ear_w -> campo C2 100% contínuo (ZERO estrias/serrilhado!)
    for _ in range(6):
        acc_h = np.zeros(nv, dtype=np.float32)
        acc_e = np.zeros(nv, dtype=np.float32)
        for a, b in ((0, 1), (1, 0), (1, 2), (2, 1), (2, 0), (0, 2)):
            np.add.at(acc_h, tris[:, a], hair_flow_w[tris[:, b]])
            np.add.at(acc_e, tris[:, a], ear_w[tris[:, b]])
        hair_flow_w = hair_flow_w * 0.4 + (acc_h / deg) * 0.6
        ear_w = ear_w * 0.4 + (acc_e / deg) * 0.6

    # 3. Máscara suave do rosto para efeito Live2D 2.5D Head Parallax Turn (nariz/olhos/boca deslocam com cursor!)
    face_dx = (uvs[:, 0] - lm.cx) / 0.14
    face_dy = (uvs[:, 1] - (lm.eye_y + 0.020)) / 0.068
    face_w = np.exp(-(face_dx * face_dx + face_dy * face_dy))

    # 4. Máscara suave do busto para respiração + física elástica soft-body Live2D!
    bust_dx = (uvs[:, 0] - lm.cx) / 0.155
    bust_dy = (uvs[:, 1] - lm.bust_y) / 0.062
    bust_w = np.exp(-(bust_dx * bust_dx + bust_dy * bust_dy))

    aux = np.stack([hair_flow_w, ear_w, face_w, bust_w], axis=1).astype(np.float32)
    return joints, weights, aux


def build_elastic_mesh(rgba_raw: np.ndarray, grid_x: int = 84, grid_y: int = 128) -> ElasticMeshData:
    """Constrói malha triangular contínua 2.5D SEM pontes sobre vãos transparentes (zero esticamento entre coxas/braços!)."""
    rgba, _ = trim_rgba_with_padding(rgba_raw, pad=6, alpha_thresh=16)
    lm = analyze_2d_character(rgba)
    h, w, _ = rgba.shape

    us = np.linspace(0.0, 1.0, grid_x + 1, dtype=np.float32)
    vs = np.linspace(0.0, 1.0, grid_y + 1, dtype=np.float32)
    uu, vv = np.meshgrid(us, vs)

    # Ativa toda célula que contenha pixels opacos (mantém 100% das bordas anti-serrilhadas da arte 2D!),
    # mas BLOQUEIA células cujo centro seja transparente E que cruzem o vão entre pernas ou entre braço e tronco!
    alpha = rgba[:, :, 3]
    cy_px = np.clip(((np.arange(grid_y) + 0.5) * h / grid_y).astype(np.int32), 0, h - 1)
    cx_px = np.clip(((np.arange(grid_x) + 0.5) * w / grid_x).astype(np.int32), 0, w - 1)
    center_alpha = alpha[cy_px[:, None], cx_px[None, :]]

    cell_max = np.zeros((grid_y, grid_x), dtype=np.uint8)
    for gy in range(grid_y):
        py0 = max(0, int(gy * h / grid_y))
        py1 = min(h, int((gy + 1) * h / grid_y) + 1)
        for gx in range(grid_x):
            px0 = max(0, int(gx * w / grid_x))
            px1 = min(w, int((gx + 1) * w / grid_x) + 1)
            cell_max[gy, gx] = int(np.max(alpha[py0:py1, px0:px1]))

    # Verifica se ambos os lados horizontais têm opaco com centro vazio (indica célula ponte sobre vão!)
    vy_px = np.clip((vs * (h - 1)).astype(np.int32), 0, h - 1)
    vx_px = np.clip((us * (w - 1)).astype(np.int32), 0, w - 1)
    v_op = alpha[vy_px[:, None], vx_px[None, :]] > 16
    left_op = v_op[:-1, :-1] | v_op[1:, :-1]
    right_op = v_op[:-1, 1:] | v_op[1:, 1:]
    bridges_gap = (center_alpha <= 4) & left_op & right_op
    cell_active = (cell_max > 10) & (~bridges_gap)

    # Compacta vértices e também verifica se os 4 cantos não pulam vão transparente:
    # Divide vértices desconectados (ex.: se duas células diagonais se tocam num vértice transparente, não gera taffy!)
    v_used = np.zeros((grid_y + 1, grid_x + 1), dtype=bool)
    v_used[:-1, :-1] |= cell_active
    v_used[:-1, 1:] |= cell_active
    v_used[1:, :-1] |= cell_active
    v_used[1:, 1:] |= cell_active

    v_map = np.full((grid_y + 1, grid_x + 1), -1, dtype=np.int32)
    ys_u, xs_u = np.where(v_used)
    v_map[ys_u, xs_u] = np.arange(len(ys_u), dtype=np.int32)

    uvs = np.stack([uu[ys_u, xs_u], vv[ys_u, xs_u]], axis=1).astype(np.float32)
    positions = np.empty_like(uvs)
    positions[:, 0] = (uvs[:, 0] - lm.cx) * lm.aspect
    positions[:, 1] = 1.0 - uvs[:, 1]

    ay, ax = np.where(cell_active)
    i00 = v_map[ay, ax]
    i10 = v_map[ay, ax + 1]
    i01 = v_map[ay + 1, ax]
    i11 = v_map[ay + 1, ax + 1]
    indices = np.empty(len(ay) * 6, dtype=np.uint32)
    indices[0::6] = i00
    indices[1::6] = i10
    indices[2::6] = i11
    indices[3::6] = i00
    indices[4::6] = i11
    indices[5::6] = i01

    joints, weights, aux = _compute_geodesic_skinning(rgba, lm, uvs, indices, grid_w=96, grid_h=144)
    return ElasticMeshData(
        landmarks=lm,
        rgba=rgba,
        positions=positions,
        uvs=uvs,
        joints=joints,
        weights=weights,
        aux=aux,
        indices=indices,
    )


def _mat3_trs(tx: float, ty: float, rot_deg: float, sx: float = 1.0, sy: float = 1.0) -> np.ndarray:
    r = math.radians(rot_deg)
    c, s = math.cos(r), math.sin(r)
    return np.array(
        [
            [c * sx, -s * sy, tx],
            [s * sx,  c * sy, ty],
            [0.0,     0.0,    1.0],
        ],
        dtype=np.float32,
    )


class Live2DMeshAnimator:
    """Animador 2.5D Live2D/Spine2D com ação sobreposta em cascata, mola soft-body e giro suave."""

    def __init__(self, landmarks: CharacterLandmarks):
        self.lm = landmarks
        self.time: float = 0.0
        self.walk_phase: float = 0.0
        self.action_timer: float = 0.0

        # Estado suavizado dos 12 ossos (ângulos em graus) + deslocamento raiz + escala X suave (giro 2.5D!)
        self._cur_rot = np.zeros(NUM_BONES, dtype=np.float32)
        self._cur_scale_y = np.ones(NUM_BONES, dtype=np.float32)
        self.root_offset = np.zeros(2, dtype=np.float32)
        self.facing_scale_x: float = 1.0
        self.back_blend: float = 0.0

        # Parâmetros Live2D contínuos (enviados aos uniforms do shader GPU!)
        self.head_turn_x: float = 0.0
        self.head_turn_y: float = 0.0
        self.breath_val: float = 0.0
        self.bust_jiggle_x: float = 0.0
        self.bust_jiggle_y: float = 0.0
        self._bust_vx: float = 0.0
        self._bust_vy: float = 0.0
        self.hair_sway_x: float = 0.0
        self.hair_sway_y: float = 0.0
        self._hair_vx: float = 0.0
        self._hair_vy: float = 0.0
        self.ear_twitch: float = 0.0
        self.blink_weight: float = 0.0
        self.happy_weight: float = 0.0
        self.blush_weight: float = 0.0
        self._prev_root_y: float = 0.0
        self._prev_root_x: float = 0.0

        self.bone_mats: np.ndarray = np.repeat(np.eye(3, dtype=np.float32)[None, :, :], NUM_BONES, axis=0)
        self.solve_fk()

    def update(
        self,
        dt: float,
        action: str,
        walk_phase: float,
        action_timer: float,
        emotion: EmotionState,
        blink_amount: float = 0.0,
        look_x: float = 0.0,
        look_y: float = 0.0,
        facing: int = 1,
        move_dir: str = "front",
        move_dx: float = 0.0,
        move_dy: float = 0.0,
        wind_speed: float = 6.0,
        asleep: bool = False,
        caressing: bool = False,
    ) -> None:
        dt = clamp(dt, 0.0, 0.08)
        self.time += dt
        self.walk_phase = walk_phase
        self.action_timer = action_timer
        t = self.time

        # 1. Giro suave 2.5D esquerda ↔ direita + transição frente ↔ costas ao subir a praça!
        # (Na dança mantém largura 100% natural com leve balanço rítmico, sem achatar como papel!)
        tgt_facing = -1.0 if facing < 0 else 1.0
        self.facing_scale_x += (tgt_facing - self.facing_scale_x) * (1.0 - math.exp(-dt * 18.0))
        if abs(self.facing_scale_x) < 0.12:
            self.facing_scale_x = 0.12 if tgt_facing >= 0 else -0.12

        tgt_back = 1.0 if (action == "walk" and move_dir == "back") else 0.0
        self.back_blend += (tgt_back - self.back_blend) * (1.0 - math.exp(-dt * 11.0))

        # 2. Alvos angulares com Ação Sobreposta em Cascata (Live2D / Spine2D!)
        tgt_rot = np.zeros(NUM_BONES, dtype=np.float32)
        tgt_sy = np.ones(NUM_BONES, dtype=np.float32)
        tgt_off = np.zeros(2, dtype=np.float32)

        b0 = math.sin(t * (1.4 if asleep else 2.25))
        b1 = math.sin(t * (1.4 if asleep else 2.25) - 0.50)
        b2 = math.sin(t * (1.4 if asleep else 2.25) - 1.00)
        self.breath_val = b1

        if asleep or action == "sleep":
            tgt_off[:] = (0.0, -0.08 + b0 * 0.006)
            tgt_rot[0] = 2.0
            tgt_rot[1] = 4.0 + b0 * 1.5
            tgt_rot[2] = 3.0 + b1 * 1.5
            tgt_rot[3] = 10.0 + b2 * 2.2
            tgt_rot[4], tgt_rot[5] = 8.0, 12.0
            tgt_rot[6], tgt_rot[7] = -8.0, -12.0
            tgt_rot[8], tgt_rot[9] = -14.0, 22.0
            tgt_rot[10], tgt_rot[11] = 14.0, -22.0
        elif action == "walk":
            ph = walk_phase + 0.10 * math.sin(walk_phase)
            s0 = math.sin(ph)
            c0 = math.cos(ph)
            s_sp = math.sin(ph - 0.35)
            s_ch = math.sin(ph - 0.70)
            s_hd = math.sin(ph - 1.05)
            s_fa = math.sin(ph - 0.85)
            bob = abs(math.cos(ph - 0.16))

            # Caminhada elástica super fluida estilo Spine2D / Live2D / Tree of Savior (sem cruzar joelhos ou torcer pés!)
            tgt_off[:] = (s0 * 0.014, bob * 0.028 - 0.004)
            tgt_rot[0] = s0 * 3.8
            tgt_rot[1] = -s_sp * 3.6
            tgt_rot[2] = -s_ch * 2.6 + bob * 1.2
            tgt_rot[3] = s_hd * 2.8 + look_x * 4.0
            # Braços balançando graciosos com atraso de antebraço (sem encostar no quadril!)
            tgt_rot[4] = s0 * 11.0 - 4.0
            tgt_rot[5] = s_fa * 9.0 + 4.0
            tgt_rot[6] = s0 * 11.0 + 4.0
            tgt_rot[7] = s_fa * 9.0 - 4.0
            # Passada 2.5D limpa: alternância vertical de joelho + abertura leve sem jamais cruzar ou fundir coxas!
            l_lift = max(0.0, -c0)
            r_lift = max(0.0, c0)
            tgt_rot[8] = -l_lift * 6.5 + s0 * 3.5
            tgt_rot[9] = l_lift * 10.0
            tgt_sy[8] = 1.0 - l_lift * 0.095
            tgt_sy[9] = 1.0 - l_lift * 0.045
            tgt_rot[10] = r_lift * 6.5 + s0 * 3.5
            tgt_rot[11] = -r_lift * 10.0
            tgt_sy[10] = 1.0 - r_lift * 0.095
            tgt_sy[11] = 1.0 - r_lift * 0.045
        elif action == "wave":
            w0 = math.sin(t * 6.4)
            w1 = math.sin(t * 6.4 - 0.65)
            sw = math.sin(t * 1.6)
            tgt_off[:] = (sw * 0.012, b0 * 0.008)
            tgt_rot[0] = sw * 2.8
            tgt_rot[1] = -sw * 2.5
            tgt_rot[2] = -2.0 + b1 * 1.5
            tgt_rot[3] = 5.0 + w1 * 3.2 + look_x * 5.0
            # Braço direito erguido para fora/cima acenando (em 2D +rot gira anti-horário = ergue braço direito!)
            tgt_rot[4] = -5.0 - b1 * 2.0
            tgt_rot[5] = -4.0 - b2 * 2.5
            tgt_rot[6] = 26.0 + w0 * 9.0
            tgt_rot[7] = 20.0 + w1 * 14.0
        elif action in ("dance", "music_sway"):
            bt0 = math.sin(t * 4.8)
            bt1 = math.sin(t * 4.8 - 0.55)
            bt2 = math.sin(t * 4.8 - 1.10)
            hf = math.sin(t * 2.4)
            tgt_off[:] = (hf * 0.022, abs(bt0) * 0.026 - 0.004)
            tgt_rot[0] = hf * 5.2
            tgt_rot[1] = -hf * 4.5
            tgt_rot[2] = -bt1 * 4.0
            tgt_rot[3] = bt2 * 5.0
            # Braço esq (-rot ergue p/ fora) e braço dir (+rot ergue p/ fora) ondulando em fase!
            tgt_rot[4] = -16.0 + bt0 * 11.0
            tgt_rot[5] = -10.0 + bt1 * 11.0
            tgt_rot[6] = 16.0 + bt0 * 11.0
            tgt_rot[7] = 10.0 + bt1 * 11.0
            tgt_rot[8] = -bt0 * 5.0
            tgt_rot[10] = bt0 * 5.0
        elif action == "stretch":
            arch = math.sin(clamp(action_timer / 4.0, 0.0, 1.0) * math.pi)
            tgt_off[:] = (0.0, arch * 0.018)
            tgt_rot[1] = -arch * 2.5
            tgt_rot[2] = -arch * 3.5
            tgt_rot[3] = -arch * 4.5
            tgt_rot[4] = -arch * 28.0
            tgt_rot[5] = -arch * 12.0
            tgt_rot[6] = arch * 28.0
            tgt_rot[7] = arch * 12.0
            tgt_sy[1] = 1.0 + arch * 0.025
        elif action in ("sit_work", "sit_relax"):
            tgt_off[:] = (0.0, -0.05 + b0 * 0.005)
            tgt_rot[1] = 2.0
            tgt_rot[2] = 2.0 + b1 * 1.4
            tgt_rot[3] = 4.0 + look_x * 6.0
            tgt_rot[4], tgt_rot[5] = -10.0, -14.0
            tgt_rot[6], tgt_rot[7] = 10.0, 14.0
        else:
            # Idle vivo estilo Live2D / Brown Dust 2 / Dungeon Squad:
            # Balanço em oito lento no quadril -> onda suave na cintura/peito -> cabeça viva -> braços respirando!
            w0 = math.sin(t * 1.15) + 0.22 * math.sin(t * 2.30)
            w1 = math.sin(t * 1.15 - 0.50) + 0.22 * math.sin(t * 2.30 - 1.00)
            w2 = math.sin(t * 1.15 - 1.00)
            w3 = math.sin(t * 1.15 - 1.45)

            tgt_off[:] = (w0 * 0.012, b0 * 0.008)
            tgt_rot[0] = w0 * 3.2
            tgt_rot[1] = -w1 * 2.8 + b1 * 0.8
            tgt_rot[2] = -w2 * 2.0 + b1 * 1.2
            tgt_rot[3] = w3 * 3.8 + look_x * 6.0 + (6.0 if caressing else 0.0)
            tgt_rot[4] = -w1 * 3.2 - b1 * 2.2
            tgt_rot[5] = -w2 * 4.0 - b2 * 3.2
            tgt_rot[6] = -w1 * 3.2 + b1 * 2.2
            tgt_rot[7] = -w2 * 4.0 + b2 * 3.2
            tgt_rot[8] = -w0 * 1.8
            tgt_rot[10] = -w0 * 1.8
            tgt_sy[2] = 1.0 + b1 * 0.018

        k = 1.0 - math.exp(-dt * (12.0 if action == "walk" else 7.5))
        self._cur_rot += (tgt_rot - self._cur_rot) * k
        self._cur_scale_y += (tgt_sy - self._cur_scale_y) * k
        self.root_offset += (tgt_off - self.root_offset) * k

        # 3. Live2D 2.5D Head Parallax Turn (segue o mouse + ritmo natural!)
        tgt_htx = clamp(look_x * 0.85 + math.sin(t * 0.9) * 0.18, -1.0, 1.0) * (1.0 if self.facing_scale_x >= 0 else -1.0)
        tgt_hty = clamp(look_y * 0.75 + b2 * 0.14 - (0.25 if caressing else 0.0), -1.0, 1.0)
        self.head_turn_x += (tgt_htx - self.head_turn_x) * (1.0 - math.exp(-dt * 8.0))
        self.head_turn_y += (tgt_hty - self.head_turn_y) * (1.0 - math.exp(-dt * 8.0))

        # 4. Física secundária de mola (Soft-Body Bust + Flowing Hair + Elf Ear Twitch!)
        vy = (float(self.root_offset[1]) - self._prev_root_y) / max(dt, 1e-4)
        vx = (float(self.root_offset[0]) - self._prev_root_x) / max(dt, 1e-4)
        self._prev_root_y = float(self.root_offset[1])
        self._prev_root_x = float(self.root_offset[0])

        # Mola macia no busto (responde à respiração e passo com atraso orgânico!)
        bust_tgt_y = clamp(-vy * 0.095 + b2 * 0.0045, -0.022, 0.022)
        bust_tgt_x = clamp(-vx * 0.075, -0.014, 0.014)
        self._bust_vy += (-110.0 * (self.bust_jiggle_y - bust_tgt_y) - 9.5 * self._bust_vy) * dt
        self.bust_jiggle_y = clamp(self.bust_jiggle_y + self._bust_vy * dt, -0.026, 0.026)
        self._bust_vx += (-95.0 * (self.bust_jiggle_x - bust_tgt_x) - 9.0 * self._bust_vx) * dt
        self.bust_jiggle_x = clamp(self.bust_jiggle_x + self._bust_vx * dt, -0.018, 0.018)

        # Mola fluida no cabelo longo (rastro ao andar + brisa contínua!)
        sign_f = 1.0 if self.facing_scale_x >= 0 else -1.0
        breeze = 0.014 + wind_speed * 0.0018
        hair_tgt_x = clamp((-move_dx * 1.45) * sign_f + math.sin(t * 1.85) * breeze - vx * 0.14, -0.095, 0.095)
        hair_tgt_y = clamp(-vy * 0.12 + (0.012 if action == "dance" else 0.0), -0.035, 0.035)
        self._hair_vx += (-48.0 * (self.hair_sway_x - hair_tgt_x) - 6.8 * self._hair_vx) * dt
        self.hair_sway_x = clamp(self.hair_sway_x + self._hair_vx * dt, -0.11, 0.11)
        self._hair_vy += (-52.0 * (self.hair_sway_y - hair_tgt_y) - 7.2 * self._hair_vy) * dt
        self.hair_sway_y = clamp(self.hair_sway_y + self._hair_vy * dt, -0.045, 0.045)

        # Micro-twitch fofo nas orelhas élficas (mais animado em carinho/felicidade!)
        ear_pulse = math.pow(max(0.0, math.sin(t * 1.35)), 12.0) * math.sin(t * 14.0)
        self.ear_twitch = ear_pulse * (0.018 if caressing else 0.009) + (0.012 if emotion.mood in ("happy", "affectionate") else 0.0) * math.sin(t * 3.0)

        # 5. Expressões 2D reais 1:1 (blink, happy, blush!)
        mood = "sleepy" if asleep else emotion.mood
        tgt_blink = 1.0 if asleep else (0.92 if caressing else clamp(blink_amount, 0.0, 1.0))
        tgt_happy = 0.85 if (action in ("wave", "dance") or mood in ("happy", "affectionate") or caressing) else 0.15
        tgt_blush = clamp(emotion.blush + (0.45 if caressing else 0.0) + (0.20 if mood in ("shy", "affectionate") else 0.0), 0.0, 1.0)
        ek = 1.0 - math.exp(-dt * 14.0)
        self.blink_weight += (tgt_blink - self.blink_weight) * ek
        self.happy_weight += (tgt_happy - self.happy_weight) * (1.0 - math.exp(-dt * 8.0))
        self.blush_weight += (tgt_blush - self.blush_weight) * (1.0 - math.exp(-dt * 6.0))

        self.solve_fk()

    def solve_fk(self) -> None:
        """Calcula matrizes 3×3 finais de skinning 2D em cadeia hierárquica para os 12 ossos."""
        pivots = self.lm.bone_pivots
        world = [np.eye(3, dtype=np.float32) for _ in range(NUM_BONES)]
        inv_bind = [np.eye(3, dtype=np.float32) for _ in range(NUM_BONES)]

        for bi in range(NUM_BONES):
            px, py = float(pivots[bi, 0]), float(pivots[bi, 1])
            inv_bind[bi] = _mat3_trs(-px, -py, 0.0)
            p_idx = BONE_PARENT[bi]
            if p_idx < 0:
                tx = px + float(self.root_offset[0])
                ty = py + float(self.root_offset[1])
                local_m = _mat3_trs(tx, ty, float(self._cur_rot[bi]), 1.0, float(self._cur_scale_y[bi]))
                world[bi] = local_m
            else:
                ppx, ppy = float(pivots[p_idx, 0]), float(pivots[p_idx, 1])
                local_m = _mat3_trs(px - ppx, py - ppy, float(self._cur_rot[bi]), 1.0, float(self._cur_scale_y[bi]))
                world[bi] = world[p_idx] @ local_m

        # Auto-aterramento suave: garante que a sola do pé mais baixo nunca afunde ou flutue!
        foot_ys = []
        for fi in (9, 11):
            ex, ey = float(self.lm.bone_ends[fi, 0]), float(self.lm.bone_ends[fi, 1])
            pt_w = (world[fi] @ inv_bind[fi]) @ np.array([ex, ey, 1.0], dtype=np.float32)
            foot_ys.append(float(pt_w[1]))
        min_foot_y = min(foot_ys) if foot_ys else 0.0
        ground_fix = _mat3_trs(0.0, -min_foot_y * 0.65, 0.0)

        for bi in range(NUM_BONES):
            self.bone_mats[bi] = ground_fix @ (world[bi] @ inv_bind[bi])


_L2D_VERTEX_SHADER = """
#version 330 core
in vec2 in_pos;
in vec2 in_uv;
in vec4 in_joints;
in vec4 in_weights;
in vec4 in_aux;   // x=hair_flow, y=ear_w, z=face_w, w=bust_w

uniform mat3 u_bones[12];
uniform float u_canvas_aspect;
uniform float u_scale;
uniform float u_offset_y;
uniform float u_facing_x;
uniform vec2 u_head_turn;
uniform vec2 u_bust_jiggle;
uniform float u_breath;
uniform vec2 u_hair_sway;
uniform float u_ear_twitch;
uniform float u_time;

out vec2 v_uv;
out vec4 v_aux;

void main() {
    // 1. Skinning elástico contínuo de 4 ossos (ZERO cortes ou juntas quebradas!)
    mat3 m =
        u_bones[int(in_joints.x + 0.5)] * in_weights.x +
        u_bones[int(in_joints.y + 0.5)] * in_weights.y +
        u_bones[int(in_joints.z + 0.5)] * in_weights.z +
        u_bones[int(in_joints.w + 0.5)] * in_weights.w;

    vec3 p3 = m * vec3(in_pos, 1.0);
    vec2 p = p3.xy;

    // 2. Live2D 2.5D Head Parallax Turn (olhos/nariz/boca giram suavemente dentro do rosto!)
    p += u_head_turn * vec2(0.016, 0.010) * in_aux.z;

    // 3. Live2D Soft-Body Bust & Breathing Cage (expansão orgânica + mola macia!)
    float bw = in_aux.w;
    p.x += u_bust_jiggle.x * bw;
    p.y += (u_bust_jiggle.y + u_breath * 0.0055) * bw;

    // 4. Física fluida nos fios longos do cabelo (onda contínua + rastro de movimento!)
    float hw = in_aux.x;
    if (hw > 0.001) {
        float w1 = sin(u_time * 3.1 - in_uv.y * 9.0 + in_uv.x * 6.5);
        float w2 = cos(u_time * 2.1 - in_uv.y * 6.0);
        p.x += (u_hair_sway.x + w1 * 0.011) * hw;
        p.y += (u_hair_sway.y + w2 * 0.005) * hw;
    }

    // 5. Micro-movimento expressivo nas orelhas élficas!
    float ew = in_aux.y;
    if (ew > 0.001) {
        float side = (in_pos.x >= 0.0) ? 1.0 : -1.0;
        p.y += u_ear_twitch * ew;
        p.x += side * abs(u_ear_twitch) * 0.35 * ew;
    }

    // 6. Espelhamento elástico 2.5D (esquerda ↔ direita) + enquadramento limpo no FBO
    p.x *= u_facing_x;
    float ndc_x = (p.x * u_scale) / max(u_canvas_aspect, 0.1);
    float ndc_y = u_offset_y + p.y * u_scale;
    gl_Position = vec4(ndc_x, ndc_y, 0.0, 1.0);
    v_uv = in_uv;
    v_aux = in_aux;
}
"""

_L2D_FRAGMENT_SHADER = """
#version 330 core
in vec2 v_uv;
in vec4 v_aux;

uniform sampler2D u_base_tex;
uniform sampler2D u_blink_tex;
uniform sampler2D u_happy_tex;
uniform sampler2D u_outfit_tex;
uniform int u_has_blink;
uniform int u_has_happy;
uniform int u_has_outfit;

uniform float u_blink;
uniform float u_happy;
uniform float u_blush;
uniform vec2 u_eye_center;
uniform vec3 u_atmo_tint;
uniform float u_atmo_alpha;
uniform vec3 u_rim_color;
uniform float u_rim_strength;

out vec4 f_out;

void main() {
    vec4 base = texture(u_base_tex, v_uv);

    // 1. Camada de roupa modular 1:1 alinhada ao mesmo UV (sobrepõe corpo base!)
    if (u_has_outfit == 1) {
        vec4 outf = texture(u_outfit_tex, v_uv);
        base.rgb = mix(base.rgb, outf.rgb, outf.a);
        base.a = max(base.a, outf.a);
    }

    if (base.a < 0.01) {
        discard;
    }

    vec3 rgb = base.rgb;

    // 2. Expressões faciais 2D reais 1:1 (somente na região do rosto -> 100% traço original!)
    float face_mask = smoothstep(0.08, 0.55, v_aux.z);
    if (u_has_happy == 1 && u_happy > 0.01 && face_mask > 0.01) {
        vec4 hap = texture(u_happy_tex, v_uv);
        rgb = mix(rgb, hap.rgb, clamp(u_happy * face_mask * hap.a, 0.0, 1.0));
    }
    if (u_has_blink == 1 && u_blink > 0.01 && face_mask > 0.01) {
        vec4 blk = texture(u_blink_tex, v_uv);
        rgb = mix(rgb, blk.rgb, clamp(u_blink * face_mask * blk.a, 0.0, 1.0));
    }

    // 3. Rubor quente dinâmico nas bochechas guiado pela rede LIF!
    if (u_blush > 0.02) {
        vec2 c_l = u_eye_center + vec2(-0.048, 0.032);
        vec2 c_r = u_eye_center + vec2( 0.048, 0.032);
        float bl = exp(-dot((v_uv - c_l) / vec2(0.036, 0.020), (v_uv - c_l) / vec2(0.036, 0.020)))
                 + exp(-dot((v_uv - c_r) / vec2(0.036, 0.020), (v_uv - c_r) / vec2(0.036, 0.020)));
        rgb = mix(rgb, rgb * vec3(1.04, 0.72, 0.72) + vec3(0.14, 0.02, 0.03), clamp(bl * u_blush * 0.42, 0.0, 0.45));
    }

    // 4. Harmonização atmosférica suave com o horário/clima da praça (Manhã, Pôr do Sol, Chuva, Noite)
    rgb = mix(rgb, rgb * mix(vec3(1.0), u_atmo_tint * 1.18, 0.78), clamp(u_atmo_alpha * 0.62, 0.0, 0.48));

    // Brilho delicado de silhueta (rim-light) apenas nas bordas externas
    vec2 ts = 1.0 / vec2(textureSize(u_base_tex, 0));
    float a_l = texture(u_base_tex, v_uv + vec2(-ts.x * 3.0, 0.0)).a;
    float a_r = texture(u_base_tex, v_uv + vec2( ts.x * 3.0, 0.0)).a;
    float a_u = texture(u_base_tex, v_uv + vec2(0.0, -ts.y * 3.0)).a;
    float edge = clamp(1.0 - min(min(a_l, a_r), a_u), 0.0, 1.0);
    rgb += u_rim_color * edge * u_rim_strength * 0.28;

    f_out = vec4(clamp(rgb, 0.0, 1.0), base.a);
}
"""


class _Live2DViewGpu:
    """Buffers GPU de uma vista (frente ou costas) do personagem Live2D 2.5D."""

    def __init__(
        self,
        ctx: moderngl.Context,
        prog: moderngl.Program,
        mesh: ElasticMeshData,
        blink_rgba: np.ndarray | None = None,
        happy_rgba: np.ndarray | None = None,
    ):
        self.ctx = ctx
        self.mesh = mesh

        interleaved = np.hstack([mesh.positions, mesh.uvs, mesh.joints, mesh.weights, mesh.aux]).astype(np.float32)
        self.vbo = ctx.buffer(np.ascontiguousarray(interleaved).tobytes())
        self.ibo = ctx.buffer(np.ascontiguousarray(mesh.indices, dtype=np.uint32).tobytes())
        self.vao = ctx.vertex_array(
            prog,
            [(self.vbo, "2f 2f 4f 4f 4f", "in_pos", "in_uv", "in_joints", "in_weights", "in_aux")],
            index_buffer=self.ibo,
        )

        self.base_tex = self._upload_tex(mesh.rgba)
        self.blink_tex = self._upload_tex(blink_rgba) if blink_rgba is not None else None
        self.happy_tex = self._upload_tex(happy_rgba) if happy_rgba is not None else None
        self.outfit_textures: dict[str, moderngl.Texture] = {}

    def _upload_tex(self, rgba: np.ndarray) -> moderngl.Texture:
        arr = np.ascontiguousarray(rgba, dtype=np.uint8)
        h, w, _ = arr.shape
        tex = self.ctx.texture((w, h), 4, arr.tobytes())
        tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
        tex.repeat_x = False
        tex.repeat_y = False
        tex.build_mipmaps()
        return tex

    def add_outfit_layer(self, outfit_key: str, rgba: np.ndarray) -> None:
        self.outfit_textures[outfit_key] = self._upload_tex(rgba)


class Live2DMeshRenderer:
    """Renderizador GPU 2.5D Live2D/Spine2D em alta definição (`640×800`, MSAA 4x, >300 FPS)."""

    def __init__(
        self,
        front_rgba: np.ndarray,
        blink_rgba: np.ndarray | None = None,
        happy_rgba: np.ndarray | None = None,
        back_rgba: np.ndarray | None = None,
        outfit_layers: dict[str, np.ndarray] | None = None,
        width: int = 640,
        height: int = 800,
    ):
        self.width = int(width)
        self.height = int(height)
        self.last_foot_v: float = 0.91  # pés fixados em NDC y = -0.82 -> v = (1 - (-0.82))/2 = 0.91

        # Recorta a base frontal e aplica o MESMO bbox nas camadas 1:1 (blink, happy, outfits!)
        trimmed_front, bbox = trim_rgba_with_padding(front_rgba, pad=6, alpha_thresh=16)

        def _crop_aligned(img: np.ndarray | None) -> np.ndarray | None:
            if img is None:
                return None
            if img.shape[:2] != front_rgba.shape[:2]:
                pil = Image.fromarray(img, mode="RGBA").resize((front_rgba.shape[1], front_rgba.shape[0]), Image.Resampling.LANCZOS)
                img = np.array(pil, dtype=np.uint8)
            x0, y0, x1, y1 = bbox
            c = np.ascontiguousarray(img[y0:y1, x0:x1])
            c[0, :, 3] = 0
            c[-1, :, 3] = 0
            c[:, 0, 3] = 0
            c[:, -1, 3] = 0
            return c

        self.front_mesh = build_elastic_mesh(trimmed_front)
        self.front_animator = Live2DMeshAnimator(self.front_mesh.landmarks)

        self.ctx = moderngl.create_standalone_context()
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA, moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA)

        self._fbo_msaa = self.ctx.simple_framebuffer((self.width, self.height), components=4, samples=4)
        self._fbo_resolve = self.ctx.simple_framebuffer((self.width, self.height), components=4)

        self.prog = self.ctx.program(vertex_shader=_L2D_VERTEX_SHADER, fragment_shader=_L2D_FRAGMENT_SHADER)
        self.prog["u_base_tex"].value = 0
        self.prog["u_blink_tex"].value = 1
        self.prog["u_happy_tex"].value = 2
        self.prog["u_outfit_tex"].value = 3
        self._dummy_tex = self.ctx.texture((1, 1), 4, bytes([0, 0, 0, 0]))

        self.front_gpu = _Live2DViewGpu(
            self.ctx,
            self.prog,
            self.front_mesh,
            blink_rgba=_crop_aligned(blink_rgba),
            happy_rgba=_crop_aligned(happy_rgba),
        )
        if outfit_layers:
            for okey, orgba in outfit_layers.items():
                aligned = _crop_aligned(orgba)
                if aligned is not None:
                    self.front_gpu.add_outfit_layer(okey, aligned)

        self.back_gpu: _Live2DViewGpu | None = None
        self.back_animator: Live2DMeshAnimator | None = None
        if back_rgba is not None:
            back_mesh = build_elastic_mesh(back_rgba)
            self.back_gpu = _Live2DViewGpu(self.ctx, self.prog, back_mesh)
            self.back_animator = Live2DMeshAnimator(back_mesh.landmarks)

    def update(
        self,
        dt: float,
        action: str,
        walk_phase: float,
        action_timer: float,
        emotion: EmotionState,
        blink_amount: float = 0.0,
        look_x: float = 0.0,
        look_y: float = 0.0,
        facing: int = 1,
        move_dir: str = "front",
        move_dx: float = 0.0,
        move_dy: float = 0.0,
        wind_speed: float = 6.0,
        asleep: bool = False,
        caressing: bool = False,
    ) -> None:
        self.front_animator.update(
            dt=dt, action=action, walk_phase=walk_phase, action_timer=action_timer,
            emotion=emotion, blink_amount=blink_amount, look_x=look_x, look_y=look_y,
            facing=facing, move_dir=move_dir, move_dx=move_dx, move_dy=move_dy,
            wind_speed=wind_speed, asleep=asleep, caressing=caressing,
        )
        if self.back_animator is not None:
            self.back_animator.update(
                dt=dt, action=action, walk_phase=walk_phase, action_timer=action_timer,
                emotion=emotion, blink_amount=0.0, look_x=0.0, look_y=0.0,
                facing=facing, move_dir=move_dir, move_dx=move_dx, move_dy=move_dy,
                wind_speed=wind_speed, asleep=asleep, caressing=caressing,
            )

    def render_pixmap(
        self,
        atmosphere: AtmospherePalette,
        outfit_key: str = "base",
        camera_focus: str = "full",
    ) -> QPixmap:
        """Renderiza o frame 2.5D Live2D/Spine2D deformado na GPU com qualidade 100% ilustração 2D."""
        use_back = (self.back_gpu is not None and self.back_animator is not None and self.front_animator.back_blend > 0.5)
        gpu = self.back_gpu if use_back else self.front_gpu
        anim = self.back_animator if use_back else self.front_animator
        lm = gpu.mesh.landmarks

        self._fbo_msaa.use()
        self.ctx.viewport = (0, 0, self.width, self.height)
        self.ctx.clear(0.0, 0.0, 0.0, 0.0)

        # Converte matrizes 3x3 row-major -> col-major (GLSL mat3)
        col_bones = np.ascontiguousarray(np.transpose(anim.bone_mats, (0, 2, 1)), dtype=np.float32)
        self.prog["u_bones"].write(col_bones.tobytes())
        self.prog["u_canvas_aspect"].value = self.width / max(float(self.height), 1.0)
        self.prog["u_scale"].value = 2.65 if camera_focus == "portrait" else 1.56
        self.prog["u_offset_y"].value = -1.78 if camera_focus == "portrait" else -0.82
        self.prog["u_facing_x"].value = float(anim.facing_scale_x)
        self.prog["u_head_turn"].value = (float(anim.head_turn_x), float(anim.head_turn_y))
        self.prog["u_bust_jiggle"].value = (float(anim.bust_jiggle_x), float(anim.bust_jiggle_y))
        self.prog["u_breath"].value = float(anim.breath_val)
        self.prog["u_hair_sway"].value = (float(anim.hair_sway_x), float(anim.hair_sway_y))
        self.prog["u_ear_twitch"].value = float(anim.ear_twitch)
        self.prog["u_time"].value = float(anim.time)

        gpu.base_tex.use(location=0)
        if gpu.blink_tex is not None and not use_back:
            gpu.blink_tex.use(location=1)
            self.prog["u_has_blink"].value = 1
        else:
            self._dummy_tex.use(location=1)
            self.prog["u_has_blink"].value = 0

        if gpu.happy_tex is not None and not use_back:
            gpu.happy_tex.use(location=2)
            self.prog["u_has_happy"].value = 1
        else:
            self._dummy_tex.use(location=2)
            self.prog["u_has_happy"].value = 0

        outf_tex = gpu.outfit_textures.get(outfit_key) if (outfit_key and outfit_key != "base" and not use_back) else None
        if outf_tex is not None:
            outf_tex.use(location=3)
            self.prog["u_has_outfit"].value = 1
        else:
            self._dummy_tex.use(location=3)
            self.prog["u_has_outfit"].value = 0

        self.prog["u_blink"].value = float(anim.blink_weight)
        self.prog["u_happy"].value = float(anim.happy_weight)
        self.prog["u_blush"].value = float(anim.blush_weight)
        self.prog["u_eye_center"].value = (float(lm.cx), float(lm.eye_y))

        tr, tg, tb = atmosphere.avatar_tint
        self.prog["u_atmo_tint"].value = (tr / 255.0, tg / 255.0, tb / 255.0)
        self.prog["u_atmo_alpha"].value = float(clamp(atmosphere.avatar_tint_alpha, 0.0, 0.7))
        rr, rg, rb = atmosphere.rim_light
        self.prog["u_rim_color"].value = (rr / 255.0, rg / 255.0, rb / 255.0)
        self.prog["u_rim_strength"].value = 0.45 + float(clamp(atmosphere.avatar_tint_alpha, 0.0, 0.5)) * 0.4

        gpu.vao.render(moderngl.TRIANGLES)

        self.ctx.copy_framebuffer(self._fbo_resolve, self._fbo_msaa)
        raw = self._fbo_resolve.read(components=4, alignment=1)
        arr = np.frombuffer(raw, dtype=np.uint8).reshape((self.height, self.width, 4))
        flipped = np.ascontiguousarray(arr[::-1, :, :])
        qimg = QImage(flipped.data, self.width, self.height, self.width * 4, QImage.Format_RGBA8888).copy()
        return QPixmap.fromImage(qimg)

    def release(self) -> None:
        try:
            self.ctx.release()
        except Exception:
            pass


def load_live2d_rig_from_dir(rig_dir: Path, width: int = 640, height: int = 800) -> Live2DMeshRenderer | None:
    """Carrega um rig Live2D 2.5D de uma pasta (`base.png` + opcionais `base_blink.png`, `base_happy.png`, `base_back.png`, `outfit_*.png`)."""
    base_p = rig_dir / "base.png"
    if not base_p.is_file():
        return None

    def _read_rgba(p: Path) -> np.ndarray | None:
        if not p.is_file():
            return None
        with Image.open(p) as im:
            return np.array(im.convert("RGBA"), dtype=np.uint8)

    front = _read_rgba(base_p)
    if front is None:
        return None
    blink = _read_rgba(rig_dir / "base_blink.png")
    happy = _read_rgba(rig_dir / "base_happy.png")
    back = _read_rgba(rig_dir / "base_back.png")

    outfits: dict[str, np.ndarray] = {}
    for op in sorted(rig_dir.glob("outfit_*.png")):
        key = op.stem.replace("outfit_", "", 1)
        arr = _read_rgba(op)
        if arr is not None:
            outfits[key] = arr

    return Live2DMeshRenderer(
        front_rgba=front,
        blink_rgba=blink,
        happy_rgba=happy,
        back_rgba=back,
        outfit_layers=outfits,
        width=width,
        height=height,
    )
