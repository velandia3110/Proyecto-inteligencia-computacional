"""Recuperador (RF-3, design-document §4): top-k por coseno sobre Mathlib.

Vectores L2-normalizados + faiss.IndexFlatIP => producto interno = coseno, busqueda
exacta. Ningun error de recuperacion es atribuible al indice.

    python -m src.retriever build            # corpus -> data/index/
    python -m src.retriever recall 5 10 20   # curva recall@k (compuerta semana 6)

El corpus sale de lean/Extract.lean (mismo commit de Mathlib que el verificador).
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[1] / "data"
CORPUS = DATA / "mathlib_premises.jsonl"
INDEX_DIR = DATA / "index"
EMBEDDING_MODEL = "BAAI/bge-m3"
MATHLIB_COMMIT = "9837ca9d65d9de6fad1ef4381750ca688774e608"

# Lemas que Lean genera solo (sizeOf, inyectividad de constructores, ecuaciones).
# No los escribe nadie y ensucian el top-k.
_AUTOGEN = re.compile(r"\.(sizeOf_spec|injEq|inj|eq_\d+|eq_def|_sunfold|proof_\d+)$")


def load_corpus(path: Path = CORPUS) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f]
    return [r for r in rows if not _AUTOGEN.search(r["name"])]


def premise_text(r: dict) -> str:
    """design §4: "{nombre} : {tipo}\\n{docstring}". El tipo es la senal fuerte."""
    ty = re.sub(r"\s+", " ", r["type"])
    return f"{r['name']} : {ty}\n{r['doc']}".strip()


class Encoder:
    """BGE-M3 via sentence-transformers. Import perezoso: pesa y no siempre hace falta."""

    def __init__(self, model: str = EMBEDDING_MODEL):
        import torch
        from sentence_transformers import SentenceTransformer

        self.name = model
        # fp16 en GPU: BGE-M3 en fp32 no cabe comodo en 4 GB. En CPU se queda en fp32.
        cuda = torch.cuda.is_available()
        self.m = SentenceTransformer(model, device="cuda" if cuda else "cpu",
                                     model_kwargs={"torch_dtype": torch.float16} if cuda else {})
        self.m.max_seq_length = 512  # los tipos largos se cortan; el nombre va primero

    def encode(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        return self.m.encode(texts, batch_size=batch_size, normalize_embeddings=True,
                             convert_to_numpy=True, show_progress_bar=len(texts) > 1000
                             ).astype("float32")


class Retriever:
    def __init__(self, names: list[str], types: list[str], docs: list[str], vectors: np.ndarray,
                 encoder):
        import faiss

        self.names, self.types, self.docs = names, types, docs
        self.encoder = encoder
        self.index = faiss.IndexFlatIP(vectors.shape[1])
        self.index.add(vectors)

    @classmethod
    def load(cls, encoder=None, index_dir: Path = INDEX_DIR) -> "Retriever":
        meta = [json.loads(l) for l in open(index_dir / "meta.jsonl", encoding="utf-8")]
        vecs = np.load(index_dir / "vectors.npy")
        return cls([m["name"] for m in meta], [m["type"] for m in meta],
                   [m["doc"] for m in meta], vecs, encoder or Encoder())

    def search(self, query: str, k: int = 10) -> dict:
        """Salida conforme a docs/contracts/retriever.schema.json."""
        q = self.encoder.encode([query])
        scores, idx = self.index.search(q, k)
        return {
            "query": query, "k": k, "embedding_model": getattr(self.encoder, "name", "?"),
            "index_commit": MATHLIB_COMMIT,
            "lemmas": [{"name": self.names[i], "type": self.types[i], "docstring": self.docs[i],
                        "score": float(np.clip(s, -1, 1))}
                       for s, i in zip(scores[0], idx[0]) if i >= 0],
        }


class RemoteRetriever:
    """Mismo `search` contra `serve()` en otra maquina. La imagen de Lean no trae faiss ni
    BGE-M3, y cargarlos ahi (~3 GB) no cabe junto al REPL en los 8 GB de Docker."""

    def __init__(self, url: str):
        self.url = url.rstrip("/")

    def search(self, query: str, k: int = 10) -> dict:
        import urllib.request
        req = urllib.request.Request(self.url, json.dumps({"query": query, "k": k}).encode(),
                                     {"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=120))


def serve(port: int = 8765) -> None:
    """python -m src.retriever serve -> POST {"query", "k"} devuelve el JSON de `search`."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    r, lock = Retriever.load(), threading.Lock()

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            q = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with lock:
                body = json.dumps(r.search(q["query"], int(q.get("k", 10))), ensure_ascii=False)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

    print(f"recuperador en :{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()


def format_lemmas(result: dict) -> str:
    """Como van los lemas en los prompts. `agents._lemma_names` parsea este formato."""
    return "\n".join(f"- `{l['name']}` : {re.sub(r'\s+', ' ', l['type'])}"
                     for l in result["lemmas"]) or "(ninguno)"


def build(encoder=None, out: Path = INDEX_DIR) -> None:
    corpus = load_corpus()
    enc = encoder or Encoder()
    vecs = enc.encode([premise_text(r) for r in corpus])
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "vectors.npy", vecs)
    with open(out / "meta.jsonl", "w", encoding="utf-8") as f:
        for r in corpus:
            f.write(json.dumps({"name": r["name"], "type": r["type"], "doc": r["doc"]},
                               ensure_ascii=False) + "\n")
    print(f"{len(corpus)} premisas, dim {vecs.shape[1]}, modelo {enc.name}")


def recall_at_k(retriever: Retriever, ks: list[int], n: int = 1000, seed: int = 0) -> dict:
    """Consulta = tipo del teorema; relevantes = premisas que usa su prueba.

    recall@k = |relevantes en top-k| / |relevantes|, promediado sobre teoremas con al menos
    una premisa. El propio teorema se saca del top-k (siempre se recuperaria a si mismo).
    """
    full = load_corpus()
    names = {r["name"] for r in full}
    # Solo cuentan premisas que estan en el indice: una filtrada no se puede recuperar.
    corpus = [dict(r, premises=[p for p in r["premises"] if p in names]) for r in full]
    corpus = [r for r in corpus if r["premises"]]
    sample = random.Random(seed).sample(corpus, min(n, len(corpus)))
    kmax = max(ks) + 1
    sums = {k: 0.0 for k in ks}
    for r in sample:
        got = [l["name"] for l in retriever.search(re.sub(r"\s+", " ", r["type"]), kmax)["lemmas"]
               if l["name"] != r["name"]]
        rel = set(r["premises"])
        for k in ks:
            sums[k] += len(rel & set(got[:k])) / len(rel)
    return {"n": len(sample), "recall": {k: round(sums[k] / len(sample), 4) for k in ks}}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build":
        build()
    elif cmd == "serve":
        serve(int(sys.argv[2]) if len(sys.argv) > 2 else 8765)
    elif cmd == "recall":
        ks = [int(x) for x in sys.argv[2:]] or [5, 10, 20]
        print(json.dumps(recall_at_k(Retriever.load(), ks), indent=2))
    else:
        print(__doc__)
