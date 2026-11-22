"""Persistência atômica de arquivos JSON e JSONL com proteção anti-NaN e tolerância a corrupção."""

import json
import os
import shutil
import sys
from pathlib import Path


def _reject_non_finite(val: str):
    raise ValueError(f"constante não permitida no JSON: {val}")


def write_json(path: str | Path, data, indent: int | None = 2) -> None:
    """Grava JSON de forma atômica (arquivo temporário + os.replace), recusando NaN/Inf."""
    p = Path(path)
    text = json.dumps(data, ensure_ascii=False, indent=indent, allow_nan=False)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, p)


def read_json(path: str | Path, default=None):
    """Lê JSON tolerando arquivo ausente ou corrompido (arquiva o inválido como .corrompido)."""
    p = Path(path)
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.loads(f.read(), parse_constant=_reject_non_finite)
    except OSError:
        return default
    except ValueError:
        try:
            os.replace(p, p.with_name(p.name + ".corrompido"))
        except OSError:
            pass
        return default


def append_line(path: str | Path, line: str) -> None:
    """Acrescenta uma linha UTF-8 ao fim do arquivo."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8", newline="") as f:
        f.write(line.rstrip("\n") + "\n")


def read_lines(path: str | Path) -> list[str]:
    """Lê todas as linhas UTF-8 de um arquivo; lista vazia se não existir."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return []


def write_lines(path: str | Path, lines: list[str]) -> None:
    """Grava linhas atomicamente via arquivo temporário."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for line in lines:
            f.write(line.rstrip("\n") + "\n")
    os.replace(tmp, p)


def remove_tree(path: str | Path) -> list[str]:
    """Apaga uma pasta inteira; retorna lista de falhas (vazia se tudo deu certo)."""
    failures: list[str] = []
    if not Path(path).exists():
        return failures
    key = "onexc" if sys.version_info >= (3, 12) else "onerror"
    shutil.rmtree(path, **{key: lambda _fn, p, _err: failures.append(str(p))})
    return failures
