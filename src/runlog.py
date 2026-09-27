"""Log JSONL de una corrida (RF-7) y la agregacion de metricas (D5.3).

Una linea por invocacion de agente, una linea `result` por problema, y un
encabezado con todo lo que hace falta para reproducir (RNF-2).

    python -m src.runlog runs/<run_id>.jsonl      # resumen de la corrida
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path


def _repo_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return "unknown"


def _mathlib_commit() -> str:
    p = Path("/app/mathlib-commit.txt")
    return p.read_text().strip() if p.exists() else "unknown"


class RunLog:
    def __init__(self, path: Path, run_id: str, config: str, seed: int, models: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.run_id = run_id
        self.config = config
        self._lock = threading.Lock()  # los workers escriben al mismo archivo
        self._f = open(path, "a", encoding="utf-8")
        self._emit({
            "type": "header", "run_id": run_id, "config": config, "seed": seed,
            "models": models, "mathlib_commit": _mathlib_commit(),
            "repo_commit": _repo_commit(), "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })

    def _emit(self, obj: dict) -> None:
        with self._lock:
            self._f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self._f.flush()

    def write(self, **fields) -> None:
        self._emit({"type": "call", "run_id": self.run_id, "config": self.config, **fields})

    def event(self, **fields) -> None:
        """Algo que paso y no es una llamada (p.ej. un lema alucinado). No cuenta en el RNF-3."""
        self._emit({"type": "event", "run_id": self.run_id, "config": self.config, **fields})

    def result(self, **fields) -> None:
        self._emit({"type": "result", "run_id": self.run_id, "config": self.config, **fields})

    def close(self) -> None:
        self._f.close()


def summarize(path: str | Path) -> dict:
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    results = [r for r in rows if r["type"] == "result"]
    calls = [r for r in rows if r["type"] == "call"]
    n = len(results)
    solved = sum(r["solved"] for r in results)
    cost = sum(c.get("cost_usd", 0) for c in calls)
    solved_calls = [r["llm_calls"] for r in results if r["solved"]]
    out = {
        "problems": n,
        "solved": solved,
        "solve_rate": round(solved / n, 4) if n else 0.0,
        "verdicts": dict(Counter(r["verdict"] for r in results)),
        "llm_calls": len(calls),
        "calls_by_agent": dict(Counter(c["agent"] for c in calls)),
        "max_calls_on_solved": max(solved_calls, default=0),  # RNF-3: debe ser <= 20
        "cost_usd": round(cost, 4),
        "cost_per_problem_usd": round(cost / n, 4) if n else 0.0,
    }
    sk = [r["skeleton_ok"] for r in results if "skeleton_ok" in r]
    if sk:  # compuerta de semana 6: esqueletos que compilan con sus sorries
        out["skeleton_ok_rate"] = round(sum(sk) / len(sk), 4)
    return out


if __name__ == "__main__":
    print(json.dumps(summarize(sys.argv[1]), indent=2, ensure_ascii=False))
