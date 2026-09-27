"""Grafo de estados del sistema multiagente (design-document §3), en LangGraph.

    PLAN -> VERIFY_SKELETON -> [RETRIEVE -> GENERATE -> FORMALIZE -> VERIFY]* -> ASSEMBLE -> VERIFY_FINAL

Configuracion `agents_only` (semana 7-8, §8.2 config 3): sin RAG y sin Critico.
Sin Critico, un subobjetivo que falla se reintenta A CIEGAS: bocetos nuevos, sin
ver el error de Lean. Es a proposito: asi la ablacion de la semana 9 mide lo que
aporta leer el error, y no lo que aporta simplemente volver a intentar.

Solo VERIFY_FINAL produce SOLVED (§3.2).
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src import agents
from src.lean_text import assemble
from src.verify import verify

MAX_ATTEMPTS = 2  # por subobjetivo, contando el primero


class State(TypedDict, total=False):
    skeleton: str
    subgoals: list[dict]      # name, statement, status, proof, attempts
    current: int
    plan_verdict: str
    lemmas: str
    sketch: dict
    formalized: dict
    verdict: str              # el ultimo veredicto del verificador (o del agente que fallo)
    proof: str
    final: str                # SOLVED / FAILED


def build(ctx, use_rag: bool = False, retriever=None, k: int = 10):
    """El grafo cierra sobre `ctx` (REPL, backends, log, presupuesto): eso no va en el
    estado porque no es serializable y el checkpoint lo copiaria."""

    def event(**kw):
        ctx.log.event(problem_id=ctx.problem_id, **kw)

    def sg(s: State) -> dict:
        return s["subgoals"][s["current"]]

    def prev(s: State) -> list[tuple[str, str]]:
        return [(g["name"], g["statement"]) for g in s["subgoals"][: s["current"]]]

    # --- nodos ---

    def plan_node(s: State) -> State:
        planned, verdict = agents.plan_and_check(ctx)  # incluye VERIFY_SKELETON y 1 replan
        event(agent="verifier", stage="VERIFY_SKELETON", verdict=verdict)
        if planned is None:
            return {"plan_verdict": verdict, "verdict": verdict}
        subs = [{"name": g["name"], "statement": g["statement"], "status": "open",
                 "proof": None, "attempts": 0} for g in planned["subgoals"]]
        return {"plan_verdict": "OK", "skeleton": planned["skeleton"], "subgoals": subs,
                "current": 0}

    def retrieve_node(s: State) -> State:
        if not use_rag:
            return {"lemmas": agents.NO_LEMMAS}
        from src.retriever import format_lemmas

        return {"lemmas": format_lemmas(retriever.search(sg(s)["statement"], k))}

    def generate_node(s: State) -> State:
        g = sg(s)
        ctx.attempt = g["attempts"]
        n = 2 if g["attempts"] == 0 else 1  # D3: self-consistency solo en el primer intento
        try:
            out = agents.generate(ctx, g, prev(s), s["lemmas"], n=n)
        except agents.AgentError:
            return {"sketch": None, "verdict": "GENERATION_FAILED"}
        return {"sketch": out["sketches"][out["selected"]]}

    def formalize_node(s: State) -> State:
        if s.get("sketch") is None:
            return {"formalized": None}
        out = agents.formalize(ctx, sg(s), prev(s), s["sketch"], s["lemmas"])
        if not out["ok"]:
            event(agent="autoformalizer", subgoal=sg(s)["name"], verdict="FORMALIZATION_FAILED",
                  reason=out["failure_reason"])
            return {"formalized": None, "verdict": "FORMALIZATION_FAILED"}
        return {"formalized": out}

    def verify_node(s: State) -> State:
        subs = [dict(g) for g in s["subgoals"]]
        g = subs[s["current"]]
        g["attempts"] += 1
        if s.get("formalized") is None:
            v = s["verdict"]
        else:
            v = agents.verify_subgoal(ctx, s["formalized"]).verdict
            event(agent="verifier", stage="VERIFY", subgoal=g["name"], attempt=g["attempts"],
                  verdict=v)
        if v == "OK":
            g["status"], g["proof"] = "proved", s["formalized"]["proof"]
        return {"subgoals": subs, "verdict": v}

    def advance_node(s: State) -> State:
        return {"current": s["current"] + 1}

    def assemble_node(s: State) -> State:
        return {"proof": assemble(s["skeleton"], {g["name"]: g["proof"] for g in s["subgoals"]})}

    def verify_final_node(s: State) -> State:
        v = verify(s["proof"], ctx.repl, theorem_name=ctx.problem["theorem_name"]).verdict
        event(agent="verifier", stage="VERIFY_FINAL", verdict=v)
        return {"verdict": v, "final": "SOLVED" if v == "OK" else "FAILED"}

    def failed_node(s: State) -> State:
        return {"final": "FAILED"}

    # --- aristas ---

    def after_plan(s: State) -> str:
        return "retrieve" if s["plan_verdict"] == "OK" else "failed"

    def after_verify(s: State) -> str:
        g = sg(s)
        if g["status"] == "proved":
            return "advance" if s["current"] + 1 < len(s["subgoals"]) else "assemble"
        # Sin Critico: reintento ciego si queda intento y cabe en el presupuesto (D3 corte temprano)
        if g["attempts"] < MAX_ATTEMPTS and ctx.budget.can_afford(2):
            return "generate"
        return "failed"

    def after_final(s: State) -> str:
        return END  # sin Critico, un ensamblado que falla no tiene a donde volver

    b = StateGraph(State)
    for name, fn in [("plan", plan_node), ("retrieve", retrieve_node),
                     ("generate", generate_node), ("formalize", formalize_node),
                     ("verify", verify_node), ("advance", advance_node),
                     ("assemble", assemble_node), ("verify_final", verify_final_node),
                     ("failed", failed_node)]:
        b.add_node(name, fn)
    b.add_edge(START, "plan")
    b.add_conditional_edges("plan", after_plan, ["retrieve", "failed"])
    b.add_edge("retrieve", "generate")
    b.add_edge("generate", "formalize")
    b.add_edge("formalize", "verify")
    b.add_conditional_edges("verify", after_verify, ["advance", "assemble", "generate", "failed"])
    b.add_edge("advance", "retrieve")
    b.add_edge("assemble", "verify_final")
    b.add_conditional_edges("verify_final", after_final, [END])
    b.add_edge("failed", END)
    return b.compile(checkpointer=MemorySaver())


def run_graph(ctx, use_rag: bool = False, retriever=None) -> dict:
    g = build(ctx, use_rag=use_rag, retriever=retriever)
    s = g.invoke({}, {"configurable": {"thread_id": ctx.problem_id}, "recursion_limit": 200})
    subs = s.get("subgoals", [])
    return {
        "verdict": s.get("verdict", "PLANNING_ERROR"),
        "solved": s.get("final") == "SOLVED",
        "proof": s.get("proof"),
        "skeleton_ok": s.get("plan_verdict") == "OK",
        "subgoals": [{k: g[k] for k in ("name", "status", "attempts")} for g in subs],
    }


def agents_only(ctx) -> dict:
    """§8.2 config 3: multiagente sin RAG y sin Critico."""
    return run_graph(ctx, use_rag=False)
