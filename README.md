# Sistema multiagente de resolución matemática verificada por Lean 4

Resuelve problemas de olimpiada separando dos regímenes: **generación flexible** (LLM, cadenas
de razonamiento, RAG sobre Mathlib) y **verificación rígida** (kernel de Lean 4). Un problema
cuenta como resuelto **solo** si el kernel acepta la prueba: sin `sorry` y sin axiomas fuera del
núcleo.

Estado: **semanas 1–4**, diseño, entorno Lean funcionando, líneas base y runner. Ver `docs/status.md`.

## Documentación

| Documento | Qué contiene |
|---|---|
| `docs/decisions.md` | Decisiones congeladas. Se lee primero. |
| `docs/design-document.md` | Entregable de las semanas 1–2: agentes, grafo de estados, veredictos, formalización del retriever. |
| `docs/related-work.md` | 27 referencias primarias por eje temático → sección *Related Work*. |
| `docs/contracts/` | Seis JSON Schema, uno por agente (RNF-4). |
| `docs/status.md` | Qué está hecho, qué falta, compuertas por semana. |
| `prompts/` | Prompts versionados como archivos. Nunca inline en el código (D5.2). |

## Arranque

```bash
# 1. Verificador en Python (no necesita Lean: usa respuestas del REPL fabricadas)
python tests/test_verify.py

# 2. Entorno Lean (~15-25 min la primera vez, descarga el cache de Mathlib)
docker build -t mathagents-lean:v4.15.0 lean/

# 3. Compuerta del dia 5 de la semana 1
docker run --rm -v "$PWD/src:/app/src" mathagents-lean:v4.15.0 \
  python3 -m src.verify --smoke

# 4. Veredictos contra el kernel real y una prueba de punta a punta
docker run --rm -v "$PWD:/work" -w /work mathagents-lean:v4.15.0 python3 tests/test_kernel.py

# 5. Una corrida (necesita ANTHROPIC_API_KEY y/o PROVER_URL segun la config)
docker run --rm -v "$PWD:/work" -w /work -e ANTHROPIC_API_KEY -e PROVER_URL \
  mathagents-lean:v4.15.0 python3 run.py --config baseline_a --limit 10
python -m src.runlog runs/<run_id>.jsonl
```

El paso 3 debe imprimir `veredicto=OK ... PASA` (ya pasa, desde la semana 3). Las pruebas que no
necesitan Docker ni API son `python tests/test_verify.py && python tests/test_pipeline.py`.

El prover (Goedel-Prover-V2-8B) no corre en una GPU chica, se sirve afuera con vLLM y se le pasa
la URL: `vllm serve Goedel-LM/Goedel-Prover-V2-8B` y `PROVER_URL=http://<host>:8000`.

## Por qué siete veredictos y no "compila / no compila"

`SORRY` y `AXIOM` existen para que el sistema no pueda autoengañarse:

- una prueba con `sorry` compila y no prueba nada;
- `axiom cheat : False` compila y prueba cualquier cosa.

Sin esos dos veredictos la métrica principal del proyecto es falsificable. Ver
`docs/design-document.md` §5.

## Licencia

MIT (código). Los benchmarks conservan la suya: miniF2F y PutnamBench, documentadas en la
dataset card de la semana 10.
