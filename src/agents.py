"""Planificador, Generador, Autoformalizador y Critico (RF-1, RF-2, RF-4, RF-6).

Cada agente: llama al LLM por `llm.call` (presupuesto + log), parsea, valida
contra su contrato y devuelve el objeto del contrato. Si la salida no cumple, se
levanta AgentError con el motivo: para el grafo es un fallo mas, con texto que
se puede devolver en el reintento.
"""

from __future__ import annotations

import re

from src.data import HEADER
from src.lean_text import (extract_lean_block, split_statement, statement_preserved,
                            subgoal_lemma, tactic_body)
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
    if not isinstance(out, dict) or not isinstance(out.get("skeleton"), str):
        raise AgentError("el JSON no trae `skeleton` como texto")
    model_sk = out["skeleton"]
    if not _HAVE.search(re.sub(r":=\s*(?:by\s*)?\n\s*sorry", ":= by sorry", model_sk)):
        # qwen3-4b a menudo deja el esqueleto en el puro enunciado y pone los pasos solo en
        # `subgoals`: se arman los `have` desde ahi y el kernel decide si compilan.
        model_sk += "".join(f"\n  have {sg['name']} : {' '.join(str(sg['statement']).split())} := by sorry"
                            for sg in out.get("subgoals") or []
                            if isinstance(sg, dict) and re.fullmatch(r"\w+", str(sg.get("name", "")))
                            and sg.get("statement"))
    out["skeleton"] = sk = normalize_skeleton(model_sk, ctx.problem["formal_statement"])
    if not statement_preserved(sk, ctx.problem["formal_statement"]):
        raise AgentError("el esqueleto no trae ningun `have nombre : enunciado := by sorry` en una linea")
    # Los subobjetivos salen del texto del esqueleto (lo que el kernel revisa), no del JSON;
    # del JSON solo se toman las pistas por nombre. Despues se valida el contrato.
    hints = {sg.get("name"): sg for sg in out.get("subgoals") or [] if isinstance(sg, dict)}
    out["subgoals"] = [{"name": n, "statement": st.strip(),
                        "depends_on": [d for d in hints.get(n, {}).get("depends_on", []) if isinstance(d, str)],
                        **({"nl_hint": str(hints[n]["nl_hint"])} if "nl_hint" in hints.get(n, {}) else {})}
                       for n, st in _HAVE.findall(sk)]
    if not 1 <= len(out["subgoals"]) <= 5:
        raise AgentError(f"hacen falta entre 1 y 5 `have ... := by sorry`, el esqueleto trae "
                         f"{len(out['subgoals'])}: junta pasos")
    out = _checked("planner", {"theorem_name": str(out.get("theorem_name") or ctx.problem_id),
                               "skeleton": sk, "subgoals": out["subgoals"],
                               "rationale": str(out.get("rationale", ""))})
    if sk.count("sorry") != len(out["subgoals"]):
        raise AgentError("hay `sorry` fuera de los subobjetivos declarados")
    return out


_HAVE = re.compile(r"^\s*have\s+(\w+)\s*:(.*?):=\s*(?:by\s+)?sorry\s*$", re.M)
# Cierre de respaldo (qwen3-4b suele poner la meta como un `have` mas, o cerrar con un
# `exact` que no encaja). Va despues de la tactica del modelo, si la hay. Si los `have` no
# implican la meta, el kernel lo rechaza y se replanifica igual que antes. decisions.md 2026-11-09.
FALLBACK_CLOSE = ("first | assumption | linarith | nlinarith | norm_num | omega"
                  " | ((repeat' constructor) <;> first | assumption | linarith | nlinarith)")


def normalize_skeleton(model_sk: str, formal_statement: str) -> str:
    """Encabezado = enunciado original + `:= by` (el modelo lo alteraba o olvidaba el `:= by`).
    Del modelo se toma lo que va desde el primer `have`; su tactica final se intenta primero."""
    model_sk = re.sub(r":=\s*(?:by\s*)?\n\s*sorry", ":= by sorry", model_sk)
    lines = model_sk.splitlines()
    idx = [i for i, l in enumerate(lines) if _HAVE.match(l)]
    if not idx:
        return model_sk  # sin `have` no hay nada que normalizar; lo rechaza plan()
    base = len(lines[idx[0]]) - len(lines[idx[0]].lstrip())  # sangria del modelo -> 2
    body = []
    for l in lines[idx[0]:idx[-1] + 1]:
        m = _HAVE.match(l)
        if m:
            body.append(f"  have {m[1]} : {m[2].strip()} := by sorry")
        elif l.strip():
            body.append("  " + l[min(base, len(l) - len(l.lstrip())):])
    tail = [l.strip() for l in lines[idx[-1] + 1:] if l.strip()]
    close = f"first | ({'; '.join(tail)}) | {FALLBACK_CLOSE}" if tail else FALLBACK_CLOSE
    return "\n".join([formal_statement.rstrip() + " := by", *body, f"  {close}"])


def verify_skeleton(ctx, planned: dict) -> Verdict:
    """Si compila con los sorries, los subobjetivos implican el teorema (design §3.1)."""
    return verify(planned["skeleton"], ctx.repl, allow_sorry=True)


def plan_and_check(ctx, max_replans: int = 1, retry: dict | None = None) -> tuple[dict | None, str]:
    """PLAN -> VERIFY_SKELETON, replanificando una vez con el error. -> (plan, veredicto).
    `retry` llega cuando el Critico manda replanificar (skeleton, error, diagnosis)."""
    for i in range(max_replans + 1):
        ctx.attempt = i
        try:
            planned = plan(ctx, retry)
        except AgentError as e:
            ctx.log.event(problem_id=ctx.problem_id, agent="planner", event="skeleton_attempt",
                          attempt=i, verdict="PLANNING_ERROR", error=str(e)[:500])
            retry, verdict = {"skeleton": "(salida invalida)", "error": str(e)}, "PLANNING_ERROR"
            continue
        v = verify_skeleton(ctx, planned)
        # Esqueleto y error al log: es el dato del analisis de fallos (§4.6 del informe).
        ctx.log.event(problem_id=ctx.problem_id, agent="verifier", event="skeleton_attempt",
                      attempt=i, verdict=v.verdict, skeleton=planned["skeleton"],
                      error=str(v.raw)[:1500])
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


# --- Autoformalizador ----------------------------------------------------------

def formalize(ctx, subgoal: dict, prev: list[tuple[str, str]], sketch: dict,
              lemmas: str = NO_LEMMAS, retry_block: str = "") -> dict:
    """Boceto -> tacticas. El prover ve el subobjetivo como lema suelto; el codigo saca
    las tacticas y arma el JSON del contrato (prompts/autoformalizer.v1.md)."""
    lemma_stmt = subgoal_lemma(ctx.problem["formal_statement"], prev, subgoal["name"],
                               subgoal["statement"])
    r = call(ctx, "autoformalizer", "autoformalizer.v1", header=HEADER.strip(),
             sketch_steps="\n".join(f"{i}. {s}" for i, s in enumerate(sketch["steps"], 1))
             .replace("-/", "- /"),
             tactic_hints=", ".join(sketch.get("tactic_hints", [])) or "-",
             retrieved_lemmas=lemmas.replace("\n", " "), subgoal_lemma=lemma_stmt,
             retry_block=retry_block)
    block = extract_lean_block(r.text)
    body = tactic_body(block) if block else None
    if body is None:
        out = {"subgoal_name": subgoal["name"], "ok": False,
               "failure_reason": "el prover no devolvio un bloque lean4 con `:= by`"}
    elif re.search(r"\b(sorry|admit)\b", body):
        out = {"subgoal_name": subgoal["name"], "ok": False,
               "failure_reason": "la prueba usa sorry/admit"}
    else:
        out = {"subgoal_name": subgoal["name"], "ok": True, "proof": body}
    out = _checked("autoformalizer", out)
    out["_lemma"] = lemma_stmt  # para verificar el subobjetivo aislado; no es del contrato
    return out


def verify_subgoal(ctx, formalized: dict) -> Verdict:
    """El subobjetivo como lema suelto, con los siete veredictos (incluye AXIOM)."""
    name = formalized["_lemma"].split()[1]
    body = "\n".join("  " + l for l in formalized["proof"].splitlines())
    return verify(f"{formalized['_lemma']} := by\n{body}", ctx.repl, theorem_name=name)


# --- Critico -------------------------------------------------------------------

# Tabla fija clase -> accion (critic.schema.json): el LLM clasifica, el codigo decide.
CRITIC_ACTION = {"SYNTAX": "RETRY_FORMALIZE", "MISSING_LEMMA": "RETRIEVE_MORE",
                 "UNSOLVED_GOALS": "REGENERATE_SKETCH", "TIMEOUT": "RETRY_FORMALIZE",
                 "PLANNING_ERROR": "REPLAN", "BUDGET_EXHAUSTED": "ABANDON"}
# Si el modelo no devuelve una clase valida, se toma la del verificador.
_VERDICT_CLASS = {"MISSING_LEMMA": "MISSING_LEMMA", "UNSOLVED_GOALS": "UNSOLVED_GOALS",
                  "TIMEOUT": "TIMEOUT"}


def critique(ctx, subgoal: dict, proof: str | None, verdict: str, raw: str,
             replanned: bool, k: int, k_max: int) -> dict:
    """Veredicto + error crudo + historial -> objeto del contrato del Critico.

    Corte temprano de D3: PLANNING_ERROR cuando ya se replanifico, o un segundo TIMEOUT del
    mismo subobjetivo, son irrecuperables y la accion pasa a ABANDON."""
    history = subgoal.get("history", [])
    r = call(ctx, "critic", "critic.v1", subgoal_name=subgoal["name"],
             subgoal_statement=subgoal["statement"], attempted_proof=proof or "(sin prueba)",
             verdict=verdict, lean_raw=raw[:4000] or "(vacia)",
             attempt_n=str(subgoal["attempts"]), k_max=str(k_max),
             attempt_history="\n".join(f"- {h['verdict']} -> {h['error_class']}" for h in history)
             or "(ninguno)",
             calls_used=str(ctx.budget.used), max_calls=str(ctx.budget.max_llm_calls))
    try:
        out = parse_json(r.text)
        cls, diag = out["error_class"], str(out["diagnosis"]).strip()
        if cls not in CRITIC_ACTION or not diag:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        cls = _VERDICT_CLASS.get(verdict, "SYNTAX")
        diag = f"(el Critico no devolvio una clase valida; se usa el veredicto {verdict})"
        ctx.log.event(problem_id=ctx.problem_id, agent="critic", event="invalid_output")
    recoverable = not ((cls == "PLANNING_ERROR" and replanned) or
                       (cls == "TIMEOUT" and any(h["error_class"] == "TIMEOUT" for h in history)))
    out = {"error_class": cls, "action": CRITIC_ACTION[cls] if recoverable else "ABANDON",
           "diagnosis": diag, "recoverable": recoverable}
    if out["action"] == "RETRIEVE_MORE":
        out["new_k"] = min(2 * k, 50)
    return _checked("critic", out)


def feedback_block(prompt_name: str, fb: dict | None) -> str:
    """Bloque de reintento con el error a la vista. critic.v1 trae el del Generador."""
    if not fb:
        return ""
    return load_prompt(prompt_name).render_retry(previous_proof=fb["proof"],
                                                 lean_error=fb["error"], diagnosis=fb["diagnosis"])
