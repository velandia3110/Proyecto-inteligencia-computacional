"""Prompts como archivos (D5.2) y los dos backends de LLM.

- Ollama (planificacion, generacion, critica): modelo local, costo 0 por token.
  Reemplazo a Claude por costo (decisions.md historial 2026-09-28).
- Prover (formalizacion): Goedel-Prover-V2 en un endpoint compatible con OpenAI
  (vLLM, o el /v1 de Ollama). Con una GPU de 4 GB el 8B no cabe entero.
Los dos por HTTP plano (stdlib).

Cada llamada pasa por `call()`, que es el unico sitio donde se gasta presupuesto
y se escribe la linea del JSONL. Asi el conteo del RNF-3 no se puede saltar.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "docs" / "contracts"

# USD por millon de tokens (entrada, salida). Todo corre local: costo marginal 0 por
# token; el costo real es la hora de GPU y se reporta aparte. Un modelo de API va aqui.
PRICES: dict[str, tuple[float, float]] = {}

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:4b-instruct")
PROVER_MODEL = os.environ.get("PROVER_MODEL", "Goedel-LM/Goedel-Prover-V2-8B")


# --- prompts ------------------------------------------------------------------

@dataclass
class Prompt:
    name: str
    meta: dict
    system: str
    user: str
    retry: str  # plantilla del bloque de reintento, "" si el prompt no tiene

    def render(self, **vals: str) -> tuple[str, str]:
        return _fill(self.system, vals), _fill(self.user, vals)

    def render_retry(self, **vals: str) -> str:
        return _fill(self.retry, vals) if self.retry else ""


_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _fill(text: str, vals: dict) -> str:
    # No se usa str.format: los prompts traen ejemplos JSON con llaves.
    def sub(m: re.Match) -> str:
        if m[1] not in vals:
            raise KeyError(f"falta el placeholder {{{m[1]}}}")
        return str(vals[m[1]])

    return _PLACEHOLDER.sub(sub, text)


def load_prompt(name: str) -> Prompt:
    """`name` = 'planner.v0'. Formato: frontmatter, # System, # User, --- bloque de reintento."""
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    _, front, body = text.split("---\n", 2)
    meta = dict(
        (k.strip(), v.strip()) for k, v in
        (l.split(":", 1) for l in front.strip().splitlines() if ":" in l)
    )
    main, _, tail = body.partition("\n---\n")
    system = main.split("# System", 1)[1].split("# User", 1)[0].strip()
    user = main.split("# User", 1)[1].strip()
    m = re.search(r"```\n(.*?)```", tail, re.S)
    return Prompt(name, meta, system, user, m[1].strip() if m else "")


# --- contratos (RNF-4) ----------------------------------------------------------

_validators: dict = {}


def validate(agent: str, obj: dict) -> None:
    """Levanta jsonschema.ValidationError si `obj` no cumple el contrato del agente."""
    import jsonschema

    if agent not in _validators:
        schema = json.loads((CONTRACTS_DIR / f"{agent}.schema.json").read_text(encoding="utf-8"))
        _validators[agent] = jsonschema.Draft202012Validator(schema)
    _validators[agent].validate(obj)


def parse_json(text: str) -> dict:
    """El modelo a veces envuelve el JSON en ```json. Se toma del primer { al ultimo }."""
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j < i:
        raise ValueError("la respuesta no trae JSON")
    return json.loads(text[i : j + 1])


# --- backends -------------------------------------------------------------------

@dataclass
class Reply:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int

    @property
    def cost_usd(self) -> float:
        pin, pout = PRICES.get(self.model, (0.0, 0.0))
        return (self.prompt_tokens * pin + self.completion_tokens * pout) / 1e6


def _post(url: str, body: dict, timeout: float) -> tuple[dict, int]:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    t = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read()), int((time.monotonic() - t) * 1000)


class Ollama:
    """Modelo local servido con Ollama. Se usa la API nativa /api/chat y no la compatible
    con OpenAI porque solo la nativa deja fijar `num_ctx`: el valor por defecto de Ollama
    es corto y recorta el prompt (esqueleto + lemas) sin avisar."""

    def __init__(self, url: str | None = None, model: str = OLLAMA_MODEL, num_ctx: int = 8192):
        # 8K: con 16K qwen3:4b ocupa 5,4 GB y queda 56 % en CPU en la GPU de 4 GB.
        self.url = (url or os.environ.get("OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        self.url += "/api/chat"
        self.model = model
        self.num_ctx = num_ctx

    def complete(self, system: str, user: str, max_tokens: int = 4096) -> Reply:
        msgs = [{"role": "system", "content": system}] if system else []
        data, ms = _post(self.url, {
            "model": self.model, "stream": False,
            # Sin modo razonamiento: con el prompt del planificador qwen3:4b (variante que
            # siempre razona) gasto los 8.192 tokens pensando (~29 min) sin responder.
            "think": False,
            # Los cuatro prompts que usan este backend piden JSON. Forzarlo evita que el
            # modelo razone en el texto hasta agotar num_predict sin llegar al JSON.
            "format": "json",
            "messages": msgs + [{"role": "user", "content": user}],
            "options": {"num_ctx": self.num_ctx, "num_predict": max_tokens},
        }, timeout=1800)  # ponytail: GPU de 4 GB con parte en CPU, una llamada larga tarda minutos
        return Reply(data["message"]["content"], self.model, data.get("prompt_eval_count", 0),
                     data.get("eval_count", 0), ms)


class Prover:
    """Goedel-Prover-V2 en /v1/chat/completions (vLLM o Ollama), para que el servidor
    aplique la plantilla de chat del modelo. Con Ollama: PROVER_URL=http://localhost:11434
    y PROVER_MODEL con el nombre local del modelo."""

    def __init__(self, url: str | None = None, model: str = PROVER_MODEL,
                 temperature: float = 0.6, max_tokens: int = 32768):
        # 32K de salida es el modo estandar del paper (plan + prueba). Con menos se corta el
        # razonamiento antes del bloque lean4. vLLM: --max-model-len 40960.
        self.url = (url or os.environ["PROVER_URL"]).rstrip("/") + "/v1/chat/completions"
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def complete(self, system: str, user: str, max_tokens: int | None = None) -> Reply:
        # El prover se entreno con un solo turno de usuario: system y user van juntos.
        prompt = f"{system}\n\n{user}".strip() if system else user
        data, ms = _post(self.url, {
            "model": self.model, "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature, "max_tokens": max_tokens or self.max_tokens,
        }, timeout=600)
        u = data.get("usage", {})
        return Reply(data["choices"][0]["message"]["content"], self.model, u.get("prompt_tokens", 0),
                     u.get("completion_tokens", 0), ms)


def backend_for(meta: dict, backends: dict):
    """El frontmatter del prompt dice que modelo lo corre."""
    return backends["prover"] if "Prover" in meta.get("model", "") else backends["llm"]


# --- la unica puerta de salida hacia un LLM ---------------------------------------

def call(ctx, agent: str, prompt_name: str, **vals: str) -> Reply:
    """Gasta presupuesto, llama, loguea. Devuelve el texto crudo; parsear es del agente."""
    p = load_prompt(prompt_name)
    backend = backend_for(p.meta, ctx.backends)
    ctx.budget.spend(agent)  # antes de llamar: si no cabe, no se paga
    system, user = p.render(**vals)
    try:
        reply = backend.complete(system, user)
    except Exception as e:
        # Se gasto presupuesto, entonces tambien queda en el log: si no, el resumen y el
        # conteo por problema del RNF-3 no cuadran.
        ctx.log.write(problem_id=ctx.problem_id, agent=agent, attempt=ctx.attempt,
                      prompt=prompt_name, error=f"{type(e).__name__}: {e}"[:500], cost_usd=0)
        raise
    ctx.log.write(
        problem_id=ctx.problem_id, agent=agent, attempt=ctx.attempt, model=reply.model,
        prompt=prompt_name, prompt_tokens=reply.prompt_tokens,
        completion_tokens=reply.completion_tokens, latency_ms=reply.latency_ms,
        cost_usd=round(reply.cost_usd, 6),
    )
    ctx.transcript.append({"agent": agent, "user": user, "response": reply.text})
    return reply
