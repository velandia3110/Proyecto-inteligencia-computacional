"""Analisis de la ablacion (semana 12): todo sale de agregar runs/*.jsonl (D5.3).

    python -m src.analysis runs/a.jsonl runs/b.jsonl ... --out results/

Un archivo por configuracion. Por configuracion: tasa de resolucion con IC de Wilson 95%,
llamadas por problema resuelto (RNF-3) y abandonados aparte, veredictos y costo (de
`runlog.summarize`). Por pares, sobre los problemas comunes: McNemar exacto con Bonferroni y,
como el estudio es exploratorio (riesgo §8.2), la diferencia de tasas con IC por bootstrap
pareado. Para baseline_b: falsos positivos evitados. Solo stdlib.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from itertools import combinations
from pathlib import Path

from src.runlog import summarize

ORDER = ["baseline_a", "baseline_b", "agents_only", "no_critic", "full"]
Z95 = statistics.NormalDist().inv_cdf(0.975)


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """IC de Wilson (sin correccion de continuidad). Con n chico no se sale de [0, 1]."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, mid - half), min(1.0, mid + half))


def mcnemar_exact(b: int, c: int) -> float:
    """p bilateral de McNemar exacto: binomial(b+c, 1/2) sobre los pares discordantes."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def bootstrap_diff(a: list[bool], b: list[bool], reps: int = 10_000, seed: int = 0,
                   alpha: float = 0.05) -> tuple[float, float]:
    """IC percentil de tasa(a) - tasa(b), remuestreando problemas (pareado)."""
    d = [int(x) - int(y) for x, y in zip(a, b)]
    n = len(d)
    if n == 0:
        return (0.0, 0.0)
    rng = random.Random(seed)
    stats = sorted(sum(rng.choices(d, k=n)) / n for _ in range(reps))
    return (stats[int(alpha / 2 * reps)], stats[int((1 - alpha / 2) * reps) - 1])


def load(path: str | Path) -> tuple[str, dict[str, dict]]:
    """(config, {problem_id: fila result}). La config sale del encabezado del log."""
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    config = next((r["config"] for r in rows if r["type"] == "header"), Path(path).stem)
    return config, {r["problem_id"]: r for r in rows if r["type"] == "result"}


def per_config(path: str | Path, results: dict[str, dict]) -> dict:
    s = summarize(path)
    k, n = s["solved"], s["problems"]
    solved = [r["llm_calls"] for r in results.values() if r["solved"]]
    failed = [r["llm_calls"] for r in results.values() if not r["solved"]]
    out = {
        "problems": n, "solved": k, "solve_rate": s["solve_rate"],
        "wilson95": [round(x, 4) for x in wilson(k, n)],
        # RNF-3 se mide sobre resueltos; los abandonados van aparte (D3 regla 3)
        "calls_solved": {"mean": round(statistics.fmean(solved), 2) if solved else None,
                         "max": max(solved, default=None),
                         "over_20": sum(c > 20 for c in solved)},
        "calls_abandoned": {"n": len(failed),
                            "mean": round(statistics.fmean(failed), 2) if failed else None,
                            "max": max(failed, default=None)},
        "verdicts": s["verdicts"],
        "cost_usd": s["cost_usd"],
        "cost_per_problem_usd": s["cost_per_problem_usd"],
        "cost_per_solved_usd": round(s["cost_usd"] / k, 4) if k else None,
    }
    sv = [r for r in results.values() if r.get("self_verdict") == "correct"]
    if any("self_verdict" in r for r in results.values()):  # solo baseline_b lo trae
        fp = sum(not r["solved"] for r in sv)
        out["false_positives_avoided"] = {
            "self_correct": len(sv), "kernel_rejected": fp,
            "rate": round(fp / len(sv), 4) if sv else None,
            "wilson95": [round(x, 4) for x in wilson(fp, len(sv))] if sv else None}
    return out


def pairwise(runs: dict[str, dict[str, dict]], reps: int, seed: int) -> list[dict]:
    pairs = list(combinations(runs, 2))
    out = []
    for a, b in pairs:
        ids = sorted(runs[a].keys() & runs[b].keys())  # solo los mismos problemas
        sa = [bool(runs[a][i]["solved"]) for i in ids]
        sb = [bool(runs[b][i]["solved"]) for i in ids]
        only_a = sum(x and not y for x, y in zip(sa, sb))
        only_b = sum(y and not x for x, y in zip(sa, sb))
        p = mcnemar_exact(only_a, only_b)
        n = len(ids)
        out.append({
            "a": a, "b": b, "n_common": n, "only_a": only_a, "only_b": only_b,
            "diff": round((sum(sa) - sum(sb)) / n, 4) if n else None,
            "diff_ci95_bootstrap": [round(x, 4) for x in bootstrap_diff(sa, sb, reps, seed)],
            "p_mcnemar": round(p, 6),
            "p_bonferroni": round(min(1.0, p * len(pairs)), 6),
        })
    return out


def analyze(paths: list[str], reps: int = 10_000, seed: int = 0) -> dict:
    runs, configs = {}, {}
    for p in paths:
        config, results = load(p)
        if config in runs:
            raise SystemExit(f"config repetida: {config} ({p})")
        runs[config] = results
        configs[config] = per_config(p, results)
    key = lambda c: ORDER.index(c) if c in ORDER else len(ORDER)
    runs = {c: runs[c] for c in sorted(runs, key=key)}
    return {"configs": {c: configs[c] for c in runs},
            "pairs": pairwise(runs, reps, seed),
            "bootstrap": {"reps": reps, "seed": seed}, "sources": [str(p) for p in paths]}


def _table(head: list[str], rows: list[list]) -> str:
    fmt = lambda v: "-" if v is None else str(v)
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    return "\n".join(lines + ["| " + " | ".join(map(fmt, r)) + " |" for r in rows])


def to_markdown(res: dict) -> str:
    cs = res["configs"]
    md = ["## Tasa de resolucion (IC de Wilson 95%)", _table(
        ["config", "n", "resueltos", "tasa", "IC 95%"],
        [[c, v["problems"], v["solved"], v["solve_rate"], v["wilson95"]] for c, v in cs.items()])]
    md += ["\n## Llamadas al LLM (RNF-3: <=20 por resuelto)", _table(
        ["config", "media resueltos", "max resueltos", ">20", "abandonados", "media abandonados",
         "max abandonados"],
        [[c, v["calls_solved"]["mean"], v["calls_solved"]["max"], v["calls_solved"]["over_20"],
          v["calls_abandoned"]["n"], v["calls_abandoned"]["mean"], v["calls_abandoned"]["max"]]
         for c, v in cs.items()])]
    verdicts = sorted({k for v in cs.values() for k in v["verdicts"]})
    md += ["\n## Veredictos", _table(
        ["config"] + verdicts, [[c] + [v["verdicts"].get(k, 0) for k in verdicts]
                                for c, v in cs.items()])]
    md += ["\n## Costo (USD)", _table(
        ["config", "total", "por problema", "por resuelto"],
        [[c, v["cost_usd"], v["cost_per_problem_usd"], v["cost_per_solved_usd"]]
         for c, v in cs.items()])]
    fp = {c: v["false_positives_avoided"] for c, v in cs.items() if "false_positives_avoided" in v}
    if fp:
        md += ["\n## Falsos positivos evitados (self_verdict correcto, kernel rechaza)", _table(
            ["config", "autoevaluadas correctas", "rechazadas por el kernel", "tasa", "IC 95%"],
            [[c, v["self_correct"], v["kernel_rejected"], v["rate"], v["wilson95"]]
             for c, v in fp.items()])]
    bs = res["bootstrap"]
    md += [f"\n## Por pares (McNemar exacto, Bonferroni x{len(res['pairs'])}; "
           f"bootstrap pareado {bs['reps']} reps, semilla {bs['seed']})", _table(
        ["a", "b", "n comun", "solo a", "solo b", "diff a-b", "IC 95% diff", "p", "p Bonferroni"],
        [[p["a"], p["b"], p["n_common"], p["only_a"], p["only_b"], p["diff"],
          p["diff_ci95_bootstrap"], p["p_mcnemar"], p["p_bonferroni"]] for p in res["pairs"]])]
    md += ["\nEstudio exploratorio (riesgo §8.2): leer el tamano de efecto y su IC, no solo p."]
    return "\n".join(md) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", help="un runs/*.jsonl por configuracion")
    ap.add_argument("--out", default="results")
    ap.add_argument("--reps", type=int, default=10_000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    res = analyze(args.runs, args.reps, args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "analysis.json").write_text(json.dumps(res, indent=2, ensure_ascii=False),
                                       encoding="utf-8")
    md = to_markdown(res)
    (out / "analysis.md").write_text(md, encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):  # consola de Windows con cp1252
        sys.stdout.reconfigure(encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
