"""Ingesta de miniF2F (Lean 4) a data/minif2f_{valid,test}.jsonl.

Fuente: la version de DeepSeek-Prover-V1.5, que ya viene portada a Lean 4 + Mathlib.
Se fija por hash para que nadie la cambie sin darse cuenta (RNF-2).

    python -m src.data

Regla D5.1: el split `test` se escribe a disco pero el runner se niega a abrirlo
sin --abrir-test. Todo el ajuste va sobre `valid` (dev).
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path

SOURCE_URL = (
    "https://raw.githubusercontent.com/deepseek-ai/DeepSeek-Prover-V1.5/"
    "main/datasets/minif2f.jsonl"
)
SOURCE_SHA256 = "d6654c88476ff14db19d57dea25bd955a240525fb52171e460f89d98f83d7dd5"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# Todos los problemas comparten este encabezado. Cada REPL lo carga una vez y los
# problemas corren sobre ese entorno (ver repl_pool.py).
HEADER = (
    "import Mathlib\nimport Aesop\n\nset_option maxHeartbeats 400000\n\n"
    "open BigOperators Real Nat Topology Rat\n"
)
# Nota: la fuente trae maxHeartbeats 0 (sin limite). Se pone 400000 para que un
# `simp` que no termina sea TIMEOUT del kernel y no un cuelgue del proceso.


def _clean_nl(prefix: str) -> str:
    return re.sub(r"^/--\s*|\s*-/\s*$", "", prefix.strip()).strip()


def normalize(row: dict) -> dict:
    fs = row["formal_statement"].rstrip()
    # Se guarda el enunciado SIN el `:= by` final: cada agente pone su propia prueba.
    fs = re.sub(r":=\s*by\s*(sorry)?\s*$", "", fs).rstrip()
    return {
        "problem_id": row["name"],
        "split": row["split"],
        "nl_statement": _clean_nl(row["informal_prefix"]),
        "formal_statement": fs,
        "theorem_name": row["name"],
    }


def load(split: str) -> list[dict]:
    path = DATA_DIR / f"minif2f_{split}.jsonl"
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def ingest() -> None:
    raw = urllib.request.urlopen(SOURCE_URL, timeout=60).read()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != SOURCE_SHA256:
        raise SystemExit(
            f"la fuente cambio: sha256={sha}\n"
            f"si el cambio es a proposito, actualizar SOURCE_SHA256 y anotarlo en decisions.md"
        )
    rows = [normalize(json.loads(l)) for l in raw.decode("utf-8").splitlines() if l.strip()]
    DATA_DIR.mkdir(exist_ok=True)
    for split in ("valid", "test"):
        part = [r for r in rows if r["split"] == split]
        with open(DATA_DIR / f"minif2f_{split}.jsonl", "w", encoding="utf-8") as f:
            for r in part:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{split}: {len(part)} problemas")


def check(split: str) -> None:
    """Cada enunciado con `sorry` tiene que compilar con NUESTRA Mathlib. Si no compila,
    ningun sistema lo puede resolver y solo mete ruido en la tasa. Corre en Docker."""
    from src.lean_repl import ReadyRepl
    from src.verify import verify

    repl = ReadyRepl(HEADER)
    bad = []
    try:
        for r in load(split):
            v = verify(r["formal_statement"] + " := by sorry", repl, allow_sorry=True)
            if not v.ok:
                bad.append((r["problem_id"], v.verdict, v.raw[:300]))
    finally:
        repl.close()
    for pid, verdict, raw in bad:
        print(f"{pid}: {verdict}\n{raw}\n")
    print(f"{split}: {len(load(split)) - len(bad)}/{len(load(split))} enunciados compilan")


if __name__ == "__main__":
    import sys

    check(sys.argv[2]) if sys.argv[1:2] == ["--check"] else ingest()
