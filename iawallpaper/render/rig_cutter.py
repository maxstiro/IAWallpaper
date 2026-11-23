"""RIG CUTTER — Auto-rigger que recorta um sprite A-pose RGBA do ComfyUI em partes articuladas (estilo Spine2D).

Algoritmo guiado por silhueta & detecção exata de axilas (armpit gap detection):
1. Detecta a primeira linha abaixo dos ombros em que surge um vão transparente entre o tronco/cintura
   e o braço estendido (`y_armpit_l`, `y_armpit_r`).
2. Abaixo da axila, APENAS pixels separados por vão transparente do núcleo central (tronco + saia)
   pertencem aos braços — garantindo que a saia, o busto e as coxas NUNCA sejam cortados pelos braços!
3. Acima da axila, liga suavemente a axila até o ponto externo do ombro com sobreposição circular na junta.
4. Detecta o cotovelo real ao longo da linha central de cada braço (ombro -> ponta da mão) e os joelhos
   ao longo de cada perna, calibrando `RigProportions` 1:1 com a anatomia real do sprite gerado.
"""

from dataclasses import dataclass
import math

import numpy as np
from PySide6.QtGui import QImage, QPixmap

from .skeleton import RigProportions


@dataclass
class RigPart:
    name: str
    pixmap: QPixmap
    pivot_x: float     # pivô local dentro da imagem recortada (px)
    pivot_y: float
    rest_angle: float  # ângulo de repouso do membro na A-pose (graus; 0 = vertical)
    scale_h: float     # proporção da altura total do sprite original
    upward: bool = False


@dataclass
class AutoRiggedCharacter:
    parts: dict[str, RigPart]
    src_width: int
    src_height: int
    proportions: RigProportions


def _qimage_from_rgba(arr: np.ndarray) -> QPixmap:
    arr_c = np.ascontiguousarray(arr, dtype=np.uint8)
    h, w, _ = arr_c.shape
    img = QImage(arr_c.data, w, h, w * 4, QImage.Format_RGBA8888).copy()
    return QPixmap.fromImage(img)


def _crop_masked(
    rgba: np.ndarray,
    mask: np.ndarray,
    pivot_x: float,
    pivot_y: float,
    rest_angle: float,
    src_h: int,
    name: str,
    upward: bool = False,
) -> RigPart | None:
    ys, xs = np.where(mask & (rgba[:, :, 3] > 10))
    if len(xs) < 12 or len(ys) < 12:
        return None
    x0, x1 = max(0, int(xs.min()) - 2), min(rgba.shape[1] - 1, int(xs.max()) + 2)
    y0, y1 = max(0, int(ys.min()) - 2), min(rgba.shape[0] - 1, int(ys.max()) + 2)

    sub = rgba[y0 : y1 + 1, x0 : x1 + 1].copy()
    sub_mask = mask[y0 : y1 + 1, x0 : x1 + 1]
    sub[:, :, 3] = np.where(sub_mask, sub[:, :, 3], 0)

    return RigPart(
        name=name,
        pixmap=_qimage_from_rgba(sub),
        pivot_x=float(pivot_x - x0),
        pivot_y=float(pivot_y - y0),
        rest_angle=float(rest_angle),
        scale_h=float(sub.shape[0]) / max(float(src_h), 1.0),
        upward=upward,
    )


def _circle_mask(yy: np.ndarray, xx: np.ndarray, cx: float, cy: float, r: float) -> np.ndarray:
    return ((xx - cx) ** 2 + (yy - cy) ** 2) <= (r * r)


def _central_run_bounds(row_opaque: np.ndarray, center_x: int) -> tuple[int, int]:
    """Retorna (left_edge, right_edge) do segmento opaco contíguo que contém center_x."""
    w = len(row_opaque)
    c = max(0, min(w - 1, center_x))
    if not row_opaque[c]:
        xs = np.where(row_opaque)[0]
        if len(xs) == 0:
            return c, c
        c = int(xs[np.argmin(np.abs(xs - c))])
    l_edge = c
    while l_edge > 0 and row_opaque[l_edge - 1]:
        l_edge -= 1
    r_edge = c
    while r_edge < w - 1 and row_opaque[r_edge + 1]:
        r_edge += 1
    return l_edge, r_edge


def build_rig_from_apose(pm: QPixmap) -> AutoRiggedCharacter | None:
    """Recorta automaticamente uma personagem full-body em A-pose em 10 partes articuladas."""
    if pm.isNull():
        return None
    img = pm.toImage().convertToFormat(QImage.Format_RGBA8888)
    w, h = img.width(), img.height()
    if w < 64 or h < 128:
        return None

    rgba = np.frombuffer(img.constBits(), dtype=np.uint8).reshape((h, w, 4)).copy()
    opaque = rgba[:, :, 3] > 14
    ys_all, xs_all = np.where(opaque)
    if len(xs_all) < 200:
        return None

    # 1. Recorta bbox exata nos pés (sola dos sapatos = h - 1)
    bx0, bx1 = max(0, int(xs_all.min()) - 2), min(w - 1, int(xs_all.max()) + 2)
    by0, by1 = max(0, int(ys_all.min()) - 2), int(ys_all.max())
    rgba = rgba[by0 : by1 + 1, bx0 : bx1 + 1]
    opaque = rgba[:, :, 3] > 14
    h, w, _ = rgba.shape
    yy, xx = np.mgrid[0:h, 0:w]

    # 2. Centro horizontal da coluna pela mediana do tronco (0.24..0.50 H)
    torso_band = opaque[int(h * 0.24) : int(h * 0.50), :]
    _, tx = np.where(torso_band)
    cx = float(np.median(tx)) if len(tx) > 0 else w * 0.5
    c_int = int(round(cx))

    # 3. Linha do pescoço (largura mais estreita entre 0.14..0.24 H)
    # Mede a largura do segmento central (não soma cabelo solto)
    central_widths = np.zeros(h, dtype=np.int32)
    for y in range(h):
        if opaque[y].any():
            le, re = _central_run_bounds(opaque[y], c_int)
            central_widths[y] = re - le + 1
    neck_start, neck_end = int(h * 0.14), int(h * 0.24)
    neck_slice = central_widths[neck_start:neck_end]
    valid_neck = np.where(neck_slice > 0)[0]
    y_neck = neck_start + int(valid_neck[np.argmin(neck_slice[valid_neck])]) if len(valid_neck) > 0 else int(h * 0.19)
    y_shoulder = min(int(h * 0.27), y_neck + max(8, int(h * 0.042)))

    # 4. Detecta entrepernas (primeira linha com vão transparente central entre 0.45..0.64 H)
    y_crotch = int(h * 0.53)
    for y in range(int(h * 0.45), int(h * 0.65)):
        row = opaque[y, :]
        left_any = bool(row[max(0, c_int - int(w * 0.24)) : max(1, c_int - 2)].any())
        right_any = bool(row[min(w - 1, c_int + 2) : min(w, c_int + int(w * 0.24))].any())
        center_gap = not bool(row[max(0, c_int - 2) : min(w, c_int + 3)].all())
        if left_any and right_any and center_gap:
            y_crotch = y
            break

    y_hip = max(int(h * 0.45), min(int(h * 0.56), y_crotch - int(h * 0.025)))
    y_knee = int(y_hip + (h - 1 - y_hip) * 0.50)
    j_rad = max(7.0, h * 0.024)

    # 5. Detecta a AXILA EXATA abaixo dos ombros/cabelo (a partir de ~0.27 H onde as mangas se separam das costelas!)
    arm_y_top = max(0, int(y_shoulder - j_rad * 0.6))
    arm_y_bot = min(h - 1, int(y_hip + h * 0.02))  # braços em A-pose terminam acima/na altura do quadril (nunca nas coxas!)

    y_armpit_l, x_armpit_l = None, None
    y_armpit_r, x_armpit_r = None, None
    armpit_search_start = max(y_shoulder + int(h * 0.05), int(h * 0.27))
    for y in range(armpit_search_start, min(arm_y_bot, int(h * 0.46))):
        row = opaque[y, :]
        if not row.any():
            continue
        le, re = _central_run_bounds(row, c_int)
        # Requer pelo menos 4px de braço externo além do vão transparente e axila próxima ao tronco
        if y_armpit_l is None and le > 4 and row[: le - 1].sum() >= 4 and (cx - le) <= w * 0.24:
            y_armpit_l = y
            x_armpit_l = float(le)
        if y_armpit_r is None and re < w - 5 and row[re + 2 :].sum() >= 4 and (re - cx) <= w * 0.24:
            y_armpit_r = y
            x_armpit_r = float(re)
        if y_armpit_l is not None and y_armpit_r is not None:
            break

    # Fallbacks seguros + simetria suave se um lado ainda teve mecha de cabelo fechando a axila
    if y_armpit_l is None and y_armpit_r is not None:
        y_armpit_l = y_armpit_r
        x_armpit_l = cx - (x_armpit_r - cx)
    elif y_armpit_r is None and y_armpit_l is not None:
        y_armpit_r = y_armpit_l
        x_armpit_r = cx + (cx - x_armpit_l)
    if y_armpit_l is None:
        y_armpit_l = int(y_shoulder + h * 0.09)
        x_armpit_l = cx - w * 0.16
    if y_armpit_r is None:
        y_armpit_r = int(y_shoulder + h * 0.09)
        x_armpit_r = cx + w * 0.16

    # Pivô real dos ombros simétrico ao centro do tronco
    armpit_hw = max(w * 0.10, min(w * 0.20, ((x_armpit_r - x_armpit_l) * 0.5)))
    sh_l_x = cx - armpit_hw - j_rad * 0.20
    sh_r_x = cx + armpit_hw + j_rad * 0.20

    # 6. Extrai máscaras LIMPAS dos braços:
    #    - Abaixo da axila: SOMENTE pixels separados por vão transparente do segmento central (nunca invade a saia!)
    #    - Entre ombro e axila: linha reta suave conectando (sh_x, y_shoulder) até (x_armpit, y_armpit)!
    raw_arm_l = np.zeros((h, w), dtype=bool)
    raw_arm_r = np.zeros((h, w), dtype=bool)

    for y in range(arm_y_top, arm_y_bot + 1):
        row = opaque[y, :]
        if not row.any():
            continue
        le, re = _central_run_bounds(row, c_int)

        # Braço esquerdo
        if y < y_armpit_l:
            t = (y - y_shoulder) / max(1.0, float(y_armpit_l - y_shoulder))
            cut_l = int(round(sh_l_x + (x_armpit_l - sh_l_x) * max(0.0, min(1.0, t))))
            # Só pega pixels realmente fora do núcleo se já houver vão ou acima da axila
            if le > 1 and row[: le - 1].any():
                raw_arm_l[y, :le] = row[:le]
            elif cut_l > 0:
                raw_arm_l[y, : cut_l + 1] = row[: cut_l + 1]
        else:
            if le > 1 and row[: le - 1].any():
                raw_arm_l[y, :le] = row[:le]

        # Braço direito
        if y < y_armpit_r:
            t = (y - y_shoulder) / max(1.0, float(y_armpit_r - y_shoulder))
            cut_r = int(round(sh_r_x + (x_armpit_r - sh_r_x) * max(0.0, min(1.0, t))))
            if re < w - 2 and row[re + 2 :].any():
                raw_arm_r[y, re + 1 :] = row[re + 1 :]
            elif cut_r < w:
                raw_arm_r[y, cut_r:] = row[cut_r:]
        else:
            if re < w - 2 and row[re + 2 :].any():
                raw_arm_r[y, re + 1 :] = row[re + 1 :]

    def _split_arm(arm_mask: np.ndarray, sh_x: float, is_left: bool):
        ay, ax = np.where(arm_mask)
        if len(ax) < 25:
            return None, None, 0.15, 0.15

        # Ponta da mão = pixel mais distante do ombro dentro da máscara LIMPA do braço
        d2 = (ax - sh_x) ** 2 + (ay - y_shoulder) ** 2
        far_i = int(np.argmax(d2))
        hand_x, hand_y = float(ax[far_i]), float(ay[far_i])

        # Estima cotovelo real pela mediana dos pixels do braço na metade do caminho (proj ~ 0.45..0.55)
        vx, vy = hand_x - sh_x, hand_y - y_shoulder
        vlen = max(1.0, math.hypot(vx, vy))
        proj_pts = ((ax - sh_x) * vx + (ay - y_shoulder) * vy) / (vlen * vlen)
        mid = (proj_pts >= 0.40) & (proj_pts <= 0.56)
        if mid.sum() >= 8:
            el_x = float(np.median(ax[mid]))
            el_y = float(np.median(ay[mid]))
        else:
            el_x = (sh_x + hand_x) * 0.5
            el_y = (y_shoulder + hand_y) * 0.5

        ang_upper = math.degrees(math.atan2(el_x - sh_x, max(1.0, el_y - y_shoulder)))
        ang_fore = math.degrees(math.atan2(hand_x - el_x, max(1.0, hand_y - el_y)))

        # Corte perpendicular no cotovelo usando projeção ao longo do segmento ombro -> cotovelo -> mão
        proj_grid = ((xx - sh_x) * vx + (yy - y_shoulder) * vy) / (vlen * vlen)
        el_proj = ((el_x - sh_x) * vx + (el_y - y_shoulder) * vy) / (vlen * vlen)

        elbow_cap = _circle_mask(yy, xx, el_x, el_y, j_rad * 0.90)
        sh_cap = _circle_mask(yy, xx, sh_x, y_shoulder, j_rad * 0.95)
        upper = (arm_mask & (proj_grid <= el_proj + 0.03)) | (opaque & sh_cap & (xx <= cx if is_left else xx >= cx)) | (arm_mask & elbow_cap)
        lower = (arm_mask & (proj_grid >= el_proj - 0.03)) | (arm_mask & elbow_cap)

        len_u = math.hypot(el_x - sh_x, el_y - y_shoulder) / max(float(h), 1.0)
        len_f = math.hypot(hand_x - el_x, hand_y - el_y) / max(float(h), 1.0)
        return (upper, sh_x, y_shoulder, ang_upper), (lower, el_x, el_y, ang_fore), len_u, len_f

    u_arm_l, f_arm_l, len_ua_l, len_fa_l = _split_arm(raw_arm_l, sh_l_x, is_left=True)
    u_arm_r, f_arm_r, len_ua_r, len_fa_r = _split_arm(raw_arm_r, sh_r_x, is_left=False)

    # 7. Cabeça (acima do pescoço + sobreposição circular na base do pescoço)
    neck_cap = _circle_mask(yy, xx, cx, y_neck, j_rad * 1.15)
    head_mask = (opaque & (yy <= y_neck + j_rad * 0.45) & ~raw_arm_l & ~raw_arm_r) | (opaque & neck_cap)

    # 8. Pernas (abaixo da linha do quadril, separadas pela linha central cx)
    leg_zone = opaque & (yy >= y_hip - j_rad * 0.35)
    raw_leg_l = leg_zone & (xx < cx)
    raw_leg_r = leg_zone & (xx >= cx)

    thigh_sample_y = min(h - 1, y_crotch + max(4, int(h * 0.04)))
    _, lx_s = np.where(raw_leg_l[max(0, thigh_sample_y - 6) : min(h, thigh_sample_y + 6), :])
    _, rx_s = np.where(raw_leg_r[max(0, thigh_sample_y - 6) : min(h, thigh_sample_y + 6), :])
    hip_l_x = float(np.median(lx_s)) if len(lx_s) > 0 else cx - w * 0.08
    hip_r_x = float(np.median(rx_s)) if len(rx_s) > 0 else cx + w * 0.08

    def _split_leg(leg_mask: np.ndarray, hx: float, is_left: bool):
        ly, lx = np.where(leg_mask)
        if len(lx) < 30:
            return None, None
        knee_band = leg_mask & (np.abs(yy - y_knee) <= 10)
        _, kx_arr = np.where(knee_band)
        kx = float(np.median(kx_arr)) if len(kx_arr) > 0 else hx
        foot_band = leg_mask & (yy >= int(h * 0.92))
        _, fx_arr = np.where(foot_band)
        fx = float(np.median(fx_arr)) if len(fx_arr) > 0 else kx

        ang_thigh = math.degrees(math.atan2(kx - hx, max(1.0, y_knee - y_hip)))
        ang_shin = math.degrees(math.atan2(fx - kx, max(1.0, (h - 1) - y_knee)))
        hip_cap = _circle_mask(yy, xx, hx, y_hip, j_rad * 1.15)
        knee_cap = _circle_mask(yy, xx, kx, y_knee, j_rad * 1.0)
        side_mask = (xx < cx) if is_left else (xx >= cx)
        thigh = (leg_mask & (yy <= y_knee + j_rad * 0.30)) | (opaque & hip_cap & side_mask) | (leg_mask & knee_cap)
        shin = (leg_mask & (yy >= y_knee - j_rad * 0.30)) | (leg_mask & knee_cap)
        return (thigh, hx, y_hip, ang_thigh), (shin, kx, y_knee, ang_shin)

    thigh_l, shin_l = _split_leg(raw_leg_l, hip_l_x, True)
    thigh_r, shin_r = _split_leg(raw_leg_r, hip_r_x, False)

    # 9. Tronco central INTEIRO (busto, cintura e saia plissada completos — apenas excluindo os braços limpos!)
    torso_mask = (
        opaque
        & (yy >= y_neck - j_rad * 0.25)
        & (yy <= y_crotch + int(h * 0.03))
        & ~raw_arm_l
        & ~raw_arm_r
    )

    parts: dict[str, RigPart] = {}

    def _add(name: str, mask, px: float, py: float, ang: float, upward: bool = False):
        if mask is None:
            return
        part = _crop_masked(rgba, mask, px, py, ang, h, name, upward=upward)
        if part is not None:
            parts[name] = part

    _add("head", head_mask, cx, y_neck, 0.0, upward=True)
    _add("torso", torso_mask, cx, y_hip, 0.0, upward=True)

    if u_arm_l is not None:
        _add("upper_arm_l", *u_arm_l, upward=False)
        _add("forearm_l", *f_arm_l, upward=False)
    if u_arm_r is not None:
        _add("upper_arm_r", *u_arm_r, upward=False)
        _add("forearm_r", *f_arm_r, upward=False)
    if thigh_l is not None:
        _add("thigh_l", *thigh_l, upward=False)
        _add("shin_l", *shin_l, upward=False)
    if thigh_r is not None:
        _add("thigh_r", *thigh_r, upward=False)
        _add("shin_r", *shin_r, upward=False)

    if "head" not in parts or "torso" not in parts:
        return None

    # 10. Calibra proporções anatômicas reais (normalizadas em H=1.0) para encaixe 1:1 com CharacterSkeleton!
    fh = float(h)
    len_thigh = max(0.14, (y_knee - y_hip) / fh)
    len_shin = max(0.14, ((h - 1) - y_knee) / fh)
    torso_span = max(0.16, (y_hip - y_shoulder) / fh)
    len_spine = torso_span * 0.48
    len_chest = torso_span * 0.52
    len_neck = max(0.02, (y_shoulder - y_neck) / fh)
    len_head = max(0.10, y_neck / fh)
    hip_hw = max(0.025, min(0.11, ((hip_r_x - hip_l_x) * 0.5) / fh))
    sh_hw = max(0.045, min(0.15, ((sh_r_x - sh_l_x) * 0.5) / fh))
    len_ua = max(0.10, min(0.24, (len_ua_l + len_ua_r) * 0.5))
    len_fa = max(0.10, min(0.24, (len_fa_l + len_fa_r) * 0.5))

    proportions = RigProportions(
        len_thigh=len_thigh,
        len_shin=len_shin,
        len_spine=len_spine,
        len_chest=len_chest,
        len_neck=len_neck,
        len_head=len_head,
        len_upper_arm=len_ua,
        len_forearm=len_fa,
        hip_half_w=hip_hw,
        shoulder_half_w=sh_hw,
    )
    return AutoRiggedCharacter(parts=parts, src_width=w, src_height=h, proportions=proportions)
