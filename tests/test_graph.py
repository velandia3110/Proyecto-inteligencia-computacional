"""Grafo (agents_only, no_critic, full) y pool de REPLs, con LLM, recuperador y REPL falsos.

    python tests/test_graph.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_pipeline import FS, GOOD_SG, GOOD_SK, FakeLLM, ScriptRepl, _plan_json, ctx

from src.budget import Budget, BudgetExhausted
from src.graph import agents_only, full, no_critic

SKETCH = json.dumps({"steps": ["despejar x"], "tactic_hints": ["linarith"], "uses_lemmas": []})


def prover_says(tactic):
    return f"Plan.\n```lean4\ntheorem t_s1 (x : ℝ) (h₀ : 2 * x = 4) :\n    x = 4 / 2 := by\n  {tactic}\n```"


def events(c):
    c.log.close()
    return [json.loads(l) for l in open(c.log.path, encoding="utf-8") if '"event"' in l]


def test_camino_feliz():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        local = FakeLLM(_plan_json(GOOD_SK, GOOD_SG), SKETCH, SKETCH)
        c = ctx(llm_local=local, llm_prover=FakeLLM(prover_says("linarith")),
                repl=ScriptRepl(good=["linarith"]), tmp=tmp)
        out = agents_only(c)
        assert out["solved"] and out["verdict"] == "OK", out
        assert "sorry" not in out["proof"] and "    linarith" in out["proof"]
        assert c.budget.used == 4  # plan + 2 bocetos + 1 formalizacion
        stages = [e["stage"] for e in events(c) if "stage" in e]
        assert stages == ["VERIFY_SKELETON", "VERIFY", "VERIFY_FINAL"], stages


def test_reintento_a_ciegas():
    # Sin Critico el segundo intento NO ve el error de Lean: eso es lo que la ablacion
    # de la semana 9 compara contra el Critico.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        local = FakeLLM(_plan_json(GOOD_SK, GOOD_SG), SKETCH, SKETCH, SKETCH)
        prover = FakeLLM(prover_says("nlinarith"), prover_says("linarith"))
        c = ctx(llm_local=local, llm_prover=prover, repl=ScriptRepl(good=["  linarith"]), tmp=tmp)
        out = agents_only(c)
        assert out["solved"], out
        assert out["subgoals"][0]["attempts"] == 2
        assert c.budget.used == 6  # plan + 2 + 1, luego reintento con n=1: + 1 + 1
        assert "unsolved goals" not in local.seen[-1] and "unsolved goals" not in prover.seen[-1]


def test_falla_tras_dos_intentos():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        local = FakeLLM(_plan_json(GOOD_SK, GOOD_SG), SKETCH, SKETCH, SKETCH)
        prover = FakeLLM(prover_says("nlinarith"), prover_says("nlinarith"))
        c = ctx(llm_local=local, llm_prover=prover, repl=ScriptRepl(good=["  linarith"]), tmp=tmp)
        out = agents_only(c)
        assert not out["solved"] and out["verdict"] == "UNSOLVED_GOALS", out
        assert out["subgoals"][0]["status"] == "open"


def test_prover_sin_codigo_es_fallo_de_formalizacion():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        local = FakeLLM(_plan_json(GOOD_SK, GOOD_SG), SKETCH, SKETCH, SKETCH)
        prover = FakeLLM("no se", prover_says("linarith"))
        c = ctx(llm_local=local, llm_prover=prover, repl=ScriptRepl(good=["  linarith"]), tmp=tmp)
        assert agents_only(c)["solved"]
        ev = [e for e in events(c) if e.get("event") != "skeleton_attempt"]
        assert [e["verdict"] for e in ev][:2] == ["OK", "FORMALIZATION_FAILED"], ev


def test_plan_fallido():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = ctx(llm_local=FakeLLM("x", "y"), tmp=tmp)
        out = agents_only(c)
        assert out["verdict"] == "PLANNING_ERROR" and not out["skeleton_ok"] and not out["solved"]


def test_presupuesto_es_techo_duro():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        local = FakeLLM(_plan_json(GOOD_SK, GOOD_SG), SKETCH, SKETCH)
        c = ctx(llm_local=local, llm_prover=FakeLLM(prover_says("linarith")),
                repl=ScriptRepl(good=["linarith"]), tmp=tmp)
        c.budget = Budget(max_llm_calls=3)
        try:
            agents_only(c)
        except BudgetExhausted:
            return
    raise AssertionError("el grafo siguio llamando pasado el techo")


def test_pool_presta_y_devuelve():
    import threading

    from src.repl_pool import ReplPool

    made = []

    class R:
        def __init__(self, header):
            made.append(self)

        def close(self):
            self.closed = True

    pool = ReplPool("h", size=2, factory=R)
    seen = set()

    def work():
        with pool.acquire() as r:
            seen.add(id(r))

    ts = [threading.Thread(target=work) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(made) == 2 and seen <= {id(r) for r in made}
    pool.close()
    assert all(r.closed for r in made)


# --- semana 9: RAG + Critico ------------------------------------------------------

def crit(cls):
    return json.dumps({"error_class": cls, "diagnosis": f"diag {cls}"})


class FakeRetriever:
    def __init__(self):
        self.ks = []

    def search(self, query, k=10):
        self.ks.append(k)
        return {"lemmas": [{"name": "sq_nonneg", "type": "0 ≤ a ^ 2"}]}


class ReadsTheError(FakeLLM):
    """Prover que solo acierta si el prompt le muestra el error de Lean."""

    def complete(self, system, user, max_tokens=None):
        self.texts = [prover_says("linarith" if "Lean error" in user else "nlinarith")]
        return super().complete(system, user, max_tokens)


def test_critico_ve_el_error_y_el_reintento_lo_incluye():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        local = FakeLLM(_plan_json(GOOD_SK, GOOD_SG), SKETCH, SKETCH, crit("UNSOLVED_GOALS"), SKETCH)
        prover = FakeLLM(prover_says("nlinarith"), prover_says("linarith"))
        c = ctx(llm_local=local, llm_prover=prover, repl=ScriptRepl(good=["  linarith"]), tmp=tmp)
        out = full(c, retriever=FakeRetriever())
        assert out["solved"] and out["subgoals"][0]["attempts"] == 2, out
        assert "unsolved goals" in local.seen[3]  # el Critico ve la salida cruda de Lean
        # REGENERATE_SKETCH: el boceto nuevo y la formalizacion llevan error y diagnostico
        assert "unsolved goals" in local.seen[4] and "diag UNSOLVED_GOALS" in local.seen[4]
        assert "unsolved goals" in prover.seen[1] and "diag UNSOLVED_GOALS" in prover.seen[1]
        assert c.budget.by_agent["critic"] == 1 and c.budget.used == 7
        assert [e["action"] for e in events(c) if e.get("agent") == "critic"] == ["REGENERATE_SKETCH"]


def test_critico_sintaxis_reformaliza_el_mismo_boceto():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        local = FakeLLM(_plan_json(GOOD_SK, GOOD_SG), SKETCH, SKETCH, crit("SYNTAX"))
        prover = FakeLLM(prover_says("nlinarith"), prover_says("linarith"))
        c = ctx(llm_local=local, llm_prover=prover, repl=ScriptRepl(good=["  linarith"]), tmp=tmp)
        assert full(c, retriever=FakeRetriever())["solved"]
        assert c.budget.by_agent["generator"] == 2 and c.budget.used == 6  # sin boceto nuevo


def test_critico_lema_faltante_recupera_mas():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        local = FakeLLM(_plan_json(GOOD_SK, GOOD_SG), SKETCH, SKETCH, crit("MISSING_LEMMA"), SKETCH)
        prover = FakeLLM(prover_says("nlinarith"), prover_says("linarith"))
        r = FakeRetriever()
        c = ctx(llm_local=local, llm_prover=prover, repl=ScriptRepl(good=["  linarith"]), tmp=tmp)
        assert full(c, retriever=r)["solved"]
        assert r.ks == [10, 20]


def test_corte_temprano_planning_error_tras_replanificar():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        plan = _plan_json(GOOD_SK, GOOD_SG)
        local = FakeLLM(plan, SKETCH, SKETCH, crit("PLANNING_ERROR"),
                        plan, SKETCH, SKETCH, crit("PLANNING_ERROR"))
        prover = FakeLLM(prover_says("nlinarith"), prover_says("nlinarith"))
        c = ctx(llm_local=local, llm_prover=prover, repl=ScriptRepl(good=["  linarith"]), tmp=tmp)
        out = full(c, retriever=FakeRetriever())
        assert not out["solved"] and out["replans"] == 1
        assert out["subgoals"][0]["attempts"] == 1  # le quedaba un intento y no lo gasto
        assert "diag PLANNING_ERROR" in local.seen[4]  # el replan ve el diagnostico
        assert [e["action"] for e in events(c) if e.get("agent") == "critic"] == ["REPLAN", "ABANDON"]
        assert c.budget.used == 10


def test_corte_temprano_timeout_repetido():
    from src.agents import critique
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = ctx(llm_local=FakeLLM(crit("TIMEOUT"), crit("TIMEOUT")), tmp=tmp)
        g = {"name": "s1", "statement": "x = 4 / 2", "attempts": 1, "history": []}
        first = critique(c, g, "simp", "TIMEOUT", "(deterministic) timeout", False, 10, 2)
        assert first["action"] == "RETRY_FORMALIZE" and first["recoverable"]
        g["history"] = [{"verdict": "TIMEOUT", "error_class": "TIMEOUT"}]
        second = critique(c, g, "simp", "TIMEOUT", "(deterministic) timeout", False, 10, 2)
        assert second["action"] == "ABANDON" and not second["recoverable"]


def test_critico_con_salida_invalida_usa_el_veredicto():
    from src.agents import critique
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = ctx(llm_local=FakeLLM("no se"), tmp=tmp)
        g = {"name": "s1", "statement": "x = 4 / 2", "attempts": 1, "history": []}
        out = critique(c, g, "nlinarith", "UNSOLVED_GOALS", "unsolved goals", False, 10, 2)
        assert out["error_class"] == "UNSOLVED_GOALS" and out["action"] == "REGENERATE_SKETCH"


def test_full_con_critico_presupuesto_es_techo_duro():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        local = FakeLLM(_plan_json(GOOD_SK, GOOD_SG), SKETCH, SKETCH, crit("UNSOLVED_GOALS"), SKETCH)
        prover = FakeLLM(prover_says("nlinarith"), prover_says("linarith"))
        c = ctx(llm_local=local, llm_prover=prover, repl=ScriptRepl(good=["  linarith"]), tmp=tmp)
        c.budget = Budget(max_llm_calls=6)  # plan + 2 + 1 + critico + boceto = 6, formalizar no cabe
        try:
            full(c, retriever=FakeRetriever())
        except BudgetExhausted:
            assert c.budget.by_agent["critic"] == 1
            return
    raise AssertionError("el grafo con Critico siguio llamando pasado el techo")


def test_full_resuelve_donde_agents_only_no():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        local = FakeLLM(_plan_json(GOOD_SK, GOOD_SG), SKETCH, SKETCH, SKETCH)
        c = ctx(llm_local=local, llm_prover=ReadsTheError(), repl=ScriptRepl(good=["  linarith"]),
                tmp=tmp)
        assert not agents_only(c)["solved"]  # dos intentos a ciegas, el mismo error
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        local = FakeLLM(_plan_json(GOOD_SK, GOOD_SG), SKETCH, SKETCH, crit("SYNTAX"))
        c = ctx(llm_local=local, llm_prover=ReadsTheError(), repl=ScriptRepl(good=["  linarith"]),
                tmp=tmp)
        assert full(c, retriever=FakeRetriever())["solved"]


def test_no_critic_usa_lemas_recuperados_y_reintenta_a_ciegas():
    uses = json.dumps({"steps": ["a"], "tactic_hints": ["nlinarith"], "uses_lemmas": ["sq_nonneg"]})
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        local = FakeLLM(_plan_json(GOOD_SK, GOOD_SG), uses, uses, uses)
        prover = FakeLLM(prover_says("nlinarith"), prover_says("linarith"))
        r = FakeRetriever()
        c = ctx(llm_local=local, llm_prover=prover, repl=ScriptRepl(good=["  linarith"]), tmp=tmp)
        out = no_critic(c, retriever=r)
        assert out["solved"] and r.ks == [10]  # el reintento ciego no vuelve a recuperar
        assert "`sq_nonneg`" in local.seen[1] and "sq_nonneg" in prover.seen[0]
        assert "unsolved goals" not in local.seen[-1] and "unsolved goals" not in prover.seen[-1]
        assert "critic" not in c.budget.by_agent
        assert not [e for e in events(c) if e.get("event") == "hallucinated_lemmas"]


def test_configs_sin_rag_no_cargan_el_recuperador():
    import subprocess
    code = ("import sys, run; assert {'no_critic', 'full', 'agents_only'} <= set(run.CONFIGS); "
            "assert 'faiss' not in sys.modules and 'src.retriever' not in sys.modules")
    subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1], check=True)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} pasan")
