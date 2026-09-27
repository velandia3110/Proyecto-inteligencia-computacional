"""Prompts como archivos (D5.2) y los dos backends de LLM.

- Claude (planificacion, generacion, critica): SDK oficial de Anthropic.
- Prover (formalizacion): Goedel-Prover-V2 servido con vLLM en un endpoint
  compatible con OpenAI. Se habla con el por HTTP plano (stdlib): con una GPU de
  4 GB no corre local, se levanta afuera y se pasa PROVER_URL.

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

# USD por millon de tokens (entrada, salida). El prover es self-hosted: costo
# marginal 0 por token; su costo real es la hora de GPU y se reporta aparte.
PRICES = {"claude-opus-5": (5.0, 25.0)}


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


class Claude:
    # claude-opus-5 no acepta `temperature` (400). La temperatura del frontmatter de
    # los prompts v0 queda como dato historico; ver decisions.md historial 2026-09-27.
    def __init__(self, model: str = "claude-opus-5", effort: str = "high"):
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model
        self.effort = effort

    def complete(self, system: str, user: str, max_tokens: int = 16000) -> Reply:
        t = time.monotonic()
        r = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            messages=[{"role": "user", "content": user}],
        )
        if r.stop_reason == "refusal":
            raise RuntimeError(f"el modelo rechazo la peticion: {r.stop_details}")
        text = "".join(b.text for b in r.content if b.type == "text")
        return Reply(text, self.model, r.usage.input_tokens, r.usage.output_tokens,
                     int((time.monotonic() - t) * 1000))


class Prover:
    """Goedel-Prover-V2 detras de `vllm serve` (endpoint /v1/chat/completions,
    para que vLLM aplique la plantilla de chat del modelo)."""

    def __init__(self, url: str | None = None, model: str = "Goedel-LM/Goedel-Prover-V2-8B",
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
        body = json.dumps({
            "model": self.model, "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature, "max_tokens": max_tokens or self.max_tokens,
        }).encode()
        req = urllib.request.Request(self.url, body, {"Content-Type": "application/json"})
        t = time.monotonic()
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read())
        u = data.get("usage", {})
        return Reply(data["choices"][0]["message"]["content"], self.model, u.get("prompt_tokens", 0),
                     u.get("completion_tokens", 0), int((time.monotonic() - t) * 1000))


def backend_for(meta: dict, backends: dict):
    """El frontmatter del prompt dice que modelo lo corre."""
    return backends["prover"] if "Prover" in meta.get("model", "") else backends["claude"]


# --- la unica puerta de salida hacia un LLM ---------------------------------------

def call(ctx, agent: str, prompt_name: str, **vals: str) -> Reply:
    """Gasta presupuesto, llama, loguea. Devuelve el texto crudo; parsear es del agente."""
    p = load_prompt(prompt_name)
    backend = backend_for(p.meta, ctx.backends)
    ctx.budget.spend(agent)  # antes de llamar: si no cabe, no se paga
    system, user = p.render(**vals)
    reply = backend.complete(system, user)
    ctx.log.write(
        problem_id=ctx.problem_id, agent=agent, attempt=ctx.attempt, model=reply.model,
        prompt=prompt_name, prompt_tokens=reply.prompt_tokens,
        completion_tokens=reply.completion_tokens, latency_ms=reply.latency_ms,
        cost_usd=round(reply.cost_usd, 6),
    )
    ctx.transcript.append({"agent": agent, "user": user, "response": reply.text})
    return reply
