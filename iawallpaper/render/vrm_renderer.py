"""VRM RENDERER — Renderizador 3D MToon Cel-Shaded em GPU via ModernGL (OpenGL 3.3 Core Profile + MSAA 4x).

Renderiza qualquer `VrmModel` animado por `VrmAnimator` em um framebuffer RGBA transparente offscreen:
- Skinning 100% na GPU via textura float `RGBA32F` (suporta número ilimitado de ossos!).
- Morph targets faciais atualizados dinamicamente em VBO leve apenas nas malhas com expressões ativas.
- Shader anime MToon (rampa 2-bandas, sombra colorida, rim-light Fresnel sincronizado ao `AtmospherePalette`,
  contorno sutil *inverted-hull* apenas em corpo/cabelo/roupas mantendo o rosto delicado).
- Retorno direto como `QPixmap` transparente pronto para composição no `WallpaperCanvas` (funciona no desktop
  Win11 Raised Desktop, em modo preview e em `QT_QPA_PLATFORM=offscreen`).
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
uniform sampler2D u_bone_tex;
uniform int u_has_skin;
uniform float u_outline_extrude;

out vec3 v_world_pos;
out vec3 v_world_norm;
out vec2 v_uv;

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
    v_world_pos = world_p.xyz;
    v_world_norm = normalize(mat3(u_model) * local_n);
    v_uv = in_uv;
    gl_Position = u_mvp * local_p;
}
"""

_FRAGMENT_SHADER = """
#version 330 core
in vec3 v_world_pos;
in vec3 v_world_norm;
in vec2 v_uv;

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
uniform int u_is_eye;
uniform int u_is_hair;
uniform int u_dark_fantasy;   // 1 = alto contraste estilo Dungeon Squad (outline forte, brilho especular, olhos luminosos)

out vec4 f_color;

void main() {
    vec4 tex = (u_has_tex == 1) ? texture(u_albedo, v_uv) : vec4(1.0);
    float alpha = tex.a * u_base_color.a;
    if (u_alpha_mode == 1 && alpha < u_alpha_cutoff) {
        discard;
    }
    if (u_is_outline == 1) {
        f_color = vec4(u_outline_color, 1.0);
        return;
    }

    vec3 albedo = tex.rgb * u_base_color.rgb * u_role_tint;
    vec3 N = normalize(v_world_norm);
    if (!gl_FrontFacing) {
        N = -N;
    }
    vec3 L = normalize(u_light_dir);
    vec3 V = normalize(u_cam_pos - v_world_pos);
    vec3 H = normalize(L + V);

    float ndotl = dot(N, L);
    float toon;
    vec3 lit;
    vec3 shaded;
    if (u_dark_fantasy == 1) {
        // Cel-shading nítido de alto contraste estilo Dungeon Squad (sombras roxo-obsidiana ricas + pele/roupa vibrantes)
        toon = (u_is_face == 1)
            ? smoothstep(-0.22, 0.14, ndotl) * 0.42 + 0.58
            : smoothstep(-0.04, 0.08, ndotl);
        vec3 deep_shade = mix(u_shade_color, vec3(0.46, 0.36, 0.62), 0.55);
        lit = albedo * (u_light_color * 0.96 + u_ambient_color * 0.14);
        shaded = albedo * deep_shade * (u_ambient_color * 0.62 + vec3(0.16));
    } else {
        toon = (u_is_face == 1)
            ? smoothstep(-0.30, 0.22, ndotl) * 0.38 + 0.62
            : smoothstep(-0.08, 0.14, ndotl);
        lit = albedo * (u_light_color * 0.86 + u_ambient_color * 0.16);
        shaded = albedo * u_shade_color * (u_ambient_color * 0.68 + vec3(0.18));
    }
    vec3 col = mix(shaded, lit, toon);

    // Brilho especular anime em cabelo e tecidos (assinatura visual de arte coreana Dungeon Squad)
    if (u_dark_fantasy == 1 && u_is_face == 0) {
        float spec_pow = (u_is_hair == 1) ? 20.0 : 32.0;
        float spec = smoothstep(0.42, 0.72, pow(max(dot(N, H), 0.0), spec_pow));
        col += mix(u_light_color, u_rim_color, 0.45) * spec * ((u_is_hair == 1) ? 0.26 : 0.14);
    }

    // Olhos emissivos luminosos para destacar o olhar sedutor no escuro (Dungeon Squad!)
    if (u_is_eye == 1 && u_dark_fantasy == 1) {
        col = mix(col, albedo * 1.28 + u_rim_color * 0.14, 0.65);
    }

    // Rim-light Fresnel arcano marcante na silhueta
    float fresnel = pow(1.0 - max(dot(N, V), 0.0), (u_dark_fantasy == 1) ? 2.6 : 3.2);
    float rim_mask = (u_is_face == 1) ? 0.24 : ((u_dark_fantasy == 1) ? 1.05 : 0.72);
    col += u_rim_color * fresnel * u_rim_strength * rim_mask;

    // Leve aumento de contraste cinematográfico no modo dark fantasy
    if (u_dark_fantasy == 1 && u_is_face == 0) {
        col = pow(clamp(col, 0.0, 1.0), vec3(1.06));
    }

    col = clamp(col, 0.0, 1.0);
    f_color = vec4(col, (u_alpha_mode == 0) ? 1.0 : alpha);
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


def compute_role_tints(persona: Persona, outfit_key: str, dynamic_recolor: bool = True) -> dict[str, tuple[float, float, float]]:
    """Calcula multiplicadores sutis de cor por papel semântico para adaptar o VRM ao traje/persona ao vivo."""
    base = {
        "hair": (1.0, 1.0, 1.0),
        "eye": (1.0, 1.0, 1.0),
        "tops": (1.0, 1.0, 1.0),
        "bottoms": (1.0, 1.0, 1.0),
        "shoes": (1.0, 1.0, 1.0),
        "skin": (1.0, 1.0, 1.0),
        "face": (1.0, 1.0, 1.0),
        "other": (1.0, 1.0, 1.0),
    }
    if not dynamic_recolor:
        return base

    def _blend_white(rgb: tuple[int, int, int], strength: float) -> tuple[float, float, float]:
        r, g, b = rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0
        # Normaliza brilho para evitar escurecer texturas já coloridas
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
    """Renderizador hardware OpenGL 3.3 MToon offscreen (MSAA 4x -> RGBA QPixmap)."""

    def __init__(self, model: VrmModel, width: int = 512, height: int = 640, samples: int = 4):
        self.model = model
        self.width = int(width)
        self.height = int(height)
        self.last_foot_v: float = 0.88

        self.ctx = moderngl.create_standalone_context()
        self.ctx.enable(moderngl.DEPTH_TEST | moderngl.BLEND)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA, moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA)

        # Framebuffer MSAA 4x + FBO resolvido RGBA8 para bordas anime ultra-nítidas
        max_samples = min(samples, getattr(self.ctx, "max_samples", 4))
        if max_samples >= 2:
            self._msaa_color = self.ctx.renderbuffer((self.width, self.height), components=4, samples=max_samples)
            self._msaa_depth = self.ctx.depth_renderbuffer((self.width, self.height), samples=max_samples)
            self._fbo_draw = self.ctx.framebuffer(color_attachments=[self._msaa_color], depth_attachment=self._msaa_depth)
            self._fbo_resolve = self.ctx.simple_framebuffer((self.width, self.height), components=4)
        else:
            self._fbo_draw = self.ctx.simple_framebuffer((self.width, self.height), components=4)
            self._fbo_resolve = self._fbo_draw

        self.prog = self.ctx.program(vertex_shader=_VERTEX_SHADER, fragment_shader=_FRAGMENT_SHADER)
        self.prog["u_albedo"].value = 0
        self.prog["u_bone_tex"].value = 1

        # Texturas dos materiais (fallback 1x1 branco)
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

        # Texturas de ossos (1 por skin, formato 4 x J RGBA32F -> número ilimitado de ossos!)
        self._skin_textures: list[moderngl.Texture] = []
        for sk in model.skins:
            n_j = max(1, len(sk.joints))
            ident = np.repeat(np.eye(4, dtype=np.float32)[None, :, :], n_j, axis=0)
            btex = self.ctx.texture((4, n_j), 4, ident.tobytes(), dtype="f4")
            btex.filter = (moderngl.NEAREST, moderngl.NEAREST)
            self._skin_textures.append(btex)
        self._dummy_bone_tex = self.ctx.texture((4, 1), 4, np.eye(4, dtype=np.float32).tobytes(), dtype="f4")
        self._dummy_bone_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)

        # VBOs & VAOs por primitiva (posição separada para morph targets faciais dinâmicos)
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

        # Ordena primitivas: OPAQUE primeiro, MASK segundo, BLEND por último
        order_map = {"OPAQUE": 0, "MASK": 1, "BLEND": 2}
        self._sorted_prims = sorted(
            self._gpu_prims,
            key=lambda gp: order_map.get(
                model.materials[gp.prim.material_index].alpha_mode if 0 <= gp.prim.material_index < len(model.materials) else "OPAQUE",
                0,
            ),
        )

    def _upload_bones_and_morphs(self, animator: VrmAnimator) -> None:
        # Atualiza texturas de ossos (transposta para column-major do GLSL mat4)
        for s_idx, jm in enumerate(animator.skin_matrices):
            if s_idx < len(self._skin_textures):
                col_major = np.ascontiguousarray(np.transpose(jm, (0, 2, 1)), dtype=np.float32)
                self._skin_textures[s_idx].write(col_major.tobytes())

        # Atualiza vértices apenas nas primitivas com morph targets (rosto ~4k vértices: <0.2ms!)
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
    ) -> QPixmap:
        """Renderiza o frame atual do avatar 3D cel-shaded em `QPixmap` RGBA transparente."""
        self._upload_bones_and_morphs(animator)

        h = self.model.height
        min_y = self.model.min_y
        # Câmera estilo Tree of Savior (inclinação suave de ~14° para baixo, lente teleobjetiva 28° sem distorção)
        # Centraliza a personagem verticalmente com folga para pés na base e mãos erguidas no topo
        center_y = min_y + h * 0.50
        dist = h * 2.55
        eye = np.array([0.0, center_y + h * 0.28, dist], dtype=np.float32)
        target = np.array([0.0, center_y - h * 0.02, 0.0], dtype=np.float32)
        proj = _perspective(28.0, self.width / max(float(self.height), 1.0), 0.1, 20.0)
        view = _look_at(eye, target, np.array([0.0, 1.0, 0.0], dtype=np.float32))
        model_m = np.eye(4, dtype=np.float32)
        mvp = proj @ view @ model_m

        # Calcula a linha vertical exata (0..1 top-down) onde a sola dos sapatos (0, min_y, 0) projeta no FBO!
        foot_clip = mvp @ np.array([0.0, min_y, 0.0, 1.0], dtype=np.float32)
        foot_ndc_y = float(foot_clip[1] / max(float(foot_clip[3]), 1e-5))
        self.last_foot_v = clamp(0.5 * (1.0 - foot_ndc_y), 0.65, 0.99)

        self.prog["u_mvp"].write(np.ascontiguousarray(mvp.T, dtype=np.float32).tobytes())
        self.prog["u_model"].write(np.ascontiguousarray(model_m.T, dtype=np.float32).tobytes())
        self.prog["u_cam_pos"].value = (float(eye[0]), float(eye[1]), float(eye[2]))

        # Luz direcional, ambiente e rim-light sincronizados ao ciclo dia/noite/clima!
        lx = (sun_x_norm - 0.5) * 1.4 + 0.35
        l_dir = np.array([lx, 0.85, 0.72], dtype=np.float32)
        l_dir /= max(float(np.linalg.norm(l_dir)), 1e-6)
        self.prog["u_light_dir"].value = (float(l_dir[0]), float(l_dir[1]), float(l_dir[2]))

        tr, tg, tb = atmosphere.avatar_tint
        ta = clamp(atmosphere.avatar_tint_alpha, 0.0, 0.75)
        light_col = (
            1.0 * (1.0 - ta * 0.35) + (tr / 255.0) * (ta * 0.45),
            1.0 * (1.0 - ta * 0.35) + (tg / 255.0) * (ta * 0.45),
            1.0 * (1.0 - ta * 0.35) + (tb / 255.0) * (ta * 0.45),
        )
        amb_col = (
            0.76 * (1.0 - ta * 0.45) + (tr / 255.0) * (ta * 0.55),
            0.78 * (1.0 - ta * 0.45) + (tg / 255.0) * (ta * 0.55),
            0.84 * (1.0 - ta * 0.45) + (tb / 255.0) * (ta * 0.55),
        )
        rr, rg, rb = atmosphere.rim_light
        self.prog["u_light_color"].value = light_col
        self.prog["u_ambient_color"].value = amb_col
        self.prog["u_rim_color"].value = (rr / 255.0, rg / 255.0, rb / 255.0)
        self.prog["u_rim_strength"].value = 0.56 + ta * 0.42
        self.prog["u_outline_color"].value = (0.07, 0.03, 0.12)
        self.prog["u_dark_fantasy"].value = 1

        role_tints = compute_role_tints(persona, outfit_key, dynamic_recolor=dynamic_recolor)

        self._fbo_draw.use()
        self.ctx.viewport = (0, 0, self.width, self.height)
        self.ctx.clear(0.0, 0.0, 0.0, 0.0, depth=1.0)

        # Passo 1: Contorno nítido estilo Dungeon Squad (inverted-hull dark ink em corpo/cabelo/roupas!)
        self.ctx.enable(moderngl.CULL_FACE)
        self.ctx.front_face = "cw"  # desenha backfaces extrudadas
        self.prog["u_is_outline"].value = 1
        self.prog["u_outline_extrude"].value = 0.0042
        for gp in self._sorted_prims:
            mat = self.model.materials[gp.prim.material_index] if 0 <= gp.prim.material_index < len(self.model.materials) else None
            if mat is None or mat.alpha_mode != "OPAQUE" or mat.role in ("face", "eye"):
                continue
            self._bind_skin(gp.prim.skin_index)
            self.prog["u_has_tex"].value = 0
            self.prog["u_alpha_mode"].value = 0
            gp.vao.render(moderngl.TRIANGLES)

        # Passo 2: Render principal MToon cel-shaded (OPAQUE -> MASK -> BLEND)
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
                self.prog["u_is_face"].value = 1 if mat.role in ("face", "skin") else 0
                self.prog["u_is_eye"].value = 1 if mat.role == "eye" else 0
                self.prog["u_is_hair"].value = 1 if mat.role == "hair" else 0
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
                self.prog["u_is_eye"].value = 0
                self.prog["u_is_hair"].value = 0
                self.ctx.depth_mask = True

            gp.vao.render(moderngl.TRIANGLES)

        self.ctx.depth_mask = True
        self.ctx.disable(moderngl.CULL_FACE)

        if self._fbo_draw is not self._fbo_resolve:
            self.ctx.copy_framebuffer(self._fbo_resolve, self._fbo_draw)

        raw = self._fbo_resolve.read(components=4, alignment=1)
        arr = np.frombuffer(raw, dtype=np.uint8).reshape((self.height, self.width, 4))
        # OpenGL origem é inferior-esquerda -> inverte eixo Y para Qt
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
