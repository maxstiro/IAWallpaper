"""SKELETON — Esqueleto hierárquico 2D de 18 ossos (FK, blend suave de poses, ciclo de caminhada real e física de mola).

Unidades normalizadas:
  - Origem (0, 0) = ponto exato do chão entre os pés.
  - +x = frente/direita (espelhado via scale(-1, 1) quando facing < 0), -y = para cima.
  - Altura total canônica H = 1.0 (topo da cabeça em y = -1.0, sola dos pés em y = 0.0).
  - Convenção de ângulos (graus, medidos via atan2(dx, dy) para ossos descendentes e atan2(dx, -dy) para ascendentes):
      * Ossos descendentes (pernas, braços): 0° = reto para baixo; +θ = para frente/direita (+x); -θ = para trás/esquerda (-x).
      * Ossos ascendentes (coluna, peito, pescoço, cabeça): 0° = reto para cima; +θ = inclinado para frente/direita (+x).
  - Auto-aterramento (ground pinning): em ações no chão, o pé mais baixo é travado em y = 0.0,
    tornando matematicamente impossível a personagem flutuar!
"""

from dataclasses import dataclass
import math

from ..mathutil import clamp


@dataclass
class RigProportions:
    """Proporções anatômicas normalizadas (H = 1.0), calibráveis automaticamente pelo AutoRigger."""

    len_thigh: float = 0.23
    len_shin: float = 0.24
    len_spine: float = 0.14
    len_chest: float = 0.15
    len_neck: float = 0.05
    len_head: float = 0.15
    len_upper_arm: float = 0.155
    len_forearm: float = 0.155
    hip_half_w: float = 0.042
    shoulder_half_w: float = 0.072


@dataclass
class BoneWorld:
    name: str
    x: float
    y: float
    end_x: float
    end_y: float
    angle_deg: float
    length: float
    upward: bool = False


@dataclass
class PoseTargets:
    pelvis_dx: float = 0.0
    pelvis_dy: float = 0.0
    spine_rot: float = 0.0
    chest_rot: float = 0.0
    head_rot: float = 0.0
    thigh_l: float = -4.0
    shin_l: float = 2.0
    thigh_r: float = 5.0
    shin_r: float = -2.0
    arm_l: float = -16.0
    forearm_l: float = 10.0
    arm_r: float = 18.0
    forearm_r: float = -16.0
    ground_pin: bool = True


def _end_point(x: float, y: float, length: float, angle_deg: float, down: bool = True) -> tuple[float, float]:
    """Calcula ponta do osso; angle_deg=0 aponta reto para baixo (down=True) ou para cima (down=False)."""
    rad = math.radians(angle_deg)
    if down:
        return x + math.sin(rad) * length, y + math.cos(rad) * length
    return x + math.sin(rad) * length, y - math.cos(rad) * length


class CharacterSkeleton:
    """Motor esquelético 2D com blend suave entre ações, física de mola para cabelo/saia e auto-aterramento."""

    def __init__(self, proportions: RigProportions | None = None):
        self.props: RigProportions = proportions or RigProportions()
        self.time: float = 0.0
        self.walk_phase: float = 0.0
        self.action_timer: float = 0.0

        # Estado atual suavizado dos ângulos (graus)
        self.pose = PoseTargets()

        # Física de mola secundária (cabelo traseiro + saia)
        self.hair_angle: float = 0.0
        self.hair_vel: float = 0.0
        self.skirt_angle: float = 0.0
        self.skirt_vel: float = 0.0

        # Ossos resolvidos no último frame
        self.bones: dict[str, BoneWorld] = {}
        self.solve_fk()

    def set_proportions(self, proportions: RigProportions | None) -> None:
        self.props = proportions or RigProportions()
        self.solve_fk()

    def _compute_target_pose(
        self,
        action: str,
        look_x: float,
        look_y: float,
        asleep: bool,
        raining: bool,
        caressing: bool,
    ) -> PoseTargets:
        t = self.time
        p = PoseTargets()
        breath = math.sin(t * (1.35 if asleep else 2.2))

        if asleep or action == "sleep":
            # Sentada/enrolada relaxada na almofada (joelhos dobrados à frente, pés recolhidos atrás)
            p.pelvis_dy = 0.19
            p.spine_rot = 9.0 + breath * 1.6
            p.chest_rot = 7.0 + breath * 1.4
            p.head_rot = 16.0 + math.sin(t * 1.1) * 3.0
            p.thigh_l = 64.0
            p.shin_l = -88.0
            p.thigh_r = 52.0
            p.shin_r = -80.0
            p.arm_l = 18.0
            p.forearm_l = 28.0
            p.arm_r = 24.0
            p.forearm_r = 24.0
            p.ground_pin = False
            return p

        if action == "walk":
            # Ciclo de caminhada anatômico real (+x = frente; joelho dobra APENAS para trás: shin <= 0!)
            ph = self.walk_phase
            s = math.sin(ph)
            c = math.cos(ph)

            # Perna esquerda (avança para +x quando s > 0; dobra joelho para trás no swing quando c < 0)
            p.thigh_l = s * 25.0
            p.shin_l = -max(0.0, -c) * 36.0 - 4.0
            # Perna direita (fase oposta de pi radianos)
            p.thigh_r = -s * 25.0
            p.shin_r = -max(0.0, c) * 36.0 - 4.0

            # Pelve sobe na fase de passagem e inclina levemente para frente
            p.pelvis_dy = -abs(c) * 0.020
            p.pelvis_dx = s * 0.010
            p.spine_rot = 4.0 + s * 2.0
            p.chest_rot = 2.0 - s * 2.5
            p.head_rot = -3.0 + look_x * 6.0 + math.sin(ph - 0.6) * 2.4

            # Braços balançam em oposição às pernas (cotovelo dobra levemente para frente: +forearm)
            p.arm_l = -s * 24.0 - 8.0
            p.forearm_l = 14.0 + max(0.0, -s) * 18.0
            p.arm_r = s * 24.0 + 8.0
            p.forearm_r = 14.0 + max(0.0, s) * 18.0
        elif action == "sit_work":
            # Sentada elegante trabalhando no notebook (joelhos dobrados à frente + antebraços digitando!)
            tap = math.sin(t * 11.0)
            p.pelvis_dy = 0.135
            p.spine_rot = 6.5 + breath * 1.2
            p.chest_rot = 4.0
            p.head_rot = 8.0 + look_x * 5.0
            p.thigh_l = 52.0
            p.shin_l = -58.0
            p.thigh_r = 44.0
            p.shin_r = -52.0
            p.arm_l = 28.0 + tap * 2.5
            p.forearm_l = 38.0 + tap * 5.5
            p.arm_r = 32.0 - tap * 2.5
            p.forearm_r = 36.0 - tap * 5.5
            p.ground_pin = True
        elif action == "wave":
            # Aceno animado com o braço direito erguido para cima e para fora (+134°)!
            w = math.sin(t * 8.5)
            p.pelvis_dx = math.sin(t * 2.8) * 0.014
            p.spine_rot = -3.0 + math.sin(t * 2.8) * 2.5
            p.chest_rot = -2.0
            p.head_rot = 5.0 + w * 4.5 + look_x * 5.0
            p.thigh_l = -6.0
            p.shin_l = 3.0
            p.thigh_r = 7.0
            p.shin_r = -3.0
            p.arm_l = -20.0
            p.forearm_l = 22.0
            p.arm_r = 132.0 + w * 10.0
            p.forearm_r = 16.0 + w * 24.0
        elif action == "stretch":
            # Alongamento gracioso erguendo os DOIS braços para o alto em V e arqueando o tronco!
            arch = math.sin(clamp(self.action_timer / 4.0, 0.0, 1.0) * math.pi)
            p.pelvis_dy = -arch * 0.018
            p.spine_rot = -arch * 6.5
            p.chest_rot = -arch * 5.5
            p.head_rot = -arch * 8.5
            p.thigh_l = -5.0
            p.shin_l = 2.0
            p.thigh_r = 6.0
            p.shin_r = -2.0
            p.arm_l = -14.0 - arch * 134.0
            p.forearm_l = 8.0 + arch * 18.0
            p.arm_r = 14.0 + arch * 134.0
            p.forearm_r = -8.0 - arch * 18.0
        elif action == "music_sway":
            # Dança rítmica suave acompanhando música
            beat = math.sin(t * 5.2)
            p.pelvis_dx = beat * 0.022
            p.pelvis_dy = abs(beat) * 0.012
            p.spine_rot = -beat * 6.0
            p.chest_rot = beat * 4.2
            p.head_rot = beat * 7.0 + look_x * 4.0
            p.thigh_l = -7.0 - beat * 5.0
            p.shin_l = -abs(beat) * 6.0
            p.thigh_r = 7.0 - beat * 5.0
            p.shin_r = -abs(beat) * 6.0
            p.arm_l = -24.0 - beat * 22.0
            p.forearm_l = 32.0 + beat * 16.0
            p.arm_r = 24.0 - beat * 22.0
            p.forearm_r = -28.0 + beat * 16.0
        else:
            # Idle maduro e vivo: contrapposto leve, respiração orgânica, cabeça seguindo o cursor
            sway = math.sin(t * 1.25)
            p.pelvis_dx = sway * 0.014
            p.pelvis_dy = breath * 0.004
            p.spine_rot = -sway * 2.4 + breath * 0.8
            p.chest_rot = sway * 1.6 + breath * 0.9
            p.head_rot = look_x * 9.0 + math.sin(t * 1.5 - 0.7) * 2.2 + (6.0 if caressing else 0.0)
            p.thigh_l = -5.0 - sway * 1.8
            p.shin_l = 2.0
            p.thigh_r = 6.0 - sway * 1.8
            p.shin_r = -2.0
            p.arm_l = -15.0 - sway * 3.5
            p.forearm_l = 10.0 + breath * 2.5
            p.arm_r = 20.0 + sway * 3.5
            p.forearm_r = -18.0 - breath * 2.5

        # Sobrepõe braço direito segurando o guarda-chuva erguido à frente na chuva
        if raining and action not in ("sit_work", "sleep"):
            p.arm_r = 56.0 + math.sin(t * 2.2) * 3.0
            p.forearm_r = 48.0

        return p

    def update(
        self,
        dt: float,
        action: str,
        walk_phase: float,
        action_timer: float,
        look_x: float = 0.0,
        look_y: float = 0.0,
        vel_x: float = 0.0,
        wind_speed: float = 6.0,
        asleep: bool = False,
        raining: bool = False,
        caressing: bool = False,
    ) -> dict[str, BoneWorld]:
        dt = clamp(dt, 0.0, 0.1)
        self.time += dt
        self.walk_phase = walk_phase
        self.action_timer = action_timer

        target = self._compute_target_pose(action, look_x, look_y, asleep, raining, caressing)
        k = 1.0 - math.exp(-dt * (12.0 if action == "walk" else 7.5))

        for field_name in (
            "pelvis_dx", "pelvis_dy", "spine_rot", "chest_rot", "head_rot",
            "thigh_l", "shin_l", "thigh_r", "shin_r",
            "arm_l", "forearm_l", "arm_r", "forearm_r",
        ):
            cur = getattr(self.pose, field_name)
            dst = getattr(target, field_name)
            setattr(self.pose, field_name, cur + (dst - cur) * k)
        self.pose.ground_pin = target.ground_pin

        # Física de mola para cabelo e saia (reage à velocidade da caminhada + vento)
        wind_force = math.sin(self.time * 2.3) * (3.0 + wind_speed * 0.35) - vel_x * 48.0
        self.hair_vel += (-42.0 * (self.hair_angle - wind_force) - 6.5 * self.hair_vel) * dt
        self.hair_angle = clamp(self.hair_angle + self.hair_vel * dt, -26.0, 26.0)

        skirt_force = -vel_x * 26.0 + math.sin(self.time * 2.6 + 0.8) * (1.8 + wind_speed * 0.2)
        self.skirt_vel += (-55.0 * (self.skirt_angle - skirt_force) - 7.5 * self.skirt_vel) * dt
        self.skirt_angle = clamp(self.skirt_angle + self.skirt_vel * dt, -16.0, 16.0)

        return self.solve_fk()

    def solve_fk(self) -> dict[str, BoneWorld]:
        """Resolve Forward Kinematics dos 18 ossos com auto-aterramento exato no chão (y=0)."""
        p = self.pose
        pr = self.props
        pelvis_base_y = -(pr.len_thigh + pr.len_shin)
        px = p.pelvis_dx
        py = pelvis_base_y + p.pelvis_dy

        # Pernas a partir dos quadris esquerdo/direito
        hl_x, hl_y = px - pr.hip_half_w, py
        kl_x, kl_y = _end_point(hl_x, hl_y, pr.len_thigh, p.thigh_l, down=True)
        fl_x, fl_y = _end_point(kl_x, kl_y, pr.len_shin, p.thigh_l + p.shin_l, down=True)

        hr_x, hr_y = px + pr.hip_half_w, py
        kr_x, kr_y = _end_point(hr_x, hr_y, pr.len_thigh, p.thigh_r, down=True)
        fr_x, fr_y = _end_point(kr_x, kr_y, pr.len_shin, p.thigh_r + p.shin_r, down=True)

        # Auto-aterramento: em ações em pé/caminhada, o pé mais baixo fica exatamente em y = 0.0!
        y_shift = -max(fl_y, fr_y) if p.ground_pin else 0.0
        py += y_shift
        hl_y += y_shift
        kl_y += y_shift
        fl_y += y_shift
        hr_y += y_shift
        kr_y += y_shift
        fr_y += y_shift

        # Coluna -> Peito -> Pescoço -> Cabeça
        wx, wy = _end_point(px, py, pr.len_spine, p.spine_rot, down=False)
        cx, cy = _end_point(wx, wy, pr.len_chest, p.spine_rot + p.chest_rot, down=False)
        nx, ny = _end_point(cx, cy, pr.len_neck, p.spine_rot + p.chest_rot + p.head_rot * 0.35, down=False)
        head_ang = p.spine_rot + p.chest_rot + p.head_rot
        hx, hy = _end_point(nx, ny, pr.len_head, head_ang, down=False)

        # Ombros rotacionados pelo peito
        chest_rad = math.radians(p.spine_rot + p.chest_rot)
        dx_sh = math.cos(chest_rad) * pr.shoulder_half_w
        dy_sh = math.sin(chest_rad) * pr.shoulder_half_w
        sh_l_x, sh_l_y = cx - dx_sh, cy - dy_sh
        sh_r_x, sh_r_y = cx + dx_sh, cy + dy_sh

        el_l_x, el_l_y = _end_point(sh_l_x, sh_l_y, pr.len_upper_arm, p.spine_rot + p.chest_rot + p.arm_l, down=True)
        ha_l_x, ha_l_y = _end_point(el_l_x, el_l_y, pr.len_forearm, p.spine_rot + p.chest_rot + p.arm_l + p.forearm_l, down=True)

        el_r_x, el_r_y = _end_point(sh_r_x, sh_r_y, pr.len_upper_arm, p.spine_rot + p.chest_rot + p.arm_r, down=True)
        ha_r_x, ha_r_y = _end_point(el_r_x, el_r_y, pr.len_forearm, p.spine_rot + p.chest_rot + p.arm_r + p.forearm_r, down=True)

        # Cabelo traseiro & saia com física de mola
        hair_end_x, hair_end_y = _end_point(nx, ny, 0.34, head_ang + self.hair_angle, down=True)
        skirt_end_x, skirt_end_y = _end_point(px, py, 0.16, p.spine_rot * 0.5 + self.skirt_angle, down=True)

        self.bones = {
            "pelvis":      BoneWorld("pelvis", px, py, wx, wy, p.spine_rot, pr.len_spine, upward=True),
            "chest":       BoneWorld("chest", wx, wy, cx, cy, p.spine_rot + p.chest_rot, pr.len_chest, upward=True),
            "neck":        BoneWorld("neck", cx, cy, nx, ny, p.spine_rot + p.chest_rot, pr.len_neck, upward=True),
            "head":        BoneWorld("head", nx, ny, hx, hy, head_ang, pr.len_head, upward=True),
            "hair_back":   BoneWorld("hair_back", nx, ny, hair_end_x, hair_end_y, head_ang + self.hair_angle, 0.34, upward=False),
            "skirt":       BoneWorld("skirt", px, py, skirt_end_x, skirt_end_y, p.spine_rot * 0.5 + self.skirt_angle, 0.16, upward=False),
            "thigh_l":     BoneWorld("thigh_l", hl_x, hl_y, kl_x, kl_y, p.thigh_l, pr.len_thigh, upward=False),
            "shin_l":      BoneWorld("shin_l", kl_x, kl_y, fl_x, fl_y, p.thigh_l + p.shin_l, pr.len_shin, upward=False),
            "thigh_r":     BoneWorld("thigh_r", hr_x, hr_y, kr_x, kr_y, p.thigh_r, pr.len_thigh, upward=False),
            "shin_r":      BoneWorld("shin_r", kr_x, kr_y, fr_x, fr_y, p.thigh_r + p.shin_r, pr.len_shin, upward=False),
            "upper_arm_l": BoneWorld("upper_arm_l", sh_l_x, sh_l_y, el_l_x, el_l_y, p.spine_rot + p.chest_rot + p.arm_l, pr.len_upper_arm, upward=False),
            "forearm_l":   BoneWorld("forearm_l", el_l_x, el_l_y, ha_l_x, ha_l_y, p.spine_rot + p.chest_rot + p.arm_l + p.forearm_l, pr.len_forearm, upward=False),
            "upper_arm_r": BoneWorld("upper_arm_r", sh_r_x, sh_r_y, el_r_x, el_r_y, p.spine_rot + p.chest_rot + p.arm_r, pr.len_upper_arm, upward=False),
            "forearm_r":   BoneWorld("forearm_r", el_r_x, el_r_y, ha_r_x, ha_r_y, p.spine_rot + p.chest_rot + p.arm_r + p.forearm_r, pr.len_forearm, upward=False),
        }
        return self.bones
