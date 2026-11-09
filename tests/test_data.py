"""Test set de la semana 10 y parser de PutnamBench, sin red ni Lean.

    python tests/test_data.py
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import data

IDS = data.test_ids()


def test_seleccion_determinista():
    assert data.select_test_set(IDS) == data.select_test_set(list(reversed(IDS)))
    assert data.select_test_set(IDS) != data.select_test_set(IDS, seed=data.TEST_SET_SEED + 1)


def test_tamano():
    assert 40 <= len(data.select_test_set(IDS)) <= 60


def test_estratificacion():
    sel = data.select_test_set(IDS)
    assert len(set(sel)) == len(sel) and set(sel) <= set(IDS)
    total, got = Counter(map(data.stratum, IDS)), Counter(map(data.stratum, sel))
    assert set(got) == set(total)  # ninguna fuente queda fuera
    for s, n in total.items():
        assert got[s] >= 2
        assert abs(got[s] - len(sel) * n / len(IDS)) <= 1.5, s  # proporcional salvo el minimo


def test_estratos():
    assert data.stratum("mathd_numbertheory_3") == "mathd_numbertheory"
    assert data.stratum("amc12b_2002_p7") == data.stratum("amc12_2000_p20") == "amc12"
    assert data.stratum("imosl_2007_algebra_p6") == data.stratum("imo_1960_p2") == "imo"


def test_archivo_y_hash():
    ids = data.load_test_set()  # falla si el archivo no casa con TEST_SET_SHA256
    assert ids == data.select_test_set(IDS)


def test_parse_putnam():
    text = ("import Mathlib\n\nopen Real\n\nabbrev putnam_x_solution : ℕ := sorry\n-- 2\n"
            "def f : ℕ := 1\n/--\nHalla n.\n-/\ntheorem putnam_x : f + 1 = putnam_x_solution :=\nsorry\n")
    r = data.parse_putnam("putnam_x", text)
    assert r["solution_answer"] == "2"
    assert r["preamble"].startswith("open Real") and "def f" in r["preamble"]
    assert r["nl_statement"] == "Halla n."
    assert r["formal_statement"] == "theorem putnam_x : f + 1 = putnam_x_solution"
    sin = data.parse_putnam("putnam_y", "import Mathlib\n/--\nP.\n-/\ntheorem putnam_y : True :=\n  sorry\n")
    assert sin["solution_answer"] is None and sin["preamble"] == ""


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} pasan")
