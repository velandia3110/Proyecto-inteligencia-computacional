"""Analisis de la semana 12 con JSONL sinteticos. Ningun numero de aqui es un resultado.

    python tests/test_analysis.py
"""

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "hf"))
sys.path.insert(0, str(ROOT / "hf" / "space"))

from src.analysis import analyze, bootstrap_diff, main, mcnemar_exact, to_markdown, wilson


def fake_run(d: Path, config: str, solved: list[bool], calls: list[int],
             self_verdicts: list | None = None) -> Path:
    """Un JSONL con el mismo formato que escribe RunLog: header, calls y results."""
    rows = [{"type": "header", "run_id": f"x-{config}", "config": config, "seed": 0}]
    for i, (s, c) in enumerate(zip(solved, calls)):
        pid = f"p{i:02d}"
        rows += [{"type": "call", "config": config, "problem_id": pid, "agent": "planner",
                  "cost_usd": 0.001} for _ in range(c)]
        r = {"type": "result", "config": config, "problem_id": pid, "llm_calls": c,
             "solved": s, "verdict": "OK" if s else "UNSOLVED_GOALS", "proof": f"proof {config} {i}"}
        if self_verdicts is not None:
            r["self_verdict"] = self_verdicts[i]
        rows.append(r)
    p = d / f"{config}.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def close(a, b, tol=1e-4):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def test_wilson_valores_conocidos():
    assert close(wilson(5, 10), (0.2366, 0.7634))
    assert close(wilson(0, 10), (0.0, 0.2775))
    assert close(wilson(10, 10), (0.7225, 1.0))
    assert wilson(0, 0) == (0.0, 1.0)


def test_mcnemar_exacto_valores_conocidos():
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(0, 5) == 2 / 32           # 2 * 0.5^5
    assert mcnemar_exact(1, 9) == 2 * 11 / 1024    # 2 * (C(10,0)+C(10,1)) / 2^10
    assert mcnemar_exact(9, 1) == mcnemar_exact(1, 9)
    assert mcnemar_exact(5, 5) == 1.0


def test_contra_scipy():
    try:
        from scipy.stats import binomtest
    except ImportError:
        print("      (scipy no instalado: se omite, `pip install .[analysis]`)")
        return
    for k, n in [(0, 7), (3, 10), (17, 50), (50, 50)]:
        ci = binomtest(k, n).proportion_ci(method="wilson")
        assert close(wilson(k, n), (ci.low, ci.high), 1e-9), (k, n)
    for b, c in [(0, 3), (2, 8), (7, 4), (12, 30)]:
        assert abs(mcnemar_exact(b, c) - binomtest(b, b + c, 0.5).pvalue) < 1e-12, (b, c)


def test_bootstrap_determinista():
    a = [True] * 30 + [False] * 20
    b = [True] * 20 + [False] * 30
    ci = bootstrap_diff(a, b, reps=2000, seed=7)
    assert ci == bootstrap_diff(a, b, reps=2000, seed=7)
    assert ci[0] <= 0.2 <= ci[1] and ci[0] > 0  # 10 discordantes, todos a favor de a
    assert bootstrap_diff(a, a, reps=500) == (0.0, 0.0)


def test_analyze_de_punta_a_punta():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        n = 20
        full = [i < 12 for i in range(n)]
        ba = [i < 4 for i in range(n)]
        bb = [i < 2 for i in range(n)]
        sv = ["correct"] * 10 + ["incorrect"] * 9 + [None]  # 10 dice correcta, kernel acepta 2
        paths = [fake_run(d, "full", full, [8] * 11 + [25] + [20] * 8),
                 fake_run(d, "baseline_a", ba, [1] * n),
                 fake_run(d, "baseline_b", bb, [2] * n, sv)]
        res = analyze([str(p) for p in paths], reps=1000, seed=0)

        assert list(res["configs"]) == ["baseline_a", "baseline_b", "full"]  # orden de §6
        f = res["configs"]["full"]
        assert f["solved"] == 12 and f["wilson95"] == [round(x, 4) for x in wilson(12, 20)]
        assert f["calls_solved"] == {"mean": 9.42, "max": 25, "over_20": 1}
        assert f["calls_abandoned"] == {"n": 8, "mean": 20, "max": 20}
        assert f["verdicts"] == {"OK": 12, "UNSOLVED_GOALS": 8}
        fp = res["configs"]["baseline_b"]["false_positives_avoided"]
        assert fp["self_correct"] == 10 and fp["kernel_rejected"] == 8 and fp["rate"] == 0.8
        assert "false_positives_avoided" not in f

        assert len(res["pairs"]) == 3
        p = next(x for x in res["pairs"] if (x["a"], x["b"]) == ("baseline_a", "full"))
        assert (p["only_a"], p["only_b"], p["diff"]) == (0, 8, -0.4)
        assert p["p_mcnemar"] == round(2 / 256, 6) and p["p_bonferroni"] == round(6 / 256, 6)
        assert p["diff_ci95_bootstrap"][1] < 0
        assert res == analyze([str(p) for p in paths], reps=1000, seed=0)  # determinista
        assert "Falsos positivos evitados" in to_markdown(res)

        with contextlib.redirect_stdout(io.StringIO()):
            main([str(p) for p in paths] + ["--out", str(d / "results"), "--reps", "200"])
        assert json.loads((d / "results" / "analysis.json").read_text(encoding="utf-8"))["pairs"]


def test_solo_problemas_comunes():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        a = fake_run(d, "full", [True] * 10, [3] * 10)
        b = fake_run(d, "no_critic", [False] * 6, [3] * 6)  # solo p00..p05
        p = analyze([str(a), str(b)], reps=200)["pairs"][0]
        assert p["n_common"] == 6 and p["a"] == "no_critic" and p["only_a"] == 0


def test_hf_prepare_y_space():
    from app import check, load, trace
    from prepare import prepare

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        run = fake_run(d, "full", [True, False], [3, 5])
        test = [json.loads(l) for l in open(ROOT / "data" / "minif2f_test.jsonl", encoding="utf-8")]
        # los ids sinteticos no estan en miniF2F; se reescriben con dos ids reales
        rows = [json.loads(l) for l in open(run, encoding="utf-8")]
        for r in rows:
            if "problem_id" in r:
                r["problem_id"] = test[int(r["problem_id"][1:])]["problem_id"]
        run.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

        out = prepare([run], d / "build")
        ds = out / "dataset"
        assert len((ds / "test_set.jsonl").read_text(encoding="utf-8").splitlines()) == 2
        manifest = (ds / "MANIFEST.sha256").read_text(encoding="utf-8")
        assert "traces/full.jsonl" in manifest and "test_set.jsonl" in manifest
        assert (out / "space" / "app.py").exists()

        runs, cache = load(out / "space" / "traces")
        pid = test[0]["problem_id"]
        summary, proof = trace(runs, "full", pid)
        assert "resuelto: True" in summary and proof == "proof full 0"
        assert check(cache, proof).startswith("cacheada: el kernel dio OK")
        assert check(cache, "by sorry").startswith("no cacheada")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} pasan")
