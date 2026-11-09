"""Ingesta de miniF2F (Lean 4) a data/minif2f_{valid,test}.jsonl.

Fuente: la version de DeepSeek-Prover-V1.5, que ya viene portada a Lean 4 + Mathlib.
Se fija por hash para que nadie la cambie sin darse cuenta (RNF-2).

    python -m src.data                 # miniF2F
    python -m src.data --test-set      # (re)genera data/test_set.v1.txt y lo compara con el hash
    python -m src.data --test-set-ids  # ids separados por coma, para run.py --problems
    python -m src.data --putnam        # PutnamBench -> data/putnambench.jsonl

Regla D5.1: el split `test` se escribe a disco pero el runner se niega a abrirlo
sin --abrir-test. Todo el ajuste va sobre `valid` (dev).
"""

from __future__ import annotations

import hashlib
import io
import json
import random
import re
import urllib.request
import zipfile
from collections import defaultdict
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


# --- Test set de la semana 10 -------------------------------------------------
# Muestra estratificada por fuente del split test. Se elige SOLO con los ids: el
# enunciado y la prueba no entran a la seleccion (sellado, D5.1).
TEST_SET_SEED = 10
TEST_SET_SIZE = 50
TEST_SET_PATH = DATA_DIR / "test_set.v1.txt"
TEST_SET_SHA256 = "43e9793670407e09612902fda36731583c65ae72a562033958730543e7bbef7f"


def stratum(pid: str) -> str:
    """Fuente del problema segun el id: mathd_algebra_478 -> mathd_algebra, amc12a_2003_p5 -> amc12."""
    if pid.startswith("mathd_"):
        return "_".join(pid.split("_")[:2])
    head = pid.split("_")[0]
    return {"amc12a": "amc12", "amc12b": "amc12", "imosl": "imo"}.get(head, head)


def test_ids() -> list[str]:
    with open(DATA_DIR / "minif2f_test.jsonl", encoding="utf-8") as f:
        return [json.loads(line)["problem_id"] for line in f]


def select_test_set(ids: list[str], n: int = TEST_SET_SIZE, seed: int = TEST_SET_SEED) -> list[str]:
    """Asignacion proporcional al tamano de cada fuente, minimo 2 por fuente."""
    by = defaultdict(list)
    for pid in sorted(ids):
        by[stratum(pid)].append(pid)
    rng = random.Random(seed)
    out = []
    for s in sorted(by):
        k = min(len(by[s]), max(2, round(n * len(by[s]) / len(ids))))
        out += rng.sample(by[s], k)
    return sorted(out)


def _ids_sha(ids: list[str]) -> str:
    # Hash del contenido normalizado, no de los bytes: git en Windows puede pasar a CRLF.
    return hashlib.sha256(("\n".join(ids) + "\n").encode()).hexdigest()


def load_test_set() -> list[str]:
    ids = TEST_SET_PATH.read_text(encoding="utf-8").split()
    if _ids_sha(ids) != TEST_SET_SHA256:
        raise SystemExit(f"{TEST_SET_PATH.name} no coincide con TEST_SET_SHA256")
    return ids


def write_test_set() -> None:
    ids = select_test_set(test_ids())
    sha = _ids_sha(ids)
    if TEST_SET_PATH.exists() and sha != TEST_SET_SHA256:
        raise SystemExit(f"la seleccion cambio: sha256={sha}. El test set v1 no se reescribe.")
    TEST_SET_PATH.write_text("\n".join(ids) + "\n", encoding="utf-8", newline="\n")
    counts = defaultdict(int)
    for pid in ids:
        counts[stratum(pid)] += 1
    print(f"{len(ids)} problemas, sha256={sha}")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")


# --- PutnamBench (benchmark secundario, D1.7) ---------------------------------
# Se fija el ULTIMO commit de PutnamBench con Lean v4.15.0 y exactamente nuestra
# Mathlib (9837ca9d, ver lean4/lake-manifest.json de ese commit). El main actual va
# con Lean v4.33.1 y no compila con nuestra imagen.
PUTNAM_COMMIT = "29a9eae7375f9cefcb13f55b62c385022df5e824"
PUTNAM_URL = f"https://codeload.github.com/trishullab/PutnamBench/zip/{PUTNAM_COMMIT}"
# Hash de los .lean de lean4/src (nombre + contenido, ordenados), no del zip: GitHub
# regenera los zips y no garantiza que los bytes sean estables.
PUTNAM_SHA256 = "c47997949b1f1eb410845596a71f570b6ef6d9c527d76437a15321e5407e7a98"
_ANSWER = re.compile(r"_solution\b[^\n]*:=\s*sorry[ \t]*\n((?:--[^\n]*(?:\n|$))+)")


def parse_putnam(name: str, text: str) -> dict:
    """Un archivo de PutnamBench: `import Mathlib`, preambulo (open, defs y la
    `abbrev ..._solution := sorry` con la respuesta en un comentario `--`),
    docstring con el enunciado y el teorema con `:= sorry`."""
    assert text.startswith("import Mathlib\n"), name
    doc = text.index("/--")
    end = text.index("-/", doc)
    preamble = text[len("import Mathlib"):doc].strip()
    answer = _ANSWER.search(preamble + "\n")
    return {
        "problem_id": name,
        "split": "putnam",
        "nl_statement": text[doc + 3:end].strip(),
        "formal_statement": re.sub(r":=\s*sorry\s*$", "", text[end + 2:].strip()).rstrip(),
        "theorem_name": name,
        "preamble": preamble,
        "solution_answer": "\n".join(l[2:].strip() for l in answer.group(1).splitlines()) if answer else None,
    }


def ingest_putnam() -> None:
    z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(PUTNAM_URL, timeout=120).read()))
    files = sorted((n.rsplit("/", 1)[1][:-5], z.read(n)) for n in z.namelist()
                   if "/lean4/src/" in n and n.endswith(".lean"))
    h = hashlib.sha256()
    for name, raw in files:
        h.update(name.encode() + b"\0" + raw + b"\0")
    if h.hexdigest() != PUTNAM_SHA256:
        raise SystemExit(f"la fuente cambio: sha256={h.hexdigest()}")
    rows = [parse_putnam(name, raw.decode("utf-8")) for name, raw in files]
    with open(DATA_DIR / "putnambench.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    n_sol = sum(r["solution_answer"] is not None for r in rows)
    print(f"putnam: {len(rows)} problemas, {n_sol} con abbrev de solucion")


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "--check":
        check(sys.argv[2])
    elif cmd == "--test-set":
        write_test_set()
    elif cmd == "--test-set-ids":
        print(",".join(load_test_set()))
    elif cmd == "--putnam":
        ingest_putnam()
    else:
        ingest()
