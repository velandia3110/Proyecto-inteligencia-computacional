"""Grafo de estados del sistema multiagente (design-document §3), en LangGraph.

    PLAN -> VERIFY_SKELETON -> [RETRIEVE -> GENERATE -> FORMALIZE -> VERIFY (-> CRITIQUE)]*
         -> ASSEMBLE -> VERIFY_FINAL

Las tres configuraciones multiagente de la §8.2 son el mismo grafo con dos interruptores:

    agents_only  sin RAG, sin Critico
    no_critic    RAG (k=10), sin Critico
    full         RAG (k=10) + Critico

Sin Critico, un subobjetivo que falla se reintenta A CIEGAS: bocetos nuevos, sin ver el
error de Lean. Con Critico, el error se clasifica y el reintento lo lleva a la vista
(reformalizar, recuperar mas lemas, nuevo boceto o replanificar). El tope de intentos por
subobjetivo y la regla de n de D3 son los mismos en las tres: la ablacion mide lo que aporta
leer el error, no lo que aporta volver a intentar.

Solo VERIFY_FINAL produce SOLVED (§3.2).
"""

from __future__ import annotations

import threading
from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src import agents
from src.lean_text import assemble
from src.verify import verify

MAX_ATTEMPTS = 2  # por subobjetivo, contando el primero
K = 10            # lemas recuperados; status.md semanas 5-6: recall@10 = 0,224


class State(TypedDict, total=False):
    skeleton: str
    subgoals: list[dict]      # name, statement, status, proof, attempts, history
    current: int
    plan_verdict: str
    lemmas: str
    k: int
    sketch: dict
    formalized: dict
    verdict: str              # el ultimo veredicto del verificador (o del agente que fallo)
    error: str                # salida cruda de Lean (o motivo del fallo) del ultimo intento
    feedback: dict            # proof, error, diagnosis: lo que el Critico pasa al reintento
    action: str               # ultima accion del Critico
    replan: dict              # skeleton, error, diagnosis para replanificar
    replans: int
    proof: str
    final: str                # SOLVED / FAILED


def build(ctx, retriever=None, critic: bool = False, k: int = K):
    """El grafo cierra sobre `ctx` (REPL, backends, log, presupuesto): eso no va en el
    estado porque no es serializable y el checkpoint lo copiaria. RAG si hay `retriever`."""

    def event(**kw):
        ctx.log.event(problem_id=ctx.problem_id, **kw)

    def sg(s: State) -> dict:
        return s["subgoals"][s["current"]]

    def prev(s: State) -> list[tuple[str, str]]:
        return [(g["name"], g["statement"]) for g in s["subgoals"][: s["current"]]]

    # --- nodos ---

    def plan_node(s: State) -> State:
        replans = s.get("replans", 0)
        if s.get("replan"):  # el Critico mando replanificar: una sola llamada, con el error
            replans += 1
            planned, verdict = agents.plan_and_check(ctx, max_replans=0, retry=s["replan"])
        else:
            planned, verdict = agents.plan_and_check(ctx)  # incluye VERIFY_SKELETON y 1 replan
        event(agent="verifier", stage="VERIFY_SKELETON", verdict=verdict)
        if planned is None:
            return {"plan_verdict": verdict, "verdict": verdict, "replans": replans}
        subs = [{"name": g["name"], "statement": g["statement"], "status": "open",
                 "proof": None, "attempts": 0, "history": []} for g in planned["subgoals"]]
        return {"plan_verdict": "OK", "skeleton": planned["skeleton"], "subgoals": subs,
                "current": 0, "replans": replans, "replan": None, "feedback": None, "k": k,
                "proof": None}

    def retrieve_node(s: State) -> State:
        if retriever is None:
            return {"lemmas": agents.NO_LEMMAS}
        from src.retriever import format_lemmas

        with _lock:  # el encoder se comparte entre workers
            found = retriever.search(sg(s)["statement"], s.get("k", k))
        return {"lemmas": format_lemmas(found)}

    def generate_node(s: State) -> State:
        g = sg(s)
        ctx.attempt = g["attempts"]
        n = 2 if g["attempts"] == 0 else 1  # D3: self-consistency solo en el primer intento
        try:
            out = agents.generate(ctx, g, prev(s), s["lemmas"], n=n,
                                  retry_block=agents.feedback_block("critic.v1", s.get("feedback")))
        except agents.AgentError as e:
            return {"sketch": None, "verdict": "GENERATION_FAILED", "error": str(e)}
        return {"sketch": out["sketches"][out["selected"]]}

    def formalize_node(s: State) -> State:
        if s.get("sketch") is None:
            return {"formalized": None}
        ctx.attempt = sg(s)["attempts"]
        out = agents.formalize(ctx, sg(s), prev(s), s["sketch"], s["lemmas"],
                               retry_block=agents.feedback_block("autoformalizer.v1",
                                                                 s.get("feedback")))
        if not out["ok"]:
            event(agent="autoformalizer", subgoal=sg(s)["name"], verdict="FORMALIZATION_FAILED",
                  reason=out["failure_reason"])
            return {"formalized": None, "verdict": "FORMALIZATION_FAILED",
                    "error": out["failure_reason"]}
        return {"formalized": out}

    def verify_node(s: State) -> State:
        subs = [dict(g) for g in s["subgoals"]]
        g = subs[s["current"]]
        g["attempts"] += 1
        if s.get("formalized") is None:
            v, raw = s["verdict"], s.get("error", "")
        else:
            res = agents.verify_subgoal(ctx, s["formalized"])
            v, raw = res.verdict, res.raw
            event(agent="verifier", stage="VERIFY", subgoal=g["name"], attempt=g["attempts"],
                  verdict=v)
        if v == "OK":
            g["status"], g["proof"] = "proved", s["formalized"]["proof"]
        return {"subgoals": subs, "verdict": v, "error": raw}

    def critique_node(s: State) -> State:
        if s.get("proof"):
            # Fallo el ensamblado: cada subobjetivo cerro aislado y el teorema no, el error
            # esta en la descomposicion. No hay subobjetivo que clasificar: se replanifica.
            event(agent="critic", stage="VERIFY_FINAL", action="REPLAN")
            return {"action": "REPLAN", "replan": {"skeleton": s["skeleton"], "error": s["error"],
                                                    "diagnosis": "el ensamblado no compila"}}
        g = sg(s)
        proof = (s.get("formalized") or {}).get("proof")
        out = agents.critique(ctx, g, proof, s["verdict"], s.get("error", ""),
                              replanned=s.get("replans", 0) > 0, k=s.get("k", k),
                              k_max=MAX_ATTEMPTS)
        event(agent="critic", subgoal=g["name"], attempt=g["attempts"], verdict=s["verdict"],
              error_class=out["error_class"], action=out["action"])
        subs = [dict(x) for x in s["subgoals"]]
        subs[s["current"]]["history"] = g["history"] + [{"verdict": s["verdict"],
                                                         "error_class": out["error_class"]}]
        fb = {"proof": proof or "(sin prueba)", "error": s.get("error", "") or "(vacio)",
              "diagnosis": out["diagnosis"]}
        upd = {"subgoals": subs, "action": out["action"], "feedback": fb}
        if out["action"] == "RETRIEVE_MORE":
            upd["k"] = out["new_k"]
        if out["action"] == "REPLAN":
            upd["replan"] = {"skeleton": s["skeleton"], "error": fb["error"],
                             "diagnosis": out["diagnosis"]}
        return upd

    def advance_node(s: State) -> State:
        return {"current": s["current"] + 1, "feedback": None, "k": k}

    def assemble_node(s: State) -> State:
        return {"proof": assemble(s["skeleton"], {g["name"]: g["proof"] for g in s["subgoals"]})}

    def verify_final_node(s: State) -> State:
        res = verify(s["proof"], ctx.repl, theorem_name=ctx.problem["theorem_name"])
        event(agent="verifier", stage="VERIFY_FINAL", verdict=res.verdict)
        return {"verdict": res.verdict, "error": res.raw,
                "final": "SOLVED" if res.ok else "FAILED"}

    def failed_node(s: State) -> State:
        return {"final": "FAILED"}

    # --- aristas ---

    def after_plan(s: State) -> str:
        return "retrieve" if s["plan_verdict"] == "OK" else "failed"

    def after_verify(s: State) -> str:
        g = sg(s)
        if g["status"] == "proved":
            return "advance" if s["current"] + 1 < len(s["subgoals"]) else "assemble"
        left = g["attempts"] < MAX_ATTEMPTS
        if critic:
            # Se consulta al Critico si queda un intento o la carta de replanificar.
            return "critique" if (left or s.get("replans", 0) == 0) and ctx.budget.can_afford(2) \
                else "failed"
        # Sin Critico: reintento ciego si queda intento y cabe en el presupuesto (D3 corte temprano)
        return "generate" if left and ctx.budget.can_afford(2) else "failed"

    def after_critique(s: State) -> str:
        a = s["action"]
        if a == "REPLAN":
            return "plan"
        if a == "ABANDON" or sg(s)["attempts"] >= MAX_ATTEMPTS:
            return "failed"
        if a == "RETRY_FORMALIZE" and s.get("sketch") is not None:
            return "formalize"  # mismo boceto, con el error a la vista
        return "retrieve" if a == "RETRIEVE_MORE" else "generate"

    def after_final(s: State) -> str:
        if s["final"] == "SOLVED" or not critic:
            return END  # sin Critico, un ensamblado que falla no tiene a donde volver
        return "critique" if s.get("replans", 0) == 0 and ctx.budget.can_afford(2) else END

    b = StateGraph(State)
    for name, fn in [("plan", plan_node), ("retrieve", retrieve_node),
                     ("generate", generate_node), ("formalize", formalize_node),
                     ("verify", verify_node), ("critique", critique_node),
                     ("advance", advance_node), ("assemble", assemble_node),
                     ("verify_final", verify_final_node), ("failed", failed_node)]:
        b.add_node(name, fn)
    b.add_edge(START, "plan")
    b.add_conditional_edges("plan", after_plan, ["retrieve", "failed"])
    b.add_edge("retrieve", "generate")
    b.add_edge("generate", "formalize")
    b.add_edge("formalize", "verify")
    b.add_conditional_edges("verify", after_verify,
                            ["advance", "assemble", "generate", "critique", "failed"])
    b.add_conditional_edges("critique", after_critique,
                            ["plan", "formalize", "retrieve", "generate", "failed"])
    b.add_edge("advance", "retrieve")
    b.add_edge("assemble", "verify_final")
    b.add_conditional_edges("verify_final", after_final, ["critique", END])
    b.add_edge("failed", END)
    return b.compile(checkpointer=MemorySaver())


def run_graph(ctx, retriever=None, critic: bool = False) -> dict:
    g = build(ctx, retriever=retriever, critic=critic)
    s = g.invoke({}, {"configurable": {"thread_id": ctx.problem_id}, "recursion_limit": 200})
    subs = s.get("subgoals", [])
    return {
        "verdict": s.get("verdict", "PLANNING_ERROR"),
        "solved": s.get("final") == "SOLVED",
        "proof": s.get("proof"),
        "skeleton_ok": s.get("plan_verdict") == "OK",
        "replans": s.get("replans", 0),
        "subgoals": [{k: g[k] for k in ("name", "status", "attempts")} for g in subs],
    }


# Indice FAISS + BGE-M3: se carga una vez, perezoso, y solo si la config usa RAG.
_retriever, _lock = None, threading.Lock()


def shared_retriever():
    global _retriever
    with _lock:
        if _retriever is None:
            import os

            from src.retriever import RemoteRetriever, Retriever

            url = os.environ.get("RETRIEVER_URL")
            _retriever = RemoteRetriever(url) if url else Retriever.load()
    return _retriever


def agents_only(ctx) -> dict:
    """§8.2 config 3: multiagente sin RAG y sin Critico."""
    return run_graph(ctx)


def no_critic(ctx, retriever=None) -> dict:
    """§8.2 config 4: con RAG, sin Critico (reintento ciego como agents_only)."""
    return run_graph(ctx, retriever=retriever or shared_retriever())


def full(ctx, retriever=None) -> dict:
    """§8.2 config 5: RAG + Critico."""
    return run_graph(ctx, retriever=retriever or shared_retriever(), critic=True)
