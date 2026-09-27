"""Un caso fabricado a mano por veredicto. Es el criterio de 'hecho' de la semana 2.

Las respuestas del REPL son literales copiados del formato real de
leanprover-community/repl, para no depender de Docker en CI.

    python tests/test_verify.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.budget import Budget, BudgetExhausted
from src.lean_repl import ReplResult
from src.verify import ALLOWED_AXIOMS, classify, parse_axioms, verify


class FakeRepl:
    """Devuelve respuestas encoladas. El segundo `run` es el `#print axioms`."""

    def __init__(self, *responses: ReplResult):
        self.queue = list(responses)
        self.commands: list[str] = []

    def run(self, cmd, env=None, timeout=120.0):
        self.commands.append(cmd)
        return self.queue.pop(0)


def err(data):
    return {"severity": "error", "data": data}


def info(data):
    return {"severity": "info", "data": data}


CODE = "theorem t : 2 + 2 = 4 := by norm_num"


def test_ok():
    repl = FakeRepl(
        ReplResult(raw="{}", env=1),
        ReplResult(raw="{}", messages=[info("'t' depends on axioms: [propext, Classical.choice, Quot.sound]")]),
    )
    v = verify(CODE, repl, theorem_name="t")
    assert v.verdict == "OK", v.verdict
    assert v.ok
    assert set(v.axioms) <= ALLOWED_AXIOMS
    assert repl.commands[1] == "#print axioms t"


def test_ok_sin_axiomas():
    repl = FakeRepl(
        ReplResult(raw="{}", env=1),
        ReplResult(raw="{}", messages=[info("'t' does not depend on any axioms")]),
    )
    assert verify(CODE, repl, theorem_name="t").verdict == "OK"


def test_sorry():
    # El caso que hace falsificable la metrica principal si no se detecta.
    repl = FakeRepl(ReplResult(
        raw="{}",
        sorries=[{"pos": {"line": 1, "column": 30}, "goal": "2 + 2 = 4"}],
        messages=[{"severity": "warning", "data": "declaration uses 'sorry'"}],
        env=1,
    ))
    v = verify("theorem t : 2 + 2 = 4 := by sorry", repl, theorem_name="t")
    assert v.verdict == "SORRY", v.verdict
    assert len(repl.queue) == 0  # no llego a chequear axiomas: corta antes


def test_sorry_permitido_es_ok():
    # Modo VERIFY_SKELETON: los sorries son esperados, se comprueba que la
    # descomposicion tipa.
    repl = FakeRepl(ReplResult(
        raw="{}",
        sorries=[{"goal": "b * h = 195"}],
        messages=[{"severity": "warning", "data": "declaration uses 'sorry'"}],
        env=1,
    ))
    v = verify("theorem t ... := by\n  have s1 : b*h = 195 := by sorry",
               repl, theorem_name="t", allow_sorry=True)
    assert v.verdict == "OK", v.verdict


def test_axiom():
    # Compila, sin sorries, y aun asi no vale: `axiom cheat : False` prueba todo.
    repl = FakeRepl(
        ReplResult(raw="{}", env=1),
        ReplResult(raw="{}", messages=[info("'t' depends on axioms: [propext, cheat, Quot.sound]")]),
    )
    v = verify(CODE, repl, theorem_name="t")
    assert v.verdict == "AXIOM", v.verdict
    assert "cheat" in v.axioms


def test_missing_lemma():
    repl = FakeRepl(ReplResult(
        raw="{}",
        messages=[err("unknown identifier 'Nat.foo_bar_baz'")],
    ))
    v = verify(CODE, repl, theorem_name="t")
    assert v.verdict == "MISSING_LEMMA", v.verdict
    assert v.missing_identifiers == ["Nat.foo_bar_baz"]


def test_unsolved_goals():
    repl = FakeRepl(ReplResult(
        raw="{}",
        messages=[err("unsolved goals\nb h v : R\nh1 : v = 1/3 * (b*h)\n|- v = 65")],
    ))
    assert verify(CODE, repl, theorem_name="t").verdict == "UNSOLVED_GOALS"


def test_syntax_error():
    repl = FakeRepl(ReplResult(
        raw="{}",
        messages=[err("unexpected token ','; expected '=>'")],
    ))
    assert verify(CODE, repl, theorem_name="t").verdict == "SYNTAX_ERROR"


def test_sintaxis_lean3_no_es_lema_faltante():
    # Mensaje literal del kernel real para `begin ... end`.
    repl = FakeRepl(ReplResult(raw="{}", messages=[
        err("unknown identifier 'begin'"), err("invalid 'end', insufficient scopes")]))
    v = verify(CODE, repl, theorem_name="t")
    assert v.verdict == "SYNTAX_ERROR", v.verdict
    assert v.missing_identifiers == []


def test_timeout():
    repl = FakeRepl(ReplResult(raw="<timeout>", timed_out=True))
    assert verify(CODE, repl, theorem_name="t").verdict == "TIMEOUT"


def test_clasificacion_por_el_primer_error():
    # Lean emite errores en cascada; el primero es la causa. Aqui el identificador
    # desconocido provoca despues la meta abierta: debe ganar MISSING_LEMMA.
    assert classify([
        "unknown constant 'Real.sq_nonneg'",
        "unsolved goals\n|- 0 <= x ^ 2",
    ]) == "MISSING_LEMMA"


def test_parse_axioms():
    assert parse_axioms(["'t' does not depend on any axioms"]) == []
    assert parse_axioms(["'t' depends on axioms: [propext, Quot.sound]"]) == ["propext", "Quot.sound"]
    assert parse_axioms([]) == []


def test_budget_corta():
    b = Budget(max_llm_calls=20)
    for _ in range(20):
        b.spend("generator")
    assert b.remaining == 0
    assert not b.can_afford(1)
    try:
        b.spend("critic")
    except BudgetExhausted:
        pass
    else:
        raise AssertionError("el presupuesto no corto: el RNF-3 seria decorativo")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} pasan")
