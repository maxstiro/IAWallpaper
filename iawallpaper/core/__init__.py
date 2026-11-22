"""Camada core: cérebro neural pulsado (LIF), homeostase, condicionamento, memória episódica, emoção e personas.

Regra arquitetural: esta camada NUNCA importa Qt (PySide6) nem APIs do sistema operacional.
"""

from .conditioning import Conditioning
from .emotion import EmotionDecoder, EmotionState
from .episodic import EpisodicMemory
from .homeostasis import Drives
from .nervous_system import Brain, WaifuSpikingBrain
from .persona import Persona, load_persona, list_personas

__all__ = [
    "Brain",
    "WaifuSpikingBrain",
    "Drives",
    "Conditioning",
    "EpisodicMemory",
    "EmotionDecoder",
    "EmotionState",
    "Persona",
    "load_persona",
    "list_personas",
]
