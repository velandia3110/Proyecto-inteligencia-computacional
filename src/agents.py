"""Planificador y Generador (RF-1, RF-2).

Cada agente: llama al LLM por `llm.call` (presupuesto + log), parsea, valida
contra su contrato y devuelve el objeto del contrato. Si la salida no cumple, se
levanta AgentError con el motivo: para el grafo es un fallo mas, con texto que
se puede devolver en el reintento.
"""

from __future__ import annotations

import re

from src.lean_text import split_statement, statement_preserved
from src.llm import call, load_prompt, parse_json, validate
from src.verify import Verdict, verify

NO_LEMMAS = "(sin lemas recuperados en esta configuracion)"


class AgentError(Exception):
    pass


def _checked(agent: str, obj: dict) -> dict:
    import jsonschema

    try:
        validate(agent, obj)
    except jsonschema.ValidationError as e:
        raise AgentError(f"la salida no cumple el contrato de {agent}: {e.message}") from None
    return obj


# --- Planificador + VERIFY_SKELETON ---------------------------------------------

def plan(ctx, retry: dict | None = None) -> dict:
    retry_block = ""
    if retry:
        retry_block = load_prompt("planner.v0").render_retry(
            previous_skeleton=retry["skeleton"], lean_error=retry["error"],
            diagnosis=retry.get("diagnosis", "(sin Critico en esta configuracion)"))
    r = call(ctx, "planner", "planner.v0", nl_statement=ctx.problem["nl_statement"],
             formal_statement=ctx.problem["formal_statement"], retry_block=retry_block)
    try:
        out = parse_json(r.text)
    except ValueError as e:
        raise AgentError(f"el planificador no devolvio JSON: {e}") from None
    out = _checked("planner", out)

    sk = out["skeleton"]
    if not statement_preserved(sk, ctx.problem["formal_statement"]):
        raise AgentError("el esqueleto cambio el enunciado del teorema")
    for sg in out["subgoals"]:
        m = re.search(rf"^\s*have\s+{re.escape(sg['name'])}\s*:(.*):=\s*by\s+sorry\s*$", sk, re.M)
        if not m:
            raise AgentError(f"el subobjetivo {sg['name']} no aparece como "
                             f"`have {sg['name']} : ... := by sorry` en una sola linea")
        # Manda el texto del esqueleto (lo que el kernel ya reviso), no el del JSON.
        sg["statement"] = m[1].strip()
    if sk.count("sorry") != len(out["subgoals"]):
        raise AgentError("hay `sorry` fuera de los subobjetivos declarados")
    return out


def verify_skeleton(ctx, planned: dict) -> Verdict:
    """Si compila con los sorries, los subobjetivos implican el teorema (design §3.1)."""
    return verify(planned["skeleton"], ctx.repl, allow_sorry=True)


def plan_and_check(ctx, max_replans: int = 1) -> tuple[dict | None, str]:
    """PLAN -> VERIFY_SKELETON, replanificando una vez con el error. -> (plan, veredicto)."""
    retry = None
    for i in range(max_replans + 1):
        ctx.attempt = i
        try:
            planned = plan(ctx, retry)
        except AgentError as e:
            retry, verdict = {"skeleton": "(salida invalida)", "error": str(e)}, "PLANNING_ERROR"
            continue
        v = verify_skeleton(ctx, planned)
        if v.ok:
            return planned, "OK"
        retry, verdict = {"skeleton": planned["skeleton"], "error": v.raw}, v.verdict
    return None, verdict


# --- Generador -----------------------------------------------------------------

def _jaccard(a: list[str], b: list[str]) -> float:
    a, b = {x.split()[0] for x in a if x.strip()}, {x.split()[0] for x in b if x.strip()}
    return len(a & b) / len(a | b) if a | b else 1.0


def vote(sketches: list[dict]) -> tuple[int, float]:
    """Self-consistency por acuerdo estructural: gana el boceto cuyas tacticas se parecen
    mas a las de los demas. Con n=1 el acuerdo es 1.0 y no dice nada."""
    n = len(sketches)
    if n == 1:
        return 0, 1.0
    scores = [sum(_jaccard(s["tactic_hints"], t["tactic_hints"]) for t in sketches if t is not s)
              for s in sketches]
    best = max(range(n), key=lambda i: scores[i])  # empate: el primero
    agree = sum(_jaccard(sketches[best]["tactic_hints"], s["tactic_hints"]) >= 0.5
                for s in sketches) / n
    return best, agree


def generate(ctx, subgoal: dict, prev: list[tuple[str, str]], lemmas: str = NO_LEMMAS,
             n: int = 2, retry_block: str = "") -> dict:
    _, binders, _ = split_statement(ctx.problem["formal_statement"])
    hyps = binders + "".join(f"\n({name} : {st})" for name, st in prev)
    sketches, allowed = [], _lemma_names(lemmas)
    for _ in range(n):
        r = call(ctx, "generator", "generator.v1",
                 formal_statement=ctx.problem["formal_statement"],
                 subgoal_name=subgoal["name"], subgoal_statement=subgoal["statement"],
                 available_hypotheses=hyps or "(ninguna)", retrieved_lemmas=lemmas,
                 retry_block=retry_block)
        try:
            s = parse_json(r.text)
        except ValueError:
            continue  # un boceto roto no tumba el subobjetivo si hay otro
        s = {k: s[k] for k in ("steps", "tactic_hints", "uses_lemmas") if k in s}
        s.setdefault("tactic_hints", [])
        # Lema citado que no estaba en la lista = alucinacion; se quita y queda en el log.
        invented = [l for l in s.get("uses_lemmas", []) if l not in allowed]
        if invented:
            ctx.log.event(problem_id=ctx.problem_id, agent="generator", event="hallucinated_lemmas",
                          lemmas=invented)
            s["uses_lemmas"] = [l for l in s.get("uses_lemmas", []) if l in allowed]
        sketches.append(s)
    if not sketches:
        raise AgentError("ningun boceto valido")
    best, agree = vote(sketches)
    return _checked("generator", {"subgoal_name": subgoal["name"], "sketches": sketches,
                                  "selected": best, "agreement": agree})


def _lemma_names(lemmas: str) -> set[str]:
    return set(re.findall(r"^- `?([\w.'₀-₉]+)`?", lemmas, re.M))


def plan_only(ctx) -> dict:
    """Config de la compuerta de semana 6: solo PLAN + VERIFY_SKELETON. No resuelve nada."""
    planned, verdict = plan_and_check(ctx)
    return {"verdict": verdict, "solved": False, "skeleton_ok": planned is not None,
            "n_subgoals": len(planned["subgoals"]) if planned else 0,
            "skeleton": planned["skeleton"] if planned else None}
