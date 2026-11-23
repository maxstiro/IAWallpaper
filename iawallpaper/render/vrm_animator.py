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

        # Estado de física secundária (oscilação suave para SpringBones de cabelo/roupas)
        self._spring_sway_x: float = 0.0
        self._spring_sway_z: float = 0.0
        self._spring_vel_x: float = 0.0
        self._spring_vel_z: float = 0.0

        # Ordem topológica (pai sempre antes de filho) para FK em passagem única
        self._topo_order: list[int] = self._build_topo_order()
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
            ph = self.walk_phase
            s = math.sin(ph)
            c = math.cos(ph)

            # Caminhada bípede feminina natural 3D (joelhos dobram SOMENTE para trás: rx > 0!)
            hips_off = (s * 0.018, abs(c) * 0.026 - 0.015, 0.0)
            e["hips"] = (3.5, s * 6.5, -s * 3.2)
            e["spine"] = (3.0, -s * 4.5, s * 2.0)
            e["chest"] = (2.0, -s * 5.0, s * 1.5)
            e["head"] = (-4.0, s * 3.0 + look_x * 12.0, -s * 1.5)

            e["leftUpperLeg"] = (-s * 28.0, 0.0, 1.5)
            e["leftLowerLeg"] = (max(0.0, -c) * 44.0 + 4.0, 0.0, 0.0)
            e["leftFoot"] = (-max(0.0, s) * 12.0 + max(0.0, -c) * 10.0, 0.0, 0.0)

            e["rightUpperLeg"] = (s * 28.0, 0.0, -1.5)
            e["rightLowerLeg"] = (max(0.0, c) * 44.0 + 4.0, 0.0, 0.0)
            e["rightFoot"] = (-max(0.0, -s) * 12.0 + max(0.0, c) * 10.0, 0.0, 0.0)

            # Braços em oposição natural às pernas
            e["leftUpperArm"] = (4.0, s * 22.0 - 4.0, -68.0)
            e["leftLowerArm"] = (0.0, -16.0 - max(0.0, -s) * 18.0, 0.0)
            e["rightUpperArm"] = (4.0, s * 22.0 + 4.0, 68.0)
            e["rightLowerArm"] = (0.0, 16.0 + max(0.0, s) * 18.0, 0.0)
        elif action == "wave":
            w = math.sin(t * 8.0)
            sway = math.sin(t * 2.4)
            hips_off = (sway * 0.014, breath * 0.005, 0.0)
            e["hips"] = (0.0, sway * 4.0, -sway * 3.0)
            e["spine"] = (-3.0, -sway * 3.0, sway * 3.0)
            e["chest"] = (-2.0, -5.0, 2.0)
            e["head"] = (-2.0 + look_y * 6.0, look_x * 14.0 + w * 4.0, 6.0 + w * 3.5)
            # Braço esquerdo relaxado + braço direito erguido acenando alegremente!
            e["leftUpperArm"] = (8.0, -10.0, -64.0)
            e["leftLowerArm"] = (0.0, -28.0, -8.0)
            e["rightShoulder"] = (0.0, 0.0, -16.0)
            e["rightUpperArm"] = (-14.0, 18.0, -44.0 + w * 10.0)
            e["rightLowerArm"] = (0.0, 24.0, -68.0 + w * 24.0)
            e["rightHand"] = (0.0, 0.0, w * 12.0)
        elif action in ("dance", "music_sway"):
            beat = math.sin(t * 5.2)
            half = math.sin(t * 2.6)
            hips_off = (half * 0.028, abs(beat) * 0.032 - 0.01, 0.0)
            e["hips"] = (2.0, half * 14.0, -half * 5.0)
            e["spine"] = (-3.0, -half * 10.0, half * 5.5)
            e["chest"] = (-3.0, -beat * 8.0, -half * 3.0)
            e["head"] = (-4.0 + beat * 4.0, half * 10.0, beat * 6.5)
            e["leftUpperArm"] = (-10.0, -22.0 + beat * 16.0, -26.0 - abs(beat) * 20.0)
            e["leftLowerArm"] = (0.0, -34.0 - beat * 18.0, 14.0)
            e["rightUpperArm"] = (-10.0, 22.0 + beat * 16.0, 26.0 + abs(beat) * 20.0)
            e["rightLowerArm"] = (0.0, 34.0 - beat * 18.0, -14.0)
            e["leftUpperLeg"] = (-10.0 - beat * 8.0, 0.0, 4.0)
            e["leftLowerLeg"] = (16.0 + abs(beat) * 14.0, 0.0, 0.0)
            e["rightUpperLeg"] = (-10.0 + beat * 8.0, 0.0, -4.0)
            e["rightLowerLeg"] = (16.0 + abs(beat) * 14.0, 0.0, 0.0)
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
            # Idle confiante e sedutor estilo Dungeon Squad: peso jogado num quadril, mão estilosa na cintura, olhar provocante!
            sway = math.sin(t * 1.35)
            hips_off = (0.018 + sway * 0.014, breath * 0.005, 0.0)
            e["hips"] = (2.0, 9.0 + sway * 4.5, -5.5 - sway * 2.5)
            e["spine"] = (-3.5 + breath * 1.5, -7.0 - sway * 3.0, 4.5 + sway * 2.0)
            e["chest"] = (-2.5 + breath * 2.0, -3.5 + sway * 2.5, 2.0)
            e["neck"] = (look_y * 5.0 - 2.0, look_x * 8.0 - 3.0, -3.0)
            e["head"] = (
                look_y * 7.0 + 3.0 + (6.0 if caressing else 0.0),
                look_x * 14.0 + math.sin(t * 1.4) * 3.0,
                -5.5 + sway * 2.5 + (6.0 if caressing else 0.0),
            )
            e["leftUpperLeg"] = (-6.0, 4.0, 5.5 + sway * 1.5)
            e["leftLowerLeg"] = (9.0, 0.0, 0.0)
            e["rightUpperLeg"] = (3.0, -4.0, -4.0 + sway * 1.5)
            e["rightLowerLeg"] = (4.0, 0.0, 0.0)
            # Braço esquerdo solto gracioso + braço direito dobrado estiloso próximo à cintura!
            e["leftUpperArm"] = (6.0, -10.0 - sway * 4.0, -62.0)
            e["leftLowerArm"] = (0.0, -24.0 + breath * 3.0, -8.0)
            e["rightShoulder"] = (0.0, 0.0, 6.0)
            e["rightUpperArm"] = (12.0, 22.0 + sway * 3.0, 48.0)
            e["rightLowerArm"] = (0.0, 62.0 - breath * 3.0, 24.0)
            e["rightHand"] = (0.0, 0.0, -18.0)

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
        self.yaw_deg = (self.yaw_deg + yaw_err * (1.0 - math.exp(-dt * 9.5))) % 360.0

        # 2. Blend exponencial suave das rotações ósseas
        targets, target_hips = self._compute_targets(action, look_x, look_y, asleep, raining, caressing)
        k = 1.0 - math.exp(-dt * (12.0 if action == "walk" else 7.5))
        for b in _ANIM_BONES:
            dst = np.array(targets.get(b, (0.0, 0.0, 0.0)), dtype=np.float32)
            self._cur_euler[b] += (dst - self._cur_euler[b]) * k
        self.hips_offset += (np.array(target_hips, dtype=np.float32) - self.hips_offset) * k

        # 3. Expressões faciais VRM (piscar + humor da rede LIF + carinho!)
        mood = "sleepy" if asleep else emotion.mood
        want_expr: dict[str, float] = {
            "blink": clamp(1.0 if asleep else (0.85 if caressing else blink_amount), 0.0, 1.0),
            "happy": 0.78 if (mood in ("happy", "affectionate") or action in ("wave", "dance") or caressing) else 0.18,
            "relaxed": 0.65 if mood in ("cozy", "calm", "sleepy") else 0.0,
            "angry": 0.55 if mood == "pouty" else 0.0,
            "sad": 0.35 if mood == "shy" else 0.0,
            "surprised": 0.0,
        }
        ek = 1.0 - math.exp(-dt * 10.0)
        for ename, target_w in want_expr.items():
            cur_w = self.expr_weights.get(ename, 0.0)
            self.expr_weights[ename] = cur_w + (target_w - cur_w) * ek

        # 4. Física de mola secundária para SpringBones (cabelos e saia reagem à brisa, passo e giro!)
        wind_x = math.sin(self.time * 2.1) * (4.0 + wind_speed * 0.45) - move_dx * 220.0
        wind_z = math.cos(self.time * 1.7) * (3.0 + wind_speed * 0.35) - (10.0 if action == "walk" else 0.0) - (14.0 if action == "dance" else 0.0)
        self._spring_vel_x += (-36.0 * (self._spring_sway_x - wind_x) - 6.0 * self._spring_vel_x) * dt
        self._spring_sway_x = clamp(self._spring_sway_x + self._spring_vel_x * dt, -24.0, 24.0)
        self._spring_vel_z += (-36.0 * (self._spring_sway_z - wind_z) - 6.0 * self._spring_vel_z) * dt
        self._spring_sway_z = clamp(self._spring_sway_z + self._spring_vel_z * dt, -24.0, 24.0)

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
            local_m = _mat4_from_trs(t, q, n.scale)
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
