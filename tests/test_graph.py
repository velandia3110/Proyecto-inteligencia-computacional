"""Grafo agents_only y pool de REPLs, con LLM y REPL falsos.

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
from src.graph import agents_only

SKETCH = json.dumps({"steps": ["despejar x"], "tactic_hints": ["linarith"], "uses_lemmas": []})


def prover_says(tactic):
    return f"Plan.\n```lean4\ntheorem t_s1 (x : ℝ) (h₀ : 2 * x = 4) :\n    x = 4 / 2 := by\n  {tactic}\n```"


def events(c):
    c.log.close()
    return [json.loads(l) for l in open(c.log.path, encoding="utf-8") if '"event"' in l]


def test_camino_feliz():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        claude = FakeLLM(_plan_json(GOOD_SK, GOOD_SG), SKETCH, SKETCH)
        c = ctx(llm_claude=claude, llm_prover=FakeLLM(prover_says("linarith")),
                repl=ScriptRepl(good=["linarith"]), tmp=tmp)
        out = agents_only(c)
        assert out["solved"] and out["verdict"] == "OK", out
        assert "sorry" not in out["proof"] and "    linarith" in out["proof"]
        assert c.budget.used == 4  # plan + 2 bocetos + 1 formalizacion
        stages = [e.get("stage") for e in events(c)]
        assert stages == ["VERIFY_SKELETON", "VERIFY", "VERIFY_FINAL"], stages


def test_reintento_a_ciegas():
    # Sin Critico el segundo intento NO ve el error de Lean: eso es lo que la ablacion
    # de la semana 9 compara contra el Critico.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        claude = FakeLLM(_plan_json(GOOD_SK, GOOD_SG), SKETCH, SKETCH, SKETCH)
        prover = FakeLLM(prover_says("nlinarith"), prover_says("linarith"))
        c = ctx(llm_claude=claude, llm_prover=prover, repl=ScriptRepl(good=["  linarith"]), tmp=tmp)
        out = agents_only(c)
        assert out["solved"], out
        assert out["subgoals"][0]["attempts"] == 2
        assert c.budget.used == 6  # plan + 2 + 1, luego reintento con n=1: + 1 + 1
        assert "unsolved goals" not in claude.seen[-1] and "unsolved goals" not in prover.seen[-1]


def test_falla_tras_dos_intentos():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        claude = FakeLLM(_plan_json(GOOD_SK, GOOD_SG), SKETCH, SKETCH, SKETCH)
        prover = FakeLLM(prover_says("nlinarith"), prover_says("nlinarith"))
        c = ctx(llm_claude=claude, llm_prover=prover, repl=ScriptRepl(good=["  linarith"]), tmp=tmp)
        out = agents_only(c)
        assert not out["solved"] and out["verdict"] == "UNSOLVED_GOALS", out
        assert out["subgoals"][0]["status"] == "open"


def test_prover_sin_codigo_es_fallo_de_formalizacion():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        claude = FakeLLM(_plan_json(GOOD_SK, GOOD_SG), SKETCH, SKETCH, SKETCH)
        prover = FakeLLM("no se", prover_says("linarith"))
        c = ctx(llm_claude=claude, llm_prover=prover, repl=ScriptRepl(good=["  linarith"]), tmp=tmp)
        assert agents_only(c)["solved"]
        assert [e["verdict"] for e in events(c)][:2] == ["OK", "FORMALIZATION_FAILED"]


def test_plan_fallido():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = ctx(llm_claude=FakeLLM("x", "y"), tmp=tmp)
        out = agents_only(c)
        assert out["verdict"] == "PLANNING_ERROR" and not out["skeleton_ok"] and not out["solved"]


def test_presupuesto_es_techo_duro():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        claude = FakeLLM(_plan_json(GOOD_SK, GOOD_SG), SKETCH, SKETCH)
        c = ctx(llm_claude=claude, llm_prover=FakeLLM(prover_says("linarith")),
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


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} pasan")
