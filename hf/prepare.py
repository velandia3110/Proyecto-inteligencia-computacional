"""Arma las carpetas a subir a Hugging Face. No sube nada y no usa tokens.

    python hf/prepare.py runs/*.jsonl --out hf/build

Deja dos carpetas:
  hf/build/dataset/  repo de resultados: trazas, test set evaluado, prompts congelados,
                     results/ (si existe) y MANIFEST.sha256
  hf/build/space/    el Space de Gradio con las mismas trazas en traces/

La subida se hace a mano despues de revisar el contenido, p.ej.:
  huggingface-cli upload <usuario>/<repo> hf/build/dataset --repo-type dataset
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HF = ROOT / "hf"


def evaluated_ids(traces: list[Path]) -> set[str]:
    return {json.loads(l)["problem_id"] for t in traces for l in open(t, encoding="utf-8")
            if l.strip() and json.loads(l)["type"] == "result"}


def prepare(traces: list[Path], out: Path, split: str = "test") -> Path:
    if not traces:
        raise SystemExit("sin trazas: primero hay que correr los experimentos (semana 11)")
    ds, sp = out / "dataset", out / "space"
    shutil.rmtree(out, ignore_errors=True)
    for d in (ds / "traces", ds / "prompts", sp / "traces"):
        d.mkdir(parents=True)
    for t in traces:
        shutil.copy2(t, ds / "traces" / t.name)
        shutil.copy2(t, sp / "traces" / t.name)
    for p in sorted((ROOT / "prompts").glob("*.md")):
        shutil.copy2(p, ds / "prompts" / p.name)
    # el test set publicado son exactamente los problemas que aparecen en las trazas
    ids = evaluated_ids(traces)
    src = ROOT / "data" / f"minif2f_{split}.jsonl"
    rows = [l for l in open(src, encoding="utf-8") if l.strip() and json.loads(l)["problem_id"] in ids]
    (ds / "test_set.jsonl").write_text("".join(rows), encoding="utf-8")
    if len(rows) != len(ids):
        print(f"aviso: {len(ids) - len(rows)} problemas de las trazas no estan en {src.name}")
    if (ROOT / "results").is_dir():
        shutil.copytree(ROOT / "results", ds / "results")
    shutil.copy2(HF / "README.md", ds / "README.md")
    for f in ("app.py", "requirements.txt", "README.md"):
        shutil.copy2(HF / "space" / f, sp / f)
    files = sorted(p for p in ds.rglob("*") if p.is_file())
    (ds / "MANIFEST.sha256").write_text("".join(
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ds).as_posix()}\n"
        for p in files), encoding="utf-8")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("traces", nargs="*", type=Path)
    ap.add_argument("--out", type=Path, default=HF / "build")
    ap.add_argument("--split", default="test", choices=["valid", "test"])
    a = ap.parse_args()
    print(f"listo: {prepare(a.traces, a.out, a.split)} (revisar antes de subir)")
