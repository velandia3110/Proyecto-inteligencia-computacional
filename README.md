# Sistema multiagente de resolución matemática verificada por Lean 4

Resuelve problemas de olimpiada separando dos regímenes: **generación flexible** (LLM, cadenas
de razonamiento, RAG sobre Mathlib) y **verificación rígida** (kernel de Lean 4). Un problema
cuenta como resuelto **solo** si el kernel acepta la prueba: sin `sorry` y sin axiomas fuera del
núcleo.

Estado: **semanas 1–8**, el grafo completo corre de punta a punta contra el kernel real (con LLM falso), falta correrlo con los modelos de verdad. Todo corre en local, sin costo por llamada: Planificador, Generador y Crítico usan Qwen3-4B con Ollama. Ver `docs/status.md`.

## Documentación

| Documento | Qué contiene |
|---|---|
| `docs/Informe_Avance_Proyecto_IA.docx` | Informe de avance, semanas 1–8 (español; también en `.doc`). |
| `docs/Informe_Avance_Proyecto_IA_EN.docx` / `.pdf` | El mismo informe en inglés. |
| `docs/decisions.md` | Decisiones congeladas. Se lee primero. |
| `docs/design-document.md` | Entregable de las semanas 1–2: agentes, grafo de estados, veredictos, formalización del retriever. |
| `docs/related-work.md` | 27 referencias primarias por eje temático → sección *Related Work*. |
| `docs/contracts/` | Seis JSON Schema, uno por agente (RNF-4). |
| `docs/status.md` | Qué está hecho, qué falta, compuertas por semana. |
| `prompts/` | Prompts versionados como archivos. Nunca inline en el código (D5.2). |

## Cómo se ejecuta

### Requisitos

- Python ≥ 3.11
- Docker (el entorno de Lean 4.15 + Mathlib vive en una imagen; ~8 GB de RAM para Docker)
- [Ollama](https://ollama.com) para los modelos de lenguaje locales
- Opcional: una GPU para el índice del Recuperador y para servir el prover

### 1. Instalar dependencias de Python

```bash
pip install -e .            # núcleo: jsonschema, langgraph, numpy
pip install -e ".[rag]"     # opcional: FAISS y sentence-transformers para el Recuperador
```

### 2. Pruebas rápidas (sin Lean, sin modelos)

Usan respuestas del REPL y de los modelos fabricadas, así que corren en cualquier máquina:

```bash
python tests/test_verify.py      # los 7 veredictos del Verificador
python tests/test_pipeline.py    # prompts, contratos, líneas base, Planificador, Generador
python tests/test_graph.py       # el grafo completo, reintentos y presupuesto
```

### 3. Entorno de Lean (Docker)

```bash
# ~15-25 min la primera vez: descarga el cache de Mathlib
docker build -t mathagents-lean:v4.15.0 lean/

# compuerta de la semana 1: debe imprimir "veredicto=OK ... PASA"
docker run --rm -v "$PWD:/work" -w /work mathagents-lean:v4.15.0 python3 -m src.verify --smoke

# veredictos contra el kernel real y un problema de miniF2F de punta a punta
docker run --rm -v "$PWD:/work" -w /work mathagents-lean:v4.15.0 python3 tests/test_kernel.py
docker run --rm -v "$PWD:/work" -w /work mathagents-lean:v4.15.0 python3 tests/test_kernel_pool.py
```

### 4. Modelos locales

```bash
ollama pull qwen3:4b-instruct    # Planificador, Generador y Crítico (costo 0 por token)
```

Se usa la variante *instruct* a propósito: la variante que razona (`qwen3:4b`) gastó todos sus tokens
pensando sin responder en una GPU de 4 GB (ver `docs/decisions.md`, historial 2026-09-28).

El prover (Goedel-Prover-V2-8B) no cabe entero en una GPU de 4 GB. Dos opciones:

- servirlo afuera con vLLM: `vllm serve Goedel-LM/Goedel-Prover-V2-8B` y `PROVER_URL=http://<host>:8000`;
- servirlo en Ollama cuantizado, entre GPU y CPU: `PROVER_URL=http://localhost:11434` y
  `PROVER_MODEL=<nombre local>`. Sirve para probar la tubería, pero es lento para la corrida completa.

### 5. Datos y Recuperador

```bash
python -m src.data                          # baja miniF2F y lo comprueba con su sha256
docker run --rm -v "$PWD:/work" -w /work mathagents-lean:v4.15.0 \
  python3 -m src.data --check valid         # los 244 enunciados de dev compilan
python -m src.retriever build               # índice FAISS sobre el corpus (~34 min en GPU)
python -m src.retriever recall 5 10 20 50   # curva recall@k
```

### 6. Una corrida

Se corre dentro de la imagen (necesita el REPL de Lean) y habla con Ollama en el host:

```bash
docker run --rm -v "$PWD:/work" -w /work \
  --add-host=host.docker.internal:host-gateway \
  -e OLLAMA_URL=http://host.docker.internal:11434 -e PROVER_URL \
  mathagents-lean:v4.15.0 python3 run.py --config plan_only --limit 10

python -m src.runlog runs/<run_id>.jsonl    # resumen: veredictos, llamadas, costo
```

| `--config` | Qué corre | Necesita |
|---|---|---|
| `baseline_a` | Línea base A: el prover, una llamada, prueba completa | `PROVER_URL` |
| `baseline_b` | Línea base B: razonamiento en lenguaje natural + autoevaluación | Ollama y `PROVER_URL` |
| `plan_only` | Solo el Planificador + `VERIFY_SKELETON` (tasa de esqueletos) | Ollama |
| `agents_only` | Multiagente sin Recuperador y sin Crítico | Ollama y `PROVER_URL` |

Otras opciones de `run.py`: `--problems id1,id2`, `--limit N`, `--seed`, `--workers N` (REPLs en
paralelo, no pasar de 3 con 8 GB). El conjunto de prueba (`--split test`) está sellado y solo se abre
con `--abrir-test`, una vez, en la semana 11.

### Variables de entorno

| Variable | Por defecto | Para qué |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Servidor de Ollama |
| `OLLAMA_MODEL` | `qwen3:4b-instruct` | Modelo de Planificador, Generador y Crítico |
| `PROVER_URL` | — (obligatoria si la config usa el prover) | Endpoint tipo OpenAI del prover (vLLM u Ollama) |
| `PROVER_MODEL` | `Goedel-LM/Goedel-Prover-V2-8B` | Nombre del modelo en ese endpoint |
| `LEAN_REPL_BIN` | `/app/repl/.lake/build/bin/repl` | Binario del REPL (ya configurado en la imagen) |
| `LEAN_PROJECT_DIR` | `/app/mathproj` | Proyecto de Lean con Mathlib (ya configurado en la imagen) |

## Por qué siete veredictos y no "compila / no compila"

`SORRY` y `AXIOM` existen para que el sistema no pueda autoengañarse:

- una prueba con `sorry` compila y no prueba nada;
- `axiom cheat : False` compila y prueba cualquier cosa.

Sin esos dos veredictos la métrica principal del proyecto es falsificable. Ver
`docs/design-document.md` §5.

## Licencia

MIT (código). Los benchmarks conservan la suya: miniF2F y PutnamBench, documentadas en la
dataset card de la semana 10.
