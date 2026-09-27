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
    from src.runlog import RunLog

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
    finally:
        repl.close()
    total = len(CASES) + 2
    print(f"\n{total - fails}/{total} pasan")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
