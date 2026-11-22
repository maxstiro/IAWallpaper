"""Utilitários matemáticos e validação numérica estrita (anti-NaN/Inf)."""

import math


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Restringe x ao intervalo [lo, hi]."""
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def lerp(a: float, b: float, t: float) -> float:
    """Interpolação linear entre a e b."""
    return a + (b - a) * clamp(t, 0.0, 1.0)


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    """Interpolação Hermite suave (0..1) entre edge0 e edge1."""
    if edge1 == edge0:
        return 0.0
    t = clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def valor_real(val, minimo: float | None = None, maximo: float | None = None) -> float:
    """Valida que val é número finito (recusa bool, NaN, Inf e fora do intervalo)."""
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise ValueError(f"esperado número real, recebido {type(val).__name__}")
    f = float(val)
    if not math.isfinite(f):
        raise ValueError(f"número não finito: {val}")
    if minimo is not None and f < minimo:
        raise ValueError(f"{f} < {minimo}")
    if maximo is not None and f > maximo:
        raise ValueError(f"{f} > {maximo}")
    return f
