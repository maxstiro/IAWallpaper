"""VRM ANIMATOR — Motor universal de animação 3D humanoide (giro 360°, expressões faciais, look-at e SpringBone).

Dirige QUALQUER modelo VRM 1.0 / VRM 0.x sem gerar vídeo por movimento:
- Giro suave em 360° (`yaw_deg`) alinhado ao vetor real de caminhada 2.5D (direita, esquerda, costas, frente, diagonais).
- Ciclo de caminhada bípede real 3D, idle orgânico com respiração, aceno caloroso, dança giratória estilo Tree of Savior,
  alongamento, sentar digitando e dormir.
- Expressões faciais VRM (piscar natural, happy, relaxed, angry, sad, surprised) guiadas por `EmotionState` +
  acompanhamento de cabeça/olhos pelo cursor + física de mola secundária nos cabelos/roupas (`VRMC_springBone`).
"""

import math

import numpy as np

from ..core.emotion import EmotionState
from ..mathutil import clamp
from .vrm_loader import VrmModel


def _quat_mul(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2
    return np.array(
        [
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        ],
        dtype=np.float32,
    )


def _quat_from_euler_xyz(rx_deg: float, ry_deg: float, rz_deg: float) -> np.ndarray:
    """Converte Euler XYZ (graus) em quaternion xyzw (ordem intrínseca Z -> Y -> X aplicada como Rz @ Ry @ Rx)."""
    hx = math.radians(rx_deg) * 0.5
    hy = math.radians(ry_deg) * 0.5
    hz = math.radians(rz_deg) * 0.5
    cx, sx = math.cos(hx), math.sin(hx)
    cy, sy = math.cos(hy), math.sin(hy)
    cz, sz = math.cos(hz), math.sin(hz)
    # q = qz * qy * qx
    qx = sx * cy * cz - cx * sy * sz
    qy = cx * sy * cz + sx * cy * sz
    qz = cx * cy * sz - sx * sy * cz
    qw = cx * cy * cz + sx * sy * sz
    return np.array([qx, qy, qz, qw], dtype=np.float32)


def _mat4_from_trs(t: np.ndarray, q: np.ndarray, s: np.ndarray) -> np.ndarray:
    x, y, z, w = float(q[0]), float(q[1]), float(q[2]), float(q[3])
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    sx, sy, sz = float(s[0]), float(s[1]), float(s[2])
    m = np.empty((4, 4), dtype=np.float32)
    m[0, 0] = (1.0 - 2.0 * (yy + zz)) * sx
    m[0, 1] = (2.0 * (xy - wz)) * sy
    m[0, 2] = (2.0 * (xz + wy)) * sz
    m[0, 3] = float(t[0])
    m[1, 0] = (2.0 * (xy + wz)) * sx
    m[1, 1] = (1.0 - 2.0 * (xx + zz)) * sy
    m[1, 2] = (2.0 * (yz - wx)) * sz
    m[1, 3] = float(t[1])
    m[2, 0] = (2.0 * (xz - wy)) * sx
    m[2, 1] = (2.0 * (yz + wx)) * sy
    m[2, 2] = (1.0 - 2.0 * (xx + yy)) * sz
    m[2, 3] = float(t[2])
    m[3, 0] = 0.0
    m[3, 1] = 0.0
    m[3, 2] = 0.0
    m[3, 3] = 1.0
    return m


def _shortest_angle_deg(cur: float, dst: float) -> float:
    return ((dst - cur + 180.0) % 360.0) - 180.0


_AIM_AXIS_VECS: dict[str, np.ndarray] = {
    "PositiveX": np.array([1.0, 0.0, 0.0], dtype=np.float32),
    "NegativeX": np.array([-1.0, 0.0, 0.0], dtype=np.float32),
    "PositiveY": np.array([0.0, 1.0, 0.0], dtype=np.float32),
    "NegativeY": np.array([0.0, -1.0, 0.0], dtype=np.float32),
    "PositiveZ": np.array([0.0, 0.0, 1.0], dtype=np.float32),
    "NegativeZ": np.array([0.0, 0.0, -1.0], dtype=np.float32),
}


def _quat_from_two_vecs(v_from: np.ndarray, v_to: np.ndarray) -> np.ndarray:
    """Menor rotação (quaternion xyzw) levando vetor unitário `v_from` até `v_to`."""
    d = float(np.dot(v_from, v_to))
    if d >= 0.99999:
        return np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
    if d <= -0.99999:
        ortho = np.cross(np.array([1.0, 0.0, 0.0], dtype=np.float32), v_from)
        if np.linalg.norm(ortho) < 1e-4:
            ortho = np.cross(np.array([0.0, 1.0, 0.0], dtype=np.float32), v_from)
        ortho /= max(float(np.linalg.norm(ortho)), 1e-6)
        return np.array([ortho[0], ortho[1], ortho[2], 0.0], dtype=np.float32)
    c = np.cross(v_from, v_to)
    q = np.array([c[0], c[1], c[2], 1.0 + d], dtype=np.float32)
    q /= max(float(np.linalg.norm(q)), 1e-6)
    return q


# Ossos humanoides controlados pelo animador universal (em graus Euler XYZ relativos à T-pose de repouso)
_ANIM_BONES = (
    "hips", "spine", "chest", "upperChest", "neck", "head",
    "leftShoulder", "leftUpperArm", "leftLowerArm", "leftHand",
    "rightShoulder", "rightUpperArm", "rightLowerArm", "rightHand",
    "leftUpperLeg", "leftLowerLeg", "leftFoot",
    "rightUpperLeg", "rightLowerLeg", "rightFoot",
)


class VrmAnimator:
    """Anima qualquer `VrmModel` em tempo real com blend suave entre poses, giro 360°, expressões e física de mola."""

    def __init__(self, model: VrmModel):
        self.model = model
        self.time: float = 0.0
        self.walk_phase: float = 0.0
        self.action_timer: float = 0.0

        # Giro suave 360° no eixo Y (0° = frente para câmera, +80° = direita, -80° = esquerda, 180° = costas)
        self.yaw_deg: float = 0.0
        self.target_yaw_deg: float = 0.0
        self._spin_offset_deg: float = 0.0

        # Deslocamento suave da pelve (y = altura, x = balanço lateral)
        self.hips_offset = np.zeros(3, dtype=np.float32)

        # Ângulos Euler suavizados por osso humanoide
        self._cur_euler: dict[str, np.ndarray] = {b: np.zeros(3, dtype=np.float32) for b in _ANIM_BONES}

        # Expressões faciais suavizadas (0..1)
        self.expr_weights: dict[str, float] = {}

        # Estado de física secundária (oscilação suave para SpringBones + vertex shader de cabelo fluido!)
        self._spring_sway_x: float = 0.0
        self._spring_sway_z: float = 0.0
        self._spring_vel_x: float = 0.0
        self._spring_vel_z: float = 0.0
        self.hair_trail_x: float = 0.0
        self.hair_trail_z: float = 0.0
        self.hair_bounce_y: float = 0.0
        self.hair_flare: float = 0.0
        self._hair_vel_x: float = 0.0
        self._hair_vel_z: float = 0.0
        self._hair_vel_y: float = 0.0
        self._prev_hips_y: float = 0.0
        self._yaw_vel: float = 0.0

        # Ordem topológica (pai sempre antes de filho) para FK em passagem única
        self._topo_order: list[int] = self._build_topo_order()
        self._is_ds_builtin: bool = model.name.startswith("DungeonSquad_")
        self._halo_node: int = next((n.index for n in model.nodes if n.name == "halo_ring"), -1)
        self.stylized_proportions: bool = False  # opcional para estilizar VRMs externos no padrão Dungeon Squad
        self.world_matrices: list[np.ndarray] = [np.eye(4, dtype=np.float32) for _ in model.nodes]
        self.skin_matrices: list[np.ndarray] = []
        self.mesh_morph_weights: dict[int, dict[int, float]] = {}

        # Aplica pose idle inicial imediata
        self._snap_to_pose(self._compute_targets("idle", 0.0, 0.0, False, False, False))
        self.solve_fk()

    def _build_topo_order(self) -> list[int]:
        order: list[int] = []
        stack = list(reversed(self.model.roots))
        visited: set[int] = set()
        while stack:
            ni = stack.pop()
            if ni in visited:
                continue
            visited.add(ni)
            order.append(ni)
            for ch in reversed(self.model.nodes[ni].children):
                stack.append(ch)
        for i in range(len(self.model.nodes)):
            if i not in visited:
                order.append(i)
        return order

    def _snap_to_pose(self, targets: tuple[dict[str, tuple[float, float, float]], tuple[float, float, float]]) -> None:
        eulers, hips_off = targets
        for b in _ANIM_BONES:
            self._cur_euler[b] = np.array(eulers.get(b, (0.0, 0.0, 0.0)), dtype=np.float32)
        self.hips_offset = np.array(hips_off, dtype=np.float32)

    def _compute_targets(
        self,
        action: str,
        look_x: float,
        look_y: float,
        asleep: bool,
        raining: bool,
        caressing: bool,
    ) -> tuple[dict[str, tuple[float, float, float]], tuple[float, float, float]]:
        t = self.time
        breath = math.sin(t * (1.4 if asleep else 2.2))

        # Base anatômica natural (baixa os braços da T-pose para postura feminina relaxada!)
        e: dict[str, tuple[float, float, float]] = {
            "hips": (0.0, 0.0, 0.0),
            "spine": (breath * 1.2, 0.0, 0.0),
            "chest": (breath * 1.4, 0.0, 0.0),
            "upperChest": (breath * 0.8, 0.0, 0.0),
            "neck": (0.0, 0.0, 0.0),
            "head": (0.0, 0.0, 0.0),
            "leftShoulder": (0.0, 0.0, -4.0),
            "leftUpperArm": (6.0, -6.0, -68.0),
            "leftLowerArm": (0.0, -14.0, -6.0),
            "leftHand": (0.0, 0.0, 6.0),
            "rightShoulder": (0.0, 0.0, 4.0),
            "rightUpperArm": (6.0, 6.0, 68.0),
            "rightLowerArm": (0.0, 14.0, 6.0),
            "rightHand": (0.0, 0.0, -6.0),
            "leftUpperLeg": (0.0, 0.0, 2.5),
            "leftLowerLeg": (2.0, 0.0, 0.0),
            "leftFoot": (0.0, 0.0, 0.0),
            "rightUpperLeg": (0.0, 0.0, -2.5),
            "rightLowerLeg": (2.0, 0.0, 0.0),
            "rightFoot": (0.0, 0.0, 0.0),
        }
        hips_off = (0.0, 0.0, 0.0)

        if asleep or action == "sleep":
            hips_off = (0.0, -0.34, 0.0)
            e["hips"] = (8.0, 0.0, 0.0)
            e["spine"] = (12.0 + breath * 1.8, 0.0, 0.0)
            e["chest"] = (10.0 + breath * 1.5, 0.0, 0.0)
            e["head"] = (18.0 + math.sin(t * 1.1) * 3.0, 8.0, 10.0)
            e["leftUpperLeg"] = (-76.0, 10.0, 8.0)
            e["leftLowerLeg"] = (110.0, 0.0, 0.0)
            e["rightUpperLeg"] = (-72.0, -10.0, -8.0)
            e["rightLowerLeg"] = (106.0, 0.0, 0.0)
            e["leftUpperArm"] = (18.0, -24.0, -58.0)
            e["leftLowerArm"] = (0.0, -45.0, 0.0)
            e["rightUpperArm"] = (18.0, 24.0, 58.0)
            e["rightLowerArm"] = (0.0, 45.0, 0.0)
            return e, hips_off

        if action == "walk":
            # Caminhada ultra-fluida estilo Tree of Savior + desfile elegante (ref 96078865):
            # Ação sobreposta (overlapping action) em cascata: quadril -> coluna -> peito -> cabeça -> braço -> antebraço -> pulso!
            ph = self.walk_phase
            # Pequena assimetria rítmica (impulso firme + passagem aérea graciosa)
            ph_e = ph + 0.12 * math.sin(ph)
            s0 = math.sin(ph_e)
            c0 = math.cos(ph_e)
            s_spine = math.sin(ph_e - 0.34)
            s_chest = math.sin(ph_e - 0.66)
            s_head = math.sin(ph_e - 0.96)
            s_arm = math.sin(ph_e - 0.24)
            s_fore = math.sin(ph_e - 0.78)
            s_hand = math.sin(ph_e - 1.28)
            step_bob = abs(math.cos(ph_e - 0.18))
            chest_bob = abs(math.cos(ph_e - 0.56))
            bank = clamp(self._yaw_vel * 0.032, -6.5, 6.5)

            hips_off = (s0 * 0.022, step_bob * 0.034 - 0.017, 0.0)
            e["hips"] = (4.2 + step_bob * 1.4, s0 * 12.0, -s0 * 6.8 + bank * 0.45)
            e["spine"] = (-4.8 + chest_bob * 1.2, -s_spine * 8.0, s_spine * 4.4 + bank * 0.55)
            e["chest"] = (-3.4 + chest_bob * 2.4, -s_chest * 5.2, s_chest * 2.4 + bank * 0.35)
            e["upperChest"] = (chest_bob * 2.0 - 0.8, 0.0, 0.0)
            e["neck"] = (2.6, s_head * 2.8, -s_head * 1.6 - bank * 0.35)
            e["head"] = (-1.6 + chest_bob * 1.4, s_head * 4.0 + look_x * 12.0, -s_head * 2.4 - bank * 0.4)

            # Passada fluida com absorção macia de joelho no contato e rolamento natural de tornozelo!
            l_swing = max(0.0, -math.cos(ph_e - 0.10))
            r_swing = max(0.0, math.cos(ph_e - 0.10))
            l_cushion = max(0.0, math.sin(ph_e + 0.35)) * 7.5
            r_cushion = max(0.0, -math.sin(ph_e + 0.35)) * 7.5

            e["leftUpperLeg"] = (-s0 * 30.0 - 2.5, 2.5, 2.5)
            e["leftLowerLeg"] = (l_swing * 44.0 + l_cushion + 5.5, 0.0, 0.0)
            e["leftFoot"] = (-max(0.0, s0) * 11.0 + l_swing * 18.0 - l_cushion * 0.4, 0.0, 0.0)

            e["rightUpperLeg"] = (s0 * 30.0 - 2.5, -2.5, -2.5)
            e["rightLowerLeg"] = (r_swing * 44.0 + r_cushion + 5.5, 0.0, 0.0)
            e["rightFoot"] = (-max(0.0, -s0) * 11.0 + r_swing * 18.0 - r_cushion * 0.4, 0.0, 0.0)

            # Braços com follow-through sedoso (cotovelo e punho acompanham atrasados como desenho 2D!)
            e["leftShoulder"] = (0.0, -s_chest * 2.5, -4.0 + chest_bob * 1.6)
            e["leftUpperArm"] = (4.5, s_arm * 20.0 - 3.0, -68.0 + chest_bob * 2.0)
            e["leftLowerArm"] = (0.0, -15.0 - max(0.0, -s_fore) * 19.0 - max(0.0, s_fore) * 4.0, -4.0 + s_fore * 3.0)
            e["leftHand"] = (s_hand * 5.0, 0.0, 8.0 + s_hand * 9.0)
            e["rightShoulder"] = (0.0, -s_chest * 2.5, 4.0 - chest_bob * 1.6)
            e["rightUpperArm"] = (4.5, s_arm * 20.0 + 3.0, 68.0 - chest_bob * 2.0)
            e["rightLowerArm"] = (0.0, 15.0 + max(0.0, s_fore) * 19.0 + max(0.0, -s_fore) * 4.0, 4.0 + s_fore * 3.0)
            e["rightHand"] = (-s_hand * 5.0, 0.0, -8.0 + s_hand * 9.0)
        elif action == "wave":
            # Aceno alegre em cascata (ombro -> braço -> antebraço -> pulso com atraso orgânico!)
            w0 = math.sin(t * 6.8)
            w1 = math.sin(t * 6.8 - 0.65)
            w2 = math.sin(t * 6.8 - 1.25)
            sway0 = math.sin(t * 1.8)
            sway1 = math.sin(t * 1.8 - 0.55)
            hips_off = (sway0 * 0.016, breath * 0.006, 0.0)
            e["hips"] = (2.0, 12.0 + sway0 * 4.5, -4.0 - sway0 * 3.0)
            e["spine"] = (-3.5, -7.0 - sway1 * 3.5, 3.0 + sway1 * 3.0)
            e["chest"] = (-2.5 + breath * 1.8, -5.0 + w0 * 1.5, 2.0)
            e["head"] = (-2.0 + look_y * 6.0, look_x * 14.0 - 4.0 + w1 * 3.8, 6.0 + w1 * 4.0)
            e["leftUpperArm"] = (8.0, -12.0 - sway1 * 3.0, -64.0)
            e["leftLowerArm"] = (0.0, -28.0 + sway1 * 4.0, -8.0)
            e["leftHand"] = (0.0, 0.0, 10.0 + sway1 * 5.0)
            e["rightShoulder"] = (0.0, 0.0, -10.0 + w0 * 2.0)
            e["rightUpperArm"] = (-8.0, 26.0, -22.0 + w0 * 10.0)
            e["rightLowerArm"] = (0.0, 14.0, -52.0 + w1 * 24.0)
            e["rightHand"] = (w2 * 6.0, 0.0, w2 * 18.0)
        elif action in ("dance", "music_sway"):
            beat0 = math.sin(t * 4.8)
            beat1 = math.sin(t * 4.8 - 0.55)
            beat2 = math.sin(t * 4.8 - 1.15)
            half0 = math.sin(t * 2.4)
            half1 = math.sin(t * 2.4 - 0.60)
            hips_off = (half0 * 0.030, abs(beat0) * 0.032 - 0.012, 0.0)
            e["hips"] = (3.0, half0 * 15.0, -half0 * 5.5)
            e["spine"] = (-3.5, -half1 * 10.0, half1 * 5.5)
            e["chest"] = (-3.5 + abs(beat1) * 2.0, -beat1 * 8.0, -half1 * 3.0)
            e["head"] = (-4.0 + beat2 * 4.5, half1 * 10.0, beat2 * 7.0)
            e["leftUpperArm"] = (-10.0, -22.0 + beat0 * 18.0, -26.0 - abs(beat0) * 20.0)
            e["leftLowerArm"] = (0.0, -34.0 - beat1 * 20.0, 14.0 + beat1 * 6.0)
            e["leftHand"] = (beat2 * 8.0, 0.0, 16.0 + beat2 * 14.0)
            e["rightUpperArm"] = (-10.0, 22.0 + beat0 * 18.0, 26.0 + abs(beat0) * 20.0)
            e["rightLowerArm"] = (0.0, 34.0 - beat1 * 20.0, -14.0 + beat1 * 6.0)
            e["rightHand"] = (-beat2 * 8.0, 0.0, -16.0 + beat2 * 14.0)
            e["leftUpperLeg"] = (-10.0 - beat0 * 8.0, 0.0, 4.0)
            e["leftLowerLeg"] = (16.0 + abs(beat0) * 14.0, 0.0, 0.0)
            e["rightUpperLeg"] = (-10.0 + beat0 * 8.0, 0.0, -4.0)
            e["rightLowerLeg"] = (16.0 + abs(beat0) * 14.0, 0.0, 0.0)
        elif action == "stretch":
            arch = math.sin(clamp(self.action_timer / 4.0, 0.0, 1.0) * math.pi)
            hips_off = (0.0, arch * 0.022, 0.0)
            e["spine"] = (-arch * 8.0, 0.0, 0.0)
            e["chest"] = (-arch * 9.0, 0.0, 0.0)
            e["head"] = (-arch * 10.0, 0.0, 0.0)
            e["leftUpperArm"] = (-arch * 12.0, -arch * 10.0, -68.0 + arch * 128.0)
            e["leftLowerArm"] = (0.0, -14.0 - arch * 18.0, arch * 18.0)
            e["rightUpperArm"] = (-arch * 12.0, arch * 10.0, 68.0 - arch * 128.0)
            e["rightLowerArm"] = (0.0, 14.0 + arch * 18.0, -arch * 18.0)
        elif action in ("sit_work", "sit_relax"):
            tap = math.sin(t * 10.5)
            hips_off = (0.0, -0.32, 0.0)
            e["hips"] = (4.0, 0.0, 0.0)
            e["spine"] = (8.0 + breath * 1.2, 0.0, 0.0)
            e["chest"] = (5.0, 0.0, 0.0)
            e["head"] = (10.0 + look_y * 6.0, look_x * 14.0, 0.0)
            e["leftUpperLeg"] = (-82.0, 4.0, 4.0)
            e["leftLowerLeg"] = (84.0, 0.0, 0.0)
            e["rightUpperLeg"] = (-80.0, -4.0, -4.0)
            e["rightLowerLeg"] = (82.0, 0.0, 0.0)
            e["leftUpperArm"] = (22.0, -34.0, -56.0)
            e["leftLowerArm"] = (0.0, -56.0 + tap * 6.0, 0.0)
            e["rightUpperArm"] = (22.0, 34.0, 56.0)
            e["rightLowerArm"] = (0.0, 56.0 - tap * 6.0, 0.0)
        else:
            # Idle icônico estilo Dungeon Squad (Titan / Stheno / Beholder):
            # Base aberta confiante em A-frame, busto em destaque com respiração viva,
            # tronco levemente em 3/4 e mãos abertas canalizando chamas arcanas!
            sway = math.sin(t * 1.65)
            ds_breath = math.sin(t * 3.1)
            hips_off = (0.015 + sway * 0.012, -0.025 + ds_breath * 0.010, 0.0)
            e["hips"] = (2.0, 14.0 + sway * 4.5, -4.5 - sway * 2.0)
            e["spine"] = (-3.0 + ds_breath * 2.2, -9.0 - sway * 3.0, 3.5 + sway * 1.8)
            e["chest"] = (-3.5 + ds_breath * 2.8, -4.5 + sway * 2.2, 1.5)
            e["upperChest"] = (-1.5 + ds_breath * 1.6, 0.0, 0.0)
            e["neck"] = (look_y * 4.5 - 1.5, look_x * 8.0 - 2.0, -2.0)
            e["head"] = (
                look_y * 7.0 + 2.0 + (6.0 if caressing else 0.0),
                look_x * 14.0 - 4.0 + math.sin(t * 1.4) * 3.0,
                -4.0 + sway * 2.4 + (6.0 if caressing else 0.0),
            )
            if self._is_ds_builtin:
                # Base larga poderosa em A-frame exibindo silhueta voluptuosa das coxas (Titan_idle!)
                e["leftUpperLeg"] = (-5.0, 10.0, 21.0 + sway * 1.2)
                e["leftLowerLeg"] = (10.0, 0.0, -5.0)
                e["leftFoot"] = (-5.0, 0.0, -14.0)
                e["rightUpperLeg"] = (4.0, -10.0, -21.0 + sway * 1.2)
                e["rightLowerLeg"] = (8.0, 0.0, 5.0)
                e["rightFoot"] = (-4.0, 0.0, 14.0)
                # Ambas as mãos erguidas lateralmente canalizando energia arcana (Titan_idle!)
                e["leftShoulder"] = (0.0, 0.0, -3.0 + ds_breath * 2.0)
                e["leftUpperArm"] = (-8.0, -20.0 - sway * 3.5, -42.0 + ds_breath * 3.0)
                e["leftLowerArm"] = (0.0, -38.0 + ds_breath * 4.0, 18.0)
                e["leftHand"] = (0.0, 0.0, 14.0)
                e["rightShoulder"] = (0.0, 0.0, 3.0 - ds_breath * 2.0)
                e["rightUpperArm"] = (-10.0, 24.0 + sway * 3.5, 44.0 - ds_breath * 3.0)
                e["rightLowerArm"] = (0.0, 42.0 - ds_breath * 4.0, -16.0)
                e["rightHand"] = (0.0, 0.0, -14.0)
            else:
                # Postura Pin-Up / ToS viva com Ação Sobreposta em Cascata (refs 96444929 & 141744777):
                # Onda orgânica sobe do quadril -> coluna -> busto -> ombros -> braços/pulsos -> cabeça!
                w0 = math.sin(t * 1.25) + 0.22 * math.sin(t * 2.50)
                w1 = math.sin(t * 1.25 - 0.45) + 0.22 * math.sin(t * 2.50 - 0.90)
                w2 = math.sin(t * 1.25 - 0.85) + 0.22 * math.sin(t * 2.50 - 1.70)
                w3 = math.sin(t * 1.25 - 1.25)
                b0 = math.sin(t * 2.45)
                b1 = math.sin(t * 2.45 - 0.48)
                b2 = math.sin(t * 2.45 - 0.92)
                b3 = math.sin(t * 2.45 - 1.38)

                hips_off = (0.022 + w0 * 0.016, -0.026 + b0 * 0.011, 0.0)
                e["hips"] = (5.8 + b0 * 0.8, 21.0 + w0 * 5.2, -8.2 - w0 * 2.8)
                e["spine"] = (-7.2 + b1 * 2.4, -9.5 - w1 * 3.4, 6.2 + w1 * 2.2)
                e["chest"] = (-5.2 + b2 * 3.4, -5.8 + w2 * 2.4, 2.4 - w2 * 1.0)
                e["upperChest"] = (-1.8 + b2 * 2.5, -1.8, 0.0)
                e["neck"] = (3.2 + look_y * 4.0 - b2 * 1.0, -5.8 + look_x * 6.0, -2.4 + w2 * 1.2)
                e["head"] = (
                    3.8 + look_y * 6.5 - b3 * 1.8 + (6.0 if caressing else 0.0),
                    -13.5 + look_x * 14.0 + w3 * 3.8,
                    -6.0 + w3 * 3.2 + (6.0 if caressing else 0.0),
                )
                # Perna esquerda firme sustentando o quadril + perna direita avançada com joelho relaxado!
                e["leftUpperLeg"] = (-4.0, 8.0, 8.0 + w0 * 1.4)
                e["leftLowerLeg"] = (9.0 - b0 * 1.5, 0.0, -2.0)
                e["leftFoot"] = (-4.0, 0.0, -6.0)
                e["rightUpperLeg"] = (-16.0 + b0 * 1.2, -14.0, -13.0 + w0 * 1.5)
                e["rightLowerLeg"] = (24.0 - b0 * 2.0, 0.0, 4.0)
                e["rightFoot"] = (10.0, 0.0, 8.0)
                # Mão direita apoiada estilosa no quadril + braço esquerdo aberto com follow-through de pulso!
                e["rightShoulder"] = (0.0, 0.0, 8.0 - b1 * 1.8)
                e["rightUpperArm"] = (14.0, -18.0 + w1 * 1.5, 44.0 - b1 * 2.4)
                e["rightLowerArm"] = (0.0, 74.0, 32.0 + b2 * 2.5)
                e["rightHand"] = (0.0, 0.0, -24.0 + b3 * 4.0)
                e["leftShoulder"] = (0.0, 0.0, -4.0 + b1 * 2.4)
                e["leftUpperArm"] = (-8.0, -18.0 - w1 * 4.5, -46.0 + b2 * 3.6)
                e["leftLowerArm"] = (0.0, -44.0 + b3 * 5.8 - w2 * 3.0, 16.0 + b3 * 3.5)
                e["leftHand"] = (12.0 + b3 * 6.0, 0.0, 22.0 + w3 * 8.0)

        # Sobrepõe braço direito segurando guarda-chuva na chuva (em pé/caminhada)
        if raining and action not in ("sleep", "sit_work", "sit_relax"):
            e["rightUpperArm"] = (-16.0, 48.0, 40.0)
            e["rightLowerArm"] = (0.0, 62.0, -38.0)

        return e, hips_off

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
        move_dx: float = 0.0,
        move_dy: float = 0.0,
        wind_speed: float = 6.0,
        asleep: bool = False,
        raining: bool = False,
        caressing: bool = False,
    ) -> None:
        dt = clamp(dt, 0.0, 0.1)
        self.time += dt
        self.walk_phase = walk_phase
        self.action_timer = action_timer

        # 1. Giro suave 360° alinhado ao vetor real de caminhada (Tree of Savior!)
        if action == "walk" and math.hypot(move_dx, move_dy) > 1e-4:
            # No mundo 2.5D: +dx = tela direita (+X -> +90°), +dy = direção câmera (+Z -> 0°), -dy = fundo (-Z -> 180°)
            vx_vis = move_dx * 1.77
            vy_vis = move_dy
            self.target_yaw_deg = math.degrees(math.atan2(vx_vis, vy_vis))
            self._spin_offset_deg += (0.0 - self._spin_offset_deg) * clamp(dt * 8.0, 0.0, 1.0)
        elif action == "dance":
            # Giro gracioso 360° estilo Tree of Savior!
            self.target_yaw_deg = 0.0
            self._spin_offset_deg = (self._spin_offset_deg + dt * 110.0) % 360.0
        else:
            # Ao parar, vira suavemente de frente (com leve orientação para o cursor)
            self.target_yaw_deg = clamp(look_x * 16.0, -18.0, 18.0)
            spin_err = _shortest_angle_deg(self._spin_offset_deg, 0.0)
            self._spin_offset_deg += spin_err * clamp(dt * 6.5, 0.0, 1.0)

        yaw_err = _shortest_angle_deg(self.yaw_deg, self.target_yaw_deg)
        prev_yaw = self.yaw_deg
        self.yaw_deg = (self.yaw_deg + yaw_err * (1.0 - math.exp(-dt * 9.5))) % 360.0
        dyaw = _shortest_angle_deg(prev_yaw, self.yaw_deg)
        inst_yaw_vel = (dyaw / max(dt, 1e-4)) + (110.0 if action == "dance" else 0.0)
        self._yaw_vel += (inst_yaw_vel - self._yaw_vel) * clamp(dt * 8.0, 0.0, 1.0)

        # 2. Blend exponencial fluido com inércia diferenciada por grupo ósseo (pernas firmes, tronco/braços/mãos sedosos!)
        targets, target_hips = self._compute_targets(action, look_x, look_y, asleep, raining, caressing)
        k_leg = 1.0 - math.exp(-dt * (14.5 if action == "walk" else 8.5))
        k_torso = 1.0 - math.exp(-dt * (10.5 if action == "walk" else 7.2))
        k_arm = 1.0 - math.exp(-dt * (9.5 if action == "walk" else 6.8))
        for b in _ANIM_BONES:
            if "Leg" in b or "Foot" in b or b == "hips":
                kb = k_leg
            elif "Arm" in b or "Hand" in b or b in ("head", "neck"):
                kb = k_arm
            else:
                kb = k_torso
            dst = np.array(targets.get(b, (0.0, 0.0, 0.0)), dtype=np.float32)
            self._cur_euler[b] += (dst - self._cur_euler[b]) * kb
        prev_hy = float(self.hips_offset[1])
        self.hips_offset += (np.array(target_hips, dtype=np.float32) - self.hips_offset) * k_leg
        hips_vel_y = (float(self.hips_offset[1]) - prev_hy) / max(dt, 1e-4)

        # 3. Expressões faciais VRM (olhos grandes brilhantes estilo Tree of Savior + piscar natural + humor LIF!)
        mood = "sleepy" if asleep else emotion.mood
        want_expr: dict[str, float] = {
            "blink": clamp(1.0 if asleep else (0.85 if caressing else blink_amount), 0.0, 1.0),
            "happy": 0.45 if (mood in ("happy", "affectionate") or action in ("wave", "dance") or caressing) else 0.14,
            "relaxed": 0.30 if mood in ("cozy", "calm", "sleepy") else 0.0,
            "angry": 0.50 if mood == "pouty" else 0.0,
            "sad": 0.30 if mood == "shy" else 0.0,
            "surprised": 0.0,
        }
        ek = 1.0 - math.exp(-dt * 10.0)
        for ename, target_w in want_expr.items():
            cur_w = self.expr_weights.get(ename, 0.0)
            self.expr_weights[ename] = cur_w + (target_w - cur_w) * ek

        # 4. Física de mola secundária para SpringBones + rastro real de cabelo em mundo 3D!
        wind_x = math.sin(self.time * 2.1) * (4.0 + wind_speed * 0.45) - move_dx * 220.0
        wind_z = math.cos(self.time * 1.7) * (3.0 + wind_speed * 0.35) - (10.0 if action == "walk" else 0.0) - (14.0 if action == "dance" else 0.0)
        self._spring_vel_x += (-36.0 * (self._spring_sway_x - wind_x) - 6.0 * self._spring_vel_x) * dt
        self._spring_sway_x = clamp(self._spring_sway_x + self._spring_vel_x * dt, -24.0, 24.0)
        self._spring_vel_z += (-36.0 * (self._spring_sway_z - wind_z) - 6.0 * self._spring_vel_z) * dt
        self._spring_sway_z = clamp(self._spring_sway_z + self._spring_vel_z * dt, -24.0, 24.0)

        # Rastro fluido de cabelo no espaço do mundo (+X = direita na tela, +Z = direção da câmera):
        # Quando anda para direita (+move_dx), o cabelo esvoaça para esquerda (-X)!
        # Quando anda para frente (+move_dy), o cabelo esvoaça para trás (-Z)!
        breeze = 0.018 + wind_speed * 0.0022
        tgt_hx = clamp(-move_dx * 1.85 + math.sin(self.time * 1.95) * breeze - self._yaw_vel * 0.00045, -0.16, 0.16)
        tgt_hz = clamp(-move_dy * 1.65 + math.cos(self.time * 1.55) * breeze * 0.75 - (0.045 if action == "walk" else 0.0), -0.16, 0.16)
        tgt_hy = clamp(-hips_vel_y * 0.18 + (0.025 if action == "dance" else 0.0), -0.05, 0.06)
        self._hair_vel_x += (-42.0 * (self.hair_trail_x - tgt_hx) - 7.5 * self._hair_vel_x) * dt
        self.hair_trail_x = clamp(self.hair_trail_x + self._hair_vel_x * dt, -0.19, 0.19)
        self._hair_vel_z += (-42.0 * (self.hair_trail_z - tgt_hz) - 7.5 * self._hair_vel_z) * dt
        self.hair_trail_z = clamp(self.hair_trail_z + self._hair_vel_z * dt, -0.19, 0.19)
        self._hair_vel_y += (-48.0 * (self.hair_bounce_y - tgt_hy) - 8.0 * self._hair_vel_y) * dt
        self.hair_bounce_y = clamp(self.hair_bounce_y + self._hair_vel_y * dt, -0.06, 0.07)
        tgt_flare = clamp(abs(self._yaw_vel) / 140.0, 0.0, 1.0) * 0.075
        self.hair_flare += (tgt_flare - self.hair_flare) * clamp(dt * 6.0, 0.0, 1.0)

        self.solve_fk()

    def solve_fk(self) -> None:
        """Resolve todas as matrizes globais dos nós, matrizes de skinning e pesos de morph targets."""
        model = self.model
        hb = model.humanoid_bones

        # Mapa inverso node_idx -> rotação delta Euler
        # VRM 1.0 olha +Z (braço esq = +X); VRM 0.x olha -Z (braço esq = -X) -> inverte sinais de X e Z para VRM 0.x!
        xz_sign = 1.0 if model.is_vrm1 else -1.0
        node_rot_delta: dict[int, np.ndarray] = {}
        for bname, euler in self._cur_euler.items():
            ni = hb.get(bname)
            if ni is not None:
                node_rot_delta[ni] = _quat_from_euler_xyz(
                    float(euler[0]) * xz_sign,
                    float(euler[1]),
                    float(euler[2]) * xz_sign,
                )

        # Aplica balanço físico nos nós das cadeias VRMC_springBone (cabelo / fitas / saia!)
        for chain_i, chain in enumerate(model.springs):
            phase_off = math.sin(self.time * 2.6 + chain_i * 0.7) * 3.5
            for depth_i, ni in enumerate(chain.joints):
                if ni in node_rot_delta:
                    continue
                amp = clamp((depth_i + 1) * 0.35, 0.25, 1.15)
                node_rot_delta[ni] = _quat_from_euler_xyz(
                    (self._spring_sway_z + phase_off) * amp * 0.65 * xz_sign,
                    0.0,
                    (self._spring_sway_x + phase_off) * amp * 0.55 * xz_sign,
                )

        # Aplica rotação celeste suave no Halo Dourado atrás da cabeça (Dungeon Squad!)
        if self._halo_node >= 0:
            node_rot_delta[self._halo_node] = _quat_from_euler_xyz(
                math.sin(self.time * 1.8) * 3.0,
                math.cos(self.time * 1.4) * 4.0,
                (self.time * 16.0) % 360.0,
            )

        # Escala estilizada opcional para VRMs externos aproximarem proporções compactas estilo Dungeon Squad
        bone_scale_mul: dict[int, np.ndarray] = {}
        if self.stylized_proportions and not self._is_ds_builtin:
            scale_map = {
                "head": (1.20, 1.18, 1.18),
                "spine": (0.88, 0.94, 0.90),
                "chest": (1.16, 1.00, 1.18),
                "leftUpperLeg": (1.20, 0.92, 1.18),
                "rightUpperLeg": (1.20, 0.92, 1.18),
            }
            for bname, sm in scale_map.items():
                bi = hb.get(bname)
                if bi is not None:
                    bone_scale_mul[bi] = np.array(sm, dtype=np.float32)

        hips_node = hb.get("hips", -1)
        # Giro total 360° aplicado na raiz (corrige +180° automaticamente para VRM 0.x que olha -Z!)
        base_facing = 0.0 if model.is_vrm1 else 180.0
        root_yaw_q = _quat_from_euler_xyz(0.0, self.yaw_deg + self._spin_offset_deg + base_facing, 0.0)
        root_mat = _mat4_from_trs(np.zeros(3, dtype=np.float32), root_yaw_q, np.ones(3, dtype=np.float32))

        world = self.world_matrices
        local_mats: list[np.ndarray] = [np.eye(4, dtype=np.float32)] * len(model.nodes)
        for ni in self._topo_order:
            n = model.nodes[ni]
            t = n.translation
            if ni == hips_node:
                t = t + self.hips_offset
            q = n.rotation
            if ni in node_rot_delta:
                q = _quat_mul(q, node_rot_delta[ni])
            sc = n.scale * bone_scale_mul[ni] if ni in bone_scale_mul else n.scale
            local_m = _mat4_from_trs(t, q, sc)
            local_mats[ni] = local_m
            if n.parent >= 0:
                world[ni] = world[n.parent] @ local_m
            else:
                world[ni] = root_mat @ local_m

        # Passo 2: Aplica restrições VRM 1.0 (`VRMC_node_constraint`: aim / roll) e propaga para os filhos (mangas/ombros!)
        if model.constraints:
            nodes = model.nodes

            def _propagate(parent_i: int) -> None:
                stack = list(nodes[parent_i].children)
                while stack:
                    ch = stack.pop()
                    world[ch] = world[nodes[ch].parent] @ local_mats[ch]
                    stack.extend(nodes[ch].children)

            for c in model.constraints:
                if c.kind == "aim" and 0 <= c.source < len(nodes):
                    n = nodes[c.node]
                    p_mat = world[n.parent] if n.parent >= 0 else root_mat
                    src_world = world[c.source][:3, 3]
                    dst_world = world[c.node][:3, 3]
                    dir_world = src_world - dst_world
                    dn = float(np.linalg.norm(dir_world))
                    if dn > 1e-5:
                        dir_world /= dn
                        dir_local = p_mat[:3, :3].T @ dir_world
                        dir_local /= max(float(np.linalg.norm(dir_local)), 1e-6)
                        aim_v = _AIM_AXIS_VECS.get(c.axis, _AIM_AXIS_VECS["PositiveX"])
                        q_aim = _quat_from_two_vecs(aim_v, dir_local)
                        local_m = _mat4_from_trs(n.translation, q_aim, n.scale)
                        local_mats[c.node] = local_m
                        world[c.node] = p_mat @ local_m
                        _propagate(c.node)
                elif c.kind in ("roll", "rotation") and c.source in node_rot_delta:
                    n = nodes[c.node]
                    p_mat = world[n.parent] if n.parent >= 0 else root_mat
                    q_src = node_rot_delta[c.source]
                    q_blend = np.array(
                        [q_src[0] * c.weight, q_src[1] * c.weight, q_src[2] * c.weight, 1.0 - (1.0 - q_src[3]) * c.weight],
                        dtype=np.float32,
                    )
                    q_blend /= max(float(np.linalg.norm(q_blend)), 1e-6)
                    local_m = _mat4_from_trs(n.translation, _quat_mul(n.rotation, q_blend), n.scale)
                    local_mats[c.node] = local_m
                    world[c.node] = p_mat @ local_m
                    _propagate(c.node)

        # Calcula matrizes finais de skinning (world[joint] @ inv_bind) para cada skin
        self.skin_matrices = []
        for sk in model.skins:
            jm = np.empty((len(sk.joints), 4, 4), dtype=np.float32)
            for j_i, node_i in enumerate(sk.joints):
                jm[j_i] = world[node_i] @ sk.inv_bind_matrices[j_i]
            self.skin_matrices.append(jm)

        # Resolve pesos finais dos morph targets por malha a partir das expressões VRM
        morph_map: dict[int, dict[int, float]] = {}
        for ename, w in self.expr_weights.items():
            if w <= 0.005:
                continue
            for mesh_i, morph_i, bind_w in model.expressions.get(ename, []):
                m_dict = morph_map.setdefault(mesh_i, {})
                m_dict[morph_i] = clamp(m_dict.get(morph_i, 0.0) + w * bind_w, 0.0, 1.0)
        self.mesh_morph_weights = morph_map
