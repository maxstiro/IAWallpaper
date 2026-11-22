"""DIRECTOR — Liga os motores da rede LIF, memória episódica, clima e contexto ao comportamento vivo da waifu."""

from dataclasses import dataclass
import random
import time

from ..core.conditioning import Conditioning
from ..core.emotion import EmotionState
from ..core.episodic import ACTIONS, EpisodicMemory
from ..core.homeostasis import Drives
from ..core.nervous_system import Brain
from ..core.persona import Persona
from ..mathutil import clamp
from ..sense.circadian import CircadianState
from ..sense.weather import WeatherState


@dataclass
class DirectorOutputs:
    outfit: str = "casual"
    asleep: bool = False
    whisper_text: str = ""
    whisper_alpha: float = 0.0
    burst_fx: str | None = None    # "heart" | "sparkle" | "note" | "zzz" | None


class BehaviorDirector:
    """Traduz decisões neurais + aprendizado em trajes dinâmicos, sussurros contextuais, sono e partículas."""

    def __init__(
        self,
        persona: Persona,
        brain: Brain,
        drives: Drives,
        conditioning: Conditioning,
        episodic: EpisodicMemory,
    ):
        self.persona = persona
        self.brain = brain
        self.drives = drives
        self.conditioning = conditioning
        self.episodic = episodic

        self.asleep: bool = False
        self.current_outfit: str = "casual"
        self.whisper_text: str = ""
        self._whisper_until: float = 0.0
        self._whisper_shown_at: float = 0.0
        self._last_action_at: float = 0.0
        self._last_caress_fx: float = 0.0
        self._last_music_fx: float = 0.0
        self._last_zzz_fx: float = 0.0
        self._pending_fx: str | None = None
        self._rng = random.Random(persona.seed + 303)

    def set_persona(self, persona: Persona) -> None:
        self.persona = persona

    def _pick_whisper(self, category: str) -> str:
        pool = self.persona.whispers.get(category) or self.persona.whispers.get("idle") or []
        return self._rng.choice(pool) if pool else ""

    def show_whisper(self, text: str, duration: float = 7.5, now: float | None = None) -> None:
        if not text:
            return
        t = time.monotonic() if now is None else now
        self.whisper_text = text
        self._whisper_shown_at = t
        self._whisper_until = t + duration

    def dismiss_whisper(self, now: float | None = None) -> None:
        t = time.monotonic() if now is None else now
        self._whisper_until = 0.0
        self.whisper_text = ""
        self.episodic.on_dismiss(now=t)
        self.brain.learn(-0.55)

    def on_caress(self, now: float | None = None) -> None:
        t = time.monotonic() if now is None else now
        if self.asleep:
            self.asleep = False
        self.drives.touched("caress", scale=0.45)
        self.drives.stimulate("caress", scale=0.5)
        self.conditioning.outcome(t, cues=("APPROACH", "RETURN"))
        self.episodic.on_positive_feedback()
        self.brain.learn(+0.85)
        if t - self._last_caress_fx >= 0.65:
            self._pending_fx = "heart"
            self._last_caress_fx = t
            if t > self._whisper_until:
                self.show_whisper(self._pick_whisper("caress"), duration=5.5, now=t)

    def on_poke(self, now: float | None = None) -> None:
        t = time.monotonic() if now is None else now
        if self.asleep:
            self.asleep = False
            self.show_whisper("Hmm...? Já acordei! ✨", duration=4.5, now=t)
        else:
            self.drives.touched("poke", scale=0.8)
            self.drives.stimulate("poke", scale=0.8)
            self.conditioning.outcome(t, cues=("APPROACH",))
            self.episodic.on_positive_feedback()
            self.brain.learn(+0.35)
            self._pending_fx = "sparkle"

    def on_gift(self, label: str = "", now: float | None = None) -> None:
        t = time.monotonic() if now is None else now
        self.asleep = False
        self.drives.touched("gift", scale=1.0)
        self.drives.stimulate("gift", scale=1.0)
        self.episodic.on_positive_feedback()
        self.brain.learn(+1.0)
        self._pending_fx = "heart"
        msg = f"Adorei {label}! Obrigada ♥" if label else "Obrigada pelo carinho! Fiquei super feliz ♥"
        self.show_whisper(msg, duration=6.5, now=t)

    def on_user_returned(self, now: float | None = None) -> None:
        t = time.monotonic() if now is None else now
        self.conditioning.set_cue("RETURN", True, t)
        self.show_whisper(self._pick_whisper("greet"), duration=7.0, now=t)
        self._pending_fx = "sparkle"

    def choose_contextual_outfit(
        self,
        activity: str,
        circadian: CircadianState,
        weather: WeatherState,
        outfit_override: str | None = None,
    ) -> str:
        if outfit_override and outfit_override in self.persona.outfits:
            return outfit_override
        if self.asleep or circadian.period == "late_night":
            return "nightwear" if "nightwear" in self.persona.outfits else "casual"
        if weather.condition in ("rain", "storm"):
            return "rainy" if "rainy" in self.persona.outfits else "cozy"
        if activity in ("PROGRAMMING", "AI_STUDIO", "DESIGNING"):
            return "focus" if "focus" in self.persona.outfits else "casual"
        if circadian.period == "night" and self.drives.affinity >= 40.0 and "starlight" in self.persona.outfits:
            return "starlight"
        if activity == "MUSIC" or weather.condition in ("snow", "fog"):
            return "cozy" if "cozy" in self.persona.outfits else "casual"
        return "casual"

    def _whisper_category_for(self, activity: str, circadian: CircadianState, weather: WeatherState, emotion: EmotionState) -> str:
        if emotion.mood == "pouty":
            return "pout"
        if emotion.mood == "sleepy":
            return "sleepy"
        if weather.condition == "storm":
            return "storm"
        if weather.condition == "rain" and self._rng.random() < 0.6:
            return "rain"
        if activity == "AI_STUDIO":
            return "ai_craft"
        if activity in ("PROGRAMMING", "DESIGNING"):
            return "work"
        if activity == "MUSIC":
            return "music"
        if activity == "GAMING":
            return "gaming"
        if circadian.period in ("night", "late_night"):
            return "night"
        return "idle"

    def step(
        self,
        now: float,
        activity: str,
        circadian: CircadianState,
        weather: WeatherState,
        emotion: EmotionState,
        decision_rates: dict[str, float],
        whispers_enabled: bool = True,
        outfit_override: str | None = None,
        test_mode: bool = False,
    ) -> DirectorOutputs:
        """Executa um passo decisório integrando rede LIF, sono, trajes e memória episódica."""
        # 1. Ciclo de sono (com consolidação de memória ao adormecer)
        doze_hz = float(decision_rates.get("DOZE_OFF", 0.0))
        if not self.asleep and (self.drives.sleepy() or (doze_hz > 10.5 and self.drives.energy < 0.35)):
            self.asleep = True
            self.episodic.consolidate()
            if whispers_enabled:
                self.show_whisper(self._pick_whisper("sleepy"), duration=5.5, now=now)
        elif self.asleep and self.drives.rested():
            self.asleep = False

        # 2. Traje dinâmico contextual
        self.current_outfit = self.choose_contextual_outfit(activity, circadian, weather, outfit_override)

        # 3. Efeitos periódicos de música e sono
        burst = self._pending_fx
        self._pending_fx = None
        if burst is None:
            if self.asleep and now - self._last_zzz_fx >= 3.2:
                burst = "zzz"
                self._last_zzz_fx = now
            elif activity == "MUSIC" and not self.asleep and now - self._last_music_fx >= 4.2:
                burst = "note"
                self._last_music_fx = now

        # 4. Ações autônomas guiadas pelos motores de decisão + Bandit contextual
        cooldown = 12.0 if test_mode else 55.0
        whisper_hz = float(decision_rates.get("WHISPER", 0.0))
        fx_hz = float(decision_rates.get("PLAY_FX", 0.0))
        if not self.asleep and (now - self._last_action_at >= cooldown) and (whisper_hz >= 2.2 or fx_hz >= 2.8):
            ctx = EpisodicMemory.context(activity, circadian.period, weather.condition, emotion.mood)
            allowed = list(ACTIONS)
            if not whispers_enabled:
                allowed = [a for a in allowed if a != "whisper"]
            action = self.episodic.choose(ctx, allowed, epsilon=0.18)
            if action:
                self._last_action_at = now
                self.episodic.start(ctx, action, now=now)
                if action == "whisper" and whispers_enabled:
                    cat = self._whisper_category_for(activity, circadian, weather, emotion)
                    self.show_whisper(self._pick_whisper(cat), duration=7.5, now=now)
                elif action == "sparkle_fx":
                    burst = "sparkle"
                elif action == "pose_wave":
                    burst = "heart" if self.drives.affinity >= 35.0 else "sparkle"

        # 5. Alpha suave da bolha de sussurro
        alpha = 0.0
        if self.whisper_text and now < self._whisper_until:
            fade_in = clamp((now - self._whisper_shown_at) / 0.45, 0.0, 1.0)
            fade_out = clamp((self._whisper_until - now) / 0.65, 0.0, 1.0)
            alpha = min(fade_in, fade_out)
        elif now >= self._whisper_until:
            self.whisper_text = ""

        return DirectorOutputs(
            outfit=self.current_outfit,
            asleep=self.asleep,
            whisper_text=self.whisper_text if whispers_enabled else "",
            whisper_alpha=alpha if whispers_enabled else 0.0,
            burst_fx=burst,
        )
