"""Los veredictos contra el kernel real. Necesita la imagen Docker:

    docker run --rm -v "$PWD:/work" -w /work mathagents-lean:v4.15.0 python3 tests/test_kernel.py

test_verify.py prueba la logica con respuestas fabricadas; este prueba que esas
respuestas se parecen a las de verdad.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data import HEADER
from src.lean_repl import ReadyRepl
from src.runlog import RunLog
from src.verify import verify

CASES = [
    ("OK", "theorem k1 (x : ℝ) (h : 2 * x = 4) : x = 2 := by linarith"),
    ("SORRY", "theorem k2 (x : ℝ) (h : 2 * x = 4) : x = 2 := by sorry"),
    ("AXIOM", "axiom cheat : False\ntheorem k3 : (1 : ℕ) = 2 := cheat.elim"),
    ("MISSING_LEMMA", "theorem k4 (x : ℝ) : 0 ≤ x ^ 2 := by exact Real.no_existe_este x"),
    ("UNSOLVED_GOALS", "theorem k5 (x : ℝ) (h : 0 < x) : x ^ 3 > x := by linarith"),
    ("SYNTAX_ERROR", "theorem k6 (x : ℕ) : x = x := begin refl end"),
]


def end_to_end(repl) -> bool:
    """Linea base A sobre un problema real de dev, con un LLM falso y el kernel real."""
    import tempfile

    from src import data
    from src.baselines import Ctx, baseline_a
    from src.llm import Reply

    p = next(r for r in data.load("valid") if r["problem_id"] == "mathd_algebra_48")

    class Fake:
        def complete(self, system, user, max_tokens=None):
            code = f"import Mathlib\n{p['formal_statement']} := by\n  rw [h₀, h₁]\n  ring"
            return Reply(f"Plan: sustituir y simplificar.\n```lean4\n{code}\n```", "fake", 1, 1, 1)

    with tempfile.TemporaryDirectory() as tmp:
        log = RunLog(Path(tmp) / "r.jsonl", "r", "baseline_a", 0, {})
        out = baseline_a(Ctx(problem=p, repl=repl, backends={"prover": Fake()}, log=log))
        log.close()
    ok = out["verdict"] == "OK"
    print(f"  {'ok ' if ok else 'MAL'} E2E baseline_a  -> {out['verdict']}")
    return ok


def graph_e2e(repl, tactic: str) -> dict:
    """agents_only (grafo completo, sin RAG ni Critico) con LLMs falsos y el kernel real."""
    import json
    import tempfile

    from src import data
    from src.baselines import Ctx
    from src.graph import agents_only
    from src.lean_text import subgoal_lemma
    from src.llm import Reply

    p = next(r for r in data.load("valid") if r["problem_id"] == "mathd_algebra_48")
    fs = p["formal_statement"]
    st = "q - e = (9 - 4 * Complex.I) - (-3 - 4 * Complex.I)"
    sk = f"{fs} := by\n  have step1 : {st} := by sorry\n  rw [step1]\n  ring"
    plan = json.dumps({"theorem_name": p["theorem_name"], "skeleton": sk, "rationale": "r",
                       "subgoals": [{"name": "step1", "statement": st, "depends_on": []}]})
    sketch = json.dumps({"steps": ["sustituir q y e"], "tactic_hints": ["rw"], "uses_lemmas": []})
    lemma = subgoal_lemma(fs, [], "step1", st)

    class Fake:
        def __init__(self, *texts):
            self.texts = list(texts)

        def complete(self, system, user, max_tokens=None):
            return Reply(self.texts.pop(0), "fake", 1, 1, 1)

    prover = Fake(*[f"```lean4\n{lemma} := by\n  {tactic}\n```"] * 2)
    with tempfile.TemporaryDirectory() as tmp:
        log = RunLog(Path(tmp) / "r.jsonl", "r", "agents_only", 0, {})
        ctx = Ctx(problem=p, repl=repl, backends={"llm": Fake(plan, *[sketch] * 3),
                                                   "prover": prover}, log=log)
        out = agents_only(ctx)
        log.close()
    return out


def graph_cases(repl) -> int:
    fails = 0
    out = graph_e2e(repl, "rw [h₀, h₁]")
    ok = out["solved"] is True and out["verdict"] == "OK" and "sorry" not in out["proof"]
    fails += not ok
    print(f"  {'ok ' if ok else 'MAL'} E2E agents_only -> {out['verdict']}")
    if not ok:
        print(out)
    # prueba mala dos veces (reintento a ciegas incluido) -> no resuelto
    out = graph_e2e(repl, "linarith")
    ok = not out["solved"] and out["verdict"] != "OK" and out["subgoals"][0]["attempts"] == 2
    fails += not ok
    print(f"  {'ok ' if ok else 'MAL'} E2E agents_only mala -> {out['verdict']}")
    return fails


def main() -> int:
    repl = ReadyRepl(HEADER)
    fails = 0
    try:
        for want, code in CASES:
            name = code.split("theorem ")[1].split()[0]
            v = verify(code, repl, theorem_name=name, timeout_s=60)
            ok = v.verdict == want
            fails += not ok
            print(f"  {'ok ' if ok else 'MAL'} {want:15} -> {v.verdict:15} {v.elapsed_ms} ms")
            if not ok:
                print(v.raw[:600])
        # modo esqueleto: con sorry permitido, la descomposicion debe dar OK
        sk = ("theorem k7 (x : ℝ) (h : 2 * x = 4) : x = 2 := by\n"
              "  have s1 : x = 4 / 2 := by sorry\n  linarith")
        v = verify(sk, repl, theorem_name="k7", allow_sorry=True)
        fails += v.verdict != "OK"
        print(f"  {'ok ' if v.verdict == 'OK' else 'MAL'} SKELETON        -> {v.verdict}")
        fails += not end_to_end(repl)
        fails += graph_cases(repl)
    finally:
        repl.close()
    total = len(CASES) + 4
    print(f"\n{total - fails}/{total} pasan")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
