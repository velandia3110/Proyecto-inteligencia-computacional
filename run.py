"""Runner: una configuracion sobre un split, todo al JSONL de runs/.

    python run.py --config baseline_a --limit 5
    python run.py --config baseline_b --problems mathd_algebra_478,amc12a_2015_p10
    python run.py --config agents_only --limit 20 --workers 2
    python -m src.runlog runs/<run_id>.jsonl

Se corre dentro de la imagen Docker (necesita el REPL de Lean). Ver README.
"""

from __future__ import annotations

import argparse
import json
import random
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src import data
from src.agents import plan_only
from src.baselines import Ctx, baseline_a, baseline_b
from src.budget import BudgetExhausted
from src.graph import agents_only
from src.runlog import RunLog, summarize

CONFIGS = {"baseline_a": baseline_a, "baseline_b": baseline_b, "plan_only": plan_only,
           "agents_only": agents_only}


def make_backends() -> dict:
    """Perezoso: una config que no usa el prover no exige PROVER_URL, y al reves."""
    from src.llm import Claude, Prover

    class Lazy:
        def __init__(self, factory):
            self.factory, self.obj = factory, None
            self.lock = threading.Lock()  # los workers comparten el backend

        def complete(self, *a, **kw):
            with self.lock:
                self.obj = self.obj or self.factory()
            return self.obj.complete(*a, **kw)

    return {"claude": Lazy(Claude), "prover": Lazy(Prover)}


def run_problem(problem: dict, config: str, repl, backends: dict, log: RunLog) -> dict:
    ctx = Ctx(problem=problem, repl=repl, backends=backends, log=log)
    t = time.monotonic()
    try:
        out = CONFIGS[config](ctx)
    except BudgetExhausted:
        out = {"verdict": "BUDGET_EXHAUSTED", "solved": False}
    except Exception as e:  # un problema roto no tumba la corrida; queda en el log
        out = {"verdict": "CRASH", "solved": False, "error": f"{type(e).__name__}: {e}",
               "trace": traceback.format_exc()[-2000:]}
    log.result(problem_id=ctx.problem_id, llm_calls=ctx.budget.used,
               calls_by_agent=dict(ctx.budget.by_agent),
               wall_ms=int((time.monotonic() - t) * 1000), **out)
    return out


def select(args) -> list[dict]:
    if args.split == "test" and not args.abrir_test:
        raise SystemExit("el test set se abre UNA vez, en la semana 11 (D5.1). "
                         "Si es ese momento, agregar --abrir-test.")
    problems = data.load(args.split)
    if args.problems:
        wanted = set(args.problems.split(","))
        problems = [p for p in problems if p["problem_id"] in wanted]
    if args.limit:
        problems = random.Random(args.seed).sample(problems, min(args.limit, len(problems)))
    return problems


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, choices=sorted(CONFIGS))
    ap.add_argument("--split", default="valid", choices=["valid", "test"])
    ap.add_argument("--abrir-test", action="store_true")
    ap.add_argument("--problems", help="ids separados por coma")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=1,
                    help="problemas en paralelo = REPLs en el pool (no pasar de 3)")
    args = ap.parse_args(argv)

    problems = select(args)
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{args.config}"
    log = RunLog(Path("runs") / f"{run_id}.jsonl", run_id, args.config, args.seed,
                 models={"claude": "claude-opus-5", "prover": "Goedel-LM/Goedel-Prover-V2-8B"})

    from src.repl_pool import ReplPool

    pool = ReplPool(data.HEADER, size=args.workers)
    backends = make_backends()
    done = iter(range(1, len(problems) + 1))  # next() sobre un iterador es atomico con el GIL

    def one(p):
        with pool.acquire() as repl:  # el REPL es del problema mientras dure
            out = run_problem(p, args.config, repl, backends, log)
        print(f"[{next(done)}/{len(problems)}] {p['problem_id']}: {out['verdict']}", flush=True)

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            list(ex.map(one, problems))
    finally:
        pool.close()
        log.close()
    print(json.dumps(summarize(log.path), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
