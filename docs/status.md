# Estado del proyecto

Actualizado: 2026-09-27 · Semanas 1–4 cerradas en lo que depende de nosotros, la corrida real de las líneas base espera la clave del API y el prover.

## Semanas 1–2

| Condición | Estado | Evidencia |
|---|---|---|
| Documento de diseño completo | ✅ | `docs/design-document.md` |
| ≥15 referencias primarias por eje | ✅ 27 | `docs/related-work.md` |
| Seis JSON Schema validan | ✅ 6/6 draft 2020-12 | `docs/contracts/` |
| `verify()` distingue los veredictos | ✅ 13/13 fabricados, 8/8 contra el kernel real | `tests/test_verify.py`, `tests/test_kernel.py` |
| Prompts v0 versionados como archivos | ✅ | `prompts/*.v0.md` |
| **Compuerta D4: `2 + 2 = 4` desde Python** | ✅ | `python3 -m src.verify --smoke` → `veredicto=OK axiomas=['propext']` |

La compuerta D4 se cerró tarde, en la semana 3, y no salió a la primera, salieron dos errores que con respuestas fabricadas nunca se hubieran visto. El primero fue que el REPL corría sin `lake env` y no encontraba ni el prelude de Lean, lo raro es que el `import Mathlib` no se quejaba, simplemente no cargaba nada, y todo lo demás fallaba con "unknown constant 'OfNat'". El segundo fue que el REPL no entiende los caracteres Unicode escapados como pares sustitutos en el JSON, entonces cualquier enunciado con `𝓝` daba error de sintaxis. Ahí también se vio que la sintaxis de Lean 3 (`begin ... end`) sale como "unknown identifier 'begin'" y el clasificador la tomaba como lema faltante, lo cual habría mandado al sistema a buscar más lemas cuando el problema era de sintaxis, eso ya quedó corregido y con su caso de prueba.

## Semanas 3–4: líneas base, runner e ingesta

Compuerta: ambas líneas base corren sobre dev de punta a punta, JSONL válido y costo por problema en dólares.

| Condición | Estado | Evidencia |
|---|---|---|
| Ingesta de miniF2F | ✅ 244 dev / 244 test | `python -m src.data`, fuente fijada por sha256 |
| Los 244 enunciados de dev compilan con nuestra Mathlib | ✅ 244/244 | `python3 -m src.data --check valid` (en Docker) |
| Línea base A (prover, una llamada) | ✅ código · ⏳ corrida | `src/baselines.py`, prueba de punta a punta con el kernel real en `tests/test_kernel.py` |
| Línea base B (CoT + autoevaluación, luego se formaliza) | ✅ código · ⏳ corrida | `src/baselines.py`, `tests/test_pipeline.py` |
| Runner con JSONL y encabezado reproducible | ✅ | `run.py`, `src/runlog.py` |
| Costo por problema en dólares | ✅ se calcula del JSONL | `python -m src.runlog runs/<id>.jsonl` |
| Test set sellado | ✅ | el runner no abre `--split test` sin `--abrir-test` |
| PutnamBench | ❌ no se hizo | ver deuda |

Lo que se hizo en estas dos semanas fue dejar toda la tubería por la que pasa cualquier configuración, el runner carga el problema, arma un contexto con su propio presupuesto, corre la configuración y escribe una línea por cada llamada al LLM y una línea de resultado por problema, y las métricas salen de agregar ese archivo y no de contar a mano. El encabezado del log guarda el commit de Mathlib y del repositorio que se leen de verdad, no escritos a mano.

Hay un chequeo que no estaba en el diseño y que resultó importante, antes de mandar una prueba al kernel se revisa que el enunciado del teorema siga igual al original. Sin eso un modelo puede probar un teorema más fácil que compila limpio y contaría como resuelto, esos casos quedan con veredicto `STATEMENT_CHANGED` y ni siquiera se le preguntan al kernel.

La línea base B guarda lo que el modelo dijo de su propia prueba (`self_verdict`) y después la formaliza con una llamada al prover, así se puede contar cuántas veces el modelo dijo "correcta" y el kernel dijo que no, que es el dato de falsos positivos evitados que va en el abstract.

**Lo que falta para cerrar la compuerta de verdad** es correr las dos líneas base sobre dev, y eso necesita dos cosas que esta máquina no tiene: una clave del API de Anthropic y el prover servido en algún lado. Goedel-Prover-V2-8B no cabe en la GPU de acá (4 GB), la idea es levantarlo con vLLM en Colab o en un endpoint de HF y pasar `PROVER_URL`. Con eso:

```bash
docker run --rm -v "$PWD:/work" -w /work -e ANTHROPIC_API_KEY -e PROVER_URL \
  mathagents-lean:v4.15.0 python3 run.py --config baseline_a
```

## Reparto y compuertas siguientes

| Semana | Entregable | Compuerta |
|---|---|---|
| 5–6 | Planificador con esqueleto + Generador, corpus y FAISS | esqueletos compilan en >70% de dev; curva recall@k para k ∈ {5,10,20} |
| 7–8 | Autoformalizador, `ASSEMBLE`, pool de REPLs, CI | un problema entra y sale veredicto del kernel, sin RAG ni Crítico |
| 9 | RAG + Crítico | las 5 configuraciones son invocables por bandera |
| 10 | Test set 40–60, dataset card | prompts CONGELADOS |
| 11 | Experimentos | el test set se abre **una sola vez** |
| 12 | Análisis y empaquetado | Wilson, McNemar, bootstrap; repo HF |
| 13 | Informe IMRaD + sustentación | ~8.000 palabras |

**Punto de corte:** si el pipeline end-to-end no corre al final de la semana 8, el RAG se recorta a extensión declarada y la ablación corre con 4 configuraciones.

## Deuda declarada

- Las líneas base no se han corrido sobre dev, falta clave del API y el prover servido (ver arriba). Es lo primero que hay que hacer cuando estén.
- PutnamBench no se ingirió. Es el benchmark secundario y sus enunciados traen definiciones de solución (`abbrev ..._solution`) que hay que manejar aparte, se deja para la semana 10 cuando se arme el test set.
- `docs/references.bib` no existe. Las 27 entradas de `related-work.md` están escritas de memoria, hay que auditar venue, año y DOI contra la fuente antes de citarlas.
- Referencia del informe del MIT sin identificar (`related-work.md` eje 7).
- `decisions.md` D2 afirma que Goedel-Prover-V2 permite desactivar la autocorrección interna, verificarlo antes de la semana 7.
- El caso `TIMEOUT` no se ha probado contra el kernel real, solo con respuesta fabricada.
