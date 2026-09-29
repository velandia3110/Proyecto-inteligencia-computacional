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


def ctx(llm_local=None, llm_prover=None, repl=None, tmp=None):
    log = RunLog(Path(tmp) / "r.jsonl", "r", "test", 0, {})
    return Ctx(problem=PROBLEM, repl=repl or ScriptRepl(),
               backends={"llm": llm_local, "prover": llm_prover}, log=log)


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
        local = FakeLLM(json.dumps({"proof": "divide por 2", "self_verdict": "correct",
                                     "confidence": 0.99}), model="qwen3:4b-instruct")
        prover = FakeLLM(f"```lean4\n{FS} := by\n  nlinarith\n```")
        c = ctx(llm_local=local, llm_prover=prover, repl=ScriptRepl(good=[]), tmp=tmp)
        out = baseline_b(c)
        # el modelo dijo "correct" y el kernel dijo que no: eso es un falso positivo
        assert out["self_verdict"] == "correct" and not out["solved"], out
        assert c.budget.used == 2
        c.log.close()
        calls = [json.loads(l) for l in open(c.log.path, encoding="utf-8")][1:]
        assert calls[0]["cost_usd"] == 0  # modelo local


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


# --- semana 5-6: planificador, generador, recuperador ---------------------------

def _plan_json(skeleton, subgoals):
    return json.dumps({"theorem_name": "t", "skeleton": skeleton, "subgoals": subgoals,
                       "rationale": "r"})


GOOD_SK = f"{FS} := by\n  have s1 : x = 4 / 2 := by sorry\n  linarith"
GOOD_SG = [{"name": "s1", "statement": "x = 4 / 2", "depends_on": []}]


def test_planner_ok_a_la_primera():
    from src.agents import plan_and_check
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = ctx(llm_local=FakeLLM(_plan_json(GOOD_SK, GOOD_SG)), tmp=tmp)
        planned, verdict = plan_and_check(c)
        assert verdict == "OK" and planned["subgoals"][0]["name"] == "s1"
        assert c.budget.used == 1


def test_planner_que_cambia_el_enunciado_replanifica():
    from src.agents import plan_and_check
    bad = GOOD_SK.replace("x = 2 :=", "x = 3 :=")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        local = FakeLLM(_plan_json(bad, GOOD_SG), _plan_json(GOOD_SK, GOOD_SG))
        c = ctx(llm_local=local, tmp=tmp)
        planned, verdict = plan_and_check(c)
        assert verdict == "OK" and c.budget.used == 2
        assert "cambio el enunciado" in local.seen[1]  # el error llego al reintento


def test_planner_se_rinde_tras_un_replan():
    from src.agents import plan_and_check
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = ctx(llm_local=FakeLLM("no hay json", "tampoco"), tmp=tmp)
        planned, verdict = plan_and_check(c)
        assert planned is None and verdict == "PLANNING_ERROR" and c.budget.used == 2


def test_planner_sorry_extra_es_invalido():
    from src.agents import AgentError, plan
    sk = GOOD_SK.replace("  linarith", "  sorry")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = ctx(llm_local=FakeLLM(_plan_json(sk, GOOD_SG)), tmp=tmp)
        try:
            plan(c)
        except AgentError as e:
            assert "fuera de los subobjetivos" in str(e)
            return
    raise AssertionError("un sorry en la tactica final paso como plan valido")


def test_voto_y_lemas_inventados():
    from src.agents import generate, vote
    assert vote([{"tactic_hints": ["linarith"]}, {"tactic_hints": ["nlinarith [sq_nonneg x]"]},
                 {"tactic_hints": ["linarith", "norm_num"]}])[0] == 0
    lemmas = "- `mul_pos` : 0 < a → 0 < b → 0 < a * b"
    sk = lambda uses: json.dumps({"steps": ["a"], "tactic_hints": ["linarith"], "uses_lemmas": uses})
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        c = ctx(llm_local=FakeLLM(sk(["mul_pos", "Real.inventado"]), sk([])), tmp=tmp)
        out = generate(c, GOOD_SG[0], [], lemmas=lemmas, n=2)
        assert out["sketches"][0]["uses_lemmas"] == ["mul_pos"]
        assert out["agreement"] == 1.0 and c.budget.used == 2
        c.log.close()
        rows = [json.loads(l) for l in open(c.log.path, encoding="utf-8")]
        assert [r["lemmas"] for r in rows if r["type"] == "event"] == [["Real.inventado"]]
        assert summarize(c.log.path)["llm_calls"] == 2  # el evento no cuenta como llamada


def test_recuperador_coseno_exacto():
    import numpy as np
    from src.retriever import Retriever, format_lemmas

    class Enc:  # bolsa de palabras normalizada: suficiente para probar el cableado
        name = "fake"
        vocab = ["mul", "pos", "add", "comm", "sq", "nonneg"]

        def encode(self, texts):
            v = np.array([[t.count(w) for w in self.vocab] for t in texts], dtype="float32")
            return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)

    names = ["mul_pos", "add_comm", "sq_nonneg"]
    enc = Enc()
    r = Retriever(names, ["0 < a * b", "a + b = b + a", "0 ≤ a ^ 2"], ["", "", ""],
                  enc.encode(names), enc)
    out = r.search("sq nonneg", k=2)
    from src.llm import validate
    validate("retriever", out)
    assert out["lemmas"][0]["name"] == "sq_nonneg" and abs(out["lemmas"][0]["score"] - 1) < 1e-5
    from src.agents import _lemma_names
    assert _lemma_names(format_lemmas(out)) == {"sq_nonneg", out["lemmas"][1]["name"]}


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} pasan")
