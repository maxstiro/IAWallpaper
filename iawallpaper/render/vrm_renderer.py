"""VRM RENDERER — Renderizador 3D estilo Tree of Savior (HD MSAA 4x Painterly Cel-Shaded) & Modo Pixel-Art opcional.

Suporta dois perfis de renderização em GPU via ModernGL (OpenGL 3.3 Core Profile):
1. **Modo Tree of Savior HD (`pixel_art=False`, padrão a partir do Milestone 16)**:
   - Renderização nativa em alta definição (`640x800`, MSAA 4x) preservando cada detalhe do rosto
     (olhos em camadas, cílios, sobrancelhas, rubor, lábios, mechas de cabelo, rendas e corpete).
   - Shader cel-shaded pictórico estilo *Tree of Savior*:
     * Sombreamento quente *subsurface* na pele/rosto (tons pêssego/âmbar em vez de cinza/roxo frio) +
       brilho especular suave de pele viva.
     * Faixa de brilho especular anime em arco (*hair gloss halo*) nos cabelos.
     * Contorno fino *inverted-hull* em tinta café-escuro apenas no corpo/cabelo/roupas (mantendo o rosto
       limpo e legível em qualquer distância no desktop).
     * Rim-light Fresnel sincronizado ao ciclo circadiano (`AtmospherePalette`).
2. **Modo Retro Pixel-Art 3D (`pixel_art=True`, opcional)**:
   - Mantém o pipeline MRT `152x190` + contorno 1px + Nearest-Neighbor disponível caso desejado.
"""

from dataclasses import dataclass
import math

import moderngl
import numpy as np
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

out vec3 v_world_pos;
out vec3 v_world_norm;
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
    if (u_outline_extrude > 0.0) {
        local_p.xyz += local_n * u_outline_extrude;
    }
    vec4 world_p = u_model * local_p;
    vec4 view_p = u_view * world_p;
    v_world_pos = world_p.xyz;
    v_world_norm = normalize(mat3(u_model) * local_n);
    v_uv = in_uv;
    v_view_depth = -view_p.z;
    gl_Position = u_mvp * local_p;
}
"""

_FRAGMENT_SHADER = """
#version 330 core
in vec3 v_world_pos;
in vec3 v_world_norm;
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
        f_meta = vec4(v_view_depth, u_mat_group, 0.0, 0.0);
        return;
    }

    vec3 albedo = tex.rgb * u_base_color.rgb * u_role_tint;
    if (u_is_emissive == 1) {
        vec3 glow_col = clamp(albedo * 1.18 + vec3(0.08), 0.0, 1.0);
        f_color = vec4(glow_col, (u_alpha_mode == 0) ? 1.0 : alpha);
        f_meta = vec4(v_view_depth, u_mat_group, 1.0, 0.0);
        return;
    }

    vec3 N = normalize(v_world_norm);
    if (!gl_FrontFacing) {
        N = -N;
    }
    vec3 L = normalize(u_light_dir);
    vec3 V = normalize(u_cam_pos - v_world_pos);
    vec3 H = normalize(L + V);

    float ndotl = dot(N, L);
    vec3 col;

    if (u_pixel_art == 1) {
        float band;
        if (u_is_face == 1) {
            band = (ndotl > -0.18) ? 1.0 : 0.68;
        } else {
            band = (ndotl > 0.24) ? 1.0 : ((ndotl > -0.10) ? 0.56 : 0.14);
        }
        vec3 deep_shade = mix(u_shade_color, vec3(0.42, 0.34, 0.56), 0.45);
        vec3 lit_c = albedo * (u_light_color * 0.96 + u_ambient_color * 0.14);
        vec3 mid_c = albedo * mix(deep_shade, vec3(1.0), 0.45) * (u_ambient_color * 0.72 + vec3(0.24));
        vec3 shd_c = albedo * deep_shade * (u_ambient_color * 0.56 + vec3(0.16));
        col = (band >= 0.85) ? lit_c : ((band >= 0.35) ? mid_c : shd_c);
        if (u_is_face == 0) {
            float sp_pow = (u_is_gold == 1) ? 14.0 : ((u_is_hair == 1) ? 16.0 : 24.0);
            float sp_raw = pow(max(dot(N, H), 0.0), sp_pow);
            float sp_step = (sp_raw > ((u_is_gold == 1) ? 0.32 : 0.46)) ? 1.0 : 0.0;
            float sp_gain = (u_is_gold == 1) ? 0.42 : ((u_is_hair == 1) ? 0.28 : 0.16);
            col += mix(vec3(1.0), u_light_color, 0.35) * sp_step * sp_gain;
        }
        float fr = pow(1.0 - max(dot(N, V), 0.0), 2.8);
        float rim_step = (fr > 0.48 && u_is_face == 0) ? 1.0 : 0.0;
        col += u_rim_color * rim_step * u_rim_strength * 0.42;
    } else {
        // ── Shader Pictórico HD estilo Tree of Savior (ToS) ──
        if (u_is_face == 1) {
            // Iluminação facial frontal generosa e suave (preserva 100% da leitura de olhos, blush e sorriso!)
            float face_lit = smoothstep(-0.38, 0.24, ndotl) * 0.30 + 0.70;
            vec3 warm_face_shade = albedo * mix(u_shade_color, vec3(0.92, 0.74, 0.70), 0.55);
            vec3 lit_face = albedo * (u_light_color * 0.90 + u_ambient_color * 0.16);
            col = mix(warm_face_shade, lit_face, face_lit);
            // Leve fresnel rosado suave nas bochechas/orelhas
            float fr_f = pow(1.0 - max(dot(N, V), 0.0), 3.6);
            col += u_rim_color * fr_f * u_rim_strength * 0.18;
        } else if (u_is_skin == 1) {
            // Pele viva com banda subsurface quente (pêssego/coral na transição luz-sombra!) + brilho úmido suave
            float toon = smoothstep(-0.14, 0.18, ndotl);
            float sss_band = exp(-pow((ndotl - 0.02) / 0.16, 2.0));
            vec3 skin_lit = albedo * (u_light_color * 0.94 + u_ambient_color * 0.14);
            vec3 skin_shd = albedo * mix(u_shade_color, vec3(0.78, 0.54, 0.52), 0.55) * (u_ambient_color * 0.72 + vec3(0.24));
            col = mix(skin_shd, skin_lit, toon);
            col += vec3(0.14, 0.05, 0.03) * sss_band * albedo;
            // Brilho especular acetinado suave de pele (colo, busto, coxas — estilo Tree of Savior!)
            float spec_skin = smoothstep(0.58, 0.90, pow(max(dot(N, H), 0.0), 20.0));
            col += mix(vec3(1.0, 0.95, 0.88), u_light_color, 0.40) * spec_skin * 0.12;
            float fr_s = pow(1.0 - max(dot(N, V), 0.0), 3.0);
            col += u_rim_color * fr_s * u_rim_strength * 0.42;
        } else if (u_is_hair == 1) {
            // Cabelo anime estilo ToS com sombra saturada quente e anel de brilho especular (angel ring!)
            float toon_h = smoothstep(-0.16, 0.16, ndotl);
            float mid_h = smoothstep(-0.45, -0.05, ndotl);
            vec3 h_lit = albedo * (u_light_color * 0.96 + u_ambient_color * 0.14);
            vec3 h_mid = albedo * mix(u_shade_color, vec3(1.0), 0.45) * (u_ambient_color * 0.76 + vec3(0.20));
            vec3 h_shd = albedo * u_shade_color * (u_ambient_color * 0.62 + vec3(0.16));
            col = mix(mix(h_shd, h_mid, mid_h), h_lit, toon_h);
            // Anel especular alongado horizontalmente (assinatura de cabelo anime pintado à mão!)
            vec3 H_aniso = normalize(vec3(H.x * 0.55, H.y * 1.45, H.z));
            float gloss = smoothstep(0.60, 0.86, pow(max(dot(N, H_aniso), 0.0), 16.0));
            float gloss_sharp = smoothstep(0.82, 0.94, pow(max(dot(N, H_aniso), 0.0), 32.0));
            col += mix(vec3(1.0, 0.98, 0.92), u_light_color, 0.25) * (gloss * 0.20 + gloss_sharp * 0.24);
            float fr_h = pow(1.0 - max(dot(N, V), 0.0), 2.8);
            col += u_rim_color * fr_h * u_rim_strength * 0.55;
        } else {
            // Roupas, couro, renda e ornamentos dourados com 2.5 bandas ricas e brilho suave
            float toon_c = smoothstep(-0.10, 0.14, ndotl);
            float deep_c = smoothstep(-0.48, -0.10, ndotl);
            vec3 c_lit = albedo * (u_light_color * 0.94 + u_ambient_color * 0.14);
            vec3 c_mid = albedo * mix(u_shade_color, vec3(1.0), 0.35) * (u_ambient_color * 0.72 + vec3(0.22));
            vec3 c_shd = albedo * u_shade_color * (u_ambient_color * 0.56 + vec3(0.16));
            col = mix(mix(c_shd, c_mid, deep_c), c_lit, toon_c);
            float sp_pow = (u_is_gold == 1) ? 16.0 : 28.0;
            float sp = smoothstep(0.45, 0.78, pow(max(dot(N, H), 0.0), sp_pow));
            col += mix(vec3(1.0, 0.96, 0.85), u_light_color, 0.35) * sp * ((u_is_gold == 1) ? 0.44 : 0.14);
            float fr_c = pow(1.0 - max(dot(N, V), 0.0), 3.0);
            col += u_rim_color * fr_c * u_rim_strength * 0.52;
        }
    }

    if (u_is_eye == 1) {
        col = mix(col, albedo * 1.22 + u_rim_color * 0.08, 0.55);
    }

    col = clamp(col, 0.0, 1.0);
    f_color = vec4(col, (u_alpha_mode == 0) ? 1.0 : alpha);
    f_meta = vec4(v_view_depth, u_mat_group, 0.0, (u_is_face == 1 || u_is_eye == 1) ? 1.0 : 0.0);
}
"""

_POST_VS = """
#version 330 core
in vec2 in_pos;
void main() {
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

_POST_FS = """
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
        bool has_emissive = false;
        vec3 em_col = vec3(0.0);
        for (int i = 0; i < 4; i++) {
            ivec2 q = clamp(p + offs[i], ivec2(0), sz - ivec2(1));
            vec4 nc = texelFetch(u_color_tex, q, 0);
            vec4 nm = texelFetch(u_meta_tex, q, 0);
            if (nc.a >= 0.5) {
                if (nm.b > 0.5) {
                    has_emissive = true;
                    em_col = max(em_col, nc.rgb);
                } else {
                    has_solid = true;
                }
            }
        }
        if (has_solid) {
            f_out = vec4(u_ink_color, 1.0);
            return;
        }
        if (has_emissive) {
            f_out = vec4(em_col, 0.45);
            return;
        }
        f_out = vec4(0.0);
        return;
    }

    if (m.b > 0.5) {
        f_out = c;
        return;
    }

    float depth = m.r;
    float group = m.g;
    bool is_face = (m.a > 0.5);
    float edge = 0.0;
    for (int i = 0; i < 4; i++) {
        ivec2 q = clamp(p + offs[i], ivec2(0), sz - ivec2(1));
        vec4 nc = texelFetch(u_color_tex, q, 0);
        vec4 nm = texelFetch(u_meta_tex, q, 0);
        if (nc.a < 0.5 || nm.b > 0.5) {
            continue;
        }
        float nd = nm.r;
        if (depth - nd > 0.065) {
            edge = max(edge, is_face ? 0.42 : 0.62);
        } else if (!is_face && abs(group - nm.g) > 0.5 && depth >= nd - 0.015) {
            edge = max(edge, 0.36);
        }
    }

    vec3 col = mix(c.rgb, u_ink_color, edge);
    col = floor(col * 18.0 + 0.5) / 18.0;
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
    """Calcula multiplicadores sutis de cor por papel semântico para adaptar VRMs externos ao traje/persona."""
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
    """Renderizador hardware OpenGL 3.3 estilo Tree of Savior HD (`640x800` MSAA 4x) + modo Pixel-Art opcional."""

    def __init__(
        self,
        model: VrmModel,
        width: int = 640,
        height: int = 800,
        samples: int = 4,
        pixel_art: bool = False,
        pixel_size: tuple[int, int] = (152, 190),
    ):
        self.model = model
        self.width = int(width)
        self.height = int(height)
        self.pixel_art = bool(pixel_art)
        self.pixel_w, self.pixel_h = int(pixel_size[0]), int(pixel_size[1])
        self.last_foot_v: float = 0.88

        self.ctx = moderngl.create_standalone_context()
        self.ctx.enable(moderngl.DEPTH_TEST | moderngl.BLEND)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA, moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA)

        # Framebuffers HD MSAA 4x (padrão estilo Tree of Savior!)
        max_samples = min(samples, getattr(self.ctx, "max_samples", 4))
        if max_samples >= 2:
            self._msaa_color = self.ctx.renderbuffer((self.width, self.height), components=4, samples=max_samples)
            self._msaa_depth = self.ctx.depth_renderbuffer((self.width, self.height), samples=max_samples)
            self._fbo_draw = self.ctx.framebuffer(
                color_attachments=[self._msaa_color],
                depth_attachment=self._msaa_depth,
            )
            self._fbo_resolve = self.ctx.simple_framebuffer((self.width, self.height), components=4)
        else:
            self._fbo_draw = self.ctx.simple_framebuffer((self.width, self.height), components=4)
            self._fbo_resolve = self._fbo_draw

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

        self._post_prog = self.ctx.program(vertex_shader=_POST_VS, fragment_shader=_POST_FS)
        self._post_prog["u_color_tex"].value = 0
        self._post_prog["u_meta_tex"].value = 1
        quad = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0], dtype=np.float32)
        self._quad_vbo = self.ctx.buffer(quad.tobytes())
        self._quad_vao = self.ctx.vertex_array(self._post_prog, [(self._quad_vbo, "2f", "in_pos")])

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
        """Renderiza o frame atual em `QPixmap` RGBA (`camera_focus`: `'full'` corpo inteiro ou `'portrait'` close-up rosto!)."""
        self._upload_bones_and_morphs(animator)

        is_builtin = self.model.name.startswith("DungeonSquad_")
        h = self.model.height
        min_y = self.model.min_y

        if camera_focus == "portrait":
            # Enquadramento retrato busto/rosto para inspeção fina de expressão e cabelo!
            target_y = min_y + h * 0.78
            eye = np.array([0.0, target_y + h * 0.03, h * 0.96], dtype=np.float32)
            target = np.array([0.0, target_y, 0.0], dtype=np.float32)
        else:
            center_y = min_y + h * (0.51 if is_builtin else 0.50)
            dist = h * (2.68 if is_builtin else 2.55)
            eye = np.array([0.0, center_y + h * (0.20 if is_builtin else 0.28), dist], dtype=np.float32)
            target = np.array([0.0, center_y - h * 0.01, 0.0], dtype=np.float32)

        rt_w = self.pixel_w if self.pixel_art else self.width
        rt_h = self.pixel_h if self.pixel_art else self.height
        proj = _perspective(27.0, rt_w / max(float(rt_h), 1.0), 0.1, 20.0)
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

        lx = (sun_x_norm - 0.5) * 1.1 + 0.36
        l_dir = np.array([lx, 0.78, 0.92], dtype=np.float32)
        l_dir /= max(float(np.linalg.norm(l_dir)), 1e-6)
        self.prog["u_light_dir"].value = (float(l_dir[0]), float(l_dir[1]), float(l_dir[2]))

        tr, tg, tb = atmosphere.avatar_tint
        ta = clamp(atmosphere.avatar_tint_alpha, 0.0, 0.68)
        light_col = (
            1.0 * (1.0 - ta * 0.28) + (tr / 255.0) * (ta * 0.38),
            1.0 * (1.0 - ta * 0.28) + (tg / 255.0) * (ta * 0.38),
            1.0 * (1.0 - ta * 0.28) + (tb / 255.0) * (ta * 0.38),
        )
        amb_col = (
            0.80 * (1.0 - ta * 0.38) + (tr / 255.0) * (ta * 0.48),
            0.80 * (1.0 - ta * 0.38) + (tg / 255.0) * (ta * 0.48),
            0.84 * (1.0 - ta * 0.38) + (tb / 255.0) * (ta * 0.48),
        )
        rr, rg, rb = atmosphere.rim_light
        self.prog["u_light_color"].value = light_col
        self.prog["u_ambient_color"].value = amb_col
        self.prog["u_rim_color"].value = (rr / 255.0, rg / 255.0, rb / 255.0)
        self.prog["u_rim_strength"].value = 0.48 + ta * 0.36
        # Tinta marrom-café/ameixa escura estilo Tree of Savior (muito mais suave e artística que preto duro!)
        self.prog["u_outline_color"].value = (0.14, 0.07, 0.09)
        self.prog["u_pixel_art"].value = 1 if self.pixel_art else 0

        role_tints = compute_role_tints(persona, outfit_key, dynamic_recolor=(dynamic_recolor and not is_builtin))

        if self.pixel_art:
            self._fbo_pa_geom.use()
            self.ctx.viewport = (0, 0, self.pixel_w, self.pixel_h)
            self.ctx.clear(0.0, 0.0, 0.0, 0.0, depth=1.0)
        else:
            self._fbo_draw.use()
            self.ctx.viewport = (0, 0, self.width, self.height)
            self.ctx.clear(0.0, 0.0, 0.0, 0.0, depth=1.0)
            # Contorno fino elegante estilo Tree of Savior (inverted-hull delicado fora do rosto/olhos!)
            self.ctx.enable(moderngl.CULL_FACE)
            self.ctx.front_face = "cw"
            self.prog["u_is_outline"].value = 1
            self.prog["u_outline_extrude"].value = 0.0026 if camera_focus == "portrait" else 0.0034
            for gp in self._sorted_prims:
                mat = self.model.materials[gp.prim.material_index] if 0 <= gp.prim.material_index < len(self.model.materials) else None
                if mat is None or mat.alpha_mode != "OPAQUE" or mat.role in ("face", "eye", "emissive"):
                    continue
                self._bind_skin(gp.prim.skin_index)
                self.prog["u_has_tex"].value = 0
                self.prog["u_alpha_mode"].value = 0
                self.prog["u_mat_group"].value = _ROLE_GROUP_ID.get(mat.role, 3.0)
                gp.vao.render(moderngl.TRIANGLES)

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
                self.prog["u_alpha_mode"].value = alpha_code.get(mat.alpha_mode, 0)
                self.prog["u_alpha_cutoff"].value = mat.alpha_cutoff
                self.prog["u_is_face"].value = 1 if mat.role == "face" else 0
                self.prog["u_is_skin"].value = 1 if mat.role == "skin" else 0
                self.prog["u_is_eye"].value = 1 if mat.role == "eye" else 0
                self.prog["u_is_hair"].value = 1 if mat.role == "hair" else 0
                self.prog["u_is_emissive"].value = 1 if mat.role == "emissive" else 0
                self.prog["u_is_gold"].value = 1 if mat.role == "gold" else 0
                self.prog["u_mat_group"].value = _ROLE_GROUP_ID.get(mat.role, 3.0)
                if mat.double_sided:
                    self.ctx.disable(moderngl.CULL_FACE)
                else:
                    self.ctx.enable(moderngl.CULL_FACE)
                self.ctx.depth_mask = mat.alpha_mode != "BLEND"
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
                self.prog["u_is_emissive"].value = 0
                self.prog["u_is_gold"].value = 0
                self.prog["u_mat_group"].value = 3.0
                self.ctx.depth_mask = True

            gp.vao.render(moderngl.TRIANGLES)

        self.ctx.depth_mask = True
        self.ctx.disable(moderngl.CULL_FACE)

        if self.pixel_art:
            self._fbo_pa_out.use()
            self.ctx.viewport = (0, 0, self.pixel_w, self.pixel_h)
            self.ctx.disable(moderngl.DEPTH_TEST)
            self.ctx.disable(moderngl.BLEND)
            self.ctx.clear(0.0, 0.0, 0.0, 0.0)
            self._pa_color_tex.use(location=0)
            self._pa_meta_tex.use(location=1)
            self._post_prog["u_ink_color"].value = (0.07, 0.04, 0.11)
            self._quad_vao.render(moderngl.TRIANGLE_STRIP)
            self.ctx.enable(moderngl.DEPTH_TEST | moderngl.BLEND)

            raw = self._fbo_pa_out.read(components=4, alignment=1)
            arr = np.frombuffer(raw, dtype=np.uint8).reshape((self.pixel_h, self.pixel_w, 4))
            flipped = np.ascontiguousarray(arr[::-1, :, :])
            qimg = QImage(flipped.data, self.pixel_w, self.pixel_h, self.pixel_w * 4, QImage.Format_RGBA8888).copy()
            return QPixmap.fromImage(qimg)

        if self._fbo_draw is not self._fbo_resolve:
            self.ctx.copy_framebuffer(self._fbo_resolve, self._fbo_draw)

        raw = self._fbo_resolve.read(components=4, alignment=1)
        arr = np.frombuffer(raw, dtype=np.uint8).reshape((self.height, self.width, 4))
        flipped = np.ascontiguousarray(arr[::-1, :, :])
        qimg = QImage(flipped.data, self.width, self.height, self.width * 4, QImage.Format_RGBA8888).copy()
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
