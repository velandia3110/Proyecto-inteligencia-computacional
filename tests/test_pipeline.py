"""Pipeline sin Docker ni API: LLM y REPL falsos.

Lo que se prueba aqui es el cableado (prompts, contratos, presupuesto, log,
ensamblado). Si una prueba es correcta lo dice el kernel, y eso se prueba con
la imagen Docker (`python -m src.verify --smoke`).

    python tests/test_pipeline.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import lean_text as lt
from src.baselines import Ctx, baseline_a, baseline_b
from src.lean_repl import ReplResult
from src.llm import PROMPTS_DIR, Reply, load_prompt
from src.runlog import RunLog, summarize

FS = "theorem t (x : ℝ) (h₀ : 2 * x = 4) : x = 2"
PROBLEM = {"problem_id": "t", "theorem_name": "t", "nl_statement": "Si 2x=4, x=2.",
           "formal_statement": FS}


class FakeLLM:
    """Devuelve respuestas encoladas y guarda lo que se le pidio."""

    def __init__(self, *texts, model="fake"):
        self.texts, self.model, self.seen = list(texts), model, []

    def complete(self, system, user, max_tokens=None):
        self.seen.append(user)
        return Reply(self.texts.pop(0), self.model, 100, 50, 1)


class ScriptRepl:
    """Responde segun el codigo: `ok` si el codigo contiene alguna de las cadenas buenas."""

    def __init__(self, good=(), sorry_ok=True):
        self.good, self.commands = good, []

    def run(self, cmd, env=None, timeout=120.0):
        self.commands.append(cmd)
        if cmd.startswith("#print axioms"):
            return ReplResult("{}", messages=[{"severity": "info",
                              "data": "'x' depends on axioms: [propext]"}])
        if "sorry" in cmd:
            return ReplResult("{}", sorries=[{"goal": "?"}], env=2)
        if any(g in cmd for g in self.good):
            return ReplResult("{}", env=2)
        return ReplResult("{}", messages=[{"severity": "error", "data": "unsolved goals\n⊢ False"}])


def ctx(llm_claude=None, llm_prover=None, repl=None, tmp=None):
    log = RunLog(Path(tmp) / "r.jsonl", "r", "test", 0, {})
    return Ctx(problem=PROBLEM, repl=repl or ScriptRepl(),
               backends={"claude": llm_claude, "prover": llm_prover}, log=log)


# --- prompts -------------------------------------------------------------------

def test_todos_los_prompts_cargan():
    for f in PROMPTS_DIR.glob("*.md"):
        p = load_prompt(f.stem)
        assert p.user, f.stem
        assert p.meta.get("model"), f.stem


def test_placeholder_faltante_falla():
    try:
        load_prompt("baseline_a.v0").render(header="h")
    except KeyError:
        return
    raise AssertionError("un placeholder sin valor paso en silencio")


def test_json_del_prompt_no_se_confunde_con_placeholder():
    # planner.v0 trae un ejemplo JSON con llaves; no debe pedir valores por eso.
    load_prompt("planner.v0").render(nl_statement="a", formal_statement="b", retry_block="")


# --- texto lean ----------------------------------------------------------------

def test_split_statement():
    assert lt.split_statement(FS) == ("t", "(x : ℝ) (h₀ : 2 * x = 4)", "x = 2")
    assert lt.split_statement("theorem u : ∀ n : ℕ, n = n") == ("u", "", "∀ n : ℕ, n = n")


def test_statement_preserved():
    assert lt.statement_preserved(FS.replace(" (h₀", "\n    (h₀") + " := by linarith", FS)
    assert not lt.statement_preserved("theorem t (x : ℝ) (h₀ : 2 * x = 4) : x = 3 := by", FS)


def test_tactic_body_y_assemble():
    code = "theorem t_s1 (x : ℝ) :\n    x = x := by\n  have := 1\n  rfl"
    body = lt.tactic_body(code)
    assert body == "have := 1\nrfl", repr(body)
    sk = f"{FS} := by\n  have s1 : x = x := by sorry\n  linarith"
    out = lt.assemble(sk, {"s1": body})
    assert "sorry" not in out
    assert "  have s1 : x = x := by\n    have := 1\n    rfl" in out, out


def test_subgoal_lemma():
    s = lt.subgoal_lemma(FS, [("s1", "2 * x = 4")], "s2", "x = 2")
    assert s.startswith("theorem t_s2 (x : ℝ) (h₀ : 2 * x = 4) (s1 : 2 * x = 4) :")


# --- lineas base ---------------------------------------------------------------

def test_baseline_a_ok():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = ctx(llm_prover=FakeLLM(f"plan...\n```lean4\nimport Mathlib\n{FS} := by\n  linarith\n```"),
                repl=ScriptRepl(good=["linarith"]), tmp=tmp)
        out = baseline_a(c)
        assert out["verdict"] == "OK", out
        assert c.budget.used == 1
        assert "import" not in c.repl.commands[0]


def test_baseline_a_enunciado_cambiado():
    # Compilaria, pero es otro teorema: no puede contar como resuelto.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = ctx(llm_prover=FakeLLM("```lean4\ntheorem t (x : ℝ) : x = x := by rfl\n```"),
                repl=ScriptRepl(good=["rfl"]), tmp=tmp)
        assert baseline_a(c)["verdict"] == "STATEMENT_CHANGED"
        assert c.repl.commands == []


def test_baseline_b_falso_positivo_queda_registrado():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        claude = FakeLLM(json.dumps({"proof": "divide por 2", "self_verdict": "correct",
                                     "confidence": 0.99}), model="claude-opus-5")
        prover = FakeLLM(f"```lean4\n{FS} := by\n  nlinarith\n```")
        c = ctx(llm_claude=claude, llm_prover=prover, repl=ScriptRepl(good=[]), tmp=tmp)
        out = baseline_b(c)
        # el modelo dijo "correct" y el kernel dijo que no: eso es un falso positivo
        assert out["self_verdict"] == "correct" and not out["solved"], out
        assert c.budget.used == 2
        c.log.close()
        calls = [json.loads(l) for l in open(c.log.path, encoding="utf-8")][1:]
        assert calls[0]["cost_usd"] == (100 * 5 + 50 * 25) / 1e6


def test_summarize():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        log = RunLog(Path(tmp) / "r.jsonl", "r", "x", 0, {})
        log.write(problem_id="a", agent="baseline_a", cost_usd=0.5)
        log.result(problem_id="a", verdict="OK", solved=True, llm_calls=1)
        log.result(problem_id="b", verdict="SORRY", solved=False, llm_calls=3)
        log.close()
        s = summarize(log.path)
        assert s["solved"] == 1 and s["problems"] == 2 and s["cost_per_problem_usd"] == 0.25


def test_runner_no_abre_test():
    import run
    try:
        run.main(["--config", "baseline_a", "--split", "test"])
    except SystemExit as e:
        assert "semana 11" in str(e)
        return
    raise AssertionError("el runner abrio el test set sin --abrir-test")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} pasan")
