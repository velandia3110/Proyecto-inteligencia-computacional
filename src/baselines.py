"""Lineas base A y B (§8.2, configuraciones 1 y 2).

Las dos devuelven el mismo diccionario de resultado que el sistema multiagente,
para que el runner y la agregacion no distingan entre configuraciones.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.budget import Budget
from src.data import HEADER
from src.lean_text import extract_lean_block, statement_preserved, strip_imports
from src.llm import call, parse_json
from src.verify import verify


@dataclass
class Ctx:
    """Todo lo que un agente necesita saber de la corrida actual."""

    problem: dict
    repl: object
    backends: dict
    log: object
    budget: Budget = field(default_factory=Budget)
    attempt: int = 0
    transcript: list = field(default_factory=list)

    @property
    def problem_id(self) -> str:
        return self.problem["problem_id"]


def check_whole_proof(ctx: Ctx, text: str) -> tuple[str, str]:
    """Respuesta del prover -> (veredicto, codigo). Chequea que el enunciado siga intacto."""
    block = extract_lean_block(text)
    if block is None:
        return "NO_CODE", ""
    code = strip_imports(block)
    if not statement_preserved(code, ctx.problem["formal_statement"]):
        # Compilaria, pero seria otro teorema. No se le pregunta al kernel.
        return "STATEMENT_CHANGED", code
    v = verify(code, ctx.repl, theorem_name=ctx.problem["theorem_name"])
    return v.verdict, code


def baseline_a(ctx: Ctx) -> dict:
    p = ctx.problem
    r = call(ctx, "baseline_a", "baseline_a.v0", header=HEADER.strip(),
             nl_statement=p["nl_statement"], formal_statement=p["formal_statement"])
    verdict, code = check_whole_proof(ctx, r.text)
    return {"verdict": verdict, "solved": verdict == "OK", "proof": code}


def baseline_b(ctx: Ctx) -> dict:
    """CoT en lenguaje natural + autoevaluacion. Se resuelve solo si el kernel acepta
    la formalizacion; `self_verdict` queda en el resultado para medir falsos positivos."""
    p = ctx.problem
    r = call(ctx, "baseline_b", "baseline_b.v0",
             nl_statement=p["nl_statement"], formal_statement=p["formal_statement"])
    try:
        out = parse_json(r.text)
        proof, self_verdict = out["proof"], out["self_verdict"]
        confidence = out.get("confidence")
    except (ValueError, KeyError):
        return {"verdict": "BAD_OUTPUT", "solved": False, "self_verdict": None}

    ctx.attempt = 1
    f = call(ctx, "baseline_b_formalize", "baseline_b_formalize.v0", header=HEADER.strip(),
             nl_statement=p["nl_statement"], nl_proof=proof.replace("-/", "- /"),
             formal_statement=p["formal_statement"])
    verdict, code = check_whole_proof(ctx, f.text)
    return {"verdict": verdict, "solved": verdict == "OK", "proof": code,
            "self_verdict": self_verdict, "confidence": confidence, "nl_proof": proof}
