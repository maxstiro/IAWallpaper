"""VRM RENDERER — Renderizador 3D Comic/Illustration HD (Rapscallion × Dungeon Squad × Tree of Savior) via ModernGL.

Pipeline GPU de 2 passos em alta definição supersampled (`960×1200` MRT -> pós-processamento Sobel Ink -> `640×800`):
1. **Passo 1 (Geometria 3D -> MRT `960×1200`)**:
   - Attachment 0 (`RGBA8`): Cel-shading gráfico nítido de 2.5 bandas estilo ilustração 2D (transição de sombra
     marcada e quente *subsurface* na pele, brilho especular recortado tipo pintura *Rapscallion/ToS*, faixa
     *angel-ring* no cabelo e rim-light sincronizado ao ciclo dia/noite).
   - Attachment 1 (`RGBA16F`): `(view_normal.x, view_normal.y, view_depth, flags)` para detecção exata de
     linhas de tinta na tela.
2. **Passo 2 (Shader Fullscreen de Traço Nanquim 2D — Comic Ink Lineart)**:
   - Calcula bordas Sobel em **Alpha** (contorno externo espesso e expressivo), **Profundidade** (linhas
     nítidas separando mechas de cabelo, queixo, busto, braços, quadris e coxas) e **Normais** (dobras
     anatômicas e de roupa, suavizadas no interior do rosto para manter olhos e expressão 100% cristalinos!).
   - Redução suave para `640×800` gerando traço limpo anti-serrilhado idêntico a ilustração 2D pintada à mão!

Também mantém modo opcional Retro Pixel-Art (`pixel_art=True`).
"""

from dataclasses import dataclass
import math

import moderngl
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from ..core.emotion import EmotionState
from ..core.persona import Persona
from ..mathutil import clamp
from .atmosphere import AtmospherePalette
from .vrm_animator import VrmAnimator
from .vrm_loader import VrmModel, VrmPrimitive

_VERTEX_SHADER = """
#version 330 core
in vec3 in_pos;
in vec3 in_norm;
in vec2 in_uv;
in vec4 in_joints;
in vec4 in_weights;

uniform mat4 u_mvp;
uniform mat4 u_model;
uniform mat4 u_view;
uniform sampler2D u_bone_tex;
uniform int u_has_skin;
uniform float u_outline_extrude;
uniform int u_hair_flow;
uniform float u_head_y;
uniform vec3 u_hair_sway;
uniform float u_hair_flare;
uniform float u_anim_time;

out vec3 v_world_pos;
out vec3 v_world_norm;
out vec3 v_view_norm;
out vec2 v_uv;
out float v_view_depth;

mat4 fetchBone(int idx) {
    return mat4(
        texelFetch(u_bone_tex, ivec2(0, idx), 0),
        texelFetch(u_bone_tex, ivec2(1, idx), 0),
        texelFetch(u_bone_tex, ivec2(2, idx), 0),
        texelFetch(u_bone_tex, ivec2(3, idx), 0)
    );
}

void main() {
    mat4 skin_m = mat4(1.0);
    if (u_has_skin == 1) {
        skin_m =
            fetchBone(int(in_joints.x + 0.5)) * in_weights.x +
            fetchBone(int(in_joints.y + 0.5)) * in_weights.y +
            fetchBone(int(in_joints.z + 0.5)) * in_weights.z +
            fetchBone(int(in_joints.w + 0.5)) * in_weights.w;
    }
    vec4 local_p = skin_m * vec4(in_pos, 1.0);
    vec3 local_n = normalize(mat3(skin_m) * in_norm);

    // Física secundária fluida em tempo real nos fios longos do cabelo (rastro ao andar, brisa e abertura no giro!)
    if (u_hair_flow == 1) {
        float drop = clamp((u_head_y - local_p.y) / 0.52, 0.0, 1.0);
        float flex = drop * drop;
        float wave = sin(u_anim_time * 3.4 - drop * 4.5 + local_p.x * 7.5);
        float wave2 = cos(u_anim_time * 2.3 - drop * 3.2 + local_p.z * 6.5);
        vec2 rad = local_p.xz;
        float rlen = max(length(rad), 0.001);
        vec2 rdir = rad / rlen;
        local_p.x += (u_hair_sway.x + wave * 0.025 + rdir.x * u_hair_flare) * flex;
        local_p.z += (u_hair_sway.z + wave2 * 0.018 + rdir.y * u_hair_flare) * flex;
        local_p.y += (u_hair_sway.y + abs(u_hair_flare) * 0.25) * flex;
    }

    if (u_outline_extrude > 0.0) {
        local_p.xyz += local_n * u_outline_extrude;
    }
    vec4 world_p = u_model * local_p;
    vec4 view_p = u_view * world_p;
    vec3 w_norm = normalize(mat3(u_model) * local_n);
    v_world_pos = world_p.xyz;
    v_world_norm = w_norm;
    v_view_norm = normalize(mat3(u_view) * w_norm);
    v_uv = in_uv;
    v_view_depth = -view_p.z;
    gl_Position = u_mvp * local_p;
}
"""

_FRAGMENT_SHADER = """
#version 330 core
in vec3 v_world_pos;
in vec3 v_world_norm;
in vec3 v_view_norm;
in vec2 v_uv;
in float v_view_depth;

uniform sampler2D u_albedo;
uniform int u_has_tex;
uniform vec4 u_base_color;
uniform vec3 u_shade_color;
uniform vec3 u_role_tint;
uniform int u_alpha_mode;     // 0=OPAQUE, 1=MASK, 2=BLEND
uniform float u_alpha_cutoff;
uniform int u_is_outline;
uniform vec3 u_outline_color;

uniform vec3 u_light_dir;
uniform vec3 u_light_color;
uniform vec3 u_ambient_color;
uniform vec3 u_rim_color;
uniform float u_rim_strength;
uniform vec3 u_cam_pos;
uniform int u_is_face;
uniform int u_is_skin;
uniform int u_is_eye;
uniform int u_is_hair;
uniform int u_is_emissive;
uniform int u_is_gold;
uniform int u_pixel_art;
uniform float u_mat_group;

layout(location = 0) out vec4 f_color;
layout(location = 1) out vec4 f_meta;

void main() {
    vec4 tex = (u_has_tex == 1) ? texture(u_albedo, v_uv) : vec4(1.0);
    float alpha = tex.a * u_base_color.a;
    if (u_alpha_mode == 1 && alpha < u_alpha_cutoff) {
        discard;
    }
    if (u_is_outline == 1) {
        f_color = vec4(u_outline_color, 1.0);
        f_meta = vec4(0.0, 0.0, v_view_depth, 0.0);
        return;
    }

    vec3 albedo = tex.rgb * u_base_color.rgb * u_role_tint;
    if (u_is_emissive == 1) {
        vec3 glow_col = clamp(albedo * 1.18 + vec3(0.08), 0.0, 1.0);
        f_color = vec4(glow_col, (u_alpha_mode == 0) ? 1.0 : alpha);
        f_meta = vec4(0.0, 0.0, v_view_depth, 2.0);
        return;
    }

    vec3 N = normalize(v_world_norm);
    vec3 VN = normalize(v_view_norm);
    if (!gl_FrontFacing) {
        N = -N;
        VN = -VN;
    }
    vec3 L = normalize(u_light_dir);
    vec3 V = normalize(u_cam_pos - v_world_pos);
    vec3 H = normalize(L + V);

    float ndotl = dot(N, L);
    vec3 col;

    if (u_pixel_art == 1) {
        float band = (u_is_face == 1)
            ? ((ndotl > -0.18) ? 1.0 : 0.68)
            : ((ndotl > 0.24) ? 1.0 : ((ndotl > -0.10) ? 0.56 : 0.14));
        vec3 deep_shade = mix(u_shade_color, vec3(0.42, 0.34, 0.56), 0.45);
        vec3 lit_c = albedo * (u_light_color * 0.96 + u_ambient_color * 0.14);
        vec3 mid_c = albedo * mix(deep_shade, vec3(1.0), 0.45) * (u_ambient_color * 0.72 + vec3(0.24));
        vec3 shd_c = albedo * deep_shade * (u_ambient_color * 0.56 + vec3(0.16));
        col = (band >= 0.85) ? lit_c : ((band >= 0.35) ? mid_c : shd_c);
        float fr = pow(1.0 - max(dot(N, V), 0.0), 2.8);
        col += u_rim_color * ((fr > 0.48 && u_is_face == 0) ? 1.0 : 0.0) * u_rim_strength * 0.42;
    } else {
        // ── Shader Aquarela / Guache 2D estilo Tree of Savior (ZERO plástico especular 3D!) ──
        // Segredo do ToS: iluminação plana de ilustração (quase 2D!), sombras quentes pastel aquareladas,
        // ZERO brilho plástico Phong na pele, textura sutil de papel/pincel e luz de borda delicada!
        float paper = fract(sin(dot(floor(gl_FragCoord.xy * 0.5), vec2(12.9898, 78.233))) * 43758.5453);
        float grain = (paper - 0.5) * 0.022;

        if (u_is_face == 1) {
            // Rosto 92% plano estilo ilustração 2D ToS (elimina manchas/sombras 3D feias no nariz e bochechas!)
            float f_band = smoothstep(-0.36, 0.10, ndotl);
            vec3 face_shd = albedo * mix(u_shade_color, vec3(0.92, 0.78, 0.76), 0.65);
            vec3 face_lit = albedo * mix(vec3(1.0), u_light_color, 0.35);
            col = mix(face_shd, face_lit, 0.76 + 0.24 * f_band) + grain * 0.4;
        } else if (u_is_skin == 1) {
            // Pele aveludada fosca estilo aquarela Tree of Savior (ZERO brilho plástico branco 3D!)
            float band = smoothstep(-0.18, 0.16, ndotl);
            float warm_term = exp(-pow((ndotl + 0.03) / 0.16, 2.0));
            vec3 sk_lit = albedo * mix(vec3(1.04), u_light_color * 1.02, 0.34);
            vec3 sk_shd = albedo * mix(u_shade_color, vec3(0.86, 0.62, 0.58), 0.56) * mix(vec3(0.88), u_ambient_color, 0.38);
            col = mix(sk_shd, sk_lit, 0.12 + 0.88 * band);
            // Leve calor pêssego-aquarela na borda da sombra
            col += vec3(0.075, 0.022, 0.014) * warm_term * albedo;
            // Gradiente suave de pintura aquarela vindo do céu (técnica clássica 2D ToS!)
            col *= (0.93 + 0.09 * clamp(N.y * 0.5 + 0.5, 0.0, 1.0));
            // Luz de recorte suave apenas na silhueta externa
            float fr_s = smoothstep(0.70, 0.86, 1.0 - max(dot(N, V), 0.0));
            col += u_rim_color * fr_s * u_rim_strength * 0.18 + grain;
        } else if (u_is_hair == 1) {
            // Cabelo guache/aquarela estilo ToS: 2 bandas macias + faixa de brilho pintada delicada (não metálica!)
            float h_band = smoothstep(-0.12, 0.10, ndotl);
            vec3 h_lit = albedo * mix(vec3(1.0), u_light_color, 0.35);
            vec3 h_shd = albedo * mix(u_shade_color, vec3(0.76, 0.60, 0.42), 0.35) * mix(vec3(0.82), u_ambient_color, 0.40);
            col = mix(h_shd, h_lit, h_band);
            // Faixa de brilho suave horizontal (angel-ring aquarelado)
            vec3 H_aniso = normalize(vec3(H.x * 0.45, H.y * 1.60, H.z));
            float gloss = smoothstep(0.76, 0.88, pow(max(dot(N, H_aniso), 0.0), 14.0));
            col += vec3(0.18, 0.16, 0.10) * gloss;
            float fr_h = smoothstep(0.66, 0.82, 1.0 - max(dot(N, V), 0.0));
            col += u_rim_color * fr_h * u_rim_strength * 0.24 + grain;
        } else {
            // Tecidos e lingerie foscos estilo ilustração 2D (sem brilho plástico!)
            float c_band = smoothstep(-0.10, 0.10, ndotl);
            vec3 c_lit = albedo * mix(vec3(1.0), u_light_color, 0.38);
            vec3 c_shd = albedo * mix(u_shade_color, vec3(0.68, 0.58, 0.66), 0.45) * mix(vec3(0.80), u_ambient_color, 0.40);
            col = mix(c_shd, c_lit, c_band);
            if (u_is_gold == 1) {
                float sp = smoothstep(0.60, 0.74, pow(max(dot(N, H), 0.0), 16.0));
                col += vec3(0.32, 0.28, 0.18) * sp;
            }
            float fr_c = smoothstep(0.68, 0.84, 1.0 - max(dot(N, V), 0.0));
            col += u_rim_color * fr_c * u_rim_strength * 0.22 + grain;
        }
    }

    if (u_is_eye == 1) {
        col = mix(col, albedo * 1.24 + u_rim_color * 0.08, 0.62);
    }

    col = clamp(col, 0.0, 1.0);
    f_color = vec4(col, (u_alpha_mode == 0) ? 1.0 : alpha);
    // flags: 0=corpo/roupa/cabelo (traço cheio), 1=rosto/olhos (traço suave interno, contorno externo normal!), 2=emissivo
    float flag = (u_is_face == 1 || u_is_eye == 1) ? 1.0 : 0.0;
    f_meta = vec4(VN.x, VN.y, v_view_depth, flag);
}
"""

_POST_VS = """
#version 330 core
in vec2 in_pos;
void main() {
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

_COMIC_INK_FS = """
#version 330 core
uniform sampler2D u_color_tex;
uniform sampler2D u_meta_tex;
uniform vec3 u_ink_color;
uniform float u_outer_radius;   // raio em px do contorno externo (ex: 2.2 em 960x1200)

out vec4 f_out;

void main() {
    ivec2 p = ivec2(gl_FragCoord.xy);
    ivec2 sz = textureSize(u_color_tex, 0);
    vec4 c = texelFetch(u_color_tex, p, 0);
    vec4 m = texelFetch(u_meta_tex, p, 0);

    // 1. Contorno externo expressivo tipo nanquim HQ (Rapscallion / Dungeon Squad!)
    if (c.a < 0.45) {
        float best = 0.0;
        float glow = 0.0;
        vec3 em_col = vec3(0.0);
        int rad = int(ceil(u_outer_radius));
        for (int dy = -rad; dy <= rad; dy++) {
            for (int dx = -rad; dx <= rad; dx++) {
                float d = length(vec2(float(dx), float(dy)));
                if (d > u_outer_radius + 0.15) continue;
                ivec2 q = clamp(p + ivec2(dx, dy), ivec2(0), sz - ivec2(1));
                vec4 nc = texelFetch(u_color_tex, q, 0);
                if (nc.a >= 0.45) {
                    vec4 nm = texelFetch(u_meta_tex, q, 0);
                    float w = smoothstep(u_outer_radius + 0.15, max(0.0, u_outer_radius - 0.85), d);
                    if (nm.a > 1.5) {
                        glow = max(glow, w * 0.45);
                        em_col = max(em_col, nc.rgb);
                    } else {
                        best = max(best, w);
                    }
                }
            }
        }
        if (best > 0.02) {
            f_out = vec4(u_ink_color, best);
            return;
        }
        if (glow > 0.02) {
            f_out = vec4(em_col, glow);
            return;
        }
        f_out = vec4(0.0);
        return;
    }

    // Elementos emissivos preservam brilho puro
    if (m.a > 1.5) {
        f_out = c;
        return;
    }

    // 2. Linhas internas de nanquim via Sobel em Profundidade + Normais (queixo, busto, coxas, braços, mechas, orelhas!)
    bool is_face = (m.a > 0.5 && m.a < 1.5);
    float d_center = m.z;
    vec2 n_center = m.xy;

    // Amostra vizinhos a 1px e 2px para traço encorpado e suave no supersampling 960x1200!
    ivec2 offs4[4] = ivec2[4](ivec2(1, 0), ivec2(-1, 0), ivec2(0, 1), ivec2(0, -1));
    ivec2 offs8[4] = ivec2[4](ivec2(2, 0), ivec2(-2, 0), ivec2(0, 2), ivec2(0, -2));

    float depth_edge = 0.0;
    float norm_edge = 0.0;
    float sil_inner = 0.0;

    for (int i = 0; i < 4; i++) {
        ivec2 q1 = clamp(p + offs4[i], ivec2(0), sz - ivec2(1));
        vec4 c1 = texelFetch(u_color_tex, q1, 0);
        vec4 m1 = texelFetch(u_meta_tex, q1, 0);
        if (c1.a < 0.45) {
            sil_inner = max(sil_inner, 0.85);
            continue;
        }
        if (m1.a > 1.5) continue;

        // Salto de profundidade (somente no lado mais distante -> linha limpa sem engrossar demais!)
        float dd1 = d_center - m1.z;
        if (dd1 > 0.028) {
            depth_edge = max(depth_edge, smoothstep(0.028, 0.072, dd1));
        }
        // Dobras de superfície (somente dobras realmente nítidas — mantém pele limpa estilo aquarela 2D ToS!)
        if (!is_face) {
            float dn = length(n_center - m1.xy);
            if (dn > 0.46) {
                norm_edge = max(norm_edge, smoothstep(0.46, 0.86, dn) * 0.58);
            }
        }

        // Segunda coroa (2px) para dar peso de nanquim nos saltos grandes (cabelo sobre rosto, braço sobre tronco!)
        ivec2 q2 = clamp(p + offs8[i], ivec2(0), sz - ivec2(1));
        vec4 c2 = texelFetch(u_color_tex, q2, 0);
        vec4 m2 = texelFetch(u_meta_tex, q2, 0);
        if (c2.a >= 0.45 && m2.a < 1.5) {
            float dd2 = d_center - m2.z;
            if (dd2 > 0.055) {
                depth_edge = max(depth_edge, smoothstep(0.055, 0.11, dd2) * (is_face ? 0.45 : 0.75));
            }
        }
    }

    // No interior do rosto, atenua linhas internas de profundidade para nunca sujar olhos/bochechas,
    // mas mantém 100% o contorno nítido do queixo e mechas!
    float ink = max(sil_inner * 0.65, max(depth_edge * (is_face ? 0.55 : 0.92), norm_edge));
    // Tinta quente rica (mistura o próprio tom escurecido com café-ameixa para traço orgânico Rapscallion!)
    vec3 colored_ink = mix(u_ink_color, c.rgb * 0.22, 0.35);
    vec3 final_rgb = mix(c.rgb, colored_ink, clamp(ink, 0.0, 0.94));
    f_out = vec4(clamp(final_rgb, 0.0, 1.0), c.a);
}
"""

_POST_PIXEL_FS = """
#version 330 core
uniform sampler2D u_color_tex;
uniform sampler2D u_meta_tex;
uniform vec3 u_ink_color;

out vec4 f_out;

void main() {
    ivec2 p = ivec2(gl_FragCoord.xy);
    ivec2 sz = textureSize(u_color_tex, 0);
    vec4 c = texelFetch(u_color_tex, p, 0);
    vec4 m = texelFetch(u_meta_tex, p, 0);
    ivec2 offs[4] = ivec2[4](ivec2(1, 0), ivec2(-1, 0), ivec2(0, 1), ivec2(0, -1));

    if (c.a < 0.5) {
        bool has_solid = false;
        for (int i = 0; i < 4; i++) {
            ivec2 q = clamp(p + offs[i], ivec2(0), sz - ivec2(1));
            if (texelFetch(u_color_tex, q, 0).a >= 0.5) has_solid = true;
        }
        f_out = has_solid ? vec4(u_ink_color, 1.0) : vec4(0.0);
        return;
    }
    float edge = 0.0;
    for (int i = 0; i < 4; i++) {
        ivec2 q = clamp(p + offs[i], ivec2(0), sz - ivec2(1));
        vec4 nm = texelFetch(u_meta_tex, q, 0);
        if (m.z - nm.z > 0.06) edge = max(edge, 0.62);
    }
    vec3 col = floor(mix(c.rgb, u_ink_color, edge) * 18.0 + 0.5) / 18.0;
    f_out = vec4(clamp(col, 0.0, 1.0), c.a);
}
"""


def _perspective(fov_y_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fov_y_deg) * 0.5)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / max(aspect, 1e-4)
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = (2.0 * far * near) / (near - far)
    m[3, 2] = -1.0
    return m


def _look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    z = eye - target
    z = z / max(float(np.linalg.norm(z)), 1e-6)
    x = np.cross(up, z)
    x = x / max(float(np.linalg.norm(x)), 1e-6)
    y = np.cross(z, x)
    m = np.eye(4, dtype=np.float32)
    m[0, :3] = x
    m[1, :3] = y
    m[2, :3] = z
    m[0, 3] = -float(np.dot(x, eye))
    m[1, 3] = -float(np.dot(y, eye))
    m[2, 3] = -float(np.dot(z, eye))
    return m


@dataclass
class _GpuPrimitive:
    prim: VrmPrimitive
    vao: moderngl.VertexArray
    pos_vbo: moderngl.Buffer
    static_vbo: moderngl.Buffer
    ibo: moderngl.Buffer
    has_morphs: bool


_ROLE_GROUP_ID: dict[str, float] = {
    "face": 0.0,
    "eye": 0.0,
    "hair": 1.0,
    "skin": 2.0,
    "tops": 3.0,
    "bottoms": 4.0,
    "shoes": 4.0,
    "cape": 5.0,
    "gold": 6.0,
    "emissive": 7.0,
    "other": 3.0,
}


def compute_role_tints(persona: Persona, outfit_key: str, dynamic_recolor: bool = True) -> dict[str, tuple[float, float, float]]:
    base = {
        "hair": (1.0, 1.0, 1.0),
        "eye": (1.0, 1.0, 1.0),
        "tops": (1.0, 1.0, 1.0),
        "bottoms": (1.0, 1.0, 1.0),
        "shoes": (1.0, 1.0, 1.0),
        "skin": (1.0, 1.0, 1.0),
        "face": (1.0, 1.0, 1.0),
        "cape": (1.0, 1.0, 1.0),
        "gold": (1.0, 1.0, 1.0),
        "emissive": (1.0, 1.0, 1.0),
        "other": (1.0, 1.0, 1.0),
    }
    if not dynamic_recolor:
        return base

    def _blend_white(rgb: tuple[int, int, int], strength: float) -> tuple[float, float, float]:
        r, g, b = rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0
        lum = max(0.35, 0.299 * r + 0.587 * g + 0.114 * b)
        nr, ng, nb = min(1.18, r / lum * 0.88), min(1.18, g / lum * 0.88), min(1.18, b / lum * 0.88)
        return (
            1.0 + (nr - 1.0) * strength,
            1.0 + (ng - 1.0) * strength,
            1.0 + (nb - 1.0) * strength,
        )

    outfit = persona.outfits.get(outfit_key) or persona.outfits.get("casual") or {}
    prim = outfit.get("primary")
    trim = outfit.get("trim")
    base["hair"] = _blend_white(persona.hair_color, 0.35)
    base["eye"] = _blend_white(persona.eye_color, 0.45)
    if prim:
        base["tops"] = _blend_white(tuple(prim), 0.55)
    if trim:
        base["bottoms"] = _blend_white(tuple(trim), 0.42)
    return base


class VrmRenderer:
    """Renderizador 3D Comic/Illustration HD (960×1200 MRT + Sobel Nanquim -> 640×800) & modo Pixel-Art opcional."""

    def __init__(
        self,
        model: VrmModel,
        width: int = 640,
        height: int = 800,
        samples: int = 4,
        pixel_art: bool = False,
        pixel_size: tuple[int, int] = (152, 190),
        supersample: float = 1.5,
    ):
        self.model = model
        self.width = int(width)
        self.height = int(height)
        self.ss_w = int(round(self.width * supersample))
        self.ss_h = int(round(self.height * supersample))
        self.pixel_art = bool(pixel_art)
        self.pixel_w, self.pixel_h = int(pixel_size[0]), int(pixel_size[1])
        self.last_foot_v: float = 0.88

        self.ctx = moderngl.create_standalone_context()
        self.ctx.enable(moderngl.DEPTH_TEST | moderngl.BLEND)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA, moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA)

        # Framebuffers Comic HD Supersampled MRT (960×1200 -> Sobel Ink -> downsample suave p/ 640×800!)
        self._hd_color_tex = self.ctx.texture((self.ss_w, self.ss_h), 4)
        self._hd_color_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self._hd_meta_tex = self.ctx.texture((self.ss_w, self.ss_h), 4, dtype="f2")
        self._hd_meta_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self._hd_depth = self.ctx.depth_renderbuffer((self.ss_w, self.ss_h))
        self._fbo_hd_geom = self.ctx.framebuffer(
            color_attachments=[self._hd_color_tex, self._hd_meta_tex],
            depth_attachment=self._hd_depth,
        )
        self._fbo_hd_out = self.ctx.simple_framebuffer((self.ss_w, self.ss_h), components=4)

        # Framebuffers opcionais do modo Retro Pixel-Art 3D
        self._pa_color_tex = self.ctx.texture((self.pixel_w, self.pixel_h), 4)
        self._pa_color_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self._pa_meta_tex = self.ctx.texture((self.pixel_w, self.pixel_h), 4, dtype="f2")
        self._pa_meta_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self._pa_depth = self.ctx.depth_renderbuffer((self.pixel_w, self.pixel_h))
        self._fbo_pa_geom = self.ctx.framebuffer(
            color_attachments=[self._pa_color_tex, self._pa_meta_tex],
            depth_attachment=self._pa_depth,
        )
        self._fbo_pa_out = self.ctx.simple_framebuffer((self.pixel_w, self.pixel_h), components=4)

        self.prog = self.ctx.program(vertex_shader=_VERTEX_SHADER, fragment_shader=_FRAGMENT_SHADER)
        self.prog["u_albedo"].value = 0
        self.prog["u_bone_tex"].value = 1

        self._comic_prog = self.ctx.program(vertex_shader=_POST_VS, fragment_shader=_COMIC_INK_FS)
        self._comic_prog["u_color_tex"].value = 0
        self._comic_prog["u_meta_tex"].value = 1

        self._pixel_prog = self.ctx.program(vertex_shader=_POST_VS, fragment_shader=_POST_PIXEL_FS)
        self._pixel_prog["u_color_tex"].value = 0
        self._pixel_prog["u_meta_tex"].value = 1

        quad = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0], dtype=np.float32)
        self._quad_vbo = self.ctx.buffer(quad.tobytes())
        self._quad_comic_vao = self.ctx.vertex_array(self._comic_prog, [(self._quad_vbo, "2f", "in_pos")])
        self._quad_pixel_vao = self.ctx.vertex_array(self._pixel_prog, [(self._quad_vbo, "2f", "in_pos")])

        self._white_tex = self.ctx.texture((1, 1), 4, bytes([255, 255, 255, 255]))
        self._mat_textures: list[moderngl.Texture] = []
        for mat in model.materials:
            if mat.texture_rgba is not None:
                arr = np.ascontiguousarray(mat.texture_rgba, dtype=np.uint8)
                h, w, _ = arr.shape
                tex = self.ctx.texture((w, h), 4, arr.tobytes())
                tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
                tex.build_mipmaps()
                self._mat_textures.append(tex)
            else:
                self._mat_textures.append(self._white_tex)

        self._skin_textures: list[moderngl.Texture] = []
        for sk in model.skins:
            n_j = max(1, len(sk.joints))
            ident = np.repeat(np.eye(4, dtype=np.float32)[None, :, :], n_j, axis=0)
            btex = self.ctx.texture((4, n_j), 4, ident.tobytes(), dtype="f4")
            btex.filter = (moderngl.NEAREST, moderngl.NEAREST)
            self._skin_textures.append(btex)
        self._dummy_bone_tex = self.ctx.texture((4, 1), 4, np.eye(4, dtype=np.float32).tobytes(), dtype="f4")
        self._dummy_bone_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)

        self._gpu_prims: list[_GpuPrimitive] = []
        for prim in model.primitives:
            pos_vbo = self.ctx.buffer(np.ascontiguousarray(prim.positions, dtype=np.float32).tobytes(), dynamic=bool(prim.morph_deltas))
            static_interleaved = np.hstack([prim.normals, prim.uvs, prim.joints, prim.weights]).astype(np.float32)
            static_vbo = self.ctx.buffer(np.ascontiguousarray(static_interleaved).tobytes())
            ibo = self.ctx.buffer(np.ascontiguousarray(prim.indices, dtype=np.uint32).tobytes())
            vao = self.ctx.vertex_array(
                self.prog,
                [
                    (pos_vbo, "3f", "in_pos"),
                    (static_vbo, "3f 2f 4f 4f", "in_norm", "in_uv", "in_joints", "in_weights"),
                ],
                index_buffer=ibo,
            )
            self._gpu_prims.append(
                _GpuPrimitive(prim=prim, vao=vao, pos_vbo=pos_vbo, static_vbo=static_vbo, ibo=ibo, has_morphs=bool(prim.morph_deltas))
            )

        order_map = {"OPAQUE": 0, "MASK": 1, "BLEND": 2}
        self._sorted_prims = sorted(
            self._gpu_prims,
            key=lambda gp: order_map.get(
                model.materials[gp.prim.material_index].alpha_mode if 0 <= gp.prim.material_index < len(model.materials) else "OPAQUE",
                0,
            ),
        )

    def _upload_bones_and_morphs(self, animator: VrmAnimator) -> None:
        for s_idx, jm in enumerate(animator.skin_matrices):
            if s_idx < len(self._skin_textures):
                col_major = np.ascontiguousarray(np.transpose(jm, (0, 2, 1)), dtype=np.float32)
                self._skin_textures[s_idx].write(col_major.tobytes())

        for gp in self._gpu_prims:
            if not gp.has_morphs:
                continue
            weights = animator.mesh_morph_weights.get(gp.prim.mesh_index)
            if not weights:
                gp.pos_vbo.write(np.ascontiguousarray(gp.prim.positions, dtype=np.float32).tobytes())
                continue
            pos = gp.prim.positions.copy()
            for m_idx, w in weights.items():
                if w > 0.005 and 0 <= m_idx < len(gp.prim.morph_deltas):
                    pos += gp.prim.morph_deltas[m_idx] * float(w)
            gp.pos_vbo.write(np.ascontiguousarray(pos, dtype=np.float32).tobytes())

    def render_pixmap(
        self,
        animator: VrmAnimator,
        atmosphere: AtmospherePalette,
        persona: Persona,
        outfit_key: str = "casual",
        sun_x_norm: float = 0.5,
        dynamic_recolor: bool = True,
        camera_focus: str = "full",
    ) -> QPixmap:
        """Renderiza o frame atual com traço nanquim Comic HD (`960×1200` -> `640×800`) ou Pixel-Art opcional."""
        self._upload_bones_and_morphs(animator)

        is_builtin = self.model.name.startswith(("DungeonSquad_", "ToS_"))
        h = self.model.height
        min_y = self.model.min_y

        if camera_focus == "portrait":
            target_y = min_y + h * 0.77
            eye = np.array([0.0, target_y + h * 0.015, h * 1.68], dtype=np.float32)
            target = np.array([0.0, target_y, 0.0], dtype=np.float32)
        else:
            # Câmera teleobjetiva quase ortográfica estilo Tree of Savior (FOV 15.5° — elimina distorção 3D!)
            center_y = min_y + h * 0.50
            dist = h * 4.45
            eye = np.array([0.0, center_y + h * 0.36, dist], dtype=np.float32)
            target = np.array([0.0, center_y - h * 0.01, 0.0], dtype=np.float32)

        rt_w = self.pixel_w if self.pixel_art else self.ss_w
        rt_h = self.pixel_h if self.pixel_art else self.ss_h
        proj = _perspective(15.5, rt_w / max(float(rt_h), 1.0), 0.2, 30.0)
        view = _look_at(eye, target, np.array([0.0, 1.0, 0.0], dtype=np.float32))
        model_m = np.eye(4, dtype=np.float32)
        mvp = proj @ view @ model_m

        foot_clip = mvp @ np.array([0.0, min_y, 0.0, 1.0], dtype=np.float32)
        foot_ndc_y = float(foot_clip[1] / max(float(foot_clip[3]), 1e-5))
        self.last_foot_v = clamp(0.5 * (1.0 - foot_ndc_y), 0.65, 0.99)

        self.prog["u_mvp"].write(np.ascontiguousarray(mvp.T, dtype=np.float32).tobytes())
        self.prog["u_model"].write(np.ascontiguousarray(model_m.T, dtype=np.float32).tobytes())
        self.prog["u_view"].write(np.ascontiguousarray(view.T, dtype=np.float32).tobytes())
        self.prog["u_cam_pos"].value = (float(eye[0]), float(eye[1]), float(eye[2]))

        # Parâmetros de física fluida de cabelo no vertex shader (inércia de passo, brisa, bounce e abertura no giro!)
        head_ni = self.model.humanoid_bones.get("head", -1)
        head_world_y = float(animator.world_matrices[head_ni][1, 3]) if 0 <= head_ni < len(animator.world_matrices) else (min_y + h * 0.82)
        self.prog["u_head_y"].value = head_world_y
        self.prog["u_anim_time"].value = float(animator.time)
        self.prog["u_hair_sway"].value = (
            float(animator.hair_trail_x),
            float(animator.hair_bounce_y),
            float(animator.hair_trail_z),
        )
        self.prog["u_hair_flare"].value = float(animator.hair_flare)
        self.prog["u_hair_flow"].value = 0

        lx = (sun_x_norm - 0.5) * 1.1 + 0.42
        l_dir = np.array([lx, 0.72, 0.85], dtype=np.float32)
        l_dir /= max(float(np.linalg.norm(l_dir)), 1e-6)
        self.prog["u_light_dir"].value = (float(l_dir[0]), float(l_dir[1]), float(l_dir[2]))

        tr, tg, tb = atmosphere.avatar_tint
        ta = clamp(atmosphere.avatar_tint_alpha, 0.0, 0.65)
        light_col = (
            1.0 * (1.0 - ta * 0.28) + (tr / 255.0) * (ta * 0.36),
            1.0 * (1.0 - ta * 0.28) + (tg / 255.0) * (ta * 0.36),
            1.0 * (1.0 - ta * 0.28) + (tb / 255.0) * (ta * 0.36),
        )
        amb_col = (
            0.80 * (1.0 - ta * 0.36) + (tr / 255.0) * (ta * 0.46),
            0.78 * (1.0 - ta * 0.36) + (tg / 255.0) * (ta * 0.46),
            0.84 * (1.0 - ta * 0.36) + (tb / 255.0) * (ta * 0.46),
        )
        rr, rg, rb = atmosphere.rim_light
        self.prog["u_light_color"].value = light_col
        self.prog["u_ambient_color"].value = amb_col
        self.prog["u_rim_color"].value = (rr / 255.0, rg / 255.0, rb / 255.0)
        self.prog["u_rim_strength"].value = 0.52 + ta * 0.36
        self.prog["u_outline_color"].value = (0.11, 0.05, 0.07)
        self.prog["u_pixel_art"].value = 1 if self.pixel_art else 0

        role_tints = compute_role_tints(persona, outfit_key, dynamic_recolor=(dynamic_recolor and not is_builtin))

        if self.pixel_art:
            self._fbo_pa_geom.use()
        else:
            self._fbo_hd_geom.use()
        self.ctx.viewport = (0, 0, rt_w, rt_h)
        self.ctx.clear(0.0, 0.0, 0.0, 0.0, depth=1.0)

        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.front_face = "ccw"
        self.prog["u_is_outline"].value = 0
        self.prog["u_outline_extrude"].value = 0.0

        alpha_code = {"OPAQUE": 0, "MASK": 1, "BLEND": 2}
        for gp in self._sorted_prims:
            mi = gp.prim.material_index
            mat = self.model.materials[mi] if 0 <= mi < len(self.model.materials) else None
            self._bind_skin(gp.prim.skin_index)
            if mat is not None:
                tex = self._mat_textures[mi]
                tex.use(location=0)
                self.prog["u_has_tex"].value = 1 if mat.texture_rgba is not None else 0
                self.prog["u_base_color"].value = mat.base_color
                self.prog["u_shade_color"].value = mat.shade_color
                self.prog["u_role_tint"].value = role_tints.get(mat.role, (1.0, 1.0, 1.0))
                # Hair e camadas faciais usam alpha-test (MASK + depth_mask=True) para nunca vazar rosto atrás do cabelo!
                effective_alpha_mode = mat.alpha_mode
                effective_cutoff = mat.alpha_cutoff
                if mat.role in ("face", "eye", "hair", "other") and mat.alpha_mode == "BLEND":
                    effective_alpha_mode = "MASK"
                    effective_cutoff = 0.22 if mat.role == "hair" else 0.18
                self.prog["u_alpha_mode"].value = alpha_code.get(effective_alpha_mode, 0)
                self.prog["u_alpha_cutoff"].value = effective_cutoff
                self.prog["u_is_face"].value = 1 if mat.role == "face" else 0
                self.prog["u_is_skin"].value = 1 if mat.role == "skin" else 0
                self.prog["u_is_eye"].value = 1 if mat.role == "eye" else 0
                self.prog["u_is_hair"].value = 1 if mat.role == "hair" else 0
                self.prog["u_hair_flow"].value = 1 if (mat.role == "hair" and "hairback" not in mat.name.lower()) else 0
                self.prog["u_is_emissive"].value = 1 if mat.role == "emissive" else 0
                self.prog["u_is_gold"].value = 1 if mat.role == "gold" else 0
                if mat.double_sided:
                    self.ctx.disable(moderngl.CULL_FACE)
                else:
                    self.ctx.enable(moderngl.CULL_FACE)
                if effective_alpha_mode == "BLEND":
                    self.ctx.enable(moderngl.BLEND)
                    self.ctx.depth_mask = False
                else:
                    # Desativa GL_BLEND em OPAQUE/MASK para nunca corromper o attachment MRT `f_meta` (normais/profundidade)!
                    self.ctx.disable(moderngl.BLEND)
                    self.ctx.depth_mask = True
            else:
                self._white_tex.use(location=0)
                self.prog["u_has_tex"].value = 0
                self.prog["u_base_color"].value = (1.0, 1.0, 1.0, 1.0)
                self.prog["u_shade_color"].value = (0.82, 0.78, 0.86)
                self.prog["u_role_tint"].value = (1.0, 1.0, 1.0)
                self.prog["u_alpha_mode"].value = 0
                self.prog["u_is_face"].value = 0
                self.prog["u_is_skin"].value = 0
                self.prog["u_is_eye"].value = 0
                self.prog["u_is_hair"].value = 0
                self.prog["u_hair_flow"].value = 0
                self.prog["u_is_emissive"].value = 0
                self.prog["u_is_gold"].value = 0
                self.ctx.depth_mask = True

            gp.vao.render(moderngl.TRIANGLES)

        self.ctx.depth_mask = True
        self.ctx.disable(moderngl.CULL_FACE)

        # Passo 2: Pós-processamento de traço nanquim (Comic Ink HD em 960×1200 ou Pixel-Art 1px)
        self.ctx.disable(moderngl.DEPTH_TEST)
        self.ctx.disable(moderngl.BLEND)
        if self.pixel_art:
            self._fbo_pa_out.use()
            self.ctx.viewport = (0, 0, self.pixel_w, self.pixel_h)
            self.ctx.clear(0.0, 0.0, 0.0, 0.0)
            self._pa_color_tex.use(location=0)
            self._pa_meta_tex.use(location=1)
            self._pixel_prog["u_ink_color"].value = (0.07, 0.04, 0.11)
            self._quad_pixel_vao.render(moderngl.TRIANGLE_STRIP)
            self.ctx.enable(moderngl.DEPTH_TEST | moderngl.BLEND)

            raw = self._fbo_pa_out.read(components=4, alignment=1)
            arr = np.frombuffer(raw, dtype=np.uint8).reshape((self.pixel_h, self.pixel_w, 4))
            flipped = np.ascontiguousarray(arr[::-1, :, :])
            qimg = QImage(flipped.data, self.pixel_w, self.pixel_h, self.pixel_w * 4, QImage.Format_RGBA8888).copy()
            return QPixmap.fromImage(qimg)

        self._fbo_hd_out.use()
        self.ctx.viewport = (0, 0, self.ss_w, self.ss_h)
        self.ctx.clear(0.0, 0.0, 0.0, 0.0)
        self._hd_color_tex.use(location=0)
        self._hd_meta_tex.use(location=1)
        # Tinta sépia-café quente estilo aquarela Tree of Savior (muito mais orgânica e 2D que preto chapado!)
        self._comic_prog["u_ink_color"].value = (0.16, 0.08, 0.09)
        self._comic_prog["u_outer_radius"].value = 2.4 if camera_focus == "portrait" else 3.2
        self._quad_comic_vao.render(moderngl.TRIANGLE_STRIP)
        self.ctx.enable(moderngl.DEPTH_TEST | moderngl.BLEND)

        raw = self._fbo_hd_out.read(components=4, alignment=1)
        arr = np.frombuffer(raw, dtype=np.uint8).reshape((self.ss_h, self.ss_w, 4))
        flipped = np.ascontiguousarray(arr[::-1, :, :])
        qimg = QImage(flipped.data, self.ss_w, self.ss_h, self.ss_w * 4, QImage.Format_RGBA8888).copy()
        if (self.ss_w, self.ss_h) != (self.width, self.height):
            qimg = qimg.scaled(self.width, self.height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        return QPixmap.fromImage(qimg)

    def _bind_skin(self, skin_idx: int) -> None:
        if 0 <= skin_idx < len(self._skin_textures):
            self._skin_textures[skin_idx].use(location=1)
            self.prog["u_has_skin"].value = 1
        else:
            self._dummy_bone_tex.use(location=1)
            self.prog["u_has_skin"].value = 0

    def release(self) -> None:
        try:
            self.ctx.release()
        except Exception:
            pass
