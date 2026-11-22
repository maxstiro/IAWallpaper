"""Camada sense: percepção de contexto do PC, ciclo solar/circadiano, clima real e rotina diária."""

from .circadian import CircadianState, compute_circadian
from .routine import RoutineTracker
from .senses import ACTIVITY_APPS, ActivityTracker, ContextSenses, detect_activity
from .weather import WeatherService, WeatherState

__all__ = [
    "CircadianState",
    "compute_circadian",
    "RoutineTracker",
    "ACTIVITY_APPS",
    "ActivityTracker",
    "ContextSenses",
    "detect_activity",
    "WeatherService",
    "WeatherState",
]
