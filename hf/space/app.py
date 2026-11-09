"""Space de Gradio (riesgo §8.3): Lean + Mathlib no caben en un Space, asi que aqui no
corre el kernel. Se reproducen trazas ya ejecutadas y la "verificacion en vivo" solo
acepta pruebas cacheadas: si el texto coincide (sha256) con una prueba que el kernel ya
juzgo en la corrida, se devuelve ese veredicto; si no, se dice que hace falta Lean local.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

TRACES = Path(__file__).parent / "traces"


def _h(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def load(traces: Path = TRACES) -> tuple[dict, dict]:
    """runs: {config: {problem_id: [filas]}}; cache: {sha256(prueba): (config, id, veredicto)}."""
    runs, cache = {}, {}
    for f in sorted(traces.glob("*.jsonl")):
        rows = [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
        config = next((r["config"] for r in rows if r["type"] == "header"), f.stem)
        by_pid = runs.setdefault(config, {})
        for r in rows:
            if "problem_id" in r:
                by_pid.setdefault(r["problem_id"], []).append(r)
            if r["type"] == "result" and r.get("proof"):
                cache[_h(r["proof"])] = (config, r["problem_id"], r["verdict"])
    return runs, cache


def trace(runs: dict, config: str, pid: str) -> tuple[str, str]:
    rows = runs.get(config, {}).get(pid, [])
    res = next((r for r in rows if r["type"] == "result"), {})
    steps = "\n".join(f"{i:>3}  {r['type']:<6} {r.get('agent', '-'):<16} "
                      f"{r.get('verdict') or r.get('decision') or ''}"
                      for i, r in enumerate(rows) if r["type"] != "result")
    summary = (f"veredicto: {res.get('verdict')}  resuelto: {res.get('solved')}  "
               f"llamadas LLM: {res.get('llm_calls')}\n\n{steps}")
    return summary, res.get("proof") or ""


def check(cache: dict, proof: str) -> str:
    hit = cache.get(_h(proof))
    if hit:
        return f"cacheada: el kernel dio {hit[2]} ({hit[0]}, {hit[1]})"
    return "no cacheada: verificar en local con la imagen Docker (python -m src.verify)"


def ui():
    import gradio as gr

    runs, cache = load()
    configs = sorted(runs)
    with gr.Blocks(title="mathagents") as demo:
        gr.Markdown("Trazas de miniF2F verificadas por Lean 4. Solo se verifican pruebas cacheadas.")
        cfg = gr.Dropdown(configs, label="configuracion", value=configs[0] if configs else None)
        pid = gr.Dropdown([], label="problema")
        out = gr.Textbox(label="traza", lines=16)
        proof = gr.Code(label="prueba (editable)", language=None)
        verdict = gr.Textbox(label="verificacion")
        cfg.change(lambda c: gr.update(choices=sorted(runs.get(c, {})), value=None), cfg, pid)
        pid.change(lambda c, p: trace(runs, c, p), [cfg, pid], [out, proof])
        gr.Button("verificar").click(lambda p: check(cache, p), proof, verdict)
    return demo


if __name__ == "__main__":
    ui().launch()
