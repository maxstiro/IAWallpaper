"""VRM SCULPTOR — Estúdio procedural de escultura 3D e texturização sobre malha anime VRM real (100% intacta).

Usa a malha base studio 100% íntegra (`Victoria_Rubin.vrm` — corpo feminino anime sem costuras e sem buracos
no tronco/busto/pernas, rosto anime expressivo com olhos grandes e 52 morphs faciais) combinada com
cabelos longos studio opcionais (`vroid_sample.vrm`, 16.600 tris enxertados no osso `head`), escultura
anatômica suave C∞ (proporções Tree of Savior × curvas maduras), orelhas élficas longas em 3D e
retexturização pictórica HD para os 4 arquétipos base:

1. `elfa_loira`    — **Lyra (Elfa Loira)**: pele bronzeada dourada, orelhas élficas longas em 3D,
   olhos esmeralda brilhantes, blush difuso quente e cabelos loiros longos.
2. `humana_ruiva`  — **Freya (Humana Ruiva)**: pele clara quente corada, cabelo ruivo-cobre e olhos verde-oliva.
3. `androide_rosa` — **Airi (Androide Rosa)**: pele porcelana luminosa, cabelo rosa-pastel longo e olhos safira.
4. `vampira_negra` — **Lilith (Vampira)**: pele clara com sardas sutis, rabo lateral preto-esmeralda e olhos jade.

Camada inicial `outfit_key="base"`: roupa de baixo simples (sutiã + calcinha limpos e combinando) sobre
o corpo esculpido sem costuras, facilitando 100% a incrementação modular de trajes nas próximas etapas!
"""

from dataclasses import dataclass
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .vrm_loader import VrmMaterial, VrmModel, VrmPrimitive, load_vrm


@dataclass(frozen=True)
class GirlArchetype:
    id: str
    label: str
    skin_rgb: tuple[int, int, int]
    skin_shade: tuple[float, float, float]
    blush_rgb: tuple[int, int, int]
    blush_strength: float
    lip_rgb: tuple[int, int, int]
    hair_rgb: tuple[int, int, int]
    hair_shade: tuple[float, float, float]
    eye_rgb: tuple[int, int, int]
    brow_rgb: tuple[int, int, int]
    underwear_rgb: tuple[int, int, int]
    underwear_trim_rgb: tuple[int, int, int]
    elf_ears: bool = False
    freckles: bool = False
    use_long_hair_graft: bool = True
    # Escultura anatômica ultra-curvilínea estilo Dungeon Squad × Rapscallion × refs Civitai (~4.1 cabeças!)
    head_scale: float = 1.26
    bust_boost: float = 2.45
    waist_pinch: float = 0.80
    hip_boost: float = 1.62
    thigh_boost: float = 1.72
    calf_boost: float = 1.32
    arm_boost: float = 1.16
    leg_compact: float = 0.71
    torso_compact: float = 0.88


GIRL_ARCHETYPES: dict[str, GirlArchetype] = {
    "elfa_loira": GirlArchetype(
        id="elfa_loira",
        label="Lyra — Elfa Loira",
        skin_rgb=(238, 178, 142),
        skin_shade=(0.80, 0.52, 0.46),
        blush_rgb=(228, 76, 66),
        blush_strength=0.72,
        lip_rgb=(218, 96, 88),
        hair_rgb=(248, 220, 140),
        hair_shade=(0.70, 0.50, 0.28),
        eye_rgb=(36, 210, 94),
        brow_rgb=(138, 88, 44),
        # Lingerie minimalista marrom-espresso com renda creme (alto contraste que valoriza a pele dourada!)
        underwear_rgb=(68, 40, 34),
        underwear_trim_rgb=(246, 236, 224),
        elf_ears=True,
        freckles=False,
        use_long_hair_graft=True,
        head_scale=1.28,
        bust_boost=1.98,
        waist_pinch=0.81,
        hip_boost=1.48,
        thigh_boost=1.46,
        calf_boost=1.22,
        arm_boost=1.12,
        leg_compact=0.74,
        torso_compact=0.89,
    ),
    "humana_ruiva": GirlArchetype(
        id="humana_ruiva",
        label="Freya — Humana Ruiva",
        skin_rgb=(248, 212, 192),
        skin_shade=(0.78, 0.52, 0.48),
        blush_rgb=(236, 88, 86),
        blush_strength=0.68,
        lip_rgb=(224, 102, 100),
        hair_rgb=(214, 90, 40),
        hair_shade=(0.58, 0.24, 0.16),
        eye_rgb=(112, 178, 62),
        brow_rgb=(132, 50, 24),
        underwear_rgb=(34, 28, 40),
        underwear_trim_rgb=(236, 188, 88),
        elf_ears=False,
        freckles=False,
        use_long_hair_graft=True,
        head_scale=1.26,
        bust_boost=2.40,
        waist_pinch=0.80,
        hip_boost=1.60,
        thigh_boost=1.70,
        calf_boost=1.30,
        arm_boost=1.14,
        leg_compact=0.72,
        torso_compact=0.88,
    ),
    "androide_rosa": GirlArchetype(
        id="androide_rosa",
        label="Airi — Androide Rosa",
        skin_rgb=(252, 224, 214),
        skin_shade=(0.82, 0.60, 0.66),
        blush_rgb=(244, 110, 148),
        blush_strength=0.62,
        lip_rgb=(242, 118, 142),
        hair_rgb=(252, 160, 196),
        hair_shade=(0.72, 0.40, 0.58),
        eye_rgb=(60, 162, 254),
        brow_rgb=(194, 90, 126),
        underwear_rgb=(244, 152, 192),
        underwear_trim_rgb=(255, 242, 248),
        elf_ears=False,
        freckles=False,
        use_long_hair_graft=True,
        head_scale=1.26,
        bust_boost=2.45,
        waist_pinch=0.79,
        hip_boost=1.58,
        thigh_boost=1.68,
        calf_boost=1.28,
        arm_boost=1.12,
        leg_compact=0.72,
        torso_compact=0.88,
    ),
    "vampira_negra": GirlArchetype(
        id="vampira_negra",
        label="Lilith — Vampira",
        skin_rgb=(244, 212, 198),
        skin_shade=(0.76, 0.52, 0.56),
        blush_rgb=(224, 92, 88),
        blush_strength=0.56,
        lip_rgb=(208, 94, 98),
        hair_rgb=(34, 44, 42),
        hair_shade=(0.18, 0.22, 0.28),
        eye_rgb=(66, 166, 134),
        brow_rgb=(36, 32, 34),
        underwear_rgb=(28, 24, 34),
        underwear_trim_rgb=(204, 48, 86),
        elf_ears=False,
        freckles=True,
        use_long_hair_graft=False,
        head_scale=1.26,
        bust_boost=2.42,
        waist_pinch=0.80,
        hip_boost=1.64,
        thigh_boost=1.74,
        calf_boost=1.32,
        arm_boost=1.14,
        leg_compact=0.71,
        torso_compact=0.88,
    ),
}


def _recompute_smooth_normals(positions: np.ndarray, indices: np.ndarray) -> np.ndarray:
    tris = indices.reshape(-1, 3)
    v0 = positions[tris[:, 0]]
    v1 = positions[tris[:, 1]]
    v2 = positions[tris[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0)
    norms = np.zeros_like(positions, dtype=np.float32)
    np.add.at(norms, tris[:, 0], fn)
    np.add.at(norms, tris[:, 1], fn)
    np.add.at(norms, tris[:, 2], fn)
    lens = np.linalg.norm(norms, axis=1, keepdims=True)
    return (norms / np.maximum(lens, 1e-6)).astype(np.float32)


def _recolor_skin_array(
    arr: np.ndarray,
    target_skin: tuple[int, int, int],
    ref_skin: tuple[float, float, float] = (254.0, 232.0, 214.0),
    mask: np.ndarray | None = None,
) -> np.ndarray:
    """Ajusta o tom de pele preservando 100% do sombreamento pictórico original."""
    out = arr.astype(np.float32).copy()
    rgb = out[:, :, :3]
    ref = np.array(ref_skin, dtype=np.float32)
    dst = np.array(target_skin, dtype=np.float32)
    ratio = dst / ref
    shifted = np.clip(rgb * ratio[None, None, :], 0.0, 255.0)
    if mask is not None:
        m = mask[:, :, None].astype(np.float32)
        out[:, :, :3] = rgb * (1.0 - m) + shifted * m
    else:
        out[:, :, :3] = shifted
    return np.clip(out, 0, 255).astype(np.uint8)


def _paint_face_texture(orig: np.ndarray, arch: GirlArchetype) -> np.ndarray:
    """Re-tonifica `Face_00_SKIN` preservando 100% da arte studio + blush quente difuso e sardas opcionais!"""
    base = _recolor_skin_array(orig, arch.skin_rgb)
    img = Image.fromarray(base, mode="RGBA")
    w, h = img.size

    # No Face_00_SKIN da Victoria_Rubin: bochechas ~ (0.31/0.69, 0.625), ponte do nariz ~ (0.50, 0.60), lábios ~ (0.50, 0.75)
    blush_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blush_layer)
    br, bg, bb = arch.blush_rgb
    a_cheek = int(125 * arch.blush_strength)
    a_nose = int(34 * arch.blush_strength)
    for cx_r in (0.33, 0.67):
        cx = int(w * cx_r)
        cy = int(h * 0.635)
        bd.ellipse([cx - int(w * 0.095), cy - int(h * 0.052), cx + int(w * 0.095), cy + int(h * 0.052)], fill=(br, bg, bb, a_cheek))
    bd.ellipse([int(w * 0.43), int(h * 0.61), int(w * 0.57), int(h * 0.66)], fill=(br, bg, bb, a_nose))
    lr, lg, lb = arch.lip_rgb
    bd.ellipse([int(w * 0.455), int(h * 0.742), int(w * 0.545), int(h * 0.772)], fill=(lr, lg, lb, 130))
    blush_layer = blush_layer.filter(ImageFilter.GaussianBlur(radius=int(w * 0.022)))
    img = Image.alpha_composite(img, blush_layer)

    if arch.freckles:
        fl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        fd = ImageDraw.Draw(fl)
        sr, sg, sb = arch.skin_rgb
        fcol = (max(0, sr - 62), max(0, sg - 72), max(0, sb - 66), 155)
        for sign in (-1, 1):
            for dx, dy in ((0.11, 0.63), (0.14, 0.64), (0.125, 0.655), (0.165, 0.635), (0.15, 0.66), (0.095, 0.645)):
                fx = int(w * (0.50 + sign * dx))
                fy = int(h * dy)
                fd.ellipse([fx - 3, fy - 3, fx + 3, fy + 3], fill=fcol)
        fl = fl.filter(ImageFilter.GaussianBlur(radius=1))
        img = Image.alpha_composite(img, fl)

    return np.array(img, dtype=np.uint8)


def _paint_victoria_body_base_texture(orig: np.ndarray, arch: GirlArchetype) -> np.ndarray:
    """Converte `F00_002_02_Body_00_SKIN` da Victoria em pele lisa bronzeada + roupa de baixo simples limpa!"""
    h, w, _ = orig.shape
    rgb = orig[:, :, :3].astype(np.float32)

    # 1. Remove as meias brancas (faixa inferior das pernas e pés: y >= 0.635 nas colunas externas + pés)
    # identificando pixels branco-azulados/cinza-frios onde B >= R - 6 (a pele sempre tem R >> B!)
    is_cool_white = (rgb[:, :, 2] >= rgb[:, :, 0] - 8.0) & (rgb[:, :, 0] > 170.0)
    # Na região das pernas/pés (y >= 0.56), substitui a meia branca e solado roxo por pele uniforme suave!
    yy, xx = np.mgrid[0:h, 0:w]
    yn = yy / float(h)
    xn = xx / float(w)
    in_panties_zone = (
        ((yn >= 0.455) & (yn <= 0.570) & (xn >= 0.235) & (xn <= 0.765))
        | ((yn >= 0.560) & (yn <= 0.642) & (xn >= 0.445) & (xn <= 0.555))
    )
    is_panties = is_cool_white & in_panties_zone

    # Recolore toda a pele para o tom exato do arquétipo!
    base = _recolor_skin_array(orig, arch.skin_rgb)

    # Remove 100% das meias nas pernas, tornozelos e pés (substituindo pelo tom exato de pele!)
    in_socks_legs = (yn >= 0.615) & ((xn < 0.242) | (xn > 0.758))
    in_feet_region = (yn >= 0.565) & (yn <= 0.795) & (xn >= 0.232) & (xn <= 0.768) & (~is_panties) & (~((yn < 0.642) & (xn > 0.455) & (xn < 0.545)))
    lum_raw = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
    is_purple_sole = (rgb[:, :, 2] > rgb[:, :, 1] + 6.0) & (yn > 0.63)
    # No UV da Victoria, a meia/pé tem baixa saturação quente (R - B < 18) diferente da pele quente (R - B >= 20)!
    is_pale_sock = (rgb[:, :, 0] - rgb[:, :, 2] < 18.0) & (lum_raw > 195.0)
    sock_mask = in_socks_legs | (in_feet_region & (is_cool_white | is_purple_sole | is_pale_sock))
    if np.any(sock_mask):
        lum_s = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]) / 255.0
        shad = np.clip(0.86 + 0.14 * lum_s, 0.82, 1.00)
        sr, sg, sb = float(arch.skin_rgb[0]), float(arch.skin_rgb[1]), float(arch.skin_rgb[2])
        base[sock_mask, 0] = np.clip(sr * shad[sock_mask], 0, 255).astype(np.uint8)
        base[sock_mask, 1] = np.clip(sg * shad[sock_mask], 0, 255).astype(np.uint8)
        base[sock_mask, 2] = np.clip(sb * shad[sock_mask], 0, 255).astype(np.uint8)

    # Recolore a calcinha já mapeada perfeitamente no UV da Victoria!
    ur, ug, ub = arch.underwear_rgb
    tr, tg, tb = arch.underwear_trim_rgb
    if np.any(is_panties):
        lum_p = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]) / 255.0
        p_sh = np.clip(lum_p / 0.96, 0.74, 1.04)
        base[is_panties, 0] = np.clip(ur * p_sh[is_panties], 0, 255).astype(np.uint8)
        base[is_panties, 1] = np.clip(ug * p_sh[is_panties], 0, 255).astype(np.uint8)
        base[is_panties, 2] = np.clip(ub * p_sh[is_panties], 0, 255).astype(np.uint8)

    # Pinta traço sépia-aquarela orgânico nas clavículas, decote e umbigo (assinatura Tree of Savior × Rapscallion!)
    img = Image.fromarray(base, mode="RGBA")
    cx = w // 2
    ink = (88, 46, 42, 228)
    soft_ink = (max(0, arch.skin_rgb[0] - 72), max(0, arch.skin_rgb[1] - 78), max(0, arch.skin_rgb[2] - 72), 185)

    # Sutiã tomara-que-caia base (pintura limpa em aquarela com renda creme!)
    d = ImageDraw.Draw(img)
    band_y0 = int(h * 0.268)
    band_y1 = int(h * 0.308)
    d.rectangle([int(w * 0.238), band_y0, int(w * 0.762), band_y1], fill=(ur, ug, ub, 255))
    for sign in (-1, 1):
        bx = cx + sign * int(w * 0.068)
        by = int(h * 0.255)
        d.ellipse([bx - int(w * 0.069), by - int(h * 0.044), bx + int(w * 0.069), by + int(h * 0.056)], fill=(ur, ug, ub, 255))
        d.arc([bx - int(w * 0.069), by - int(h * 0.044), bx + int(w * 0.069), by + int(h * 0.056)], start=185, end=355, fill=(tr, tg, tb, 255), width=7)

    # Camada de traço sépia macio (suavizada com GaussianBlur 1px para fundir como tinta aquarela 2D!)
    ink_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    idraw = ImageDraw.Draw(ink_layer)
    idraw.line([(cx - int(w * 0.088), int(h * 0.125)), (cx - int(w * 0.016), int(h * 0.136))], fill=soft_ink, width=4)
    idraw.line([(cx + int(w * 0.088), int(h * 0.125)), (cx + int(w * 0.016), int(h * 0.136))], fill=soft_ink, width=4)
    idraw.line([(cx, int(h * 0.218)), (cx, int(h * 0.280))], fill=ink, width=4)
    idraw.arc([cx - 8, int(h * 0.398), cx + 8, int(h * 0.418)], start=20, end=160, fill=soft_ink, width=4)
    for sign in (-1, 1):
        bx = cx + sign * int(w * 0.068)
        by = int(h * 0.255)
        idraw.arc([bx - int(w * 0.069), by - int(h * 0.044), bx + int(w * 0.069), by + int(h * 0.056)], start=192, end=348, fill=ink, width=3)
        idraw.arc([bx - int(w * 0.066), by - int(h * 0.036), bx + int(w * 0.066), by + int(h * 0.058)], start=25, end=155, fill=ink, width=3)
    idraw.line([(int(w * 0.238), band_y1), (int(w * 0.762), band_y1)], fill=ink, width=3)
    idraw.line([(int(w * 0.24), int(h * 0.482)), (int(w * 0.76), int(h * 0.482))], fill=ink, width=3)
    ink_layer = ink_layer.filter(ImageFilter.GaussianBlur(radius=1.0))
    img = Image.alpha_composite(img, ink_layer)

    return np.array(img, dtype=np.uint8)


def _bold_comic_strokes(orig: np.ndarray, target_rgb: tuple[int, int, int], thicken: int = 5) -> np.ndarray:
    """Engrossa e escurece delineado, cílios e sobrancelhas no estilo nanquim expressivo Rapscallion!"""
    img = Image.fromarray(orig, mode="RGBA")
    r, g, b, a = img.split()
    a_bold = a.filter(ImageFilter.MaxFilter(size=thicken))
    a_np = np.array(a_bold, dtype=np.float32)
    a_np = np.clip(a_np * 1.35, 0, 255).astype(np.uint8)
    out = np.zeros_like(orig, dtype=np.uint8)
    out[:, :, 0] = target_rgb[0]
    out[:, :, 1] = target_rgb[1]
    out[:, :, 2] = target_rgb[2]
    out[:, :, 3] = a_np
    return out


def _recolor_iris_texture(orig: np.ndarray, eye_rgb: tuple[int, int, int]) -> np.ndarray:
    """Recolore as grandes íris pintadas à mão da Victoria mantendo pupila, brilho inferior e textura de traços!"""
    arr = orig.astype(np.float32).copy()
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3]
    lum = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]) / 255.0

    # Na Victoria o fundo é branco transparente (alpha=0) e a íris tem alpha > 20!
    tr, tg, tb = eye_rgb[0] / 255.0, eye_rgb[1] / 255.0, eye_rgb[2] / 255.0
    # Preserva contraste entre anel superior escuro, pupila e crescente luminoso inferior
    val = np.clip(lum * 1.38, 0.0, 1.0)
    hi = np.clip((lum - 0.62) / 0.34, 0.0, 1.0)
    nr = np.clip((val * tr * 1.15 + hi * 0.45) * 255.0, 0.0, 255.0)
    ng = np.clip((val * tg * 1.15 + hi * 0.48) * 255.0, 0.0, 255.0)
    nb = np.clip((val * tb * 1.15 + hi * 0.40) * 255.0, 0.0, 255.0)

    valid = alpha > 16
    arr[valid, 0] = nr[valid]
    arr[valid, 1] = ng[valid]
    arr[valid, 2] = nb[valid]
    return np.clip(arr, 0, 255).astype(np.uint8)


def _recolor_hair_texture(orig: np.ndarray, hair_rgb: tuple[int, int, int]) -> np.ndarray:
    """Recolore texturas de cabelo preservando 100% dos fios, sombras e faixas de brilho pintadas à mão!"""
    arr = orig.astype(np.float32).copy()
    rgb = arr[:, :, :3]
    lum = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]) / 255.0
    mask = arr[:, :, 3] > 20
    l_mean = max(float(np.mean(lum[mask])) if np.any(mask) else 0.40, 0.15)
    norm_l = np.clip(lum / l_mean, 0.46, 1.42)
    norm_l = np.power(norm_l, 0.85)

    tr, tg, tb = float(hair_rgb[0]), float(hair_rgb[1]), float(hair_rgb[2])
    arr[:, :, 0] = np.clip(tr * norm_l, 0.0, 255.0)
    arr[:, :, 1] = np.clip(tg * norm_l, 0.0, 255.0)
    arr[:, :, 2] = np.clip(tb * norm_l, 0.0, 255.0)
    return arr.astype(np.uint8)


def _build_elf_ears_primitive(
    head_joint_in_skin: int,
    head_pos: np.ndarray,
    is_vrm1: bool,
    skin_index: int,
    material_index: int,
    mesh_index: int,
) -> VrmPrimitive:
    """Constrói par de orelhas élficas longas e elegantes em 3D ancoradas exatamente na cabeça do VRM!"""
    z_fwd = 1.0 if is_vrm1 else -1.0  # VRM 0.x olha -Z; orelhas varrem suavemente para trás (-z_fwd)!
    pos_list: list[np.ndarray] = []
    norm_list: list[np.ndarray] = []
    uv_list: list[np.ndarray] = []
    j_list: list[np.ndarray] = []
    w_list: list[np.ndarray] = []
    idx_list: list[np.ndarray] = []
    v_off = 0

    ear_y = float(head_pos[1]) + 0.058
    ear_z = float(head_pos[2]) + 0.005 * z_fwd
    ear_x = 0.072

    stations = [
        (0.000, 0.000,  0.000, 0.022, 0.013),
        (0.028, 0.010, -0.008, 0.023, 0.012),
        (0.062, 0.026, -0.020, 0.020, 0.010),
        (0.098, 0.044, -0.032, 0.015, 0.008),
        (0.132, 0.062, -0.042, 0.010, 0.006),
        (0.160, 0.078, -0.050, 0.005, 0.003),
        (0.178, 0.090, -0.055, 0.001, 0.001),
    ]
    n_r = len(stations)
    n_seg = 16

    for side in (1.0, -1.0):
        grid = np.zeros((n_r, n_seg + 1, 3), dtype=np.float32)
        uv = np.zeros((n_r, n_seg + 1, 2), dtype=np.float32)
        for r, (dx, dy, dz, ry, rz) in enumerate(stations):
            v_c = r / max(n_r - 1, 1)
            for c in range(n_seg + 1):
                u = c / n_seg
                ang = u * math.tau
                ly = math.cos(ang) * ry
                lz = math.sin(ang) * rz
                if lz * z_fwd > 0 and 0.15 < v_c < 0.78:
                    lz *= 0.42
                grid[r, c] = (side * (ear_x + dx), ear_y + dy + ly, ear_z + dz * z_fwd + lz)
                uv[r, c] = (u, v_c)

        pts = grid.reshape(-1, 3)
        tris: list[int] = []
        flip = side < 0
        for r in range(n_r - 1):
            for c in range(n_seg):
                i00 = v_off + r * (n_seg + 1) + c
                i01 = i00 + 1
                i10 = i00 + (n_seg + 1)
                i11 = i10 + 1
                if not flip:
                    tris.extend([i00, i01, i11, i00, i11, i10])
                else:
                    tris.extend([i00, i11, i01, i00, i10, i11])
        idx_arr = np.array(tris, dtype=np.uint32)
        norms = _recompute_smooth_normals(pts, idx_arr - v_off)

        n_v = len(pts)
        jts = np.zeros((n_v, 4), dtype=np.float32)
        wts = np.zeros((n_v, 4), dtype=np.float32)
        jts[:, 0] = float(head_joint_in_skin)
        wts[:, 0] = 1.0

        pos_list.append(pts)
        norm_list.append(norms)
        uv_list.append(uv.reshape(-1, 2).astype(np.float32))
        j_list.append(jts)
        w_list.append(wts)
        idx_list.append(idx_arr)
        v_off += n_v

    return VrmPrimitive(
        mesh_index=mesh_index,
        skin_index=skin_index,
        material_index=material_index,
        positions=np.vstack(pos_list),
        normals=np.vstack(norm_list),
        uvs=np.vstack(uv_list),
        joints=np.vstack(j_list),
        weights=np.vstack(w_list),
        indices=np.concatenate(idx_list),
    )


def _make_elf_ear_texture(arch: GirlArchetype) -> np.ndarray:
    w, h = 128, 256
    sr, sg, sb = arch.skin_rgb
    br, bg, bb = arch.blush_rgb
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    for y in range(h):
        t = y / max(h - 1, 1)
        k = (t ** 1.3) * 0.64
        arr[y, :, 0] = np.clip(int(sr * (1.0 - k) + min(255, br + 20) * k), 0, 255)
        arr[y, :, 1] = np.clip(int(sg * (1.0 - k) + bg * k), 0, 255)
        arr[y, :, 2] = np.clip(int(sb * (1.0 - k) + bb * k), 0, 255)
        arr[y, :, 3] = 255
    return arr


def _find_head_skin(model: VrmModel) -> tuple[int, int, np.ndarray]:
    head_node = model.humanoid_bones.get("head", -1)
    for s_i, sk in enumerate(model.skins):
        if head_node in sk.joints:
            j_i = sk.joints.index(head_node)
            head_bind = np.linalg.inv(sk.inv_bind_matrices[j_i])[:3, 3]
            return s_i, j_i, head_bind
    return -1, -1, np.zeros(3, dtype=np.float32)


def _graft_long_hair(dst_model: VrmModel, hair_vrm_path: Path, arch: GirlArchetype) -> None:
    """Enxerta o cabelo longo ondulado studio (16.600 tris do `vroid_sample.vrm`) na cabeça da malha base!"""
    if not hair_vrm_path.is_file():
        return
    src = load_vrm(hair_vrm_path)
    dst_skin_idx, dst_head_j, dst_head_pos = _find_head_skin(dst_model)
    _, _, src_head_pos = _find_head_skin(src)
    if dst_skin_idx < 0:
        return

    # Remove apenas as mechas de cabelo externas da malha destino, preservando a calota limpa `HairBack` da própria Victoria!
    dst_model.primitives = [
        p for p in dst_model.primitives
        if not (dst_model.materials[p.material_index].role == "hair" and "hairback" not in dst_model.materials[p.material_index].name.lower())
    ]

    flip_y180 = (dst_model.is_vrm1 != src.is_vrm1)
    # Alinhamento fino: `vroid_sample` cobre perfeitamente o crânio e as orelhas humanas da Victoria sem vazamento!
    hair_scale = np.array([1.08, 1.05, 1.08], dtype=np.float32)
    next_mesh_idx = max((p.mesh_index for p in dst_model.primitives), default=0) + 1

    mat_remap: dict[int, int] = {}
    for p in src.primitives:
        smat = src.materials[p.material_index]
        if smat.role != "hair" or "hairback" in smat.name.lower():
            continue
        if p.material_index not in mat_remap:
            new_mi = len(dst_model.materials)
            tex = _recolor_hair_texture(smat.texture_rgba, arch.hair_rgb) if smat.texture_rgba is not None else None
            dst_model.materials.append(
                VrmMaterial(
                    index=new_mi,
                    name=f"Grafted_{smat.name}",
                    role="hair",
                    base_color=(1.0, 1.0, 1.0, 1.0),
                    shade_color=arch.hair_shade,
                    texture_rgba=tex,
                    alpha_mode=smat.alpha_mode,
                    alpha_cutoff=smat.alpha_cutoff,
                    double_sided=True,
                )
            )
            mat_remap[p.material_index] = new_mi

        pos = (p.positions - src_head_pos[None, :]) * hair_scale[None, :]
        norms = p.normals.copy()
        if flip_y180:
            pos[:, 0] = -pos[:, 0]
            pos[:, 2] = -pos[:, 2]
            norms[:, 0] = -norms[:, 0]
            norms[:, 2] = -norms[:, 2]
        pos = pos + dst_head_pos[None, :] + np.array([0.0, 0.012, 0.004 * (1.0 if dst_model.is_vrm1 else -1.0)], dtype=np.float32)

        n_v = len(pos)
        jts = np.zeros((n_v, 4), dtype=np.float32)
        wts = np.zeros((n_v, 4), dtype=np.float32)
        jts[:, 0] = float(dst_head_j)
        wts[:, 0] = 1.0

        dst_model.primitives.append(
            VrmPrimitive(
                mesh_index=next_mesh_idx,
                skin_index=dst_skin_idx,
                material_index=mat_remap[p.material_index],
                positions=pos.astype(np.float32),
                normals=norms.astype(np.float32),
                uvs=p.uvs.copy(),
                joints=jts,
                weights=wts,
                indices=p.indices.copy(),
            )
        )
        next_mesh_idx += 1


def _sculpt_body_vertices(model: VrmModel, arch: GirlArchetype) -> None:
    """Escultura anatômica contínua C∞ diretamente sobre a malha studio `Body_00_SKIN` (ZERO costuras!)."""
    # Detecta automaticamente escala Y e orientação frontal (+Z p/ VRM 1.0, -Z p/ VRM 0.x!)
    z_fwd = 1.0 if model.is_vrm1 else -1.0
    _, _, head_bind = _find_head_skin(model)
    # Coordenadas proporcionais à altura da cabeça (funciona tanto em Victoria 1.74m quanto em vroid_sample 1.62m!)
    h_ref = float(head_bind[1]) if head_bind[1] > 1.0 else 1.497
    y_chest = h_ref * 0.840    # ≈ 1.257 na Victoria
    y_waist = h_ref * 0.745    # ≈ 1.115 na Victoria
    y_hips = h_ref * 0.625     # ≈ 0.935 na Victoria
    y_thigh = h_ref * 0.525    # ≈ 0.785 na Victoria

    for prim in model.primitives:
        mat = model.materials[prim.material_index] if 0 <= prim.material_index < len(model.materials) else None
        if mat is None or mat.role not in ("skin", "tops", "bottoms"):
            continue
        p = prim.positions.copy()
        x, y, z = p[:, 0], p[:, 1], p[:, 2]
        zf = z * z_fwd  # positivo = frente do corpo!

        # 1. Busto volumoso, redondo e natural em perfil e frente (refs 96078865 / 141744777 / 96444929!)
        if arch.bust_boost > 0.01:
            amp = 0.044 * arch.bust_boost
            front_mask = np.clip((zf - 0.004) / 0.044, 0.0, 1.0)
            arm_mask = np.clip((0.165 - np.abs(x)) / 0.040, 0.0, 1.0)
            for sign in (-1.0, 1.0):
                dx = (x - sign * 0.064) / 0.082
                dy = (y - (y_chest - 0.006)) / 0.088
                g = np.exp(-(dx * dx + dy * dy)) * front_mask * arm_mask
                p[:, 2] += g * (amp * z_fwd)
                p[:, 0] += g * (sign * amp * 0.28)
                p[:, 1] -= g * (amp * 0.24)

        # 2. Cintura bem fina contrastando com busto e quadris (ampulheta shortstack!)
        waist_w = np.exp(-((y - y_waist) / 0.078) ** 2) * np.clip((0.155 - np.abs(x)) / 0.038, 0.0, 1.0)
        p[:, 0] *= (1.0 - (1.0 - arch.waist_pinch) * waist_w)
        p[:, 2] *= (1.0 - (1.0 - arch.waist_pinch) * 0.55 * waist_w)

        # 3. Quadris amplos, glúteos redondos suaves e coxas curvilíneas com transição ultra-orgânica até o joelho!
        y_calf = h_ref * 0.24
        y_knee = h_ref * 0.36
        knee_taper = np.clip((y - y_knee) / 0.19, 0.0, 1.0)
        knee_taper = knee_taper * knee_taper * (3.0 - 2.0 * knee_taper)  # smoothstep C1 -> ZERO quina em perfil!
        hip_w = np.exp(-((y - (y_hips - 0.01)) / 0.165) ** 2)
        thigh_w = np.exp(-((y - (y_thigh + 0.01)) / 0.185) ** 2) * (0.28 + 0.72 * knee_taper)
        calf_w = np.exp(-((y - y_calf) / 0.135) ** 2) * np.clip((y - 0.09) / 0.09, 0.0, 1.0)

        hip_x_gain = (arch.hip_boost - 1.0) * 0.68 * hip_w
        thigh_x_gain = (arch.thigh_boost - 1.0) * 0.60 * thigh_w
        calf_x_gain = (arch.calf_boost - 1.0) * 0.62 * calf_w

        below_crotch = np.clip((y_hips - 0.01 - y) / 0.17, 0.0, 1.0)
        leg_cx = np.sign(x) * 0.095
        x_hip = x * (1.0 + hip_x_gain)
        x_leg = leg_cx + (x_hip - leg_cx) * (1.0 + thigh_x_gain * below_crotch + calf_x_gain * below_crotch)
        p[:, 0] = x_leg

        # Profundidade Z suave e redonda (glúteos pêssego + coxa superior cheia afinando limpa no joelho!)
        p[:, 2] *= (1.0 + (arch.hip_boost - 1.0) * 0.68 * hip_w + (arch.thigh_boost - 1.0) * 0.50 * thigh_w + (arch.calf_boost - 1.0) * 0.55 * calf_w)
        back_mask = np.clip((-zf - 0.008) / 0.048, 0.0, 1.0)
        p[:, 2] -= hip_w * back_mask * (0.056 * z_fwd) * (arch.hip_boost - 1.0) / 0.56
        front_thigh_mask = np.clip((zf - 0.006) / 0.045, 0.0, 1.0) * below_crotch * knee_taper
        p[:, 2] += thigh_w * front_thigh_mask * (0.016 * z_fwd)

        # 4. Braços levemente mais macios/encorpados para harmonizar com o busto e quadris (|x| > 0.16)
        in_arms = np.clip((np.abs(x) - 0.16) / 0.06, 0.0, 1.0) * np.clip((y - (y_waist + 0.05)) / 0.12, 0.0, 1.0)
        arm_y_c = h_ref * 0.918
        p[:, 1] = arm_y_c + (p[:, 1] - arm_y_c) * (1.0 + (arch.arm_boost - 1.0) * in_arms)
        p[:, 2] *= (1.0 + (arch.arm_boost - 1.0) * in_arms)

        prim.positions = p.astype(np.float32)
        prim.normals = _recompute_smooth_normals(prim.positions, prim.indices)


def _apply_tos_proportions(model: VrmModel, arch: GirlArchetype) -> None:
    """Ajusta proporções estilizadas Rapscallion × Dungeon Squad (~4.5 cabeças, pernas compactas e rosto expressivo)."""
    hb = model.humanoid_bones
    head_i = hb.get("head")
    if head_i is not None:
        s = float(arch.head_scale)
        model.nodes[head_i].scale = model.nodes[head_i].scale * np.array([s, s, s], dtype=np.float32)

    # Compacta suavemente o tronco para silhueta menos alongada
    spine_i = hb.get("spine")
    if spine_i is not None:
        tc = float(arch.torso_compact)
        model.nodes[spine_i].scale = model.nodes[spine_i].scale * np.array([1.0, tc, 1.0], dtype=np.float32)

    for bname in ("leftUpperLeg", "rightUpperLeg"):
        bi = hb.get(bname)
        if bi is not None:
            model.nodes[bi].scale = model.nodes[bi].scale * np.array([1.0, float(arch.leg_compact), 1.0], dtype=np.float32)

    hips_i = hb.get("hips")
    if hips_i is not None:
        drop = (1.0 - float(arch.leg_compact)) * 0.96
        model.nodes[hips_i].translation = model.nodes[hips_i].translation - np.array([0.0, drop, 0.0], dtype=np.float32)
        model.height = max(1.18, model.height - drop + 0.04)


def build_sculpted_vrm_girl(
    vrm_dir: Path,
    archetype_id: str = "elfa_loira",
    outfit_key: str = "base",
) -> VrmModel:
    """Constrói um dos 4 arquétipos base em HD sobre malha studio 100% íntegra (`Victoria_Rubin.vrm`)."""
    arch = GIRL_ARCHETYPES.get(archetype_id, GIRL_ARCHETYPES["elfa_loira"])
    base_vrm = vrm_dir / "Victoria_Rubin.vrm"
    if not base_vrm.is_file():
        base_vrm = vrm_dir / "vroid_sample.vrm"
    model = load_vrm(base_vrm)
    model.name = f"ToS_{arch.id}_{outfit_key}"

    # 1. Camada base (`outfit_key == "base"`): oculta roupas externas para exibir a roupa de baixo limpa!
    if outfit_key == "base":
        model.primitives = [
            p for p in model.primitives
            if model.materials[p.material_index].role not in ("tops", "bottoms", "shoes")
        ]

    # 2. Enxerta cabelo longo studio (16.600 tris) para Elfa Loira / Humana Ruiva / Androide Rosa
    if arch.use_long_hair_graft and (vrm_dir / "vroid_sample.vrm").is_file():
        _graft_long_hair(model, vrm_dir / "vroid_sample.vrm", arch)

    # 3. Retexturização artística HD preservando 100% da arte studio original
    for mat in model.materials:
        nlow = mat.name.lower()
        if mat.texture_rgba is None:
            continue
        if "face_00_skin" in nlow:
            mat.texture_rgba = _paint_face_texture(mat.texture_rgba, arch)
            mat.shade_color = arch.skin_shade
        elif "body_00_skin" in nlow:
            mat.texture_rgba = _paint_victoria_body_base_texture(mat.texture_rgba, arch)
            mat.shade_color = arch.skin_shade
        elif "eyeiris" in nlow:
            mat.texture_rgba = _recolor_iris_texture(mat.texture_rgba, arch.eye_rgb)
        elif "faceeyeline" in nlow or "faceeyelash" in nlow:
            mat.texture_rgba = _bold_comic_strokes(mat.texture_rgba, (24, 10, 14), thicken=7)
        elif "facebrow" in nlow:
            mat.texture_rgba = _bold_comic_strokes(mat.texture_rgba, arch.brow_rgb, thicken=7)
        elif mat.role == "hair" and not mat.name.startswith("Grafted_"):
            mat.texture_rgba = _recolor_hair_texture(mat.texture_rgba, arch.hair_rgb)
            mat.shade_color = arch.hair_shade

    # 4. Escultura anatômica contínua sem costuras no corpo studio
    _sculpt_body_vertices(model, arch)

    # 5. Orelhas élficas longas em 3D (para Elfa Loira!)
    if arch.elf_ears and model.skins:
        target_skin_idx, head_joint_in_skin, head_bind_pos = _find_head_skin(model)
        if target_skin_idx >= 0:
            ear_mat_idx = len(model.materials)
            model.materials.append(
                VrmMaterial(
                    index=ear_mat_idx,
                    name="ToS_ElfEars_SKIN",
                    role="skin",
                    base_color=(1.0, 1.0, 1.0, 1.0),
                    shade_color=arch.skin_shade,
                    texture_rgba=_make_elf_ear_texture(arch),
                )
            )
            ear_prim = _build_elf_ears_primitive(
                head_joint_in_skin=head_joint_in_skin,
                head_pos=head_bind_pos,
                is_vrm1=model.is_vrm1,
                skin_index=target_skin_idx,
                material_index=ear_mat_idx,
                mesh_index=max((p.mesh_index for p in model.primitives), default=0) + 1,
            )
            model.primitives.append(ear_prim)

    # 6. Proporções estilizadas Tree of Savior (~4.3 cabeças) e suavização do morph 'happy' p/ manter olhos grandes abertos!
    if "happy" in model.expressions:
        model.expressions["happy"] = [(mi, mo, bw * 0.62) for (mi, mo, bw) in model.expressions["happy"]]
    _apply_tos_proportions(model, arch)
    return model
