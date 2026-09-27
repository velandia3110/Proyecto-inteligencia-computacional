"""Manipulacion de texto Lean: extraer, comprobar, partir y ensamblar.

Nada de esto decide si una prueba es correcta (eso es del kernel). Lo que si
decide es que el kernel este revisando el teorema correcto: `statement_preserved`
existe porque un modelo puede "probar" un enunciado mas facil y compilar limpio.
"""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", s).strip()


def extract_lean_block(text: str) -> str | None:
    """Ultimo bloque ```lean / ```lean4 de la respuesta: los provers razonan antes."""
    blocks = re.findall(r"```lean4?\s*\n(.*?)```", text, re.S)
    return blocks[-1].strip() if blocks else None


def strip_imports(code: str) -> str:
    # El REPL ya tiene el encabezado cargado; un `import` a mitad de sesion es error.
    return "\n".join(l for l in code.splitlines() if not l.lstrip().startswith("import "))


def statement_preserved(code: str, formal_statement: str) -> bool:
    return _norm(formal_statement) in _norm(code)


def split_statement(formal_statement: str) -> tuple[str, str, str]:
    """'theorem foo (x : R) (h : x > 0) : x ^ 2 > 0' -> ('foo', '(x : R) (h : x > 0)', 'x ^ 2 > 0').

    Parte en el primer ':' que no esta dentro de parentesis, corchetes o llaves.
    """
    m = re.match(r"\s*(?:theorem|lemma)\s+(\S+)", formal_statement)
    if not m:
        raise ValueError("no empieza con theorem/lemma")
    name, rest = m[1], formal_statement[m.end():]
    depth = 0
    for i, ch in enumerate(rest):
        if ch in "([{⦃":
            depth += 1
        elif ch in ")]}⦄":
            depth -= 1
        elif ch == ":" and depth == 0 and rest[i + 1 : i + 2] != "=":
            return name, rest[:i].strip(), rest[i + 1 :].strip()
    raise ValueError("no hay ':' de nivel superior")


def subgoal_lemma(formal_statement: str, prev: list[tuple[str, str]], name: str,
                  statement: str) -> str:
    """El subobjetivo como lema suelto: hipotesis del teorema + `have` previos como hipotesis.

    Asi se verifica aislado (y el prover lo ve como un teorema normal). Como los
    nombres coinciden con los del esqueleto, la prueba se trasplanta tal cual.
    """
    thm, binders, _ = split_statement(formal_statement)
    extra = " ".join(f"({n} : {s})" for n, s in prev)
    return f"theorem {thm}_{name} {binders} {extra} :\n    {statement}".replace("  :", " :")


def tactic_body(code: str) -> str | None:
    """Lo que va despues del primer ':= by' del ultimo teorema del bloque."""
    idx = code.rfind("theorem ")
    if idx < 0:
        return None
    m = re.search(r":=\s*by\b", code[idx:])
    if not m:
        return None
    body = code[idx + m.end():]
    lines = body.split("\n")
    first, rest = lines[0].strip(), [l for l in lines[1:] if l.strip()]
    if not rest:
        return first or None
    indent = min(len(l) - len(l.lstrip()) for l in rest)
    out = ([first] if first else []) + [l[indent:] for l in rest]
    return "\n".join(out).strip() or None


def assemble(skeleton: str, proofs: dict[str, str]) -> str:
    """Reemplaza el `sorry` de cada `have name : ... := by sorry` por su prueba (ASSEMBLE)."""
    out = []
    for line in skeleton.splitlines():
        m = re.match(r"^(\s*)have\s+(\w+)\b(.*?):=\s*by\s+sorry\s*$", line)
        if m and m[2] in proofs:
            ind = m[1]
            body = "\n".join(ind + "  " + l for l in proofs[m[2]].splitlines())
            out.append(f"{ind}have {m[2]}{m[3]}:= by\n{body}")
        else:
            out.append(line)
    return "\n".join(out)
