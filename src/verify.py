"""Verificador (RF-5). Es el unico arbitro de si un problema esta resuelto.

`verify()` NO responde "compila?". Responde con uno de siete veredictos. Los dos que
importan y que casi nadie implementa son SORRY y AXIOM:

  - Sin SORRY, una prueba con `sorry` cuenta como resuelta. La metrica principal del
    proyecto seria falsificable.
  - Sin AXIOM, `axiom foo : False` demuestra cualquier cosa y compila limpio.

Ver docs/design-document.md seccion 5.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Protocol

from src.lean_repl import ReplResult

# Axiomas del nucleo de Lean 4. Todo lo que este fuera de este conjunto es una
# suposicion introducida por la prueba y la invalida como "verificada".
ALLOWED_AXIOMS = frozenset({"propext", "Classical.choice", "Quot.sound"})

VERDICTS = (
    "OK",
    "SORRY",
    "AXIOM",
    "SYNTAX_ERROR",
    "MISSING_LEMMA",
    "UNSOLVED_GOALS",
    "TIMEOUT",
)


@dataclass
class Verdict:
    verdict: str
    raw: str
    axioms: list[str] = field(default_factory=list)
    missing_identifiers: list[str] = field(default_factory=list)
    elapsed_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.verdict == "OK"

    def to_json(self) -> dict:
        """Conforme a docs/contracts/verifier.schema.json."""
        return {
            "verdict": self.verdict,
            "raw": self.raw,
            "axioms": self.axioms,
            "missing_identifiers": self.missing_identifiers,
            "elapsed_ms": self.elapsed_ms,
        }


class Repl(Protocol):
    def run(self, cmd: str, env: int | None = ..., timeout: float = ...) -> ReplResult: ...


# --- clasificador de errores (seccion 8.3) ------------------------------------

_UNKNOWN_ID = re.compile(r"unknown (?:identifier|constant)\s+'([^']+)'")

# El orden importa: el primer patron que casa gana, porque Lean suele emitir errores
# en cascada y el primero es la causa.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("MISSING_LEMMA", re.compile(r"unknown (identifier|constant)")),
    ("TIMEOUT", re.compile(r"(deterministic\) timeout|maximum recursion depth)")),
    ("UNSOLVED_GOALS", re.compile(
        r"(unsolved goals|linarith failed|nlinarith failed|"
        r"simp made no progress|ring_nf failed|omega could not)"
    )),
    ("SYNTAX_ERROR", re.compile(
        r"(unexpected token|expected |unexpected identifier|"
        r"function expected|type mismatch|failed to synthesize)"
    )),
]


# Palabras de Lean 3 que Lean 4 reporta como "unknown identifier". Visto contra el
# kernel real (tests/test_kernel.py): sin esto, `begin ... end` se clasificaba como
# lema faltante y se iba a buscar mas lemas en vez de corregir la sintaxis.
_LEAN3_WORDS = frozenset({"begin", "assume"})


def classify(errors: list[str]) -> str:
    """Mapea los mensajes de error de Lean a la taxonomia de la seccion 8.3.

    Clasifica por el PRIMER error reportado: los posteriores suelen ser consecuencia.
    """
    if not errors:
        return "SYNTAX_ERROR"
    first = errors[0]
    if set(_UNKNOWN_ID.findall(first)) & _LEAN3_WORDS:
        return "SYNTAX_ERROR"
    for verdict, pattern in _PATTERNS:
        if pattern.search(first):
            return verdict
    # Cualquier error que el compilador acepta emitir pero no reconocemos se trata
    # como sintaxis: es la clase con el reintento mas barato.
    return "SYNTAX_ERROR"


def missing_identifiers(errors: list[str]) -> list[str]:
    """Nombres que el modelo alucino. Alimentan la reconsulta dirigida del RAG."""
    found: list[str] = []
    for err in errors:
        for name in _UNKNOWN_ID.findall(err):
            if name not in found and name not in _LEAN3_WORDS:
                found.append(name)
    return found


# --- axiomas ------------------------------------------------------------------

_AXIOM_LINE = re.compile(r"depends on axioms:\s*\[([^\]]*)\]")


def parse_axioms(info_messages: list[str]) -> list[str]:
    """Extrae la lista de `#print axioms`.

    Formatos posibles:
      "'foo' depends on axioms: [propext, Classical.choice, Quot.sound]"
      "'foo' does not depend on any axioms"
    """
    for msg in info_messages:
        if "does not depend on any axioms" in msg:
            return []
        m = _AXIOM_LINE.search(msg)
        if m:
            return [a.strip() for a in m.group(1).split(",") if a.strip()]
    return []


# --- verificador --------------------------------------------------------------

def verify(
    code: str,
    repl: Repl,
    theorem_name: str | None = None,
    timeout_s: float = 120.0,
    allow_sorry: bool = False,
) -> Verdict:
    """Veredicto del kernel sobre `code`.

    allow_sorry=True es el modo de VERIFY_SKELETON: ahi los `sorry` son esperados y
    lo que se comprueba es que la descomposicion tipa, es decir que los subobjetivos
    implican el teorema.
    """
    started = time.monotonic()

    def elapsed() -> int:
        return int((time.monotonic() - started) * 1000)

    r = repl.run(code, timeout=timeout_s)

    if r.timed_out:
        return Verdict("TIMEOUT", r.raw, elapsed_ms=elapsed())

    if r.has_errors:
        errs = r.errors
        return Verdict(
            classify(errs),
            r.raw,
            missing_identifiers=missing_identifiers(errs),
            elapsed_ms=elapsed(),
        )

    if r.has_sorries and not allow_sorry:
        return Verdict("SORRY", r.raw, elapsed_ms=elapsed())

    # Compila y no hay sorries. Queda la puerta trasera: un `axiom` declarado a mano.
    # Con allow_sorry el chequeo no aplica -- sorryAx aparecera siempre.
    if theorem_name and not allow_sorry:
        ax = repl.run(f"#print axioms {theorem_name}", env=r.env, timeout=timeout_s)
        if ax.timed_out:
            return Verdict("TIMEOUT", ax.raw, elapsed_ms=elapsed())
        axioms = parse_axioms(ax.infos)
        extra = [a for a in axioms if a not in ALLOWED_AXIOMS]
        if extra:
            return Verdict("AXIOM", ax.raw, axioms=axioms, elapsed_ms=elapsed())
        return Verdict("OK", r.raw, axioms=axioms, elapsed_ms=elapsed())

    return Verdict("OK", r.raw, elapsed_ms=elapsed())


def _smoke() -> int:
    """Compuerta del dia 5 de la semana 1 (decisions.md D4). Requiere la imagen Docker."""
    from src.lean_repl import ReadyRepl

    # Ojo: cada comando del REPL sin `env` arranca de un entorno vacio. Hay que
    # verificar sobre el entorno donde quedo cargado Mathlib; ReadyRepl hace eso.
    repl = ReadyRepl("import Mathlib")
    try:
        v = verify(
            "theorem smoke_test : 2 + 2 = 4 := by norm_num",
            repl,
            theorem_name="smoke_test",
        )
    finally:
        repl.close()
    print(f"veredicto={v.verdict} axiomas={v.axioms} {v.elapsed_ms} ms")
    print("PASA" if v.ok else f"FALLA\n{v.raw}")
    return 0 if v.ok else 1


if __name__ == "__main__":
    import sys

    sys.exit(_smoke() if "--smoke" in sys.argv else 0)
